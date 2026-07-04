import json
import os
import re
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import redis
except ImportError:
    redis = None

from services.org_keys import (
    PERSONAL_ORG_ID,
    ORG_NAMESPACE,
    group_entities_by_org,
    legacy_org_card_detail_key,
    legacy_org_flat_lists_key,
    legacy_org_list_cards_key,
    legacy_org_list_state_key,
    legacy_org_projects_key,
    merge_card_record,
    org_board_lists_key,
    org_boards_key,
    org_card_detail_key,
    org_list_cards_key,
    org_list_state_key,
    org_meta_key,
    org_root,
    split_card_record,
)

EDITABLE_FONT_HASH_FIELDS = ("family", "style", "weight", "size", "color")

EDITABLE_FONT_SCOPE_IDS = (
    "board_title",
    "list_title",
    "card_title_board",
    "card_title_modal",
    "checklist_item",
    "checklist_item_done",
    "comment",
    "comment_reply",
    "description",
)


def _default_font_profile(**overrides: str) -> dict[str, str]:
    profile = {
        "family": "microsoft-yahei",
        "style": "normal",
        "weight": "400",
        "size": "15",
        "color": "#e8eaed",
    }
    profile.update(overrides)
    return profile


DEFAULT_EDITABLE_FONTS: dict[str, dict[str, str]] = {
    "board_title": _default_font_profile(size="22", weight="400", color="#e8eaed"),
    "list_title": _default_font_profile(size="15", weight="600"),
    "card_title_board": _default_font_profile(size="14", weight="400"),
    "card_title_modal": _default_font_profile(size="24", weight="600", color="#e8eaed"),
    "checklist_item": _default_font_profile(size="14"),
    "checklist_item_done": _default_font_profile(size="14", color="#9aa3ad"),
    "comment": _default_font_profile(size="15", color="#f3f4f6"),
    "comment_reply": _default_font_profile(size="14", color="#e8eaed"),
    "description": _default_font_profile(size="15", color="#1f2328"),
}


class StorageUnavailable(RuntimeError):
    pass


DEFAULT_DATA = {
    "boards": [],
    "lists": [],
    "cards": [],
    "meta": {"next_board_id": 1, "next_list_id": 1, "next_card_id": 1},
    "settings": {
        "card_types": [
            {"id": "user_story", "label": "用户故事", "color": "#3fb950"},
            {"id": "task", "label": "任务", "color": "#58a6ff"},
            {"id": "bug", "label": "缺陷", "color": "#f85149"},
        ],
        "board_statuses": [
            {"id": "not_started", "label": "未开始", "color": "#9ca3af", "icon": "circle"},
            {"id": "in_progress", "label": "进行中", "color": "#16a34a", "icon": "dot"},
            {"id": "finished", "label": "已结束", "color": "#2563eb", "icon": "check"},
            {"id": "unset", "label": "未设状态", "color": "#6b7280", "icon": "none"},
        ],
        "organizations": [],
        "editable_fonts": json.loads(json.dumps(DEFAULT_EDITABLE_FONTS)),
    },
}


def _clone_default_data() -> dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_DATA))


def _pipeline_hset_mapping(pipeline: Any, key: str, mapping: dict[str, str]) -> None:
    for field, value in mapping.items():
        pipeline.hset(key, field, value)


