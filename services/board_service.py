import copy
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from services.storage import DEFAULT_DATA, DEFAULT_EDITABLE_FONTS, EDITABLE_FONT_SCOPE_IDS


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _plain_text(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


class BoardService:
    def __init__(self, storage) -> None:
        self.storage = storage
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        return copy.deepcopy(self.storage.read())

    def _write(self, data: dict[str, Any]) -> None:
        self.storage.write(data)

    def _next_id(self, data: dict[str, Any], key: str) -> str:
        meta = data.setdefault("meta", {})
        current = int(meta.get(key, 1))
        meta[key] = current + 1
        return str(current)

    def get_settings(self) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            settings = data.get("settings", DEFAULT_DATA["settings"])
            settings.setdefault("card_types", DEFAULT_DATA["settings"]["card_types"])
            settings.setdefault("board_statuses", DEFAULT_DATA["settings"]["board_statuses"])
            settings.setdefault("organizations", DEFAULT_DATA["settings"]["organizations"])
            settings.setdefault("editable_fonts", DEFAULT_EDITABLE_FONTS)
            return settings

    def _validate_font_profile(self, font: dict[str, Any]) -> dict[str, str]:
        allowed_families = {
            "microsoft-yahei",
            "simsun",
            "simhei",
            "kaiti",
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
            data = self._read()
            settings = data.setdefault("settings", {})
            settings["editable_fonts"] = validated
            self._write(data)
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
            settings = data.setdefault("settings", {})
            old_orgs = settings.get("organizations", DEFAULT_DATA["settings"]["organizations"])
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

            removed_names = {
                (item.get("name") or "").strip()
                for item in old_orgs
                if str(item.get("id")) not in new_ids
            }
            for board in data.get("boards", []):
                if (board.get("organization") or "").strip() in removed_names:
                    board["organization"] = ""

            settings["organizations"] = validated
            self._write(data)
            return settings

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

            fallback_id = "unset" if "unset" in new_ids else validated[0]["id"]
            for board in data.get("boards", []):
                board_status_id = str(board.get("status_id") or "")
                if board_status_id in removed_ids or board_status_id not in new_ids:
                    self._apply_board_status(data, board, fallback_id)
                else:
                    self._apply_board_status(data, board, board_status_id)

            self._write(data)
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
                    }
                )
            for item in result:
                self._apply_board_status(data, item, item.get("status_id") or item.get("status"))
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
            settings = data.get("settings", DEFAULT_DATA["settings"])
            settings.setdefault("card_types", DEFAULT_DATA["settings"]["card_types"])
            settings.setdefault("board_statuses", DEFAULT_DATA["settings"]["board_statuses"])
            settings.setdefault("organizations", DEFAULT_DATA["settings"]["organizations"])
            settings.setdefault("editable_fonts", DEFAULT_EDITABLE_FONTS)
            return {
                "board": board_payload,
                "lists": list_payload,
                "settings": settings,
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
            self._touch_board(data, board_id)
            self._write(data)
            return lst

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
                "created_at": now,
                "updated_at": now,
            }
            data.setdefault("cards", []).append(card)
            self._touch_board(data, board_id)
            self._write(data)
            return card

    def update_card(self, board_id: str, card_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            card = self._find_card(data, board_id, card_id)
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
                field: card.get(field),
            }

    def update_card_editor(self, board_id: str, card_id: str, field: str, payload: Any) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            card = self._find_card(data, board_id, card_id)
            card[field] = payload
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

    def add_comment(self, board_id: str, card_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        content = (payload.get("content") or "").strip()
        if not content:
            raise ValueError("评论内容不能为空")
        parent_id = (payload.get("parent_id") or "").strip()

        with self._lock:
            data = self._read()
            card = self._find_card(data, board_id, card_id)
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
    ) -> dict[str, Any]:
        content = (payload.get("content") or "").strip()
        if not content:
            raise ValueError("评论内容不能为空")

        with self._lock:
            data = self._read()
            card = self._find_card(data, board_id, card_id)
            target, _parent = self._locate_comment(card, comment_id)
            target["content"] = content
            target["updated_at"] = _now_iso()
            card["updated_at"] = _now_iso()
            self._touch_board(data, board_id)
            self._write(data)
            return card

    def delete_comment(self, board_id: str, card_id: str, comment_id: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            card = self._find_card(data, board_id, card_id)
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
            data = self._read()
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
            self._write(data)

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

    def export_system_dat(self) -> tuple[bytes, str]:
        from services.data_transfer import export_system

        with self._lock:
            return export_system(self._read())

    def export_organization_dat(self, org_id: str) -> tuple[bytes, str]:
        from services.data_transfer import export_organization

        with self._lock:
            return export_organization(self._read(), org_id)

    def export_board_dat(self, board_id: str) -> tuple[bytes, str]:
        from services.data_transfer import export_board

        with self._lock:
            data = self._read()
            self._find_board(data, board_id)
            return export_board(data, board_id)

    def validate_import_dat(self, raw: bytes | str, *, expected_kind: str | None = None) -> dict[str, Any]:
        from services.data_transfer import parse_package, validate_package

        package = parse_package(raw)
        return validate_package(package, expected_kind=expected_kind)

    def import_dat(self, raw: bytes | str, *, mode: str = "merge") -> dict[str, Any]:
        from services.data_transfer import apply_import, parse_package, validate_package

        package = parse_package(raw)
        validation = validate_package(package)
        if not validation["valid"]:
            raise ValueError("数据包校验未通过：" + "；".join(validation["errors"][:3]))

        with self._lock:
            current = self._read()
            imported = apply_import(current, package, mode=mode)
            self._write(imported)
            return validation

