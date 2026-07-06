"""BoardFlow 联邦只读 API：供跨实例看板对比拉取数据。"""

from __future__ import annotations

import re
import secrets
from typing import Any

from services.tenant_keys import (
    SUPER_ADMIN_ID,
    SUPER_ADMIN_TENANT_TYPE,
    USER_TENANT_TYPE,
    user_scope_root,
)

FEDERATION_API_VERSION = 1
DEFAULT_ACCOUNTS_PAGE_SIZE = 20
DEFAULT_BOARDS_PAGE_SIZE = 20
DEFAULT_CARDS_PAGE_SIZE = 50


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def is_federation_enabled(config: dict[str, Any]) -> bool:
    return _truthy(config.get("FEDERATION_COMPARE_ENABLED"))


def get_federation_token(config: dict[str, Any]) -> str:
    return (config.get("FEDERATION_COMPARE_TOKEN") or "").strip()


def verify_federation_token(config: dict[str, Any], token: str | None) -> bool:
    expected = get_federation_token(config)
    if not expected:
        return False
    provided = (token or "").strip()
    if not provided:
        return False
    return secrets.compare_digest(provided, expected)


def build_health_payload(*, version: str, enabled: bool) -> dict[str, Any]:
    from config import format_app_version_label

    return {
        "ok": True,
        "name": "BoardFlow",
        "version": version,
        "label": format_app_version_label(version),
        "federation": {
            "enabled": enabled,
            "api_version": FEDERATION_API_VERSION,
            "sync_enabled": enabled,
        },
    }


def account_cursor_key(tenant_type: str, tenant_id: str) -> str:
    return f"{tenant_type}:{tenant_id}"


def build_tenant_context_for_federation(tenant_type: str, tenant_id: str) -> dict[str, Any]:
    normalized_type = (tenant_type or "").strip()
    normalized_id = (tenant_id or "").strip()
    if normalized_type == SUPER_ADMIN_TENANT_TYPE:
        if normalized_id != SUPER_ADMIN_ID:
            raise ValueError("超级管理员账号标识无效")
        return {
            "type": SUPER_ADMIN_TENANT_TYPE,
            "id": SUPER_ADMIN_ID,
            "scope_mode": "org_multi",
        }
    if normalized_type == USER_TENANT_TYPE:
        if not normalized_id:
            raise ValueError("用户账号标识无效")
        return {
            "type": USER_TENANT_TYPE,
            "id": normalized_id,
            "scope_mode": "user_single",
            "scope_root": user_scope_root(normalized_id),
        }
    raise ValueError("不支持的账号类型")


def build_federation_account_catalog(storage) -> list[dict[str, Any]]:
    settings = storage.read_settings()
    accounts: list[dict[str, Any]] = []

    super_ctx = build_tenant_context_for_federation(SUPER_ADMIN_TENANT_TYPE, SUPER_ADMIN_ID)
    super_data = storage.read_tenant(super_ctx, settings)
    accounts.append(
        {
            "tenant_type": SUPER_ADMIN_TENANT_TYPE,
            "tenant_id": SUPER_ADMIN_ID,
            "display_name": "超级管理员",
            "board_count": len(super_data.get("boards") or []),
        }
    )

    users = sorted(storage.list_users(), key=lambda item: str(item.get("id") or ""))
    for user in users:
        user_id = str(user.get("id") or "")
        if not user_id:
            continue
        user_ctx = build_tenant_context_for_federation(USER_TENANT_TYPE, user_id)
        user_data = storage.read_tenant(user_ctx, settings)
        accounts.append(
            {
                "tenant_type": USER_TENANT_TYPE,
                "tenant_id": user_id,
                "display_name": (user.get("display_name") or user.get("username") or user_id),
                "board_count": len(user_data.get("boards") or []),
            }
        )
    return accounts


def paginate_federation_accounts(
    storage,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_ACCOUNTS_PAGE_SIZE,
) -> dict[str, Any]:
    catalog = build_federation_account_catalog(storage)
    safe_limit = max(1, min(int(limit or DEFAULT_ACCOUNTS_PAGE_SIZE), 100))
    start = 0
    normalized_cursor = (cursor or "").strip()
    if normalized_cursor:
        for index, account in enumerate(catalog):
            key = account_cursor_key(account["tenant_type"], account["tenant_id"])
            if key == normalized_cursor:
                start = index + 1
                break

    items = catalog[start : start + safe_limit]
    done = start + len(items) >= len(catalog)
    next_cursor = None
    if items and not done:
        last = items[-1]
        next_cursor = account_cursor_key(last["tenant_type"], last["tenant_id"])
    return {"items": items, "next_cursor": next_cursor, "done": done}


