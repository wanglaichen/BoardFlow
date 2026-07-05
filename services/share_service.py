from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from services.org_keys import PERSONAL_BOARD_ORG_NAME, PERSONAL_ORG_ID, resolve_org_id
from services.tenant_keys import (
    SUPER_ADMIN_TENANT_TYPE,
    USER_TENANT_TYPE,
    build_tenant_context,
    owner_tenant_scope_root,
    shared_board_entry_id,
    shared_org_index_entry_id,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ShareService:
    def __init__(self, storage, auth_service) -> None:
        self.storage = storage
        self.auth_service = auth_service

    def list_received_shares(self, grantee_user_id: str) -> list[dict[str, Any]]:
        return self.storage.list_shares_for_grantee(grantee_user_id)

    def list_board_shares(self, owner_ctx: dict[str, Any], board_id: str) -> list[dict[str, Any]]:
        return [
            item
            for item in self.storage.list_shares()
            if str(item.get("board_id")) == str(board_id)
            and str(item.get("owner_tenant_id")) == str(owner_ctx.get("id"))
            and item.get("owner_tenant_type") == owner_ctx.get("type")
        ]

    def create_share(
        self,
        owner_ctx: dict[str, Any],
        board_id: str,
        grantee_user_id: str,
        permissions: dict[str, Any],
    ) -> dict[str, Any]:
        if owner_ctx.get("type") == USER_TENANT_TYPE and owner_ctx.get("id") == grantee_user_id:
            raise ValueError("不能分享给自己")
        grantee = self.storage.get_user(grantee_user_id)
        if not grantee:
            raise ValueError("目标用户不存在")

        existing = self._find_share(owner_ctx, board_id, grantee_user_id)
        if existing:
            return self.update_share(existing["id"], permissions)

        share = {
            "id": f"share_{uuid.uuid4().hex[:10]}",
            "owner_tenant_type": owner_ctx.get("type"),
            "owner_tenant_id": owner_ctx.get("id"),
            "board_id": str(board_id),
            "grantee_user_id": grantee_user_id,
            "permissions": self._normalize_permissions(permissions),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        self.storage.save_share(share)
        self.sync_grantee_share_index(grantee_user_id)
        return share

    def update_share(self, share_id: str, permissions: dict[str, Any]) -> dict[str, Any]:
        share = self.storage.get_share(share_id)
        if not share:
            raise ValueError("分享记录不存在")
        share["permissions"] = self._normalize_permissions(permissions)
        share["updated_at"] = _now_iso()
        self.storage.save_share(share)
        grantee_user_id = share.get("grantee_user_id")
        if grantee_user_id:
            self.sync_grantee_share_index(str(grantee_user_id))
        return share

    def delete_share(self, share_id: str) -> None:
        share = self.storage.get_share(share_id)
        if not share:
            raise ValueError("分享记录不存在")
        grantee_user_id = share.get("grantee_user_id")
        self.storage.delete_share(share_id)
        if grantee_user_id:
            self.sync_grantee_share_index(str(grantee_user_id))

    def resolve_board_access(
        self,
        board_id: str,
        current_user: dict[str, Any],
        owner_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tenant_ctx = build_tenant_context(current_user)
        own_data = self.storage.read_tenant(tenant_ctx, self.storage.read_settings())
        if any(str(board.get("id")) == str(board_id) for board in own_data.get("boards", [])):
            return {
                "tenant_ctx": tenant_ctx,
                "board_id": str(board_id),
                "is_owner": True,
                "shared": False,
                "permissions": {"view": True, "edit": True},
            }

        share = self._find_received_share(current_user.get("id"), board_id, owner_hint)
        if not share:
            raise ValueError("看板不存在或无权访问")

        owner_ctx = {
            "type": share.get("owner_tenant_type"),
            "id": share.get("owner_tenant_id"),
            "scope_mode": "org_multi" if share.get("owner_tenant_type") == SUPER_ADMIN_TENANT_TYPE else "user_single",
        }
        if owner_ctx["scope_mode"] == "user_single":
            owner_ctx["scope_root"] = owner_tenant_scope_root(owner_ctx["type"], owner_ctx["id"])

        owner_data = self.storage.read_tenant(owner_ctx, self.storage.read_settings())
        if not any(str(board.get("id")) == str(board_id) for board in owner_data.get("boards", [])):
            raise ValueError("分享的看板不存在")

        permissions = share.get("permissions") or {"view": True, "edit": False}
        return {
            "tenant_ctx": owner_ctx,
            "board_id": str(board_id),
            "is_owner": False,
            "shared": True,
            "share_id": share.get("id"),
            "permissions": permissions,
        }

    def assert_board_permission(self, access: dict[str, Any], action: str = "edit") -> None:
        permissions = access.get("permissions") or {}
        if action == "view":
            if not permissions.get("view", True):
                raise PermissionError("无权查看该看板")
            return
        if not permissions.get("edit"):
            raise PermissionError("无权修改该看板")

    def list_shared_boards(self, current_user: dict[str, Any]) -> list[dict[str, Any]]:
        if current_user.get("is_super_admin"):
            return []
        grantee_user_id = str(current_user.get("id") or "")
        if not grantee_user_id:
            return []
        self.sync_grantee_share_index(grantee_user_id)
        entries = self.storage.list_user_shared_boards(grantee_user_id)
        settings = self.storage.read_settings()
        boards: list[dict[str, Any]] = []
        for entry in entries:
            board = self._load_shared_board_payload(entry, settings)
            if board:
                boards.append(board)
        return boards

    def sync_grantee_share_index(self, grantee_user_id: str) -> list[dict[str, Any]]:
        shared_boards = self._build_shared_board_entries(grantee_user_id)
        self.storage.write_user_shared_boards(grantee_user_id, shared_boards)
        self.storage.write_user_shared_org_index(
            grantee_user_id,
            self._build_shared_org_index(shared_boards),
        )
        self.storage.migrate_legacy_user_index_keys(grantee_user_id)
        return shared_boards

    def _build_shared_board_entries(self, grantee_user_id: str) -> list[dict[str, Any]]:
        shares = self.list_received_shares(grantee_user_id)
        settings = self.storage.read_settings()
        global_orgs = settings.get("organizations") or []
        entries: list[dict[str, Any]] = []

        for share in shares:
            owner_ctx = self._owner_ctx_from_share(share)
            owner_data = self.storage.read_tenant(owner_ctx, settings)
            board = next(
                (item for item in owner_data.get("boards", []) if str(item.get("id")) == str(share.get("board_id"))),
                None,
            )
            if not board:
                continue

            board_id = str(board["id"])
            owner_user = self.storage.get_user(share.get("owner_tenant_id") or "")
            owner_display_name = (owner_user or {}).get("display_name") or (owner_user or {}).get("username") or ""
            if share.get("owner_tenant_type") == SUPER_ADMIN_TENANT_TYPE:
                owner_display_name = owner_display_name or "超级管理员"

            org_name = (board.get("organization") or "").strip() or PERSONAL_BOARD_ORG_NAME
            org_id = self._resolve_organization_id(
                org_name,
                str(share.get("owner_tenant_type") or ""),
                str(share.get("owner_tenant_id") or ""),
                global_orgs,
            )
            entry_id = shared_board_entry_id(
                str(share.get("owner_tenant_type") or ""),
                str(share.get("owner_tenant_id") or ""),
                board_id,
            )
            entries.append(
                {
                    "id": entry_id,
                    "share_id": share.get("id"),
                    "board_id": board_id,
                    "board_title": board.get("title") or "",
                    "organization": org_name,
                    "organization_id": org_id,
                    "owner_tenant_type": share.get("owner_tenant_type"),
                    "owner_tenant_id": share.get("owner_tenant_id"),
                    "owner_display_name": owner_display_name,
                    "permissions": share.get("permissions") or {"view": True, "edit": False},
                    "created_at": share.get("created_at") or _now_iso(),
                    "updated_at": share.get("updated_at") or _now_iso(),
                }
            )
        return entries

    @staticmethod
    def _build_shared_org_index(shared_boards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for entry in shared_boards:
            org_name = (entry.get("organization") or "").strip() or PERSONAL_BOARD_ORG_NAME
            org_id = str(entry.get("organization_id") or PERSONAL_ORG_ID)
            owner_type = str(entry.get("owner_tenant_type") or SUPER_ADMIN_TENANT_TYPE)
            owner_id = str(entry.get("owner_tenant_id") or "")
            owner_display_name = (entry.get("owner_display_name") or "").strip()
            group_key = f"{owner_type}:{owner_id}:{org_name}"
            board_id = str(entry.get("board_id") or "")
            existing = grouped.get(group_key)
            if existing:
                if board_id and board_id not in existing["board_ids"]:
                    existing["board_ids"].append(board_id)
                    existing["board_count"] = len(existing["board_ids"])
                existing["updated_at"] = _now_iso()
                continue
            grouped[group_key] = {
                "id": shared_org_index_entry_id(owner_type, owner_id, org_id),
                "organization_id": org_id,
                "organization": org_name,
                "owner_tenant_type": owner_type,
                "owner_tenant_id": owner_id,
                "owner_display_name": owner_display_name,
                "board_ids": [board_id] if board_id else [],
                "board_count": 1 if board_id else 0,
                "created_at": entry.get("created_at") or _now_iso(),
                "updated_at": entry.get("updated_at") or _now_iso(),
            }
        return sorted(
            grouped.values(),
            key=lambda item: (
                item.get("owner_display_name") or "",
                item.get("organization") or "",
            ),
        )

    def _load_shared_board_payload(self, entry: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any] | None:
        share = self.storage.get_share(entry.get("share_id") or "")
        if not share:
            return None
        owner_ctx = self._owner_ctx_from_share(share)
        owner_data = self.storage.read_tenant(owner_ctx, settings)
        board = next(
            (item for item in owner_data.get("boards", []) if str(item.get("id")) == str(entry.get("board_id"))),
            None,
        )
        if not board:
            return None

        board_id = str(board["id"])
        board_lists = [item for item in owner_data.get("lists", []) if str(item.get("board_id")) == board_id]
        board_cards = [item for item in owner_data.get("cards", []) if str(item.get("board_id")) == board_id]
        permissions = entry.get("permissions") or share.get("permissions") or {"view": True, "edit": False}
        org_name = entry.get("organization") or board.get("organization") or PERSONAL_BOARD_ORG_NAME
        org_id = entry.get("organization_id") or self._resolve_organization_id(
            org_name,
            str(entry.get("owner_tenant_type") or ""),
            str(entry.get("owner_tenant_id") or ""),
            settings.get("organizations") or [],
        )
        return {
            **board,
            "shared": True,
            "share_id": entry.get("share_id") or share.get("id"),
            "share_permissions": permissions,
            "owner_user_id": entry.get("owner_tenant_id"),
            "owner_tenant_type": entry.get("owner_tenant_type"),
            "owner_tenant_id": entry.get("owner_tenant_id"),
            "owner_display_name": entry.get("owner_display_name") or "",
            "organization": org_name,
            "organization_id": org_id,
            "list_count": len(board_lists),
            "card_count": len(board_cards),
        }

    @staticmethod
    def _resolve_organization_id(
        org_name: str,
        owner_tenant_type: str,
        owner_tenant_id: str,
        global_orgs: list[dict[str, Any]],
    ) -> str:
        name = (org_name or "").strip() or PERSONAL_BOARD_ORG_NAME
        if name == PERSONAL_BOARD_ORG_NAME:
            return PERSONAL_ORG_ID

        for org in global_orgs:
            if (org.get("name") or "").strip() != name or not org.get("id"):
                continue
            creator_type = org.get("created_by_type") or SUPER_ADMIN_TENANT_TYPE
            creator_id = str(org.get("created_by_id") or "")
            if owner_tenant_type == SUPER_ADMIN_TENANT_TYPE and creator_type == SUPER_ADMIN_TENANT_TYPE:
                return str(org["id"])
            if (
                owner_tenant_type == USER_TENANT_TYPE
                and creator_type == USER_TENANT_TYPE
                and creator_id == str(owner_tenant_id)
            ):
                return str(org["id"])

        return resolve_org_id(name, global_orgs)

    @staticmethod
    def _owner_ctx_from_share(share: dict[str, Any]) -> dict[str, Any]:
        owner_ctx = {
            "type": share.get("owner_tenant_type"),
            "id": share.get("owner_tenant_id"),
            "scope_mode": "org_multi"
            if share.get("owner_tenant_type") == SUPER_ADMIN_TENANT_TYPE
            else "user_single",
        }
        if owner_ctx["scope_mode"] == "user_single":
            owner_ctx["scope_root"] = owner_tenant_scope_root(owner_ctx["type"], owner_ctx["id"])
        return owner_ctx

    def _find_share(self, owner_ctx: dict[str, Any], board_id: str, grantee_user_id: str) -> dict[str, Any] | None:
        for share in self.storage.list_shares():
            if (
                str(share.get("board_id")) == str(board_id)
                and str(share.get("grantee_user_id")) == str(grantee_user_id)
                and share.get("owner_tenant_type") == owner_ctx.get("type")
                and str(share.get("owner_tenant_id")) == str(owner_ctx.get("id"))
            ):
                return share
        return None

    def _find_received_share(
        self,
        grantee_user_id: str | None,
        board_id: str,
        owner_hint: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not grantee_user_id:
            return None
        for share in self.storage.list_shares_for_grantee(grantee_user_id):
            if str(share.get("board_id")) != str(board_id):
                continue
            if owner_hint:
                if str(share.get("owner_tenant_id")) != str(owner_hint.get("owner_tenant_id")):
                    continue
                if share.get("owner_tenant_type") != owner_hint.get("owner_tenant_type"):
                    continue
            return share
        return None

    @staticmethod
    def _normalize_permissions(permissions: dict[str, Any]) -> dict[str, bool]:
        return {
            "view": bool(permissions.get("view", True)),
            "edit": bool(permissions.get("edit", False)),
        }