def _normalize_data(data: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _clone_default_data()
    if not isinstance(data, dict):
        return normalized

    for key in ("boards", "lists", "cards"):
        value = data.get(key)
        if isinstance(value, list):
            normalized[key] = value

    meta = data.get("meta")
    if isinstance(meta, dict):
        normalized["meta"].update(meta)

    settings = data.get("settings")
    if isinstance(settings, dict):
        normalized["settings"].update(settings)

    normalized["settings"].setdefault("card_types", DEFAULT_DATA["settings"]["card_types"])
    normalized["settings"].setdefault("board_statuses", DEFAULT_DATA["settings"]["board_statuses"])
    normalized["settings"].setdefault("organizations", DEFAULT_DATA["settings"]["organizations"])
    fonts = normalized["settings"].get("editable_fonts")
    if not isinstance(fonts, dict):
        fonts = {}
    merged_fonts = json.loads(json.dumps(DEFAULT_EDITABLE_FONTS))
    legacy_font = normalized["settings"].pop("editable_font", None)
    if isinstance(legacy_font, dict):
        for scope_id in EDITABLE_FONT_SCOPE_IDS:
            merged_fonts[scope_id] = {**merged_fonts[scope_id], **legacy_font}
    for scope_id in EDITABLE_FONT_SCOPE_IDS:
        scope_font = fonts.get(scope_id)
        if isinstance(scope_font, dict):
            merged_fonts[scope_id] = {**merged_fonts[scope_id], **scope_font}
    normalized["settings"]["editable_fonts"] = merged_fonts
    return normalized


class JsonStorage:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def read(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return _clone_default_data()

            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)

            return _normalize_data(data)

    def write(self, data: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
            with tmp_path.open("w", encoding="utf-8") as file:
                json.dump(_normalize_data(data), file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(tmp_path, self.path)


class RedisStorage:
    def __init__(
        self,
        url: str,
        key_prefix: str,
        timeout_seconds: float = 5,
        settings_key: str = "",
    ) -> None:
        if redis is None:
            raise StorageUnavailable("redis 依赖未安装，请先执行 pip install -r requirements.txt")
        self.url = url
        self.key_prefix = key_prefix.rstrip(":")
        self.settings_key = settings_key.strip() or f"{self.key_prefix}:settings"
        self._timeout = timeout_seconds
        self._client: redis.Redis | None = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis.from_url(
                self.url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=self._timeout,
            )
        return self._client

    @property
    def _boards_key(self) -> str:
        return f"{self.key_prefix}:boards"

    @property
    def _lists_key(self) -> str:
        return f"{self.key_prefix}:lists"

    @property
    def _cards_key(self) -> str:
        return f"{self.key_prefix}:cards"

    @property
    def _meta_key(self) -> str:
        return f"{self.key_prefix}:meta"

    @property
    def _legacy_state_key(self) -> str:
        return f"{self.key_prefix}:state"

    @property
    def _settings_card_types_key(self) -> str:
        return f"{self.settings_key}:card_types"

    @property
    def _settings_board_statuses_key(self) -> str:
        return f"{self.settings_key}:board_statuses"

    @property
    def _settings_organizations_key(self) -> str:
        return f"{self.settings_key}:organizations"

    @property
    def _settings_editable_fonts_key(self) -> str:
        return f"{self.settings_key}:editable_fonts"

    @property
    def _settings_editable_font_key(self) -> str:
        return f"{self.settings_key}:editable_font"

    def read(self) -> dict[str, Any]:
        legacy_state = self._read_legacy_state()
        settings = self._read_settings()
        if settings is None and legacy_state:
            settings = legacy_state.get("settings", DEFAULT_DATA["settings"])
        settings = settings or DEFAULT_DATA["settings"]

        self._cleanup_legacy_settings_string()

        if self._has_org_data():
            boards, lists, cards, meta = self._read_org_scoped(settings)
        else:
            boards = self._read_entity_hash(self._boards_key)
            lists = self._read_entity_hash(self._lists_key)
            cards = self._read_entity_hash(self._cards_key)
            meta = self._read_meta()
            if not boards and not lists and not cards and legacy_state:
                boards = legacy_state.get("boards", [])
                lists = legacy_state.get("lists", [])
                cards = legacy_state.get("cards", [])
            if not meta and legacy_state:
                meta = legacy_state.get("meta", {})

        return _normalize_data(
            {
                "boards": boards,
                "lists": lists,
                "cards": cards,
                "meta": meta or {},
                "settings": settings,
            }
        )

    def write(self, data: dict[str, Any]) -> None:
        normalized = _normalize_data(data)
        settings = normalized.get("settings", DEFAULT_DATA["settings"])
        buckets = group_entities_by_org(normalized)
        meta = normalized.get("meta", {})

        pipeline = self.client.pipeline()
        self._write_settings_hashes(pipeline, settings)
        pipeline.delete(self.settings_key)
        self._write_org_scoped(pipeline, buckets, meta, settings)
        self._delete_legacy_flat_keys(pipeline)
        pipeline.execute()

    def ping(self) -> bool:
        self.client.ping()
        return True

    def _has_org_data(self) -> bool:
        pattern = f"{ORG_NAMESPACE}:*:meta"
        for key in self.client.scan_iter(match=pattern, count=100):
            if self._key_type(key) == "hash":
                return True
        return False

    def _discover_org_ids(self, settings: dict[str, Any]) -> set[str]:
        org_ids = {PERSONAL_ORG_ID}
        for org in settings.get("organizations") or []:
            if org.get("id"):
                org_ids.add(str(org["id"]))

        pattern = re.compile(rf"^{re.escape(ORG_NAMESPACE)}:([^:]+):meta$")
        for key in self.client.scan_iter(match=f"{ORG_NAMESPACE}:*:meta", count=200):
            matched = pattern.match(key)
            if matched:
                org_ids.add(matched.group(1))
        return org_ids

    def _flat_lists_key(self, org_id: str) -> str:
        return f"{org_root(org_id)}:lists"

    def _flat_cards_key(self, org_id: str) -> str:
        return f"{org_root(org_id)}:cards"

    def _flat_card_details_key(self, org_id: str) -> str:
        return f"{org_root(org_id)}:card_details"

    @staticmethod
    def _records_look_like_lists(items: list[dict[str, Any]]) -> bool:
        if not items:
            return False
        return all(isinstance(item, dict) and item.get("board_id") is not None for item in items)

    def _has_new_list_layout(self, org_id: str) -> bool:
        pattern = f"{org_root(org_id)}:boards:*:lists"
        for key in self.client.scan_iter(match=pattern, count=50):
            if self._key_type(key) == "hash" and self.client.hlen(key) > 0:
                return True
        return False

    def _discover_board_ids(self, org_id: str, org_boards: list[dict[str, Any]]) -> set[str]:
        board_ids = {str(board.get("id")) for board in org_boards if board.get("id") is not None}
        pattern = re.compile(rf"^{re.escape(org_root(org_id))}:boards:([^:]+):lists$")
        for key in self.client.scan_iter(match=f"{org_root(org_id)}:boards:*:lists", count=200):
            matched = pattern.match(key)
            if matched:
                board_ids.add(matched.group(1))
        return {board_id for board_id in board_ids if board_id}

    def _read_org_boards(self, org_id: str) -> list[dict[str, Any]]:
        boards = self._read_entity_hash(org_boards_key(org_id))
        if boards and not self._records_look_like_lists(boards):
            return boards

        projects = self._read_entity_hash(legacy_org_projects_key(org_id))
        if projects:
            return projects

        if boards and self._records_look_like_lists(boards):
            return []

        return []

    def _read_org_lists(self, org_id: str, org_boards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._has_new_list_layout(org_id):
            lists: list[dict[str, Any]] = []
            for board_id in sorted(self._discover_board_ids(org_id, org_boards)):
                lists.extend(self._read_entity_hash(org_board_lists_key(org_id, board_id)))
            if lists:
                return lists

        legacy_lists = self._read_entity_hash(legacy_org_flat_lists_key(org_id))
        if legacy_lists and self._records_look_like_lists(legacy_lists):
            return legacy_lists

        return self._read_entity_hash(self._flat_lists_key(org_id))

    def _read_org_cards(self, org_id: str, org_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for lst in org_lists:
            board_id = str(lst.get("board_id") or "")
            list_id = str(lst.get("id") or "")
            if not board_id or not list_id:
                continue
            cards.extend(self._read_cards_for_list(org_id, board_id, list_id))

        if cards:
            return cards

        for lst in org_lists:
            list_id = str(lst.get("id") or "")
            if not list_id:
                continue
            cards.extend(self._read_legacy_list_cards(org_id, list_id))

        if cards:
            return cards

        flat_cards = self._read_entity_hash(self._flat_cards_key(org_id))
        if not flat_cards:
            return []

        details_key = self._flat_card_details_key(org_id)
        details_raw = self.client.hgetall(details_key) if self._key_type(details_key) == "hash" else {}
        merged: list[dict[str, Any]] = []
        for card in flat_cards:
            card_id = str(card.get("id") or "")
            payload = dict(card)
            raw = details_raw.get(card_id)
            if raw:
                try:
                    detail = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    detail = None
                if isinstance(detail, dict):
                    for key in ("comments", "checklist", "canvas_data", "mindmap_data", "table_data", "description_data"):
                        if key in detail:
                            payload[key] = detail[key]
            merged.append(payload)
        return merged

    def _read_cards_for_list(self, org_id: str, board_id: str, list_id: str) -> list[dict[str, Any]]:
        card_cores = {
            str(item.get("id")): item
            for item in self._read_entity_hash(org_list_cards_key(org_id, board_id, list_id))
            if item.get("id") is not None
        }
        if not card_cores:
            return self._read_legacy_list_cards(org_id, list_id)

        card_states = {
            str(item.get("id")): item
            for item in self._read_entity_hash(org_list_state_key(org_id, board_id, list_id))
            if item.get("id") is not None
        }
        cards: list[dict[str, Any]] = []
        for card_id, core in card_cores.items():
            detail = self._read_card_detail_hash(org_id, board_id, list_id, card_id)
            cards.append(merge_card_record(core, card_states.get(card_id, {}), detail))
        return cards

    def _read_legacy_list_cards(self, org_id: str, list_id: str) -> list[dict[str, Any]]:
        card_cores = {
            str(item.get("id")): item
            for item in self._read_entity_hash(legacy_org_list_cards_key(org_id, list_id))
            if item.get("id") is not None
        }
        if not card_cores:
            return []

        card_states = {
            str(item.get("id")): item
            for item in self._read_entity_hash(legacy_org_list_state_key(org_id, list_id))
            if item.get("id") is not None
        }
        cards: list[dict[str, Any]] = []
        for card_id, core in card_cores.items():
            detail = self._read_legacy_card_detail_hash(org_id, list_id, card_id)
            cards.append(merge_card_record(core, card_states.get(card_id, {}), detail))
        return cards

    def _read_org_scoped(self, settings: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict], dict]:
        boards: list[dict[str, Any]] = []
        lists: list[dict[str, Any]] = []
        cards: list[dict[str, Any]] = []
        merged_meta: dict[str, Any] = {}

        for org_id in sorted(self._discover_org_ids(settings)):
            org_boards = self._read_org_boards(org_id)
            org_lists = self._read_org_lists(org_id, org_boards)
            boards.extend(org_boards)
            lists.extend(org_lists)
            cards.extend(self._read_org_cards(org_id, org_lists))

            org_meta = self._read_hash_meta(org_meta_key(org_id))
            for key, value in org_meta.items():
                if key.startswith("next_"):
                    try:
                        merged_meta[key] = max(int(merged_meta.get(key, 0)), int(value))
                    except (TypeError, ValueError):
                        merged_meta[key] = value
                else:
                    merged_meta.setdefault(key, value)

        return boards, lists, cards, merged_meta

    def _read_card_detail_hash(self, org_id: str, board_id: str, list_id: str, card_id: str) -> dict[str, Any]:
        key = org_card_detail_key(org_id, board_id, list_id, card_id)
        detail = self._read_detail_hash(key, card_id)
        if detail:
            return detail
        return self._read_legacy_card_detail_hash(org_id, list_id, card_id)

    def _read_legacy_card_detail_hash(self, org_id: str, list_id: str, card_id: str) -> dict[str, Any]:
        return self._read_detail_hash(legacy_org_card_detail_key(org_id, list_id, card_id), card_id)

    def _read_detail_hash(self, key: str, card_id: str) -> dict[str, Any]:
        if self._key_type(key) != "hash":
            return {}
        detail: dict[str, Any] = {"id": card_id}
        for field, raw in self.client.hgetall(key).items():
            try:
                detail[field] = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                detail[field] = raw
        return detail if len(detail) > 1 else {}

    def _read_hash_meta(self, key: str) -> dict[str, Any]:
        meta_raw = self.client.hgetall(key)
        if not meta_raw:
            return {}
        meta: dict[str, Any] = {}
        for field, value in meta_raw.items():
            if field.startswith("next_"):
                try:
                    meta[field] = int(value)
                except (TypeError, ValueError):
                    meta[field] = value
            else:
                meta[field] = value
        return meta

    def _write_org_scoped(
        self,
        pipeline: Any,
        buckets: dict[str, dict[str, Any]],
        meta: dict[str, Any],
        settings: dict[str, Any],
    ) -> None:
        active_org_ids = set(buckets.keys())
        active_org_ids.update(self._discover_org_ids(settings))

        for org_id in active_org_ids:
            bucket = buckets.get(org_id, {"boards": [], "lists": [], "cards": []})
            boards = bucket.get("boards", [])
            lists = bucket.get("lists", [])
            cards = bucket.get("cards", [])

            board_mapping = {
                str(item["id"]): json.dumps(item, ensure_ascii=False)
                for item in boards
                if item.get("id") is not None
            }
            self._sync_hash(pipeline, org_boards_key(org_id), board_mapping)

            lists_by_board: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for lst in lists:
                board_id = str(lst.get("board_id") or "")
                if board_id:
                    lists_by_board[board_id].append(lst)

            cards_by_list: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            for card in cards:
                board_id = str(card.get("board_id") or "")
                list_id = str(card.get("list_id") or "")
                if board_id and list_id:
                    cards_by_list[(board_id, list_id)].append(card)

            active_board_ids = set(board_mapping.keys())
            for board_id in active_board_ids:
                board_lists = lists_by_board.get(board_id, [])
                list_mapping = {
                    str(item["id"]): json.dumps(item, ensure_ascii=False)
                    for item in board_lists
                    if item.get("id") is not None
                }
                self._sync_hash(pipeline, org_board_lists_key(org_id, board_id), list_mapping)

                active_list_ids = set(list_mapping.keys())
                for list_id in active_list_ids:
                    list_cards = cards_by_list.get((board_id, list_id), [])
                    card_core_mapping: dict[str, str] = {}
                    card_state_mapping: dict[str, str] = {}
                    active_card_ids: set[str] = set()

                    for card in list_cards:
                        card_id = str(card.get("id") or "")
                        if not card_id:
                            continue
                        core, state, detail = split_card_record(card)
                        card_core_mapping[card_id] = json.dumps(core, ensure_ascii=False)
                        card_state_mapping[card_id] = json.dumps(state, ensure_ascii=False)
                        active_card_ids.add(card_id)
                        self._sync_card_detail(pipeline, org_id, board_id, list_id, card_id, detail)

                    self._sync_hash(pipeline, org_list_cards_key(org_id, board_id, list_id), card_core_mapping)
                    self._sync_hash(pipeline, org_list_state_key(org_id, board_id, list_id), card_state_mapping)
                    self._cleanup_stale_card_details(pipeline, org_id, board_id, list_id, active_card_ids)

                self._cleanup_stale_list_children(pipeline, org_id, board_id, active_list_ids)

            self._cleanup_stale_board_children(pipeline, org_id, active_board_ids)
            self._cleanup_legacy_org_layout(pipeline, org_id)

            pipeline.delete(org_meta_key(org_id))
            if meta:
                _pipeline_hset_mapping(
                    pipeline,
                    org_meta_key(org_id),
                    {key: str(value) for key, value in meta.items()},
                )

    def _sync_card_detail(
        self,
        pipeline: Any,
        org_id: str,
        board_id: str,
        list_id: str,
        card_id: str,
        detail: dict[str, Any],
    ) -> None:
        key = org_card_detail_key(org_id, board_id, list_id, card_id)
        payload = {field: value for field, value in detail.items() if field != "id" and value is not None}
        if not payload:
            pipeline.delete(key)
            pipeline.delete(legacy_org_card_detail_key(org_id, list_id, card_id))
            return

        serialized = {field: json.dumps(value, ensure_ascii=False) for field, value in payload.items()}
        pipeline.delete(key)
        _pipeline_hset_mapping(pipeline, key, serialized)
        pipeline.delete(legacy_org_card_detail_key(org_id, list_id, card_id))

    def _cleanup_stale_card_details(
        self,
        pipeline: Any,
        org_id: str,
        board_id: str,
        list_id: str,
        active_card_ids: set[str],
    ) -> None:
        prefix = f"{org_root(org_id)}:boards:{board_id}:lists:{list_id}:detail:"
        for key in self.client.scan_iter(match=f"{prefix}*", count=200):
            card_id = key.rsplit(":", 1)[-1]
            if card_id not in active_card_ids:
                pipeline.delete(key)

        legacy_prefix = f"{org_root(org_id)}:boards:{list_id}:detail:"
        for key in self.client.scan_iter(match=f"{legacy_prefix}*", count=200):
            card_id = key.rsplit(":", 1)[-1]
            if card_id not in active_card_ids:
                pipeline.delete(key)

    def _cleanup_stale_list_children(
        self,
        pipeline: Any,
        org_id: str,
        board_id: str,
        active_list_ids: set[str],
    ) -> None:
        prefix = f"{org_root(org_id)}:boards:{board_id}:lists:"
        for key in self.client.scan_iter(match=f"{prefix}*", count=500):
            if key == org_board_lists_key(org_id, board_id):
                continue
            parts = key.split(":")
            if len(parts) < 8 or parts[6] != "lists":
                continue
            list_id = parts[7]
            if list_id not in active_list_ids:
                pipeline.delete(key)

    def _cleanup_stale_board_children(self, pipeline: Any, org_id: str, active_board_ids: set[str]) -> None:
        prefix = f"{org_root(org_id)}:boards:"
        for key in self.client.scan_iter(match=f"{prefix}*", count=500):
            if key == org_boards_key(org_id):
                continue
            parts = key.split(":")
            if len(parts) < 6:
                continue
            board_id = parts[5]
            if board_id not in active_board_ids:
                pipeline.delete(key)

    def _cleanup_legacy_org_layout(self, pipeline: Any, org_id: str) -> None:
        pipeline.delete(legacy_org_projects_key(org_id))
        self._cleanup_flat_org_keys(pipeline, org_id)

        prefix = f"{org_root(org_id)}:boards:"
        for key in self.client.scan_iter(match=f"{prefix}*", count=500):
            if key == org_boards_key(org_id):
                continue
            if "lists" not in key.split(":"):
                pipeline.delete(key)

    def _cleanup_flat_org_keys(self, pipeline: Any, org_id: str) -> None:
        pipeline.delete(self._flat_lists_key(org_id))
        pipeline.delete(self._flat_cards_key(org_id))
        pipeline.delete(self._flat_card_details_key(org_id))

    def _delete_legacy_flat_keys(self, pipeline: Any) -> None:
        for key in (self._boards_key, self._lists_key, self._cards_key, self._meta_key):
            pipeline.delete(key)
        for key in (self._legacy_state_key, f"{self.key_prefix}/state"):
            if self._key_type(key) != "none":
                pipeline.delete(key)

    def _read_entity_hash(self, key: str) -> list[dict[str, Any]]:
        if self._key_type(key) != "hash":
            return []

        items: list[dict[str, Any]] = []
        for raw in self.client.hgetall(key).values():
            try:
                item = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(item, dict):
                items.append(item)
        return items

    def _read_meta(self) -> dict[str, Any]:
        meta_raw = self.client.hgetall(self._meta_key)
        if not meta_raw:
            return {}

        meta: dict[str, Any] = {}
        for key, value in meta_raw.items():
            if key.startswith("next_"):
                try:
                    meta[key] = int(value)
                except (TypeError, ValueError):
                    meta[key] = value
            else:
                meta[key] = value
        return meta

    def _read_settings(self) -> dict[str, Any] | None:
        if self._has_settings_hashes():
            card_types = self._read_settings_collection(self._settings_card_types_key)
            board_statuses = self._read_settings_collection(self._settings_board_statuses_key)
            organizations = self._read_settings_collection(self._settings_organizations_key)
            return {
                "card_types": card_types or DEFAULT_DATA["settings"]["card_types"],
                "board_statuses": board_statuses or DEFAULT_DATA["settings"]["board_statuses"],
                "organizations": organizations or [],
                "editable_fonts": self._read_editable_fonts(),
            }

        legacy_settings = self._read_legacy_settings_string()
        if legacy_settings is not None:
            return legacy_settings
        return None

    def _has_settings_hashes(self) -> bool:
        return any(
            self._key_type(key) == "hash"
            for key in (
                self._settings_card_types_key,
                self._settings_board_statuses_key,
                self._settings_organizations_key,
                self._settings_editable_fonts_key,
                self._settings_editable_font_key,
            )
        )

    def _cleanup_legacy_settings_string(self) -> None:
        if self._key_type(self.settings_key) != "string":
            return
        if not self._has_settings_hashes():
            return
        self.client.delete(self.settings_key)

    def _read_legacy_settings_string(self) -> dict[str, Any] | None:
        if self._key_type(self.settings_key) != "string":
            return None
        raw = self.client.get(self.settings_key)
        if not raw:
            return None
        try:
            settings = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(settings, dict):
            return None
        settings = dict(settings)
        settings.setdefault("editable_fonts", self._read_editable_fonts())
        return settings

    def _read_legacy_editable_font(self) -> dict[str, str] | None:
        key = self._settings_editable_font_key
        key_type = self._key_type(key)
        if key_type == "hash":
            raw = self.client.hgetall(key)
            if raw and all(field in raw for field in EDITABLE_FONT_HASH_FIELDS):
                return {field: str(raw[field]) for field in EDITABLE_FONT_HASH_FIELDS}
        if key_type == "string":
            raw = self.client.get(key)
            if raw:
                try:
                    parsed = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    parsed = None
                if isinstance(parsed, dict):
                    return {
                        field: str(parsed[field])
                        for field in EDITABLE_FONT_HASH_FIELDS
                        if field in parsed
                    }
        return None

    def _read_editable_fonts(self) -> dict[str, dict[str, str]]:
        merged = json.loads(json.dumps(DEFAULT_EDITABLE_FONTS))
        key = self._settings_editable_fonts_key
        key_type = self._key_type(key)
        has_scope_data = False

        if key_type == "hash":
            raw = self.client.hgetall(key)
            for scope_id in EDITABLE_FONT_SCOPE_IDS:
                payload = raw.get(scope_id)
                if not payload:
                    continue
                try:
                    parsed = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(parsed, dict):
                    merged[scope_id] = {**merged[scope_id], **parsed}
                    has_scope_data = True

        if not has_scope_data:
            legacy = self._read_legacy_editable_font()
            if legacy:
                for scope_id in EDITABLE_FONT_SCOPE_IDS:
                    merged[scope_id] = {**merged[scope_id], **legacy}

        return merged

    def _write_editable_fonts_hash(self, pipeline: Any, fonts: dict[str, Any] | None) -> None:
        mapping: dict[str, str] = {}
        source = fonts if isinstance(fonts, dict) else {}
        for scope_id in EDITABLE_FONT_SCOPE_IDS:
            default = DEFAULT_EDITABLE_FONTS[scope_id]
            scope_font = source.get(scope_id)
            if not isinstance(scope_font, dict):
                scope_font = {}
            payload = {field: str(scope_font.get(field, default[field])) for field in EDITABLE_FONT_HASH_FIELDS}
            mapping[scope_id] = json.dumps(payload, ensure_ascii=False)
        self._sync_hash(pipeline, self._settings_editable_fonts_key, mapping)

    def _read_settings_collection(self, key: str) -> list[dict[str, Any]] | None:
        key_type = self._key_type(key)
        if key_type == "none":
            return None
        if key_type != "hash":
            return []

        items: list[dict[str, Any]] = []
        for raw in self.client.hgetall(key).values():
            try:
                item = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(item, dict):
                items.append(item)

        items.sort(key=lambda item: (item.get("position", 0), str(item.get("id", ""))))
        return [{key: value for key, value in item.items() if key != "position"} for item in items]

    def _write_settings_hashes(self, pipeline: Any, settings: dict[str, Any]) -> None:
        self._write_settings_collection(
            pipeline,
            self._settings_card_types_key,
            settings.get("card_types", DEFAULT_DATA["settings"]["card_types"]),
        )
        self._write_settings_collection(
            pipeline,
            self._settings_board_statuses_key,
            settings.get("board_statuses", DEFAULT_DATA["settings"]["board_statuses"]),
        )
        self._write_settings_collection(
            pipeline,
            self._settings_organizations_key,
            settings.get("organizations", DEFAULT_DATA["settings"]["organizations"]),
        )
        self._write_editable_fonts_hash(pipeline, settings.get("editable_fonts"))

    def _write_settings_collection(self, pipeline: Any, key: str, items: list[dict[str, Any]]) -> None:
        mapping: dict[str, str] = {}
        for index, item in enumerate(items):
            item_id = item.get("id")
            if item_id is None:
                continue
            payload = dict(item)
            payload["position"] = index
            mapping[str(item_id)] = json.dumps(payload, ensure_ascii=False)
        self._sync_hash(pipeline, key, mapping)

    def _read_legacy_state(self) -> dict[str, Any]:
        for key in (self._legacy_state_key, f"{self.key_prefix}/state"):
            if self._key_type(key) != "string":
                continue
            try:
                raw_data = self.client.get(key)
                if not raw_data:
                    continue
                data = json.loads(raw_data)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                return _normalize_data(data)
        return {}

    def _sync_hash(self, pipeline: Any, key: str, mapping: dict[str, str]) -> None:
        key_type = self._key_type(key)
        existing_fields = set(self.client.hkeys(key)) if key_type == "hash" else set()
        stale_fields = existing_fields - set(mapping)

        if key_type not in {"none", "hash"}:
            pipeline.delete(key)
        elif stale_fields:
            pipeline.hdel(key, *stale_fields)

        if mapping:
            _pipeline_hset_mapping(pipeline, key, mapping)
        else:
            pipeline.delete(key)

    def _key_type(self, key: str) -> str:
        key_type = self.client.type(key)
        if isinstance(key_type, bytes):
            return key_type.decode("utf-8")
        return str(key_type)


class QuickFallbackStorage:
    def __init__(self, primary: RedisStorage, fallback: JsonStorage) -> None:
        self.primary = primary
        self.fallback = fallback
        self._use_fallback = False

    def read(self) -> dict[str, Any]:
        if self._use_fallback:
            return self.fallback.read()
        try:
            return self.primary.read()
        except Exception:
            self._use_fallback = True
            return self.fallback.read()

    def write(self, data: dict[str, Any]) -> None:
        if self._use_fallback:
            self.fallback.write(data)
            return
        try:
            self.primary.write(data)
        except Exception:
            self._use_fallback = True
            self.fallback.write(data)

    @property
    def using_fallback(self) -> bool:
        return self._use_fallback


def create_storage(config: dict[str, Any]) -> JsonStorage | RedisStorage | QuickFallbackStorage:
    backend = config.get("STORAGE_BACKEND", "auto").strip().lower()
    if backend == "json":
        return JsonStorage(config["STORAGE_FILE"])

    redis_url = config.get("REDIS_URL", "").strip()
    json_path = config.get("STORAGE_FILE", "")

    if redis_url:
        redis_storage = RedisStorage(
            redis_url,
            config.get("REDIS_KEY_PREFIX", "jjob:boardflow:state"),
            float(config.get("REDIS_TIMEOUT_SECONDS", 5)),
            settings_key=config.get("REDIS_SETTINGS_KEY", "jjob:boardflow:settings"),
        )
        if json_path:
            return QuickFallbackStorage(redis_storage, JsonStorage(json_path))
        return redis_storage

    if backend == "redis" and not redis_url:
        raise StorageUnavailable("STORAGE_BACKEND=redis 时必须配置 REDIS_URL")
    return JsonStorage(json_path or "data/boards.json")