def _status_label(settings: dict[str, Any], status_id: str | None) -> str:
    normalized = (status_id or "unset").strip() or "unset"
    for item in settings.get("board_statuses") or []:
        if str(item.get("id")) == normalized:
            return str(item.get("label") or normalized)
    return "未设状态" if normalized == "unset" else normalized


def _normalize_status_id(board: dict[str, Any]) -> str:
    raw = board.get("status_id") or board.get("status") or "unset"
    return str(raw or "unset").strip() or "unset"


def build_federation_board_summaries(storage, tenant_type: str, tenant_id: str) -> list[dict[str, Any]]:
    settings = storage.read_settings()
    tenant_ctx = build_tenant_context_for_federation(tenant_type, tenant_id)
    tenant_data = storage.read_tenant(tenant_ctx, settings)
    boards = tenant_data.get("boards") or []
    lists = tenant_data.get("lists") or []
    cards = tenant_data.get("cards") or []

    summaries: list[dict[str, Any]] = []
    for board in boards:
        if board.get("id") is None:
            continue
        board_id = str(board["id"])
        board_lists = [item for item in lists if str(item.get("board_id")) == board_id]
        board_cards = [item for item in cards if str(item.get("board_id")) == board_id]
        status_id = _normalize_status_id(board)
        summaries.append(
            {
                "id": board_id,
                "title": board.get("title") or "",
                "organization": (board.get("organization") or "").strip(),
                "status_id": status_id,
                "status": _status_label(settings, status_id),
                "list_count": len(board_lists),
                "card_count": len(board_cards),
                "updated_at": board.get("updated_at") or "",
            }
        )
    return sorted(summaries, key=lambda item: item.get("updated_at", ""), reverse=True)


def paginate_federation_boards(
    storage,
    tenant_type: str,
    tenant_id: str,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_BOARDS_PAGE_SIZE,
) -> dict[str, Any]:
    catalog = build_federation_board_summaries(storage, tenant_type, tenant_id)
    safe_limit = max(1, min(int(limit or DEFAULT_BOARDS_PAGE_SIZE), 100))
    start = 0
    normalized_cursor = (cursor or "").strip()
    if normalized_cursor:
        for index, board in enumerate(catalog):
            if str(board.get("id")) == normalized_cursor:
                start = index + 1
                break

    items = catalog[start : start + safe_limit]
    done = start + len(items) >= len(catalog)
    next_cursor = None
    if items and not done:
        next_cursor = str(items[-1]["id"])
    return {
        "tenant_type": tenant_type,
        "tenant_id": tenant_id,
        "items": items,
        "next_cursor": next_cursor,
        "done": done,
    }


def _find_board_or_raise(tenant_data: dict[str, Any], board_id: str) -> dict[str, Any]:
    for board in tenant_data.get("boards") or []:
        if str(board.get("id")) == str(board_id):
            return board
    raise ValueError(f"看板不存在：{board_id}")


def _board_lists(tenant_data: dict[str, Any], board_id: str) -> list[dict[str, Any]]:
    return sorted(
        [item for item in tenant_data.get("lists") or [] if str(item.get("board_id")) == str(board_id)],
        key=lambda item: item.get("position", 0),
    )


def _board_cards(tenant_data: dict[str, Any], board_id: str) -> list[dict[str, Any]]:
    return [item for item in tenant_data.get("cards") or [] if str(item.get("board_id")) == str(board_id)]


