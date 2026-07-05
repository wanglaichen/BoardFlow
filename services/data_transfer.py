"""BoardFlow 数据包导入导出：.dat 文件格式、校验与合并逻辑。"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from services.org_keys import PERSONAL_BOARD_ORG_NAME, PERSONAL_ORG_ID, resolve_org_id
from services.storage import DEFAULT_DATA

PACKAGE_FORMAT = "boardflow-package"
PACKAGE_VERSION = 2
PACKAGE_VERSION_LEGACY = 1
PACKAGE_MAGIC = "BFLOW1"

CARD_DETAIL_KEYS = ("comments", "checklist", "canvas_data", "mindmap_data", "table_data", "description_data")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_checksum(payload: Any) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _slug_filename(value: str, fallback: str = "export") -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", (value or "").strip()).strip("-")
    return slug[:48] or fallback


def build_package(
    kind: str,
    payload: dict[str, Any],
    meta: dict[str, Any] | None = None,
    *,
    version: int = PACKAGE_VERSION,
) -> dict[str, Any]:
    checksum = _build_checksum(payload)
    return {
        "magic": PACKAGE_MAGIC,
        "format": PACKAGE_FORMAT,
        "version": version,
        "kind": kind,
        "exported_at": _now_iso(),
        "checksum": checksum,
        "meta": meta or {},
        "payload": payload,
    }


def _is_v2_system_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload, dict) and (
        "super_admin_tenant" in payload or "users" in payload or "shares" in payload
    )


def _validate_tenant_bundle(
    boards: list[dict[str, Any]],
    lists: list[dict[str, Any]],
    cards: list[dict[str, Any]],
    *,
    prefix: str = "",
) -> tuple[list[str], list[str]]:
    return _validate_refs(boards, lists, cards, prefix=prefix)


def serialize_package(package: dict[str, Any]) -> bytes:
    body = json.dumps(package, ensure_ascii=False, indent=2)
    return f"{PACKAGE_MAGIC}\n{body}\n".encode("utf-8")


def parse_package(raw: bytes | str) -> dict[str, Any]:
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    text = text.strip()
    if not text:
        raise ValueError("文件为空")

    if text.startswith(f"{PACKAGE_MAGIC}\n"):
        text = text[len(PACKAGE_MAGIC) + 1 :].strip()
    elif text.startswith(PACKAGE_MAGIC):
        text = text[len(PACKAGE_MAGIC) :].strip()

    try:
        package = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"无法解析 .dat 文件：{error}") from error

    if not isinstance(package, dict):
        raise ValueError("数据包格式无效：根节点必须是对象")
    return package


def _validate_refs(
    boards: list[dict[str, Any]],
    lists: list[dict[str, Any]],
    cards: list[dict[str, Any]],
    *,
    prefix: str = "",
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    board_ids = {str(item.get("id")) for item in boards if item.get("id") is not None}
    list_ids = {str(item.get("id")) for item in lists if item.get("id") is not None}
    list_board_map = {str(item.get("id")): str(item.get("board_id")) for item in lists if item.get("id") is not None}

    for board in boards:
        if not (board.get("title") or "").strip():
            errors.append(f"{prefix}看板缺少标题（id={board.get('id')}）")

    for lst in lists:
        list_id = str(lst.get("id") or "")
        board_id = str(lst.get("board_id") or "")
        if not list_id:
            errors.append(f"{prefix}列表缺少 id")
            continue
        if not board_id:
            errors.append(f"{prefix}列表 {list_id} 缺少 board_id")
        elif board_id not in board_ids:
            errors.append(f"{prefix}列表 {list_id} 引用了不存在的看板 {board_id}")

    for card in cards:
        card_id = str(card.get("id") or "")
        list_id = str(card.get("list_id") or "")
        board_id = str(card.get("board_id") or "")
        if not card_id:
            errors.append(f"{prefix}卡片缺少 id")
            continue
        if not (card.get("title") or "").strip():
            warnings.append(f"{prefix}卡片 {card_id} 标题为空")
        if not list_id:
            errors.append(f"{prefix}卡片 {card_id} 缺少 list_id")
        elif list_id not in list_ids:
            errors.append(f"{prefix}卡片 {card_id} 引用了不存在的列表 {list_id}")
        elif board_id and list_board_map.get(list_id) and board_id != list_board_map[list_id]:
            errors.append(f"{prefix}卡片 {card_id} 的 board_id 与列表不一致")
        elif not board_id:
            warnings.append(f"{prefix}卡片 {card_id} 缺少 board_id，导入时将自动补齐")

    return errors, warnings


def validate_package(package: dict[str, Any], *, expected_kind: str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {}

    if package.get("magic") not in (PACKAGE_MAGIC, None):
        errors.append("文件魔数不匹配，可能不是 BoardFlow 数据包")
    if package.get("format") != PACKAGE_FORMAT:
        errors.append(f"不支持的 format：{package.get('format')}")
    version = package.get("version")
    if version not in (PACKAGE_VERSION, PACKAGE_VERSION_LEGACY):
        errors.append(f"不支持的数据包版本：{version}")
    kind = package.get("kind")
    if kind not in ("system", "organization", "board"):
        errors.append(f"未知的数据包类型 kind：{kind}")
    if expected_kind and kind != expected_kind:
        errors.append(f"数据包类型应为 {expected_kind}，实际为 {kind}")

    payload = package.get("payload")
    if not isinstance(payload, dict):
        errors.append("payload 必须是对象")
        return _validation_result(False, kind, errors, warnings, summary, package)

    checksum = package.get("checksum") or ""
    expected = _build_checksum(payload)
    if checksum != expected:
        errors.append("校验和失败，文件可能已损坏或被篡改")

    if kind == "system":
        if _is_v2_system_payload(payload):
            settings = payload.get("settings")
            super_tenant = payload.get("super_admin_tenant") or {}
            users = payload.get("users") if isinstance(payload.get("users"), list) else None
            shares = payload.get("shares") if isinstance(payload.get("shares"), list) else None
            if not isinstance(settings, dict):
                errors.append("系统包缺少 settings 对象")
            if not isinstance(super_tenant, dict):
                errors.append("系统包缺少 super_admin_tenant 对象")
            if users is None:
                errors.append("系统包缺少 users 数组")
                users = []
            if shares is None:
                errors.append("系统包缺少 shares 数组")
                shares = []
            super_boards = super_tenant.get("boards") if isinstance(super_tenant.get("boards"), list) else []
            super_lists = super_tenant.get("lists") if isinstance(super_tenant.get("lists"), list) else []
            super_cards = super_tenant.get("cards") if isinstance(super_tenant.get("cards"), list) else []
            ref_errors, ref_warnings = _validate_tenant_bundle(super_boards, super_lists, super_cards, prefix="[超管] ")
            errors.extend(ref_errors)
            warnings.extend(ref_warnings)
            user_board_total = 0
            for index, entry in enumerate(users):
                if not isinstance(entry, dict):
                    errors.append(f"users[{index}] 必须是对象")
                    continue
                profile = entry.get("profile")
                tenant = entry.get("tenant")
                if not isinstance(profile, dict):
                    errors.append(f"users[{index}] 缺少 profile")
                elif not profile.get("id"):
                    errors.append(f"users[{index}] 缺少用户 id")
                if not isinstance(tenant, dict):
                    errors.append(f"users[{index}] 缺少 tenant")
                    continue
                boards = tenant.get("boards") if isinstance(tenant.get("boards"), list) else []
                lists = tenant.get("lists") if isinstance(tenant.get("lists"), list) else []
                cards = tenant.get("cards") if isinstance(tenant.get("cards"), list) else []
                user_board_total += len(boards)
                label = (profile or {}).get("username") or (profile or {}).get("id") or str(index)
                u_errors, u_warnings = _validate_tenant_bundle(
                    boards, lists, cards, prefix=f"[用户:{label}] "
                )
                errors.extend(u_errors)
                warnings.extend(u_warnings)
            summary = {
                "boards": len(super_boards) + user_board_total,
                "lists": len(super_lists) + sum(
                    len((entry.get("tenant") or {}).get("lists") or [])
                    for entry in users
                    if isinstance(entry, dict)
                ),
                "cards": len(super_cards) + sum(
                    len((entry.get("tenant") or {}).get("cards") or [])
                    for entry in users
                    if isinstance(entry, dict)
                ),
                "organizations": len((settings or {}).get("organizations") or []) if isinstance(settings, dict) else 0,
                "users": len(users),
                "shares": len(shares),
                "card_types": len((settings or {}).get("card_types") or []) if isinstance(settings, dict) else 0,
                "board_statuses": len((settings or {}).get("board_statuses") or []) if isinstance(settings, dict) else 0,
            }
        else:
            boards = payload.get("boards") if isinstance(payload.get("boards"), list) else None
            lists = payload.get("lists") if isinstance(payload.get("lists"), list) else None
            cards = payload.get("cards") if isinstance(payload.get("cards"), list) else None
            settings = payload.get("settings")
            if boards is None:
                errors.append("系统包缺少 boards 数组")
                boards = []
            if lists is None:
                errors.append("系统包缺少 lists 数组")
                lists = []
            if cards is None:
                errors.append("系统包缺少 cards 数组")
                cards = []
            if not isinstance(settings, dict):
                errors.append("系统包缺少 settings 对象")
            ref_errors, ref_warnings = _validate_refs(boards, lists, cards)
            errors.extend(ref_errors)
            warnings.extend(ref_warnings)
            warnings.append("检测到旧版系统包（仅含超管扁平数据），导入时将只恢复超管看板")
            summary = {
                "boards": len(boards),
                "lists": len(lists),
                "cards": len(cards),
                "organizations": len((settings or {}).get("organizations") or []) if isinstance(settings, dict) else 0,
                "card_types": len((settings or {}).get("card_types") or []) if isinstance(settings, dict) else 0,
                "board_statuses": len((settings or {}).get("board_statuses") or []) if isinstance(settings, dict) else 0,
                "legacy": True,
            }

    elif kind == "organization":
        organization = payload.get("organization")
        boards = payload.get("boards") if isinstance(payload.get("boards"), list) else None
        lists = payload.get("lists") if isinstance(payload.get("lists"), list) else None
        cards = payload.get("cards") if isinstance(payload.get("cards"), list) else None
        if not isinstance(organization, dict):
            errors.append("组织包缺少 organization 对象")
        elif not (organization.get("name") or "").strip():
            errors.append("组织包缺少组织名称")
        if boards is None:
            errors.append("组织包缺少 boards 数组")
            boards = []
        if lists is None:
            errors.append("组织包缺少 lists 数组")
            lists = []
        if cards is None:
            errors.append("组织包缺少 cards 数组")
            cards = []
        ref_errors, ref_warnings = _validate_refs(boards, lists, cards)
        errors.extend(ref_errors)
        warnings.extend(ref_warnings)
        board_owners = payload.get("board_owners") if isinstance(payload.get("board_owners"), dict) else {}
        summary = {
            "organization": (organization or {}).get("name") if isinstance(organization, dict) else "",
            "boards": len(boards),
            "lists": len(lists),
            "cards": len(cards),
            "tenants": len({(v.get("type"), v.get("id")) for v in board_owners.values() if isinstance(v, dict)})
            if board_owners
            else 1,
        }
        if board_owners:
            summary["board_owners"] = len(board_owners)

    elif kind == "board":
        board = payload.get("board")
        lists = payload.get("lists") if isinstance(payload.get("lists"), list) else None
        cards = payload.get("cards") if isinstance(payload.get("cards"), list) else None
        if not isinstance(board, dict):
            errors.append("看板包缺少 board 对象")
        elif not (board.get("title") or "").strip():
            errors.append("看板包缺少看板标题")
        if lists is None:
            errors.append("看板包缺少 lists 数组")
            lists = []
        if cards is None:
            errors.append("看板包缺少 cards 数组")
            cards = []
        boards = [board] if isinstance(board, dict) else []
        ref_errors, ref_warnings = _validate_refs(boards, lists, cards)
        errors.extend(ref_errors)
        warnings.extend(ref_warnings)
        summary = {
            "board_title": (board or {}).get("title") if isinstance(board, dict) else "",
            "lists": len(lists),
            "cards": len(cards),
        }

    meta = package.get("meta") if isinstance(package.get("meta"), dict) else {}
    summary["exported_at"] = package.get("exported_at")
    summary["label"] = meta.get("label") or kind

    return _validation_result(not errors, kind, errors, warnings, summary, package)


def _validation_result(
    valid: bool,
    kind: str | None,
    errors: list[str],
    warnings: list[str],
    summary: dict[str, Any],
    package: dict[str, Any],
) -> dict[str, Any]:
    return {
        "valid": valid,
        "kind": kind,
        "errors": errors,
        "warnings": warnings,
        "summary": summary,
        "checksum": package.get("checksum"),
        "exported_at": package.get("exported_at"),
    }


def export_system(storage) -> tuple[bytes, str]:
    payload = storage.export_full_snapshot()
    package = build_package(
        "system",
        payload,
        {
            "label": "BoardFlow 全系统备份",
            "scope": "system",
            "includes_settings": True,
            "includes_users": True,
            "includes_shares": True,
            "settings_keys": ["card_types", "board_statuses", "organizations", "editable_fonts"],
        },
        version=PACKAGE_VERSION,
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return serialize_package(package), f"boardflow-system-{stamp}.dat"


def import_system_snapshot(storage, package: dict[str, Any], *, share_service=None) -> None:
    payload = package.get("payload") or {}
    if not _is_v2_system_payload(payload):
        raise ValueError("不是新版全量系统包")
    storage.import_full_snapshot(payload)
    if share_service:
        for user in storage.list_users():
            user_id = str(user.get("id") or "")
            if user_id:
                share_service.sync_grantee_share_index(user_id)


def import_organization_snapshot(
    storage,
    package: dict[str, Any],
    *,
    mode: str = "merge",
    share_service=None,
    owner_type: str | None = None,
    owner_id: str | None = None,
) -> None:
    payload = package.get("payload") or {}
    organization = copy.deepcopy(payload.get("organization") or {})
    boards = copy.deepcopy(payload.get("boards") or [])
    lists = copy.deepcopy(payload.get("lists") or [])
    cards = copy.deepcopy(payload.get("cards") or [])
    board_owners = copy.deepcopy(payload.get("board_owners") or {})
    org_id = str(organization.get("id") or "")
    org_name = (organization.get("name") or "").strip()

    settings = copy.deepcopy(storage.read_settings())
    orgs = settings.setdefault("organizations", [])
    if org_name and org_name != PERSONAL_BOARD_ORG_NAME:
        existing = next(
            (item for item in orgs if str(item.get("id")) == org_id or (item.get("name") or "").strip() == org_name),
            None,
        )
        if existing:
            existing.update({key: value for key, value in organization.items() if key != "id"})
        else:
            orgs.append(organization)
    storage.write_settings(settings)

    from services.tenant_keys import SUPER_ADMIN_TENANT_TYPE, user_scope_root

    if owner_type and owner_id:
        for board_id, owner in board_owners.items():
            if not isinstance(owner, dict):
                continue
            if str(owner.get("type")) != str(owner_type) or str(owner.get("id")) != str(owner_id):
                raise PermissionError(f"无权导入看板 {board_id}：归属不匹配")

    grouped: dict[tuple[str, str], set[str]] = {}
    for board in boards:
        board_id = str(board.get("id") or "")
        if not board_id:
            continue
        owner = board_owners.get(board_id) or {"type": SUPER_ADMIN_TENANT_TYPE, "id": "super_admin"}
        key = (str(owner.get("type") or SUPER_ADMIN_TENANT_TYPE), str(owner.get("id") or "super_admin"))
        grouped.setdefault(key, set()).add(board_id)

    if not grouped:
        default_owner = (owner_type, owner_id) if owner_type and owner_id else (SUPER_ADMIN_TENANT_TYPE, "super_admin")
        grouped[default_owner] = {str(board.get("id")) for board in boards if board.get("id")}

    for (tenant_type, tenant_id), board_ids in grouped.items():
        if tenant_type == SUPER_ADMIN_TENANT_TYPE:
            tenant_ctx = {"type": SUPER_ADMIN_TENANT_TYPE, "id": "super_admin", "scope_mode": "org_multi"}
        else:
            tenant_ctx = {
                "type": "user",
                "id": tenant_id,
                "scope_mode": "user_single",
                "scope_root": user_scope_root(tenant_id),
            }

        tenant_data = copy.deepcopy(storage.read_tenant(tenant_ctx, settings))
        tenant_data["settings"] = settings
        subset_boards = [item for item in boards if str(item.get("id")) in board_ids]
        subset_lists = [item for item in lists if str(item.get("board_id")) in board_ids]
        subset_cards = [item for item in cards if str(item.get("board_id")) in board_ids]

        if mode == "replace":
            remove_ids = _collect_org_board_ids(tenant_data, org_id, org_name)
            tenant_data["boards"] = [
                item for item in tenant_data.get("boards") or [] if str(item.get("id")) not in remove_ids
            ]
            tenant_data["lists"] = [
                item for item in tenant_data.get("lists") or [] if str(item.get("board_id")) not in remove_ids
            ]
            tenant_data["cards"] = [
                item for item in tenant_data.get("cards") or [] if str(item.get("board_id")) not in remove_ids
            ]
            subset_boards, subset_lists, subset_cards = _remap_entities(
                subset_boards, subset_lists, subset_cards, tenant_data
            )
        else:
            subset_boards, subset_lists, subset_cards = _remap_entities(
                subset_boards, subset_lists, subset_cards, tenant_data
            )

        tenant_data.setdefault("boards", []).extend(subset_boards)
        tenant_data.setdefault("lists", []).extend(subset_lists)
        tenant_data.setdefault("cards", []).extend(subset_cards)
        storage.write_tenant(
            tenant_ctx,
            {
                "boards": tenant_data.get("boards") or [],
                "lists": tenant_data.get("lists") or [],
                "cards": tenant_data.get("cards") or [],
                "meta": tenant_data.get("meta") or {},
            },
            settings,
        )

    if share_service:
        for user in storage.list_users():
            user_id = str(user.get("id") or "")
            if user_id:
                share_service.sync_grantee_share_index(user_id)


def _collect_org_board_ids(data: dict[str, Any], org_id: str, org_name: str) -> set[str]:
    settings = data.get("settings") or {}
    organizations = settings.get("organizations") or []
    board_ids: set[str] = set()
    for board in data.get("boards") or []:
        if board.get("id") is None:
            continue
        resolved = resolve_org_id(board.get("organization"), organizations)
        board_org_name = (board.get("organization") or "").strip()
        if resolved == org_id or (org_name and board_org_name == org_name):
            board_ids.add(str(board["id"]))
    return board_ids


def export_organization(
    storage,
    org_id: str,
    *,
    owner_type: str | None = None,
    owner_id: str | None = None,
) -> tuple[bytes, str]:
    if hasattr(storage, "export_organization_bundle"):
        bundle = storage.export_organization_bundle(
            org_id,
            owner_type=owner_type,
            owner_id=owner_id,
        )
        organization = bundle.get("organization") or {}
        boards = bundle.get("boards") or []
        lists = bundle.get("lists") or []
        cards = bundle.get("cards") or []
        board_owners = bundle.get("board_owners") or {}
    else:
        organization = None
        boards = lists = cards = []
        board_owners = {}
        raise ValueError("存储后端不支持组织导出")

    org_name = (organization or {}).get("name") or ""
    payload = {
        "organization": copy.deepcopy(organization or {"id": org_id, "name": org_name or org_id, "note": ""}),
        "boards": copy.deepcopy(boards),
        "lists": copy.deepcopy(lists),
        "cards": copy.deepcopy(cards),
        "board_owners": copy.deepcopy(board_owners),
    }
    package = build_package(
        "organization",
        payload,
        {
            "label": f"组织导出：{org_name or org_id}",
            "organization_id": org_id,
            "organization_name": org_name,
            "includes_board_owners": bool(board_owners),
        },
        version=PACKAGE_VERSION,
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"boardflow-org-{_slug_filename(org_name, org_id)}-{stamp}.dat"
    return serialize_package(package), filename


def _export_organization_legacy(data: dict[str, Any], org_id: str) -> tuple[bytes, str]:
    settings = data.get("settings") or {}
    organizations = settings.get("organizations") or []
    organization = next((item for item in organizations if str(item.get("id")) == org_id), None)
    org_name = (organization or {}).get("name") or ""
    if not organization and org_id == PERSONAL_ORG_ID:
        organization = {"id": PERSONAL_ORG_ID, "name": PERSONAL_BOARD_ORG_NAME, "note": "内置个人看板组织"}
        org_name = PERSONAL_BOARD_ORG_NAME

    board_ids = _collect_org_board_ids(data, org_id, org_name)
    boards = [copy.deepcopy(item) for item in data.get("boards") or [] if str(item.get("id")) in board_ids]
    lists = [copy.deepcopy(item) for item in data.get("lists") or [] if str(item.get("board_id")) in board_ids]
    cards = [copy.deepcopy(item) for item in data.get("cards") or [] if str(item.get("board_id")) in board_ids]

    payload = {
        "organization": copy.deepcopy(organization or {"id": org_id, "name": org_name or org_id, "note": ""}),
        "boards": boards,
        "lists": lists,
        "cards": cards,
    }
    package = build_package(
        "organization",
        payload,
        {
            "label": f"组织导出：{org_name or org_id}",
            "organization_id": org_id,
            "organization_name": org_name,
        },
        version=PACKAGE_VERSION_LEGACY,
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"boardflow-org-{_slug_filename(org_name, org_id)}-{stamp}.dat"
    return serialize_package(package), filename


def export_board(data: dict[str, Any], board_id: str) -> tuple[bytes, str]:
    board = next((item for item in data.get("boards") or [] if str(item.get("id")) == board_id), None)
    if not board:
        raise ValueError("看板不存在")

    lists = [copy.deepcopy(item) for item in data.get("lists") or [] if str(item.get("board_id")) == board_id]
    list_ids = {str(item.get("id")) for item in lists}
    cards = [
        copy.deepcopy(item)
        for item in data.get("cards") or []
        if str(item.get("board_id")) == board_id or str(item.get("list_id")) in list_ids
    ]

    payload = {
        "board": copy.deepcopy(board),
        "lists": lists,
        "cards": cards,
    }
    title = (board.get("title") or board_id).strip()
    package = build_package(
        "board",
        payload,
        {"label": f"看板导出：{title}", "board_id": board_id, "board_title": title},
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"boardflow-board-{_slug_filename(title, board_id)}-{stamp}.dat"
    return serialize_package(package), filename


def _next_ids(data: dict[str, Any]) -> dict[str, int]:
    meta = data.setdefault("meta", {})
    return {
        "board": int(meta.get("next_board_id", 1)),
        "list": int(meta.get("next_list_id", 1)),
        "card": int(meta.get("next_card_id", 1)),
    }


def _bump_meta(data: dict[str, Any], counters: dict[str, int]) -> None:
    meta = data.setdefault("meta", {})
    meta["next_board_id"] = counters["board"]
    meta["next_list_id"] = counters["list"]
    meta["next_card_id"] = counters["card"]


def _allocate_id(existing: set[str], counters: dict[str, int], key: str, original: str) -> str:
    if original and original not in existing:
        existing.add(original)
        numeric = int(original) if str(original).isdigit() else None
        if numeric is not None and numeric >= counters[key]:
            counters[key] = numeric + 1
        return original
    while True:
        candidate = str(counters[key])
        counters[key] += 1
        if candidate not in existing:
            existing.add(candidate)
            return candidate


def _remap_entities(
    boards: list[dict[str, Any]],
    lists: list[dict[str, Any]],
    cards: list[dict[str, Any]],
    data: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    counters = _next_ids(data)
    existing_boards = {str(item.get("id")) for item in data.get("boards") or [] if item.get("id") is not None}
    existing_lists = {str(item.get("id")) for item in data.get("lists") or [] if item.get("id") is not None}
    existing_cards = {str(item.get("id")) for item in data.get("cards") or [] if item.get("id") is not None}

    board_map: dict[str, str] = {}
    list_map: dict[str, str] = {}

    remapped_boards: list[dict[str, Any]] = []
    for board in boards:
        old_id = str(board.get("id"))
        new_id = _allocate_id(existing_boards, counters, "board", old_id)
        board_map[old_id] = new_id
        remapped = copy.deepcopy(board)
        remapped["id"] = new_id
        remapped_boards.append(remapped)

    remapped_lists: list[dict[str, Any]] = []
    for lst in lists:
        old_id = str(lst.get("id"))
        old_board_id = str(lst.get("board_id"))
        new_id = _allocate_id(existing_lists, counters, "list", old_id)
        new_board_id = board_map.get(old_board_id, old_board_id)
        list_map[old_id] = new_id
        remapped = copy.deepcopy(lst)
        remapped["id"] = new_id
        remapped["board_id"] = new_board_id
        remapped_lists.append(remapped)

    remapped_cards: list[dict[str, Any]] = []
    for card in cards:
        old_id = str(card.get("id"))
        old_list_id = str(card.get("list_id"))
        old_board_id = str(card.get("board_id") or "")
        new_id = _allocate_id(existing_cards, counters, "card", old_id)
        new_list_id = list_map.get(old_list_id, old_list_id)
        new_board_id = board_map.get(old_board_id, old_board_id)
        if not new_board_id:
            new_board_id = next(
                (str(item.get("board_id")) for item in remapped_lists if str(item.get("id")) == new_list_id),
                old_board_id,
            )
        remapped = copy.deepcopy(card)
        remapped["id"] = new_id
        remapped["list_id"] = new_list_id
        remapped["board_id"] = new_board_id
        remapped_cards.append(remapped)

    _bump_meta(data, counters)
    return remapped_boards, remapped_lists, remapped_cards


def apply_import(data: dict[str, Any], package: dict[str, Any], *, mode: str = "merge") -> dict[str, Any]:
    validation = validate_package(package)
    if not validation["valid"]:
        raise ValueError("数据包校验未通过，无法导入")

    kind = package["kind"]
    payload = package["payload"]
    result = copy.deepcopy(data)

    if kind == "system":
        if mode != "replace":
            raise ValueError("系统导入仅支持 replace 模式（全量覆盖）")
        if _is_v2_system_payload(payload):
            raise ValueError("新版系统包请使用 import_system_snapshot 导入")
        normalized = {
            "boards": copy.deepcopy(payload.get("boards") or []),
            "lists": copy.deepcopy(payload.get("lists") or []),
            "cards": copy.deepcopy(payload.get("cards") or []),
            "meta": copy.deepcopy(payload.get("meta") or {}),
            "settings": copy.deepcopy(payload.get("settings") or DEFAULT_DATA["settings"]),
        }
        return normalized

    if kind == "organization":
        if payload.get("board_owners"):
            raise ValueError("新版组织包请使用 import_organization_snapshot 导入")
        organization = copy.deepcopy(payload.get("organization") or {})
        org_name = (organization.get("name") or "").strip()
        org_id = str(organization.get("id") or "")
        boards = copy.deepcopy(payload.get("boards") or [])
        lists = copy.deepcopy(payload.get("lists") or [])
        cards = copy.deepcopy(payload.get("cards") or [])

        settings = result.setdefault("settings", copy.deepcopy(DEFAULT_DATA["settings"]))
        orgs = settings.setdefault("organizations", [])
        if org_name and org_name != PERSONAL_BOARD_ORG_NAME:
            existing = next(
                (item for item in orgs if str(item.get("id")) == org_id or (item.get("name") or "").strip() == org_name),
                None,
            )
            if existing:
                existing.update({key: value for key, value in organization.items() if key != "id"})
            else:
                orgs.append(organization)

        if mode == "replace":
            remove_ids = _collect_org_board_ids(result, org_id, org_name)
            result["boards"] = [item for item in result.get("boards") or [] if str(item.get("id")) not in remove_ids]
            result["lists"] = [item for item in result.get("lists") or [] if str(item.get("board_id")) not in remove_ids]
            result["cards"] = [item for item in result.get("cards") or [] if str(item.get("board_id")) not in remove_ids]
            boards, lists, cards = _remap_entities(boards, lists, cards, result)
        else:
            boards, lists, cards = _remap_entities(boards, lists, cards, result)

        result.setdefault("boards", []).extend(boards)
        result.setdefault("lists", []).extend(lists)
        result.setdefault("cards", []).extend(cards)
        return result

    if kind == "board":
        board = copy.deepcopy(payload.get("board") or {})
        lists = copy.deepcopy(payload.get("lists") or [])
        cards = copy.deepcopy(payload.get("cards") or [])
        board_id = str(board.get("id") or "")

        if mode == "replace" and board_id:
            result["boards"] = [item for item in result.get("boards") or [] if str(item.get("id")) != board_id]
            result["lists"] = [item for item in result.get("lists") or [] if str(item.get("board_id")) != board_id]
            result["cards"] = [item for item in result.get("cards") or [] if str(item.get("board_id")) != board_id]

        boards, lists, cards = _remap_entities([board], lists, cards, result)
        result.setdefault("boards", []).extend(boards)
        result.setdefault("lists", []).extend(lists)
        result.setdefault("cards", []).extend(cards)
        return result

    raise ValueError(f"不支持的数据包类型：{kind}")
