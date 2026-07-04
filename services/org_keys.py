import hashlib
import json
from collections import defaultdict
from typing import Any

PERSONAL_ORG_ID = "org_0"
PERSONAL_BOARD_ORG_NAME = "个人看板"
ORG_NAMESPACE = "jjob:boardflow:org"


def org_root(org_id: str) -> str:
    return f"{ORG_NAMESPACE}:{org_id}"


def org_meta_key(org_id: str) -> str:
    return f"{org_root(org_id)}:meta"


def org_boards_key(org_id: str) -> str:
    """组织下所有看板项目 Hash，field=board_id。"""
    return f"{org_root(org_id)}:boards"


def org_board_lists_key(org_id: str, board_id: str) -> str:
    """某看板下所有大列 Hash，field=list_id。"""
    return f"{org_root(org_id)}:boards:{board_id}:lists"


def org_list_cards_key(org_id: str, board_id: str, list_id: str) -> str:
    return f"{org_root(org_id)}:boards:{board_id}:lists:{list_id}:cards"


def org_list_state_key(org_id: str, board_id: str, list_id: str) -> str:
    return f"{org_root(org_id)}:boards:{board_id}:lists:{list_id}:state"


def org_card_detail_key(org_id: str, board_id: str, list_id: str, card_id: str) -> str:
    return f"{org_root(org_id)}:boards:{board_id}:lists:{list_id}:detail:{card_id}"


# --- 旧版键（读取迁移用） ---


def legacy_org_projects_key(org_id: str) -> str:
    """旧：看板存在 :projects。"""
    return f"{org_root(org_id)}:projects"


def legacy_org_flat_lists_key(org_id: str) -> str:
    """旧：大列平铺在 :boards（与看板键名冲突）。"""
    return org_boards_key(org_id)


def legacy_org_list_cards_key(org_id: str, list_id: str) -> str:
    """旧：cards 挂在 :boards:{list_id}:cards。"""
    return f"{org_root(org_id)}:boards:{list_id}:cards"


def legacy_org_list_state_key(org_id: str, list_id: str) -> str:
    return f"{org_root(org_id)}:boards:{list_id}:state"


def legacy_org_card_detail_key(org_id: str, list_id: str, card_id: str) -> str:
    return f"{org_root(org_id)}:boards:{list_id}:detail:{card_id}"


def resolve_org_id(organization: str | None, organizations: list[dict[str, Any]]) -> str:
    name = (organization or "").strip()
    if not name or name == PERSONAL_BOARD_ORG_NAME:
        return PERSONAL_ORG_ID

    for org in organizations:
        if (org.get("name") or "").strip() == name and org.get("id"):
            return str(org["id"])

    slug = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return f"org_custom_{slug}"


def group_entities_by_org(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    settings = data.get("settings") or {}
    organizations = settings.get("organizations") or []
    boards = data.get("boards") or []
    lists = data.get("lists") or []
    cards = data.get("cards") or []

    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"boards": [], "lists": [], "cards": []}
    )
    board_to_org: dict[str, str] = {}

    for board in boards:
        if board.get("id") is None:
            continue
        org_id = resolve_org_id(board.get("organization"), organizations)
        board_id = str(board["id"])
        board_to_org[board_id] = org_id
        board_payload = dict(board)
        board_payload["org_id"] = org_id
        buckets[org_id]["boards"].append(board_payload)

    for lst in lists:
        if lst.get("id") is None:
            continue
        board_id = str(lst.get("board_id") or "")
        org_id = board_to_org.get(board_id, PERSONAL_ORG_ID)
        list_payload = dict(lst)
        list_payload["org_id"] = org_id
        buckets[org_id]["lists"].append(list_payload)

    for card in cards:
        if card.get("id") is None:
            continue
        board_id = str(card.get("board_id") or "")
        org_id = board_to_org.get(board_id, PERSONAL_ORG_ID)
        card_payload = dict(card)
        card_payload["org_id"] = org_id
        buckets[org_id]["cards"].append(card_payload)

    return dict(buckets)


def split_card_record(card: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    card_id = str(card["id"])
    list_id = str(card.get("list_id") or "")
    board_id = str(card.get("board_id") or "")

    core = {
        key: value
        for key, value in card.items()
        if key not in {"comments", "checklist", "canvas_data", "mindmap_data", "table_data", "description_data", "position"}
    }
    state = {
        "id": card_id,
        "board_id": board_id,
        "list_id": list_id,
        "position": card.get("position", 0),
        "updated_at": card.get("updated_at"),
    }
    detail: dict[str, Any] = {"id": card_id}
    for key in ("comments", "checklist", "canvas_data", "mindmap_data", "table_data", "description_data"):
        if key in card:
            detail[key] = card[key]
    return core, state, detail


def merge_card_record(core: dict[str, Any], state: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    merged = dict(core)
    if state:
        merged["position"] = state.get("position", merged.get("position", 0))
        if state.get("updated_at"):
            merged["updated_at"] = state["updated_at"]
    for key in ("comments", "checklist", "canvas_data", "mindmap_data", "table_data", "description_data"):
        if key in detail:
            merged[key] = detail[key]
    return merged


def dumps_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)
