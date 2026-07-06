"""看板对比 diff 计算（纯函数）。"""

from __future__ import annotations

from typing import Any

BOARD_META_FIELDS = (
    "title",
    "organization",
    "status_id",
    "status",
    "description",
    "start_date",
    "end_date",
)

LIST_FIELDS = ("title", "position")

CARD_FIELDS = (
    "title",
    "type",
    "position",
    "comment_count",
    "checklist_done",
    "checklist_total",
)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _field_changed(local_value: Any, remote_value: Any) -> bool:
    return _normalize_text(local_value) != _normalize_text(remote_value)


def _diff_fields(
    local_obj: dict[str, Any] | None,
    remote_obj: dict[str, Any] | None,
    fields: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    changed: dict[str, dict[str, Any]] = {}
    local_obj = local_obj or {}
    remote_obj = remote_obj or {}
    for field in fields:
        local_value = local_obj.get(field)
        remote_value = remote_obj.get(field)
        if _field_changed(local_value, remote_value):
            changed[field] = {"local": local_value, "remote": remote_value}
    return changed


def diff_board_meta(local_board: dict[str, Any] | None, remote_board: dict[str, Any] | None) -> dict[str, Any]:
    fields = _diff_fields(local_board, remote_board, BOARD_META_FIELDS)
    if not local_board:
        return {"status": "only_remote", "fields": fields}
    if not remote_board:
        return {"status": "only_local", "fields": fields}
    status = "equal" if not fields else "changed"
    return {"status": status, "fields": fields}


def diff_lists(local_lists: list[dict[str, Any]], remote_lists: list[dict[str, Any]]) -> dict[str, Any]:
    local_map = {str(item.get("id")): item for item in local_lists if item.get("id") is not None}
    remote_map = {str(item.get("id")): item for item in remote_lists if item.get("id") is not None}

    added = [
        {
            "id": board_id,
            "title": remote_map[board_id].get("title") or "",
        }
        for board_id in remote_map
        if board_id not in local_map
    ]
    removed = [
        {
            "id": board_id,
            "title": local_map[board_id].get("title") or "",
        }
        for board_id in local_map
        if board_id not in remote_map
    ]
    changed: list[dict[str, Any]] = []
    for list_id, local_list in local_map.items():
        remote_list = remote_map.get(list_id)
        if not remote_list:
            continue
        field_changes = _diff_fields(local_list, remote_list, LIST_FIELDS)
        local_sections = local_list.get("card_sections") or {}
        remote_sections = remote_list.get("card_sections") or {}
        if local_sections != remote_sections:
            field_changes["card_sections"] = {"local": local_sections, "remote": remote_sections}
        if field_changes:
            changed.append({"id": list_id, "fields": field_changes})

    status = "equal"
    if added or removed or changed:
        status = "changed"
    return {"status": status, "added": added, "removed": removed, "changed": changed}


def diff_cards(
    local_cards: list[dict[str, Any]],
    remote_cards: list[dict[str, Any]],
    *,
    extra_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    compare_fields = CARD_FIELDS + tuple(extra_fields)
    local_map = {str(item.get("id")): item for item in local_cards if item.get("id") is not None}
    remote_map = {str(item.get("id")): item for item in remote_cards if item.get("id") is not None}

    added = [
        {
            "id": card_id,
            "title": remote_map[card_id].get("title") or "",
        }
        for card_id in remote_map
        if card_id not in local_map
    ]
    removed = [
        {
            "id": card_id,
            "title": local_map[card_id].get("title") or "",
        }
        for card_id in local_map
        if card_id not in remote_map
    ]
    changed: list[dict[str, Any]] = []
    for card_id, local_card in local_map.items():
        remote_card = remote_map.get(card_id)
        if not remote_card:
            continue
        field_changes = _diff_fields(local_card, remote_card, compare_fields)
        if field_changes:
            changed.append({"id": card_id, "fields": field_changes})

    status = "equal"
    if added or removed or changed:
        status = "changed"
    return {"status": status, "added": added, "removed": removed, "changed": changed}


def summarize_board_diff(
    *,
    pair_status: str | None,
    meta_diff: dict[str, Any] | None = None,
    lists_diff: dict[str, Any] | None = None,
    cards_diff_by_list: dict[str, dict[str, Any]] | None = None,
) -> str:
    if pair_status in ("only_local", "only_remote"):
        return pair_status
    if pair_status == "error":
        return "error"

    statuses: list[str] = []
    if meta_diff:
        statuses.append(meta_diff.get("status") or "equal")
    if lists_diff:
        statuses.append(lists_diff.get("status") or "equal")
    for list_diff in (cards_diff_by_list or {}).values():
        statuses.append(list_diff.get("status") or "equal")

    if not statuses:
        return "equal"
    if any(status == "changed" for status in statuses):
        return "changed"
    return "equal"


def build_board_compare_result(
    *,
    pair_index: int,
    queued: dict[str, Any],
    meta_diff: dict[str, Any] | None = None,
    lists_diff: dict[str, Any] | None = None,
    cards_diff_by_list: dict[str, dict[str, Any]] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    pair_status = queued.get("status") or "matched"
    if error:
        overall = "error"
    else:
        overall = summarize_board_diff(
            pair_status=pair_status,
            meta_diff=meta_diff,
            lists_diff=lists_diff,
            cards_diff_by_list=cards_diff_by_list,
        )

    return {
        "pair_index": pair_index,
        "tenant_type": queued.get("tenant_type"),
        "tenant_id": queued.get("tenant_id"),
        "display_name": queued.get("display_name"),
        "local_board_id": queued.get("local_board_id"),
        "remote_board_id": queued.get("remote_board_id"),
        "local_title": queued.get("local_title"),
        "remote_title": queued.get("remote_title"),
        "status": overall,
        "pair_status": pair_status,
        "error": error,
        "meta": meta_diff,
        "lists": lists_diff,
        "cards": {"by_list": cards_diff_by_list or {}},
    }