def _plain_text(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _card_summary(card: dict[str, Any], *, include_description: bool = False) -> dict[str, Any]:
    checklist = card.get("checklist") or []
    if isinstance(checklist, list):
        checklist_total = len(checklist)
        checklist_done = sum(1 for item in checklist if isinstance(item, dict) and item.get("done"))
    else:
        checklist_total = int(card.get("checklist_total") or 0)
        checklist_done = int(card.get("checklist_done") or 0)
    comments = card.get("comments") or []
    comment_count = len(comments) if isinstance(comments, list) else int(card.get("comment_count") or 0)
    summary = {
        "id": str(card.get("id") or ""),
        "title": card.get("title") or "",
        "type": card.get("type") or "",
        "position": card.get("position", 0),
        "comment_count": comment_count,
        "checklist_done": checklist_done,
        "checklist_total": checklist_total,
        "updated_at": card.get("updated_at") or "",
    }
    if include_description:
        summary["description"] = _plain_text(card.get("description"))[:500]
    return summary


def get_federation_board_meta(storage, tenant_type: str, tenant_id: str, board_id: str) -> dict[str, Any]:
    settings = storage.read_settings()
    tenant_ctx = build_tenant_context_for_federation(tenant_type, tenant_id)
    tenant_data = storage.read_tenant(tenant_ctx, settings)
    board = _find_board_or_raise(tenant_data, board_id)
    board_lists = _board_lists(tenant_data, board_id)
    board_cards = _board_cards(tenant_data, board_id)
    status_id = _normalize_status_id(board)
    return {
        "board": {
            "id": str(board.get("id")),
            "title": board.get("title") or "",
            "organization": (board.get("organization") or "").strip(),
            "status_id": status_id,
            "status": _status_label(settings, status_id),
            "description": board.get("description") or "",
            "start_date": board.get("start_date") or "",
            "end_date": board.get("end_date") or "",
            "updated_at": board.get("updated_at") or "",
        },
        "list_count": len(board_lists),
        "card_count": len(board_cards),
    }


def get_federation_board_lists(storage, tenant_type: str, tenant_id: str, board_id: str) -> dict[str, Any]:
    settings = storage.read_settings()
    tenant_ctx = build_tenant_context_for_federation(tenant_type, tenant_id)
    tenant_data = storage.read_tenant(tenant_ctx, settings)
    _find_board_or_raise(tenant_data, board_id)
    board_cards = _board_cards(tenant_data, board_id)
    lists_payload = []
    for lst in _board_lists(tenant_data, board_id):
        list_id = str(lst.get("id"))
        card_count = sum(1 for card in board_cards if str(card.get("list_id")) == list_id)
        lists_payload.append(
            {
                "id": list_id,
                "title": lst.get("title") or "",
                "position": lst.get("position", 0),
                "card_count": card_count,
                "card_sections": lst.get("card_sections") or {"show_checklist": True, "show_comments": True},
            }
        )
    return {"lists": lists_payload}


def build_federation_list_card_summaries(
    storage,
    tenant_type: str,
    tenant_id: str,
    board_id: str,
    list_id: str,
    *,
    include_description: bool = False,
) -> list[dict[str, Any]]:
    settings = storage.read_settings()
    tenant_ctx = build_tenant_context_for_federation(tenant_type, tenant_id)
    tenant_data = storage.read_tenant(tenant_ctx, settings)
    _find_board_or_raise(tenant_data, board_id)
    cards = sorted(
        [
            _card_summary(card, include_description=include_description)
            for card in _board_cards(tenant_data, board_id)
            if str(card.get("list_id")) == str(list_id)
        ],
        key=lambda item: item.get("position", 0),
    )
    return cards


def paginate_federation_list_cards(
    storage,
    tenant_type: str,
    tenant_id: str,
    board_id: str,
    list_id: str,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_CARDS_PAGE_SIZE,
    include_description: bool = False,
) -> dict[str, Any]:
    catalog = build_federation_list_card_summaries(
        storage,
        tenant_type,
        tenant_id,
        board_id,
        list_id,
        include_description=include_description,
    )
    safe_limit = max(1, min(int(limit or DEFAULT_CARDS_PAGE_SIZE), 100))
    start = 0
    normalized_cursor = (cursor or "").strip()
    if normalized_cursor:
        for index, card in enumerate(catalog):
            if str(card.get("id")) == normalized_cursor:
                start = index + 1
                break

    items = catalog[start : start + safe_limit]
    done = start + len(items) >= len(catalog)
    next_cursor = None
    if items and not done:
        next_cursor = str(items[-1]["id"])
    return {
        "board_id": str(board_id),
        "list_id": str(list_id),
        "items": items,
        "next_cursor": next_cursor,
        "done": done,
    }


def load_board_compare_snapshot(
    storage,
    tenant_type: str,
    tenant_id: str,
    board_id: str,
    *,
    include_description: bool = False,
) -> dict[str, Any]:
    meta = get_federation_board_meta(storage, tenant_type, tenant_id, board_id)
    lists_payload = get_federation_board_lists(storage, tenant_type, tenant_id, board_id)
    cards_by_list: dict[str, list[dict[str, Any]]] = {}
    for lst in lists_payload.get("lists") or []:
        list_id = str(lst.get("id"))
        cards_by_list[list_id] = build_federation_list_card_summaries(
            storage,
            tenant_type,
            tenant_id,
            board_id,
            list_id,
            include_description=include_description,
        )
    return {
        "board": meta.get("board") or {},
        "lists": lists_payload.get("lists") or [],
        "cards_by_list": cards_by_list,
    }
