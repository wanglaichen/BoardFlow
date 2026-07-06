"""多平台看板对比：逐条同步（本地 ↔ 远程）。"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any

from services.data_transfer import _resolve_board_organization, apply_import
from services.federation_service import (
    build_tenant_context_for_federation,
)
from services.org_keys import PERSONAL_BOARD_ORG_NAME, PERSONAL_ORG_ID
from services.tenant_keys import SUPER_ADMIN_TENANT_TYPE, USER_TENANT_TYPE


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _organizations_for_tenant(storage, tenant_type: str, tenant_id: str, settings: dict[str, Any]) -> list[dict[str, Any]]:
    if tenant_type == USER_TENANT_TYPE:
        return storage.list_user_organizations(tenant_id)
    return settings.get("organizations") or []


def _merge_settings_organization(settings: dict[str, Any], org_meta: dict[str, Any]) -> dict[str, Any]:
    name = (org_meta.get("name") or "").strip()
    org_id = str(org_meta.get("id") or "").strip()
    note = (org_meta.get("note") or "").strip()
    if not name or name == PERSONAL_BOARD_ORG_NAME:
        return {"id": PERSONAL_ORG_ID, "name": PERSONAL_BOARD_ORG_NAME, "note": ""}

    orgs = settings.setdefault("organizations", [])
    now = _now_iso()

    if org_id:
        existing = next((org for org in orgs if str(org.get("id")) == org_id), None)
        if existing:
            if note and note != (existing.get("note") or "").strip():
                existing["note"] = note
                existing["updated_at"] = now
            if name != (existing.get("name") or "").strip():
                existing["name"] = name
                existing["updated_at"] = now
            return copy.deepcopy(existing)

    existing = next((org for org in orgs if (org.get("name") or "").strip() == name), None)
    if existing:
        if note and note != (existing.get("note") or "").strip():
            existing["note"] = note
            existing["updated_at"] = now
        return copy.deepcopy(existing)

    new_id = org_id if org_id and not any(str(org.get("id")) == org_id for org in orgs) else f"org_{uuid.uuid4().hex[:8]}"
    new_org = {
        "id": new_id,
        "name": name,
        "note": note,
        "created_at": now,
        "updated_at": now,
    }
    orgs.append(new_org)
    return copy.deepcopy(new_org)


def _merge_user_organization(storage, user_id: str, org_meta: dict[str, Any]) -> dict[str, Any]:
    name = (org_meta.get("name") or "").strip()
    org_id = str(org_meta.get("id") or "").strip()
    note = (org_meta.get("note") or "").strip()
    if not name or name == PERSONAL_BOARD_ORG_NAME:
        return {"id": PERSONAL_ORG_ID, "name": PERSONAL_BOARD_ORG_NAME, "note": ""}

    orgs = storage.list_user_organizations(user_id)
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
                storage.write_user_organizations(user_id, orgs)
            return copy.deepcopy(existing)

    existing = next((org for org in orgs if (org.get("name") or "").strip() == name), None)
    if existing:
        if note and note != (existing.get("note") or "").strip():
            existing["note"] = note
            existing["updated_at"] = now
            storage.write_user_organizations(user_id, orgs)
        return copy.deepcopy(existing)

    new_id = org_id if org_id and not any(str(org.get("id")) == org_id for org in orgs) else f"org_{uuid.uuid4().hex[:8]}"
    new_org = {
        "id": new_id,
        "name": name,
        "note": note,
        "created_at": now,
        "updated_at": now,
    }
    orgs.append(new_org)
    storage.write_user_organizations(user_id, orgs)
    return copy.deepcopy(new_org)


def load_board_full_sync_payload(
    storage,
    tenant_type: str,
    tenant_id: str,
    board_id: str,
) -> dict[str, Any]:
    settings = storage.read_settings()
    tenant_ctx = build_tenant_context_for_federation(tenant_type, tenant_id)
    tenant_data = storage.read_tenant(tenant_ctx, settings)
    board = _find_board_or_raise(tenant_data, board_id)
    lists = [copy.deepcopy(item) for item in _board_lists(tenant_data, board_id)]
    list_ids = {str(item.get("id")) for item in lists}
    cards = [
        copy.deepcopy(item)
        for item in tenant_data.get("cards") or []
        if str(item.get("board_id")) == str(board_id) or str(item.get("list_id")) in list_ids
    ]
    organizations = _organizations_for_tenant(storage, tenant_type, tenant_id, settings)
    organization = _resolve_board_organization(board, organizations)
    return {
        "board": copy.deepcopy(board),
        "organization": organization,
        "lists": lists,
        "cards": cards,
    }


def apply_board_sync_payload(
    storage,
    tenant_type: str,
    tenant_id: str,
    payload: dict[str, Any],
    *,
    target_board_id: str | None = None,
    mode: str = "replace",
) -> dict[str, Any]:
    sync_mode = (mode or "replace").strip().lower()
    if sync_mode not in ("replace", "merge"):
        raise ValueError("mode 必须是 replace 或 merge")

    settings = storage.read_settings()
    tenant_ctx = build_tenant_context_for_federation(tenant_type, tenant_id)
    tenant_data = storage.read_tenant(tenant_ctx, settings)

    payload = copy.deepcopy(payload or {})
    board = payload.get("board") or {}
    org_meta = payload.get("organization")
    if not isinstance(org_meta, dict):
        org_name = (board.get("organization") or "").strip()
        org_meta = {"id": "", "name": org_name, "note": ""} if org_name else {}

    if org_meta:
        if tenant_type == USER_TENANT_TYPE:
            merged_org = _merge_user_organization(storage, tenant_id, org_meta)
        else:
            merged_org = _merge_settings_organization(settings, org_meta)
            storage.write_settings(settings)
        board = copy.deepcopy(board)
        board["organization"] = merged_org.get("name") or board.get("organization") or ""
        payload["board"] = board
        payload["organization"] = merged_org

    normalized_target = (target_board_id or "").strip() or None
    source_board_id = str(board.get("id") or "")
    if normalized_target:
        board["id"] = normalized_target
        payload["board"] = board

    old_board_ids = {str(item.get("id")) for item in tenant_data.get("boards") or [] if item.get("id") is not None}
    updated = apply_import(copy.deepcopy(tenant_data), {"kind": "board", "payload": payload}, mode=sync_mode)
    storage.write_tenant(tenant_ctx, updated, settings)

    result_id = normalized_target or source_board_id
    if sync_mode == "merge" and not normalized_target:
        new_boards = [
            item
            for item in updated.get("boards") or []
            if str(item.get("id")) not in old_board_ids
        ]
        if new_boards:
            result_id = str(new_boards[-1]["id"])

    return {
        "board_id": result_id,
        "mode": sync_mode,
        "target_board_id": normalized_target,
        "tenant_type": tenant_type,
        "tenant_id": tenant_id,
    }
