import copy
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from services.card_revision import assert_revision, bump_revision, card_revision
from services.collaboration_settings import merge_settings_collaboration, normalize_collaboration
from services.org_keys import PERSONAL_BOARD_ORG_NAME, PERSONAL_ORG_ID
from services.storage import DEFAULT_DATA, DEFAULT_EDITABLE_FONTS, EDITABLE_FONT_SCOPE_IDS
from services.tenant_keys import (
    SUPER_ADMIN_ID,
    SUPER_ADMIN_TENANT_TYPE,
    USER_TENANT_TYPE,
    build_tenant_context,
)

SUPER_ADMIN_ORG_CREATOR = {
    "created_by_type": SUPER_ADMIN_TENANT_TYPE,
    "created_by_id": SUPER_ADMIN_ID,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _plain_text(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


class BoardService:
    def __init__(self, storage, auth_service=None, share_service=None) -> None:
        self.storage = storage
        self.auth_service = auth_service
        self.share_service = share_service
        self._lock = threading.RLock()
        self._board_access: dict[str, Any] | None = None

    def set_board_access(self, access: dict[str, Any] | None) -> None:
        self._board_access = access

    def clear_board_access(self) -> None:
        self._board_access = None

    def _tenant_ctx(self) -> dict[str, Any]:
        if self._board_access:
            return self._board_access["tenant_ctx"]
        if not self.auth_service:
            return {"type": "super_admin", "id": "super_admin", "scope_mode": "org_multi"}
        return self.auth_service.get_current_tenant()

    def _read(self) -> dict[str, Any]:
        settings = self.storage.read_settings()
        tenant_data = self.storage.read_tenant(self._tenant_ctx(), settings)
        return copy.deepcopy({**tenant_data, "settings": settings})

    def _write(self, data: dict[str, Any], *, write_settings: bool = False) -> None:
        settings = data.get("settings") or self.storage.read_settings()
        tenant_payload = {
            "boards": data.get("boards", []),
            "lists": data.get("lists", []),
            "cards": data.get("cards", []),
            "meta": data.get("meta", {}),
        }
        self.storage.write_tenant(self._tenant_ctx(), tenant_payload, settings)
        if write_settings and self.auth_service:
            user = self.auth_service.get_current_user() or {}
            if user.get("is_super_admin"):
                self.storage.write_settings(settings)

    def _next_id(self, data: dict[str, Any], key: str) -> str:
        meta = data.setdefault("meta", {})
        current = int(meta.get(key, 1))
        meta[key] = current + 1
        return str(current)

    def _collaboration_config(self) -> dict[str, Any]:
        settings = self.storage.read_settings()
        return merge_settings_collaboration(settings)

    def _tenant_lock_identity(self) -> tuple[str, str]:
        ctx = self._tenant_ctx()
        return str(ctx.get("type") or ""), str(ctx.get("id") or "")

    def get_settings(self) -> dict[str, Any]:
        with self._lock:
            settings = copy.deepcopy(self.storage.read_settings())
            settings.setdefault("card_types", DEFAULT_DATA["settings"]["card_types"])
            settings.setdefault("board_statuses", DEFAULT_DATA["settings"]["board_statuses"])
            settings.setdefault("editable_fonts", DEFAULT_EDITABLE_FONTS)
            settings.setdefault("shared_boards", [])
            settings.setdefault("shared_org_index", [])
            settings["collaboration"] = merge_settings_collaboration(settings)

            user = self.auth_service.get_current_user() if self.auth_service else None
            if user and not user.get("is_super_admin"):
                user_id = str(user.get("id") or "")
                self._migrate_user_organizations(user_id)
                self._maybe_seed_user_organizations(user_id)
                if self.share_service:
                    self.share_service.sync_grantee_share_index(user_id)
                settings["organizations"] = self._read_user_organizations(user_id)
                settings["shared_boards"] = self.storage.list_user_shared_boards(user_id)
                settings["shared_org_index"] = self.storage.list_user_shared_org_index(user_id)
            elif user and user.get("is_super_admin"):
                settings["organizations"] = self._read_admin_organizations()
            else:
                settings["organizations"] = self._read_admin_organizations()
            return settings

    def _read_admin_organizations(self) -> list[dict[str, Any]]:
        settings = self.storage.read_settings()
        organizations = copy.deepcopy(settings.get("organizations") or DEFAULT_DATA["settings"]["organizations"])
        changed = False
        now = _now_iso()
        cleaned: list[dict[str, Any]] = []
        for org in organizations:
            if org.get("created_by_type") == USER_TENANT_TYPE:
                changed = True
                continue
            if not org.get("created_by_type") or not org.get("created_by_id"):
                org.update(SUPER_ADMIN_ORG_CREATOR)
                org.setdefault("created_at", now)
                org["updated_at"] = now
                changed = True
            cleaned.append(org)
        if changed:
            settings["organizations"] = cleaned
            self.storage.write_settings(settings)
        return cleaned

    def _write_admin_organizations(self, organizations: list[dict[str, Any]]) -> None:
        settings = self.storage.read_settings()
        settings["organizations"] = organizations
        self.storage.write_settings(settings)

    def _read_user_organizations(self, user_id: str) -> list[dict[str, Any]]:
        return self.storage.list_user_organizations(user_id)

    def _write_user_organizations(self, user_id: str, organizations: list[dict[str, Any]]) -> None:
        self.storage.write_user_organizations(user_id, organizations)

    def _migrate_user_organizations(self, user_id: str) -> None:
        existing = self.storage.list_user_organizations(user_id)
        if existing:
            self._purge_user_orgs_from_global_settings(user_id)
            self.storage.delete_legacy_user_index_keys(user_id)
            return

        merged: dict[str, dict[str, Any]] = {}
        now = _now_iso()

        for item in self.storage.list_legacy_user_org_entries(user_id):
            name = (item.get("name") or "").strip()
            if not name:
                continue
            org_id = str(item.get("id") or item.get("org_id") or f"org_{uuid.uuid4().hex[:8]}")
            while org_id in merged:
                org_id = f"org_{uuid.uuid4().hex[:8]}"
            merged[org_id] = {
                "id": org_id,
                "name": name,
                "note": (item.get("note") or "").strip(),
                "created_at": item.get("created_at") or now,
                "updated_at": now,
            }

        settings = self.storage.read_settings()
        global_orgs = settings.get("organizations") or []
        admin_names = {
            (org.get("name") or "").strip()
            for org in global_orgs
            if (org.get("created_by_type") or SUPER_ADMIN_TENANT_TYPE) == SUPER_ADMIN_TENANT_TYPE
        }
        for org in global_orgs:
            if org.get("created_by_type") != USER_TENANT_TYPE:
                continue
            if str(org.get("created_by_id") or "") != str(user_id):
                continue
            name = (org.get("name") or "").strip()
            if not name or name in admin_names:
                continue
            org_id = str(org.get("id") or f"org_{uuid.uuid4().hex[:8]}")
            if org_id in merged:
                continue
            merged[org_id] = {
                "id": org_id,
                "name": name,
                "note": (org.get("note") or "").strip(),
                "created_at": org.get("created_at") or now,
                "updated_at": org.get("updated_at") or now,
            }

        if merged:
            self._write_user_organizations(user_id, list(merged.values()))

        self._purge_user_orgs_from_global_settings(user_id)
        self.storage.delete_legacy_user_index_keys(user_id)

    def _purge_user_orgs_from_global_settings(self, user_id: str | None = None) -> None:
        settings = self.storage.read_settings()
        organizations = settings.get("organizations") or []
        if user_id:
            filtered = [
                org
                for org in organizations
                if not (
                    org.get("created_by_type") == USER_TENANT_TYPE
                    and str(org.get("created_by_id") or "") == str(user_id)
                )
            ]
        else:
            filtered = [org for org in organizations if org.get("created_by_type") != USER_TENANT_TYPE]
        if len(filtered) != len(organizations):
            settings["organizations"] = filtered
            self.storage.write_settings(settings)

    def _maybe_seed_user_organizations(self, user_id: str) -> None:
        if self._read_user_organizations(user_id):
            return

        tenant_ctx = build_tenant_context({"id": user_id, "is_super_admin": False})
        data = self.storage.read_tenant(tenant_ctx, self.storage.read_settings())
        orgs = list(self._read_user_organizations(user_id))
        for board in data.get("boards", []):
            name = (board.get("organization") or "").strip()
            if name and name != PERSONAL_BOARD_ORG_NAME:
                org = self._ensure_user_organization(user_id, name, orgs)
                if org and not any(str(item.get("id")) == str(org.get("id")) for item in orgs):
                    orgs.append(org)

    def _ensure_user_organization(
        self,
        user_id: str,
        org_name: str,
        user_orgs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        normalized = (org_name or "").strip()
        if not normalized or normalized == PERSONAL_BOARD_ORG_NAME:
            return None

        user_orgs = user_orgs if user_orgs is not None else self._read_user_organizations(user_id)
        existing = next(
            (org for org in user_orgs if (org.get("name") or "").strip() == normalized),
            None,
        )
        now = _now_iso()
        if not existing:
            existing = {
                "id": f"org_{uuid.uuid4().hex[:8]}",
                "name": normalized,
                "note": "",
                "created_at": now,
                "updated_at": now,
            }
            user_orgs = [*user_orgs, existing]
            self._write_user_organizations(user_id, user_orgs)

        return existing

    def _organizations_for_current_tenant(self) -> list[dict[str, Any]]:
        user = self.auth_service.get_current_user() if self.auth_service else None
        if user and not user.get("is_super_admin"):
            return copy.deepcopy(self._read_user_organizations(str(user.get("id") or "")))
        return copy.deepcopy(self._read_admin_organizations())

    def _write_organizations_for_current_tenant(self, organizations: list[dict[str, Any]]) -> None:
        user = self.auth_service.get_current_user() if self.auth_service else None
        if user and not user.get("is_super_admin"):
            self._write_user_organizations(str(user.get("id") or ""), organizations)
            return
        self._write_admin_organizations(organizations)

    def _import_merge_organization(self, org_meta: dict[str, Any]) -> dict[str, Any]:
        name = (org_meta.get("name") or "").strip()
        org_id = str(org_meta.get("id") or "").strip()
        note = (org_meta.get("note") or "").strip()
        if not name or name == PERSONAL_BOARD_ORG_NAME:
            return {"id": PERSONAL_ORG_ID, "name": PERSONAL_BOARD_ORG_NAME, "note": ""}

        orgs = self._organizations_for_current_tenant()
        now = _now_iso()

        if org_id:
            existing = next((org for org in orgs if str(org.get("id")) == org_id), None)
            if existing:
                changed = False
                if note and note != (existing.get("note") or "").strip():
                    existing["note"] = note
                    changed = True
                if name != (existing.get("name") or "").strip():
                    existing["name"] = name
                    changed = True
                if changed:
                    existing["updated_at"] = now
                    self._write_organizations_for_current_tenant(orgs)
                return existing

        existing = next((org for org in orgs if (org.get("name") or "").strip() == name), None)
        if existing:
            if note and note != (existing.get("note") or "").strip():
                existing["note"] = note
                existing["updated_at"] = now
                self._write_organizations_for_current_tenant(orgs)
            return existing

        user = self.auth_service.get_current_user() if self.auth_service else None
        new_id = org_id if org_id and not any(str(org.get("id")) == org_id for org in orgs) else f"org_{uuid.uuid4().hex[:8]}"
        new_org: dict[str, Any] = {
            "id": new_id,
            "name": name,
            "note": note,
            "created_at": now,
            "updated_at": now,
        }
        if not user or user.get("is_super_admin"):
            new_org.update(SUPER_ADMIN_ORG_CREATOR)
        orgs.append(new_org)
        self._write_organizations_for_current_tenant(orgs)
        return new_org

    def _ensure_super_admin_organization(
        self,
        org_name: str,
        admin_orgs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        normalized = (org_name or "").strip()
        if not normalized or normalized == PERSONAL_BOARD_ORG_NAME:
            return None

        admin_orgs = admin_orgs if admin_orgs is not None else self._read_admin_organizations()
        existing = next(
            (org for org in admin_orgs if (org.get("name") or "").strip() == normalized),
            None,
        )
        now = _now_iso()
        if not existing:
            existing = {
                "id": f"org_{uuid.uuid4().hex[:8]}",
                "name": normalized,
                "note": "",
                **SUPER_ADMIN_ORG_CREATOR,
                "created_at": now,
                "updated_at": now,
            }
            admin_orgs = [*admin_orgs, existing]
            self._write_admin_organizations(admin_orgs)

        return existing

    def _ensure_organization_for_board(self, org_name: str) -> None:
        user = self.auth_service.get_current_user() if self.auth_service else None
        if user and user.get("is_super_admin"):
            self._ensure_super_admin_organization(org_name)
            return
        user_id = self._current_user_id()
        if user_id:
            self._ensure_user_organization(user_id, org_name)

    def _current_user_id(self) -> str | None:
        if not self.auth_service:
            return None
        user = self.auth_service.get_current_user() or {}
        if user.get("is_super_admin"):
            return None
        return str(user.get("id") or "") or None

    def _validate_font_profile(self, font: dict[str, Any]) -> dict[str, str]:
        allowed_families = {
            "microsoft-yahei",
            "simsun",
            "simhei",
            "kaiti",
            "stkaiti",
            "stxingkai",
            "simli",
            "youyuan",
            "pingfang-sc",
            "noto-sans-sc",
            "arial",
            "system-ui",
        }
        allowed_styles = {"normal", "italic"}
        allowed_weights = {"400", "500", "600", "700", "normal", "bold"}

        family = (font.get("family") or "microsoft-yahei").strip()
        if family not in allowed_families:
            raise ValueError(f"不支持的字体：{family}")

        style = (font.get("style") or "normal").strip()
        if style not in allowed_styles:
            raise ValueError(f"无效的字体样式：{style}")

        weight = str(font.get("weight") or "400").strip()
        if weight not in allowed_weights:
            raise ValueError(f"无效的字重：{weight}")
        if weight == "normal":
            weight = "400"
        if weight == "bold":
            weight = "700"

        try:
            size = int(font.get("size") or 15)
        except (TypeError, ValueError) as error:
            raise ValueError("字号必须是数字") from error
        if size < 12 or size > 32:
            raise ValueError("字号需在 12–32 之间")

        color = (font.get("color") or "#e8eaed").strip()
        if not re.match(r"^#[0-9a-fA-F]{6}$", color):
            raise ValueError("字体颜色格式无效")

        return {
            "family": family,
            "style": style,
            "weight": weight,
            "size": str(size),
            "color": color.lower(),
        }

    def update_editable_fonts(self, fonts: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(fonts, dict):
            raise ValueError("字体设置格式无效")

        validated: dict[str, dict[str, str]] = {}
        for scope_id in EDITABLE_FONT_SCOPE_IDS:
            scope_font = fonts.get(scope_id)
            if not isinstance(scope_font, dict):
                scope_font = DEFAULT_EDITABLE_FONTS[scope_id]
            validated[scope_id] = self._validate_font_profile(scope_font)

        with self._lock:
            settings = self.get_settings()
            settings["editable_fonts"] = validated
            self.storage.write_settings(settings)
            return settings

    def update_collaboration(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            settings = self.get_settings()
            merged = normalize_collaboration({**settings.get("collaboration", {}), **(payload or {})})
            settings["collaboration"] = merged
            self.storage.write_settings(settings)
            return settings

    def update_organizations(self, organizations: list[dict[str, Any]]) -> dict[str, Any]:
        validated: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_names: set[str] = set()

        for item in organizations:
            name = (item.get("name") or "").strip()
            if not name:
                raise ValueError("组织名称不能为空")
            if name in seen_names:
                raise ValueError(f"组织名称重复：{name}")
            seen_names.add(name)

            org_id = (item.get("id") or "").strip() or f"org_{uuid.uuid4().hex[:8]}"
            while org_id in seen_ids:
                org_id = f"{org_id}_{len(seen_ids)}"
            seen_ids.add(org_id)

            note = (item.get("note") or "").strip()
            validated.append({"id": org_id, "name": name, "note": note})

        with self._lock:
            data = self._read()
            old_orgs = self._read_admin_organizations()
            old_by_id = {str(item.get("id")): item for item in old_orgs if item.get("id") is not None}
            now = _now_iso()
            validated = [
                {
                    **org,
                    **SUPER_ADMIN_ORG_CREATOR,
                    "created_at": (old_by_id.get(org["id"]) or {}).get("created_at") or now,
                    "updated_at": now,
                }
                for org in validated
            ]
            new_ids = {item["id"] for item in validated}

            for org in validated:
                old_org = old_by_id.get(org["id"])
                if not old_org:
                    continue
                old_name = (old_org.get("name") or "").strip()
                if old_name and old_name != org["name"]:
                    for board in data.get("boards", []):
                        if (board.get("organization") or "").strip() == old_name:
                            board["organization"] = org["name"]

            removed_names = {
                (item.get("name") or "").strip()
                for item in old_orgs
                if str(item.get("id")) not in new_ids
            }
            for board in data.get("boards", []):
                if (board.get("organization") or "").strip() in removed_names:
                    board["organization"] = ""

            settings = data.setdefault("settings", {})
            settings["organizations"] = validated
            data["settings"] = settings
            self._write(data)
            self._write_admin_organizations(validated)
            settings["organizations"] = validated
            return settings

    def update_my_organizations(self, organizations: list[dict[str, Any]]) -> dict[str, Any]:
        user_id = self._current_user_id()
        if not user_id:
            raise PermissionError("仅普通用户可维护个人项目组织")

        validated: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_names: set[str] = set()

        for item in organizations:
            name = (item.get("name") or "").strip()
            if not name:
                raise ValueError("组织名称不能为空")
            if name == PERSONAL_BOARD_ORG_NAME:
                raise ValueError("不能创建与内置个人看板同名的组织")
            if name in seen_names:
                raise ValueError(f"组织名称重复：{name}")
            seen_names.add(name)

            org_id = (item.get("id") or "").strip() or f"org_{uuid.uuid4().hex[:8]}"
            while org_id in seen_ids:
                org_id = f"{org_id}_{len(seen_ids)}"
            seen_ids.add(org_id)

            note = (item.get("note") or "").strip()
            validated.append({"id": org_id, "name": name, "note": note})

        with self._lock:
            tenant_ctx = build_tenant_context({"id": user_id, "is_super_admin": False})
            data = self.storage.read_tenant(tenant_ctx, self.storage.read_settings())
            old_orgs = self._read_user_organizations(user_id)
            old_by_id = {str(item.get("id")): item for item in old_orgs if item.get("id") is not None}
            now = _now_iso()
            validated = [
                {
                    **org,
                    "created_at": (old_by_id.get(org["id"]) or {}).get("created_at") or now,
                    "updated_at": now,
                }
                for org in validated
            ]
            new_ids = {item["id"] for item in validated}

            for org in validated:
                old_org = old_by_id.get(org["id"])
                if not old_org:
                    continue
                old_name = (old_org.get("name") or "").strip()
                if old_name and old_name != org["name"]:
                    for board in data.get("boards", []):
                        if (board.get("organization") or "").strip() == old_name:
                            board["organization"] = org["name"]

            removed_ids = {
                str(item.get("id"))
                for item in old_orgs
                if str(item.get("id")) not in new_ids
            }
            removed_names = {(item.get("name") or "").strip() for item in old_orgs if str(item.get("id")) in removed_ids}
            for board in data.get("boards", []):
                if (board.get("organization") or "").strip() in removed_names:
                    board["organization"] = ""

            self._write_user_organizations(user_id, validated)
            self.storage.write_tenant(tenant_ctx, data, self.storage.read_settings())

            return self.get_settings()

    def update_board_statuses(self, statuses: list[dict[str, Any]]) -> dict[str, Any]:
        if not statuses:
            raise ValueError("至少保留一个看板状态")

        validated: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_labels: set[str] = set()

        for item in statuses:
            label = (item.get("label") or "").strip()
            if not label:
                raise ValueError("状态名称不能为空")
            if label in seen_labels:
                raise ValueError(f"状态名称重复：{label}")
            seen_labels.add(label)

            status_id = (item.get("id") or "").strip() or f"status_{uuid.uuid4().hex[:8]}"
            while status_id in seen_ids:
                status_id = f"{status_id}_{len(seen_ids)}"
            seen_ids.add(status_id)

            icon = (item.get("icon") or "circle").strip()
            if icon not in {"circle", "dot", "check", "none"}:
                raise ValueError(f"无效图标类型：{icon}")

            color = (item.get("color") or "#9ca3af").strip()
            validated.append({"id": status_id, "label": label, "color": color, "icon": icon})

        with self._lock:
            data = self._read()
            settings = data.setdefault("settings", {})
            old_statuses = settings.get("board_statuses", DEFAULT_DATA["settings"]["board_statuses"])
            old_ids = {str(item.get("id")) for item in old_statuses}
            new_ids = {item["id"] for item in validated}
            removed_ids = old_ids - new_ids

            settings["board_statuses"] = validated
            data["settings"] = settings

            fallback_id = "unset" if "unset" in new_ids else validated[0]["id"]
            for board in data.get("boards", []):
                board_status_id = str(board.get("status_id") or "")
                if board_status_id in removed_ids or board_status_id not in new_ids:
                    self._apply_board_status(data, board, fallback_id)
                else:
                    self._apply_board_status(data, board, board_status_id)

            self._write(data)
            self.storage.write_settings(settings)
            return settings

    def _normalize_status_id(self, data: dict[str, Any], raw: str | None) -> str:
        statuses = data.get("settings", DEFAULT_DATA["settings"]).get(
            "board_statuses", DEFAULT_DATA["settings"]["board_statuses"]
        )
        value = (raw or "unset").strip()
        for item in statuses:
            if item.get("id") == value or item.get("label") == value:
                return str(item["id"])
        return "unset"

    def _status_label(self, data: dict[str, Any], status_id: str) -> str:
        statuses = data.get("settings", DEFAULT_DATA["settings"]).get(
            "board_statuses", DEFAULT_DATA["settings"]["board_statuses"]
        )
        for item in statuses:
            if item.get("id") == status_id:
                return str(item.get("label") or status_id)
        return "未设状态"

    def _apply_board_status(self, data: dict[str, Any], board: dict[str, Any], raw_status: str | None) -> None:
        status_id = self._normalize_status_id(data, raw_status or board.get("status_id") or board.get("status"))
        board["status_id"] = status_id
        board["status"] = self._status_label(data, status_id)

    def list_boards(self) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read()
            boards = sorted(data.get("boards", []), key=lambda item: item.get("updated_at", ""), reverse=True)
            lists = data.get("lists", [])
            cards = data.get("cards", [])
            result = []
            for board in boards:
                board_id = str(board["id"])
                board_lists = [item for item in lists if str(item.get("board_id")) == board_id]
                board_cards = [item for item in cards if str(item.get("board_id")) == board_id]
                result.append(
                    {
                        **board,
                        "list_count": len(board_lists),
                        "card_count": len(board_cards),
                        "shared": False,
                    }
                )
            for item in result:
                self._apply_board_status(data, item, item.get("status_id") or item.get("status"))

            if self.share_service and self.auth_service:
                user = self.auth_service.get_current_user()
                if user and not user.get("is_super_admin"):
                    shared_boards = self.share_service.list_shared_boards(user)
                    existing_keys = {
                        f"own:{item.get('id')}" for item in result if not item.get("shared")
                    }
                    for board in shared_boards:
                        board_key = (
                            f"shared:{board.get('owner_tenant_type')}:"
                            f"{board.get('owner_tenant_id')}:{board.get('id')}"
                        )
                        if board_key in existing_keys:
                            continue
                        board_id = str(board["id"])
                        self._apply_board_status(data, board, board.get("status_id") or board.get("status"))
                        result.append(
                            {
                                **board,
                                "list_count": board.get("list_count", 0),
                                "card_count": board.get("card_count", 0),
                            }
                        )
                        existing_keys.add(board_key)
            return result

    def create_board(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = (payload.get("title") or "").strip()
        if not title:
            raise ValueError("看板标题不能为空")

        with self._lock:
            data = self._read()
            board_id = self._next_id(data, "next_board_id")
            now = _now_iso()
            board = {
                "id": board_id,
                "title": title,
                "start_date": (payload.get("start_date") or "").strip(),
                "end_date": (payload.get("end_date") or "").strip(),
                "organization": (payload.get("organization") or "").strip(),
                "description": (payload.get("description") or "").strip(),
                "created_at": now,
                "updated_at": now,
            }
            self._apply_board_status(data, board, payload.get("status_id") or payload.get("status") or "not_started")
            data.setdefault("boards", []).append(board)
            self._write(data)
            self._ensure_organization_for_board(board.get("organization"))
            return board

    def update_board(self, board_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            board = self._find_board(data, board_id)
            for field in ("title", "start_date", "end_date", "organization", "description"):
                if field in payload:
                    board[field] = (payload.get(field) or "").strip()
            if "status_id" in payload or "status" in payload:
                self._apply_board_status(data, board, payload.get("status_id") or payload.get("status"))
            elif "status_id" not in board:
                self._apply_board_status(data, board, board.get("status"))
            if "title" in payload and not board["title"]:
                raise ValueError("看板标题不能为空")
            board["updated_at"] = _now_iso()
            self._write(data)
            if "organization" in payload:
                self._ensure_organization_for_board(board.get("organization"))
            return board

    def delete_board(self, board_id: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            self._find_board(data, board_id)
            data["boards"] = [item for item in data.get("boards", []) if str(item.get("id")) != board_id]
            data["lists"] = [item for item in data.get("lists", []) if str(item.get("board_id")) != board_id]
            data["cards"] = [item for item in data.get("cards", []) if str(item.get("board_id")) != board_id]
            self._write(data)
            return {"id": board_id}

    def get_board_detail(self, board_id: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            board = self._find_board(data, board_id)
            lists = sorted(
                [item for item in data.get("lists", []) if str(item.get("board_id")) == board_id],
                key=lambda item: item.get("position", 0),
            )
            cards = data.get("cards", [])
            list_payload = []
            for lst in lists:
                list_id = str(lst["id"])
                list_cards = sorted(
                    [item for item in cards if str(item.get("list_id")) == list_id],
                    key=lambda item: item.get("position", 0),
                )
                list_payload.append({**lst, "cards": list_cards})
            board_payload = dict(board)
            self._apply_board_status(data, board_payload, board_payload.get("status_id") or board_payload.get("status"))
            return {
                "board": board_payload,
                "lists": list_payload,
                "settings": self.get_settings(),
            }

    def create_list(self, board_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        title = (payload.get("title") or "").strip()
        if not title:
            raise ValueError("列表标题不能为空")

        with self._lock:
            data = self._read()
            self._find_board(data, board_id)
            list_id = self._next_id(data, "next_list_id")
            board_lists = [item for item in data.get("lists", []) if str(item.get("board_id")) == board_id]
            position = len(board_lists)
            lst = {
                "id": list_id,
                "board_id": board_id,
                "title": title,
                "position": position,
                "created_at": _now_iso(),
                "card_sections": {"show_checklist": True, "show_comments": True},
            }
            data.setdefault("lists", []).append(lst)
            self._touch_board(data, board_id)
            self._write(data)
            return {**lst, "cards": []}

    def update_list(self, board_id: str, list_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            self._find_board(data, board_id)
            lst = self._find_list(data, board_id, list_id)
            if "title" in payload:
                title = (payload.get("title") or "").strip()
                if not title:
                    raise ValueError("列表标题不能为空")
                lst["title"] = title
            if "card_sections" in payload:
                lst["card_sections"] = self._normalize_card_sections(
                    payload.get("card_sections"),
                    lst.get("card_sections"),
                )
            self._touch_board(data, board_id)
            self._write(data)
            return lst

    @staticmethod
    def _normalize_card_sections(
        payload_sections: Any,
        existing_sections: Any = None,
    ) -> dict[str, bool]:
        merged: dict[str, bool] = {}
        if isinstance(existing_sections, dict):
            merged["show_checklist"] = existing_sections.get("show_checklist", True) is not False
            merged["show_comments"] = existing_sections.get("show_comments", True) is not False
        else:
            merged = {"show_checklist": True, "show_comments": True}
        if isinstance(payload_sections, dict):
            if "show_checklist" in payload_sections:
                merged["show_checklist"] = bool(payload_sections.get("show_checklist"))
            if "show_comments" in payload_sections:
                merged["show_comments"] = bool(payload_sections.get("show_comments"))
        return merged

    def delete_list(self, board_id: str, list_id: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            self._find_board(data, board_id)
            self._find_list(data, board_id, list_id)
            data["lists"] = [
                item
                for item in data.get("lists", [])
                if not (str(item.get("board_id")) == board_id and str(item.get("id")) == list_id)
            ]
            data["cards"] = [
                item
                for item in data.get("cards", [])
                if not (str(item.get("board_id")) == board_id and str(item.get("list_id")) == list_id)
            ]
            self._reindex_lists(data, board_id)
            self._touch_board(data, board_id)
            self._write(data)
            return {"id": list_id}

    def reorder_lists(self, board_id: str, ordered_ids: list[str]) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read()
            self._find_board(data, board_id)
            board_lists = {str(item["id"]): item for item in data.get("lists", []) if str(item.get("board_id")) == board_id}
            for index, list_id in enumerate(ordered_ids):
                if list_id in board_lists:
                    board_lists[list_id]["position"] = index
            self._touch_board(data, board_id)
            self._write(data)
            return sorted(board_lists.values(), key=lambda item: item.get("position", 0))

    def create_card(self, board_id: str, list_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        title = (payload.get("title") or "").strip()
        if not title:
            raise ValueError("卡片标题不能为空")

        with self._lock:
            data = self._read()
            self._find_board(data, board_id)
            self._find_list(data, board_id, list_id)
            card_id = str(uuid.uuid4())
            list_cards = [
                item
                for item in data.get("cards", [])
                if str(item.get("board_id")) == board_id and str(item.get("list_id")) == list_id
            ]
            card_type = (payload.get("type") or "user_story").strip()
            now = _now_iso()
            card = {
                "id": card_id,
                "board_id": board_id,
                "list_id": list_id,
                "title": title,
                "type": card_type,
                "description": (payload.get("description") or "").strip(),
                "position": len(list_cards),
                "comment_count": 0,
                "checklist_done": 0,
                "checklist_total": 0,
                "checklist": [],
                "comments": [],
                "canvas_data": None,
                "mindmap_data": None,
                "table_data": None,
                "description_data": None,
                "revision": 1,
                "created_at": now,
                "updated_at": now,
            }
            data.setdefault("cards", []).append(card)
            self._touch_board(data, board_id)
            self._write(data)
            return card

    def update_card(
        self,
        board_id: str,
        card_id: str,
        payload: dict[str, Any],
        *,
        base_revision: Any = None,
        force: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            card = self._find_card(data, board_id, card_id)
            collab = self._collaboration_config()
            assert_revision(
                card,
                base_revision if base_revision is not None else payload.get("base_revision"),
                enabled=collab.get("card_optimistic_lock", True),
                force=force or bool(payload.get("force")),
            )
            if "title" in payload:
                title = (payload.get("title") or "").strip()
                if not title:
                    raise ValueError("卡片标题不能为空")
                card["title"] = title
            for field in ("type", "description"):
                if field in payload:
                    card[field] = (payload.get(field) or "").strip()
            if "description_data" in payload:
                card["description_data"] = payload.get("description_data")
            if "checklist" in payload and isinstance(payload["checklist"], list):
                checklist = []
                for item in payload["checklist"]:
                    text = (item.get("text") or "").strip()
                    if not text:
                        continue
                    checklist.append(
                        {
                            "id": item.get("id") or str(uuid.uuid4())[:8],
                            "text": text,
                            "done": bool(item.get("done")),
                        }
                    )
                card["checklist"] = checklist
                card["checklist_done"] = sum(1 for item in checklist if item["done"])
                card["checklist_total"] = len(checklist)
                card["checklist_done"] = sum(1 for item in checklist if item["done"])
                card["checklist_total"] = len(checklist)
            bump_revision(card)
            card["updated_at"] = _now_iso()
            self._touch_board(data, board_id)
            self._write(data)
            return card

    def get_card_editor(self, board_id: str, card_id: str, field: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            card = self._find_card(data, board_id, card_id)
            return {
                "id": card_id,
                "title": card.get("title") or "",
                "revision": card_revision(card),
                field: card.get(field),
            }

    def update_card_editor(
        self,
        board_id: str,
        card_id: str,
        field: str,
        payload: Any,
        *,
        base_revision: Any = None,
        force: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            card = self._find_card(data, board_id, card_id)
            collab = self._collaboration_config()
            assert_revision(
                card,
                base_revision,
                enabled=collab.get("card_optimistic_lock", True),
                force=force,
            )
            card[field] = payload
            bump_revision(card)
            card["updated_at"] = _now_iso()
            self._touch_board(data, board_id)
            self._write(data)
            return card

    def get_card_canvas(self, board_id: str, card_id: str) -> dict[str, Any]:
        return self.get_card_editor(board_id, card_id, "canvas_data")

    def update_card_canvas(self, board_id: str, card_id: str, canvas_data: Any) -> dict[str, Any]:
        return self.update_card_editor(board_id, card_id, "canvas_data", canvas_data)

    def get_card_mindmap(self, board_id: str, card_id: str) -> dict[str, Any]:
        return self.get_card_editor(board_id, card_id, "mindmap_data")

    def update_card_mindmap(self, board_id: str, card_id: str, mindmap_data: Any) -> dict[str, Any]:
        return self.update_card_editor(board_id, card_id, "mindmap_data", mindmap_data)

    def delete_card(self, board_id: str, card_id: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            card = self._find_card(data, board_id, card_id)
            list_id = str(card["list_id"])
            data["cards"] = [
                item
                for item in data.get("cards", [])
                if not (str(item.get("board_id")) == board_id and str(item.get("id")) == card_id)
            ]
            self._reindex_cards(data, board_id, list_id)
            self._touch_board(data, board_id)
            self._write(data)
            return {"id": card_id}

    def move_card(
        self,
        board_id: str,
        card_id: str,
        target_list_id: str,
        target_position: int,
    ) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            card = self._find_card(data, board_id, card_id)
            self._find_list(data, board_id, target_list_id)
            source_list_id = str(card["list_id"])
            card["list_id"] = target_list_id

            source_cards = [
                item
                for item in data.get("cards", [])
                if str(item.get("board_id")) == board_id and str(item.get("list_id")) == source_list_id and str(item.get("id")) != card_id
            ]
            target_cards = [
                item
                for item in data.get("cards", [])
                if str(item.get("board_id")) == board_id and str(item.get("list_id")) == target_list_id and str(item.get("id")) != card_id
            ]

            source_cards.sort(key=lambda item: item.get("position", 0))
            target_cards.sort(key=lambda item: item.get("position", 0))

            target_position = max(0, min(target_position, len(target_cards)))
            target_cards.insert(target_position, card)

            for index, item in enumerate(source_cards):
                item["position"] = index
            for index, item in enumerate(target_cards):
                item["position"] = index

            card["updated_at"] = _now_iso()
            self._touch_board(data, board_id)
            self._write(data)
            return card

    def add_comment(
        self,
        board_id: str,
        card_id: str,
        payload: dict[str, Any],
        *,
        base_revision: Any = None,
        force: bool = False,
    ) -> dict[str, Any]:
        content = (payload.get("content") or "").strip()
        if not content:
            raise ValueError("评论内容不能为空")
        parent_id = (payload.get("parent_id") or "").strip()

        with self._lock:
            data = self._read()
            card = self._find_card(data, board_id, card_id)
            collab = self._collaboration_config()
            assert_revision(
                card,
                base_revision if base_revision is not None else payload.get("base_revision"),
                enabled=collab.get("card_optimistic_lock", True),
                force=force or bool(payload.get("force")),
            )
            item = {
                "id": str(uuid.uuid4())[:8],
                "content": content,
                "author": (payload.get("author") or "我").strip(),
                "created_at": _now_iso(),
            }
            if parent_id:
                parent = self._find_top_level_comment(card, parent_id)
                parent.setdefault("replies", []).append(item)
            else:
                item["replies"] = []
                card.setdefault("comments", []).append(item)
            card["comment_count"] = self._count_comments(card.get("comments", []))
            bump_revision(card)
            card["updated_at"] = _now_iso()
            self._touch_board(data, board_id)
            self._write(data)
            return card

    def update_comment(
        self,
        board_id: str,
        card_id: str,
        comment_id: str,
        payload: dict[str, Any],
        *,
        base_revision: Any = None,
        force: bool = False,
    ) -> dict[str, Any]:
        content = (payload.get("content") or "").strip()
        if not content:
            raise ValueError("评论内容不能为空")

        with self._lock:
            data = self._read()
            card = self._find_card(data, board_id, card_id)
            collab = self._collaboration_config()
            assert_revision(
                card,
                base_revision if base_revision is not None else payload.get("base_revision"),
                enabled=collab.get("card_optimistic_lock", True),
                force=force or bool(payload.get("force")),
            )
            target, _parent = self._locate_comment(card, comment_id)
            target["content"] = content
            target["updated_at"] = _now_iso()
            bump_revision(card)
            card["updated_at"] = _now_iso()
            self._touch_board(data, board_id)
            self._write(data)
            return card

    def delete_comment(
        self,
        board_id: str,
        card_id: str,
        comment_id: str,
        *,
        base_revision: Any = None,
        force: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            card = self._find_card(data, board_id, card_id)
            collab = self._collaboration_config()
            assert_revision(
                card,
                base_revision,
                enabled=collab.get("card_optimistic_lock", True),
                force=force,
            )
            _target, parent = self._locate_comment(card, comment_id)
            if parent is None:
                card["comments"] = [
                    item for item in card.get("comments", []) if str(item.get("id")) != comment_id
                ]
            else:
                parent["replies"] = [
                    item for item in parent.get("replies", []) if str(item.get("id")) != comment_id
                ]
            card["comment_count"] = self._count_comments(card.get("comments", []))
            bump_revision(card)
            card["updated_at"] = _now_iso()
            self._touch_board(data, board_id)
            self._write(data)
            return card

    def search(self, keyword: str) -> dict[str, Any]:
        keyword = (keyword or "").strip().lower()
        with self._lock:
            data = self._read()
            if not keyword:
                return {"groups": [], "total": 0, "keyword": ""}

            boards_by_id = {str(item["id"]): item for item in data.get("boards", [])}
            lists_by_id = {str(item["id"]): item for item in data.get("lists", [])}
            groups: dict[str, dict[str, Any]] = {}

            def ensure_group(board_id: str) -> dict[str, Any]:
                board_id = str(board_id)
                if board_id not in groups:
                    board = boards_by_id.get(board_id, {})
                    groups[board_id] = {
                        "board_id": board_id,
                        "board_title": board.get("title") or f"看板 #{board_id}",
                        "items": [],
                    }
                return groups[board_id]

            def add_match(
                board_id: str,
                item_type: str,
                item_id: str,
                title: str,
                subtitle: str = "",
                card_id: str | None = None,
            ) -> None:
                group = ensure_group(board_id)
                group["items"].append(
                    {
                        "type": item_type,
                        "id": item_id,
                        "title": title,
                        "subtitle": subtitle,
                        "board_id": str(board_id),
                        "card_id": card_id or (item_id if item_type == "card" else None),
                    }
                )

            for board in data.get("boards", []):
                board_id = str(board["id"])
                haystack = " ".join(
                    [
                        board.get("title") or "",
                        board.get("description") or "",
                        board.get("organization") or "",
                        board.get("status") or "",
                    ]
                ).lower()
                if keyword in haystack:
                    add_match(board_id, "board", board_id, board.get("title") or "", "看板")

            for lst in data.get("lists", []):
                board_id = str(lst.get("board_id"))
                if keyword in (lst.get("title") or "").lower():
                    add_match(board_id, "list", str(lst["id"]), lst.get("title") or "", "列表")

            for card in data.get("cards", []):
                board_id = str(card.get("board_id"))
                card_id = str(card["id"])
                list_title = lists_by_id.get(str(card.get("list_id")), {}).get("title", "")

                card_text = f"{card.get('title') or ''} {_plain_text(card.get('description'))}".lower()
                if keyword in card_text:
                    add_match(
                        board_id,
                        "card",
                        card_id,
                        card.get("title") or "",
                        list_title or "卡片",
                        card_id,
                    )

                for comment in card.get("comments", []):
                    content = comment.get("content") or ""
                    if keyword in content.lower():
                        snippet = content if len(content) <= 40 else f"{content[:40]}..."
                        add_match(
                            board_id,
                            "card",
                            card_id,
                            card.get("title") or "",
                            f"评论: {snippet}",
                            card_id,
                        )
                    for reply in comment.get("replies", []):
                        reply_content = reply.get("content") or ""
                        if keyword in reply_content.lower():
                            snippet = reply_content if len(reply_content) <= 40 else f"{reply_content[:40]}..."
                            add_match(
                                board_id,
                                "card",
                                card_id,
                                card.get("title") or "",
                                f"回复: {snippet}",
                                card_id,
                            )

            result_groups = sorted(groups.values(), key=lambda group: group.get("board_title") or "")
            total = sum(len(group["items"]) for group in result_groups)
            return {"groups": result_groups, "total": total, "keyword": keyword}

    def seed_demo_if_empty(self) -> None:
        with self._lock:
            tenant_ctx = {"type": "super_admin", "id": "super_admin", "scope_mode": "org_multi"}
            settings = self.storage.read_settings()
            data = self.storage.read_tenant(tenant_ctx, settings)
            if data.get("boards"):
                return

            data["boards"] = [
                {
                    "id": "1",
                    "title": "Linux_ubuntu 学习",
                    "status_id": "unset",
                    "status": "未设状态",
                    "start_date": "2022-04-04",
                    "end_date": "2022-04-17",
                    "organization": "某某公司",
                    "description": "Ubuntu 与 Linux 学习流程看板",
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                }
            ]
            data["lists"] = [
                {"id": "1", "board_id": "1", "title": "mysql学习", "position": 0, "created_at": _now_iso()},
                {"id": "2", "board_id": "1", "title": "svn 服务器", "position": 1, "created_at": _now_iso()},
                {"id": "3", "board_id": "1", "title": "svn服务器", "position": 2, "created_at": _now_iso()},
            ]
            data["cards"] = [
                {
                    "id": "1",
                    "board_id": "1",
                    "list_id": "1",
                    "title": "卸载mysql",
                    "type": "user_story",
                    "description": "",
                    "position": 0,
                    "comment_count": 1,
                    "checklist_done": 0,
                    "checklist_total": 0,
                    "checklist": [],
                    "comments": [{"id": "c1", "content": "已完成卸载", "author": "我", "created_at": _now_iso(), "replies": []}],
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                },
                {
                    "id": "2",
                    "board_id": "1",
                    "list_id": "2",
                    "title": "ubuntu学习 svn服务器",
                    "type": "task",
                    "description": "",
                    "position": 0,
                    "comment_count": 0,
                    "checklist_done": 0,
                    "checklist_total": 8,
                    "checklist": [{"id": "t1", "text": "安装 svn", "done": False}],
                    "comments": [],
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                },
                {
                    "id": "3",
                    "board_id": "1",
                    "list_id": "2",
                    "title": "Ubuntu下如何将普通用户提升到root权限",
                    "type": "user_story",
                    "description": "",
                    "position": 1,
                    "comment_count": 0,
                    "checklist_done": 0,
                    "checklist_total": 0,
                    "checklist": [],
                    "comments": [],
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                },
                {
                    "id": "4",
                    "board_id": "1",
                    "list_id": "2",
                    "title": "切换终端用户",
                    "type": "user_story",
                    "description": "",
                    "position": 2,
                    "comment_count": 0,
                    "checklist_done": 0,
                    "checklist_total": 0,
                    "checklist": [],
                    "comments": [],
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                },
                {
                    "id": "5",
                    "board_id": "1",
                    "list_id": "2",
                    "title": "安装ssh服务器",
                    "type": "user_story",
                    "description": "",
                    "position": 3,
                    "comment_count": 0,
                    "checklist_done": 0,
                    "checklist_total": 0,
                    "checklist": [],
                    "comments": [],
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                },
                {
                    "id": "6",
                    "board_id": "1",
                    "list_id": "3",
                    "title": "安装桌面",
                    "type": "user_story",
                    "description": "",
                    "position": 0,
                    "comment_count": 6,
                    "checklist_done": 0,
                    "checklist_total": 0,
                    "checklist": [],
                    "comments": [
                        {
                            "id": f"c{i}",
                            "content": f"讨论 {i}",
                            "author": "我",
                            "created_at": _now_iso(),
                            "replies": [],
                        }
                        for i in range(1, 7)
                    ],
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                },
            ]
            data["meta"] = {"next_board_id": 2, "next_list_id": 4, "next_card_id": 7}
            self.storage.write_tenant(tenant_ctx, data, settings)

    def _find_board(self, data: dict[str, Any], board_id: str) -> dict[str, Any]:
        for board in data.get("boards", []):
            if str(board.get("id")) == board_id:
                return board
        raise ValueError("看板不存在")

    def _find_list(self, data: dict[str, Any], board_id: str, list_id: str) -> dict[str, Any]:
        for lst in data.get("lists", []):
            if str(lst.get("board_id")) == board_id and str(lst.get("id")) == list_id:
                return lst
        raise ValueError("列表不存在")

    def _find_card(self, data: dict[str, Any], board_id: str, card_id: str) -> dict[str, Any]:
        for card in data.get("cards", []):
            if str(card.get("board_id")) == board_id and str(card.get("id")) == card_id:
                return card
        raise ValueError("卡片不存在")

    def _find_top_level_comment(self, card: dict[str, Any], comment_id: str) -> dict[str, Any]:
        for comment in card.get("comments", []):
            if str(comment.get("id")) == comment_id:
                return comment
        raise ValueError("评论不存在")

    def _locate_comment(self, card: dict[str, Any], comment_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
        for comment in card.get("comments", []):
            if str(comment.get("id")) == comment_id:
                return comment, None
            for reply in comment.get("replies", []):
                if str(reply.get("id")) == comment_id:
                    return reply, comment
        raise ValueError("评论不存在")

    @staticmethod
    def _count_comments(comments: list[dict[str, Any]]) -> int:
        total = 0
        for comment in comments:
            total += 1
            total += len(comment.get("replies", []))
        return total

    def _touch_board(self, data: dict[str, Any], board_id: str) -> None:
        board = self._find_board(data, board_id)
        board["updated_at"] = _now_iso()

    def _reindex_lists(self, data: dict[str, Any], board_id: str) -> None:
        lists = sorted(
            [item for item in data.get("lists", []) if str(item.get("board_id")) == board_id],
            key=lambda item: item.get("position", 0),
        )
        for index, lst in enumerate(lists):
            lst["position"] = index

    def _reindex_cards(self, data: dict[str, Any], board_id: str, list_id: str) -> None:
        cards = sorted(
            [
                item
                for item in data.get("cards", [])
                if str(item.get("board_id")) == board_id and str(item.get("list_id")) == list_id
            ],
            key=lambda item: item.get("position", 0),
        )
        for index, card in enumerate(cards):
            card["position"] = index

    def _current_owner_scope(self) -> dict[str, str]:
        user = self.auth_service.get_current_user() if self.auth_service else None
        if user and user.get("is_super_admin"):
            return {"type": SUPER_ADMIN_TENANT_TYPE, "id": SUPER_ADMIN_ID}
        if user:
            return {"type": USER_TENANT_TYPE, "id": str(user.get("id") or "")}
        return {"type": SUPER_ADMIN_TENANT_TYPE, "id": SUPER_ADMIN_ID}

    def _find_org(self, org_id: str, scope: dict[str, str]) -> dict[str, Any] | None:
        if scope["type"] == USER_TENANT_TYPE:
            orgs = self._read_user_organizations(scope["id"])
        else:
            orgs = self._read_admin_organizations()
        return next((item for item in orgs if str(item.get("id")) == org_id), None)

    def _is_org_owned_by_scope(self, org: dict[str, Any], scope: dict[str, str]) -> bool:
        if str(org.get("id")) == PERSONAL_ORG_ID:
            return True
        if scope["type"] == USER_TENANT_TYPE:
            return True
        org_type = str(org.get("created_by_type") or SUPER_ADMIN_TENANT_TYPE)
        org_owner = str(org.get("created_by_id") or SUPER_ADMIN_ID)
        return org_type == scope["type"] and org_owner == scope["id"]

    def assert_org_owner(self, org_id: str) -> dict[str, Any]:
        scope = self._current_owner_scope()
        org = self._find_org(org_id, scope)
        if not org and org_id == PERSONAL_ORG_ID:
            org = {"id": PERSONAL_ORG_ID, "name": PERSONAL_BOARD_ORG_NAME, "note": ""}
        if not org:
            raise ValueError("组织不存在")
        user = self.auth_service.get_current_user() if self.auth_service else None
        if user and user.get("is_super_admin") and scope["type"] == SUPER_ADMIN_TENANT_TYPE:
            return org
        if not self._is_org_owned_by_scope(org, scope):
            raise PermissionError("无权操作该组织")
        return org

    def assert_import_permission(self, package: dict[str, Any]) -> None:
        kind = package.get("kind")
        payload = package.get("payload") or {}
        user = self.auth_service.get_current_user() if self.auth_service else None
        if not user:
            raise PermissionError("请先登录")

        if kind == "system":
            if not user.get("is_super_admin"):
                raise PermissionError("仅超级管理员可导入系统包")
            return

        if kind == "organization":
            organization = payload.get("organization") or {}
            org_id = str(organization.get("id") or "")
            if org_id:
                self.assert_org_owner(org_id)
            else:
                scope = self._current_owner_scope()
                org_type = str(organization.get("created_by_type") or scope["type"])
                org_owner = str(organization.get("created_by_id") or scope["id"])
                if org_type != scope["type"] or org_owner != scope["id"]:
                    raise PermissionError("无权导入该组织包")
            return

        if kind == "board":
            if user.get("is_super_admin"):
                return
            scope = self._current_owner_scope()
            board_owners = payload.get("board_owners") if isinstance(payload.get("board_owners"), dict) else {}
            board = payload.get("board") or {}
            board_id = str(board.get("id") or "")
            owner = board_owners.get(board_id) if board_id else None
            if isinstance(owner, dict):
                if str(owner.get("type")) != scope["type"] or str(owner.get("id")) != scope["id"]:
                    raise PermissionError("无权导入该看板包")
            return

    def export_system_dat(self) -> tuple[bytes, str]:
        from services.data_transfer import export_system

        with self._lock:
            return export_system(self.storage)

    def export_organization_dat(
        self,
        org_id: str,
        *,
        owner_only: bool = False,
    ) -> tuple[bytes, str]:
        from services.data_transfer import export_organization

        with self._lock:
            owner_type = owner_id = None
            if owner_only:
                self.assert_org_owner(org_id)
                scope = self._current_owner_scope()
                owner_type = scope["type"]
                owner_id = scope["id"]
            return export_organization(
                self.storage,
                org_id,
                owner_type=owner_type,
                owner_id=owner_id,
            )

    def export_board_dat(self, board_id: str) -> tuple[bytes, str]:
        from services.data_transfer import export_board

        with self._lock:
            data = self._read()
            self._find_board(data, board_id)
            organizations = self._organizations_for_current_tenant()
            return export_board(data, board_id, organizations=organizations)

    def _prepare_board_import_package(self, package: dict[str, Any]) -> dict[str, Any]:
        payload = copy.deepcopy(package.get("payload") or {})
        board = payload.get("board") or {}
        org_meta = payload.get("organization")
        if not isinstance(org_meta, dict):
            org_name = (board.get("organization") or "").strip()
            org_meta = {"id": "", "name": org_name, "note": ""} if org_name else {}
        if org_meta:
            resolved = self._import_merge_organization(org_meta)
            board = copy.deepcopy(board)
            board["organization"] = resolved.get("name") or board.get("organization") or ""
            payload["board"] = board
            payload["organization"] = resolved
        return {**package, "payload": payload}

    def validate_import_dat(self, raw: bytes | str, *, expected_kind: str | None = None) -> dict[str, Any]:
        from services.data_transfer import parse_package, validate_package

        package = parse_package(raw)
        validation = validate_package(package, expected_kind=expected_kind)
        if validation.get("valid"):
            self.assert_import_permission(package)
        return validation

    def import_dat(self, raw: bytes | str, *, mode: str = "merge", owner_only: bool = False) -> dict[str, Any]:
        from services.data_transfer import (
            _is_v2_system_payload,
            apply_import,
            import_organization_snapshot,
            import_system_snapshot,
            parse_package,
            validate_package,
        )

        package = parse_package(raw)
        validation = validate_package(package)
        if not validation["valid"]:
            raise ValueError("数据包校验未通过：" + "；".join(validation["errors"][:3]))
        self.assert_import_permission(package)

        kind = package.get("kind")
        payload = package.get("payload") or {}
        owner_scope = self._current_owner_scope()

        with self._lock:
            self.clear_board_access()
            if kind == "system" and _is_v2_system_payload(payload):
                import_system_snapshot(
                    self.storage,
                    package,
                    share_service=self.share_service,
                )
                return validation

            if kind == "organization" and (payload.get("board_owners") or owner_only):
                import_organization_snapshot(
                    self.storage,
                    package,
                    mode=mode,
                    share_service=self.share_service,
                    owner_type=owner_scope["type"] if owner_only else None,
                    owner_id=owner_scope["id"] if owner_only else None,
                )
                return validation

            if kind == "board":
                package = self._prepare_board_import_package(package)

            current = self._read()
            imported = apply_import(current, package, mode=mode)
            self._write(imported)
            return validation

    def iter_clear_all_system_data(self):
        self.clear_board_access()
        yield from self.storage.iter_clear_all_system_data()

