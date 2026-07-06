from __future__ import annotations

import copy
import json
import os
import re
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

from services.org_keys import (
    PERSONAL_BOARD_ORG_NAME,
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
    resolve_org_id,
    split_card_record,
)
from services.storage import DEFAULT_DATA, JsonStorage, RedisStorage, QuickFallbackStorage, _clone_default_data, _normalize_data, _pipeline_hset_mapping
from services.tenant_keys import (
    SUPER_ADMIN_TENANT_TYPE,
    USER_NAMESPACE,
    legacy_settings_user_organizations_key,
    legacy_settings_user_shared_boards_key,
    legacy_settings_user_shared_organizations_key,
    legacy_user_share_inbox_key,
    orgshare_key,
    scope_board_lists_key,
    scope_boards_key,
    scope_card_detail_key,
    scope_list_cards_key,
    scope_list_state_key,
    scope_meta_key,
    settings_users_key,
    tenant_scope_roots,
    user_scope_root,
    user_shared_boards_key,
    user_shared_org_index_key,
    user_organizations_key,
)


class BoardFlowStorage:
    """Multi-tenant storage facade over Redis/JSON backends."""

    def __init__(self, backend: JsonStorage | RedisStorage | QuickFallbackStorage, config: dict[str, Any]) -> None:
        self._backend = backend
        self._config = config
        self._lock = threading.RLock()
        self.key_prefix = (config.get("REDIS_KEY_PREFIX") or "jjob:boardflow").rstrip(":")
        self.settings_key = (config.get("REDIS_SETTINGS_KEY") or f"{self.key_prefix}:settings").rstrip(":")

    @property
    def using_fallback(self) -> bool:
        return bool(getattr(self._backend, "using_fallback", False))

    def ping(self) -> bool:
        if hasattr(self._backend, "ping"):
            return self._backend.ping()
        return True

    def read(self) -> dict[str, Any]:
        return self._backend.read()

    def write(self, data: dict[str, Any]) -> None:
        self._backend.write(data)

    def _resolve_backend(self) -> JsonStorage | RedisStorage:
        if isinstance(self._backend, QuickFallbackStorage):
            return self._backend.primary if not self._backend._use_fallback else self._backend.fallback
        return self._backend

    def _is_redis(self) -> bool:
        return isinstance(self._resolve_backend(), RedisStorage)

    def _redis(self) -> RedisStorage:
        backend = self._resolve_backend()
        if not isinstance(backend, RedisStorage):
            raise RuntimeError("当前存储后端不支持 Redis 多租户操作")
        return backend

    def _json_base_dir(self) -> Path:
        backend = self._resolve_backend()
        if isinstance(backend, JsonStorage):
            return backend.path.parent
        return Path(self._config.get("DATA_DIR") or "data")

    def read_settings(self) -> dict[str, Any]:
        with self._lock:
            if self._is_redis():
                data = self._redis().read()
                return copy.deepcopy(data.get("settings", DEFAULT_DATA["settings"]))
            data = self._read_json_sidecar("settings.json", DEFAULT_DATA["settings"])
            return _normalize_data({"settings": data}).get("settings", DEFAULT_DATA["settings"])

    def write_settings(self, settings: dict[str, Any]) -> None:
        with self._lock:
            if self._is_redis():
                payload = self._redis().read()
                payload["settings"] = settings
                self._redis().write(payload)
                return
            self._write_json_sidecar("settings.json", settings)

    def list_users(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._is_redis():
                return self._redis_hlist(settings_users_key(self.settings_key))
            return self._read_json_sidecar("users.json", [])

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            if self._is_redis():
                raw = self._redis().client.hget(settings_users_key(self.settings_key), user_id)
                return self._loads_dict(raw)
            for user in self.list_users():
                if str(user.get("id")) == str(user_id):
                    return user
            return None

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        normalized = (username or "").strip().lower()
        for user in self.list_users():
            if (user.get("username") or "").strip().lower() == normalized:
                return user
        return None

    def save_user(self, user: dict[str, Any]) -> None:
        with self._lock:
            if self._is_redis():
                key = settings_users_key(self.settings_key)
                self._redis().client.hset(key, user["id"], json.dumps(user, ensure_ascii=False))
                return
            users = self.list_users()
            updated = [item for item in users if item.get("id") != user.get("id")]
            updated.append(user)
            self._write_json_sidecar("users.json", updated)

    def delete_user(self, user_id: str) -> None:
        with self._lock:
            if self._is_redis():
                self._redis().client.hdel(settings_users_key(self.settings_key), user_id)
                return
            users = [item for item in self.list_users() if item.get("id") != user_id]
            self._write_json_sidecar("users.json", users)

    def list_shares(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._is_redis():
                return self._redis_hlist(orgshare_key(self.key_prefix))
            return self._read_json_sidecar("shares.json", [])

    def get_share(self, share_id: str) -> dict[str, Any] | None:
        with self._lock:
            if self._is_redis():
                raw = self._redis().client.hget(orgshare_key(self.key_prefix), share_id)
                return self._loads_dict(raw)
            for share in self.list_shares():
                if share.get("id") == share_id:
                    return share
            return None

    def save_share(self, share: dict[str, Any]) -> None:
        with self._lock:
            if self._is_redis():
                redis = self._redis()
                redis.client.hset(orgshare_key(self.key_prefix), share["id"], json.dumps(share, ensure_ascii=False))
                return
            shares = [item for item in self.list_shares() if item.get("id") != share.get("id")]
            shares.append(share)
            self._write_json_sidecar("shares.json", shares)

    def delete_share(self, share_id: str) -> None:
        with self._lock:
            if self._is_redis():
                redis = self._redis()
                redis.client.hdel(orgshare_key(self.key_prefix), share_id)
                return
            shares = [item for item in self.list_shares() if item.get("id") != share_id]
            self._write_json_sidecar("shares.json", shares)

    def list_shares_for_grantee(self, grantee_user_id: str) -> list[dict[str, Any]]:
        return [
            share
            for share in self.list_shares()
            if str(share.get("grantee_user_id")) == str(grantee_user_id)
        ]

    def list_legacy_user_org_entries(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            if self._is_redis():
                items = self._redis_hlist(legacy_settings_user_organizations_key(self.settings_key, user_id))
            else:
                items = self._read_json_sidecar(f"user_orgs_{user_id}.json", [])
            return items

    def list_user_organizations(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            if self._is_redis():
                items = self._redis_hlist(user_organizations_key(user_id))
            else:
                items = self._read_json_sidecar(f"user_organizations_{user_id}.json", [])
            return sorted(items, key=lambda item: (item.get("position", 0), item.get("name") or ""))

    def write_user_organizations(self, user_id: str, organizations: list[dict[str, Any]]) -> None:
        mapping: dict[str, str] = {}
        for item in organizations:
            org_id = str(item.get("id") or "")
            if not org_id:
                continue
            mapping[org_id] = json.dumps(item, ensure_ascii=False)
        with self._lock:
            if self._is_redis():
                redis = self._redis()
                key = user_organizations_key(user_id)
                existing = set(redis.client.hkeys(key))
                desired = set(mapping.keys())
                if existing - desired:
                    redis.client.hdel(key, *list(existing - desired))
                if mapping:
                    self._hset_mapping(redis.client, key, mapping)
                elif existing:
                    redis.client.delete(key)
                return
            self._write_json_sidecar(f"user_organizations_{user_id}.json", organizations)

    def _hset_mapping(self, client: Any, key: str, mapping: dict[str, str]) -> None:
        for field, value in mapping.items():
            client.hset(key, field, value)

    def list_user_shared_boards(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            if self._is_redis():
                items = self._redis_hlist(user_shared_boards_key(user_id))
            else:
                items = self._read_json_sidecar(f"user_shared_boards_{user_id}.json", [])
            return sorted(items, key=lambda item: (item.get("owner_display_name") or "", item.get("board_title") or ""))

    def write_user_shared_boards(self, user_id: str, boards: list[dict[str, Any]]) -> None:
        mapping: dict[str, str] = {}
        for item in boards:
            entry_id = str(item.get("id") or "")
            if not entry_id:
                continue
            mapping[entry_id] = json.dumps(item, ensure_ascii=False)
        with self._lock:
            if self._is_redis():
                redis = self._redis()
                key = user_shared_boards_key(user_id)
                existing = set(redis.client.hkeys(key))
                desired = set(mapping.keys())
                if existing - desired:
                    redis.client.hdel(key, *list(existing - desired))
                if mapping:
                    self._hset_mapping(redis.client, key, mapping)
                elif existing:
                    redis.client.delete(key)
                return
            self._write_json_sidecar(f"user_shared_boards_{user_id}.json", boards)

    def list_user_shared_org_index(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            if self._is_redis():
                items = self._redis_hlist(user_shared_org_index_key(user_id))
            else:
                items = self._read_json_sidecar(f"user_shared_org_index_{user_id}.json", [])
            return sorted(items, key=lambda item: (item.get("owner_display_name") or "", item.get("organization") or ""))

    def write_user_shared_org_index(self, user_id: str, org_entries: list[dict[str, Any]]) -> None:
        mapping: dict[str, str] = {}
        for item in org_entries:
            entry_id = str(item.get("id") or "")
            if not entry_id:
                continue
            mapping[entry_id] = json.dumps(item, ensure_ascii=False)
        with self._lock:
            if self._is_redis():
                redis = self._redis()
                key = user_shared_org_index_key(user_id)
                existing = set(redis.client.hkeys(key))
                desired = set(mapping.keys())
                if existing - desired:
                    redis.client.hdel(key, *list(existing - desired))
                if mapping:
                    self._hset_mapping(redis.client, key, mapping)
                elif existing:
                    redis.client.delete(key)
                return
            self._write_json_sidecar(f"user_shared_org_index_{user_id}.json", org_entries)

    def delete_legacy_user_index_keys(self, user_id: str) -> None:
        with self._lock:
            if not self._is_redis():
                for filename in (f"user_orgs_{user_id}.json", f"user_shared_orgs_{user_id}.json"):
                    path = self._json_base_dir() / filename
                    if path.exists():
                        path.unlink()
                return
            redis = self._redis()
            for key in (
                legacy_settings_user_organizations_key(self.settings_key, user_id),
                legacy_settings_user_shared_organizations_key(self.settings_key, user_id),
                legacy_settings_user_shared_boards_key(self.settings_key, user_id),
                legacy_user_share_inbox_key(user_id),
            ):
                redis.client.delete(key)

    def migrate_legacy_user_index_keys(self, user_id: str) -> None:
        with self._lock:
            if self._is_redis():
                current = self.list_user_shared_boards(user_id)
                if not current:
                    legacy_items = self._redis_hlist(
                        legacy_settings_user_shared_boards_key(self.settings_key, user_id)
                    )
                    if legacy_items:
                        self.write_user_shared_boards(user_id, legacy_items)
            self.delete_legacy_user_index_keys(user_id)

    def delete_user_settings(self, user_id: str) -> None:
        self.delete_legacy_user_index_keys(user_id)

    def ensure_tenant(self, tenant_ctx: dict[str, Any]) -> None:
        with self._lock:
            settings = self.read_settings()
            data = self.read_tenant(tenant_ctx, settings)
            if data.get("boards") or (data.get("meta") or {}).get("next_board_id"):
                return
            data["meta"] = _clone_default_data()["meta"]
            self.write_tenant(tenant_ctx, data, settings)

    def delete_user_tenant(self, user_id: str) -> None:
        with self._lock:
            if self._is_redis():
                redis = self._redis()
                scope_root = user_scope_root(user_id)
                for key in redis.client.scan_iter(match=f"{scope_root}*", count=200):
                    redis.client.delete(key)
                self.delete_legacy_user_index_keys(user_id)
                return
            path = self._json_base_dir() / "tenants" / f"{user_id}.json"
            if path.exists():
                path.unlink()

    def read_tenant(self, tenant_ctx: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            settings = settings or self.read_settings()
            if self._is_redis():
                return self._read_tenant_redis(tenant_ctx, settings)
            return self._read_tenant_json(tenant_ctx)

    def write_tenant(self, tenant_ctx: dict[str, Any], data: dict[str, Any], settings: dict[str, Any] | None = None) -> None:
        with self._lock:
            settings = settings or self.read_settings()
            normalized = _normalize_data({**data, "settings": settings})
            tenant_payload = {
                "boards": normalized.get("boards", []),
                "lists": normalized.get("lists", []),
                "cards": normalized.get("cards", []),
                "meta": normalized.get("meta", {}),
            }
            if self._is_redis():
                self._write_tenant_redis(tenant_ctx, tenant_payload, settings)
                return
            self._write_tenant_json(tenant_ctx, tenant_payload)

    def _read_tenant_redis(self, tenant_ctx: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        redis = self._redis()
        if tenant_ctx.get("type") == SUPER_ADMIN_TENANT_TYPE:
            boards, lists, cards, meta = redis._read_org_scoped(settings)
            return {"boards": boards, "lists": lists, "cards": cards, "meta": meta}

        scope_root = tenant_ctx.get("scope_root") or user_scope_root(tenant_ctx["id"])
        return self._read_scope_bundle(redis, scope_root)

    def _write_tenant_redis(self, tenant_ctx: dict[str, Any], data: dict[str, Any], settings: dict[str, Any]) -> None:
        redis = self._redis()
        pipeline = redis.client.pipeline()
        if tenant_ctx.get("type") == SUPER_ADMIN_TENANT_TYPE:
            buckets = group_entities_by_org({**data, "settings": settings})
            redis._write_org_scoped(pipeline, buckets, data.get("meta", {}), settings)
            pipeline.execute()
            return

        scope_root = tenant_ctx.get("scope_root") or user_scope_root(tenant_ctx["id"])
        self._write_scope_bundle(redis, pipeline, scope_root, data)
        pipeline.execute()

    def _read_scope_bundle(self, redis: RedisStorage, scope_root: str) -> dict[str, Any]:
        boards = self._read_scope_boards(redis, scope_root)
        lists = self._read_scope_lists(redis, scope_root, boards)
        cards = self._read_scope_cards(redis, scope_root, lists)
        meta = redis._read_hash_meta(scope_meta_key(scope_root))
        return {"boards": boards, "lists": lists, "cards": cards, "meta": meta or _clone_default_data()["meta"]}

    def _write_scope_bundle(self, redis: RedisStorage, pipeline: Any, scope_root: str, data: dict[str, Any]) -> None:
        boards = data.get("boards", [])
        lists = data.get("lists", [])
        cards = data.get("cards", [])
        meta = data.get("meta", {})

        board_mapping = {
            str(item["id"]): json.dumps(item, ensure_ascii=False)
            for item in boards
            if item.get("id") is not None
        }
        redis._sync_hash(pipeline, scope_boards_key(scope_root), board_mapping)

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

        for board_id in set(board_mapping.keys()):
            board_lists = lists_by_board.get(board_id, [])
            list_mapping = {
                str(item["id"]): json.dumps(item, ensure_ascii=False)
                for item in board_lists
                if item.get("id") is not None
            }
            redis._sync_hash(pipeline, scope_board_lists_key(scope_root, board_id), list_mapping)
            for list_id in list_mapping:
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
                    self._sync_scope_card_detail(pipeline, scope_root, board_id, list_id, card_id, detail)
                redis._sync_hash(pipeline, scope_list_cards_key(scope_root, board_id, list_id), card_core_mapping)
                redis._sync_hash(pipeline, scope_list_state_key(scope_root, board_id, list_id), card_state_mapping)
                self._cleanup_scope_card_details(redis, pipeline, scope_root, board_id, list_id, active_card_ids)

        pipeline.delete(scope_meta_key(scope_root))
        if meta:
            _pipeline_hset_mapping(
                pipeline,
                scope_meta_key(scope_root),
                {key: str(value) for key, value in meta.items()},
            )

    def _read_scope_boards(self, redis: RedisStorage, scope_root: str) -> list[dict[str, Any]]:
        return redis._read_entity_hash(scope_boards_key(scope_root))

    def _read_scope_lists(self, redis: RedisStorage, scope_root: str, boards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        lists: list[dict[str, Any]] = []
        board_ids = {str(board.get("id")) for board in boards if board.get("id") is not None}
        pattern = re.compile(rf"^{re.escape(scope_root)}:boards:([^:]+):lists$")
        discovered = set(board_ids)
        for key in redis.client.scan_iter(match=f"{scope_root}:boards:*:lists", count=200):
            matched = pattern.match(key)
            if matched:
                discovered.add(matched.group(1))
        for board_id in sorted(discovered):
            lists.extend(redis._read_entity_hash(scope_board_lists_key(scope_root, board_id)))
        return lists

    def _read_scope_cards(self, redis: RedisStorage, scope_root: str, lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for lst in lists:
            board_id = str(lst.get("board_id") or "")
            list_id = str(lst.get("id") or "")
            if not board_id or not list_id:
                continue
            card_cores = {
                str(item.get("id")): item
                for item in redis._read_entity_hash(scope_list_cards_key(scope_root, board_id, list_id))
                if item.get("id") is not None
            }
            card_states = {
                str(item.get("id")): item
                for item in redis._read_entity_hash(scope_list_state_key(scope_root, board_id, list_id))
                if item.get("id") is not None
            }
            for card_id, core in card_cores.items():
                detail = self._read_scope_card_detail(redis, scope_root, board_id, list_id, card_id)
                cards.append(merge_card_record(core, card_states.get(card_id, {}), detail))
        return cards

    def _read_scope_card_detail(
        self,
        redis: RedisStorage,
        scope_root: str,
        board_id: str,
        list_id: str,
        card_id: str,
    ) -> dict[str, Any]:
        return redis._read_detail_hash(scope_card_detail_key(scope_root, board_id, list_id, card_id), card_id)

    def _sync_scope_card_detail(
        self,
        pipeline: Any,
        scope_root: str,
        board_id: str,
        list_id: str,
        card_id: str,
        detail: dict[str, Any],
    ) -> None:
        key = scope_card_detail_key(scope_root, board_id, list_id, card_id)
        payload = {field: value for field, value in detail.items() if field != "id" and value is not None}
        if not payload:
            pipeline.delete(key)
            return
        serialized = {field: json.dumps(value, ensure_ascii=False) for field, value in payload.items()}
        pipeline.delete(key)
        _pipeline_hset_mapping(pipeline, key, serialized)

    def _cleanup_scope_card_details(
        self,
        redis: RedisStorage,
        pipeline: Any,
        scope_root: str,
        board_id: str,
        list_id: str,
        active_card_ids: set[str],
    ) -> None:
        prefix = f"{scope_root}:boards:{board_id}:lists:{list_id}:detail:"
        for key in redis.client.scan_iter(match=f"{prefix}*", count=200):
            card_id = key.rsplit(":", 1)[-1]
            if card_id not in active_card_ids:
                pipeline.delete(key)

    def _read_tenant_json(self, tenant_ctx: dict[str, Any]) -> dict[str, Any]:
        if tenant_ctx.get("type") == SUPER_ADMIN_TENANT_TYPE:
            return _normalize_data(self._backend.read())
        path = self._json_base_dir() / "tenants" / f"{tenant_ctx['id']}.json"
        if not path.exists():
            return _clone_default_data()
        with path.open("r", encoding="utf-8") as file:
            return _normalize_data(json.load(file))

    def _write_tenant_json(self, tenant_ctx: dict[str, Any], data: dict[str, Any]) -> None:
        if tenant_ctx.get("type") == SUPER_ADMIN_TENANT_TYPE:
            payload = self._backend.read()
            payload.update(data)
            self._backend.write(payload)
            return
        path = self._json_base_dir() / "tenants" / f"{tenant_ctx['id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(_normalize_data(data), file, ensure_ascii=False, indent=2)
            file.write("\n")

    def _read_json_sidecar(self, filename: str, default: Any) -> Any:
        path = self._json_base_dir() / filename
        if not path.exists():
            return copy.deepcopy(default)
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _write_json_sidecar(self, filename: str, payload: Any) -> None:
        path = self._json_base_dir() / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(tmp, path)

    def _redis_hlist(self, key: str) -> list[dict[str, Any]]:
        redis = self._redis()
        if redis._key_type(key) != "hash":
            return []
        items: list[dict[str, Any]] = []
        for raw in redis.client.hgetall(key).values():
            parsed = self._loads_dict(raw)
            if parsed:
                items.append(parsed)
        return items

    def replace_all_shares(self, shares: list[dict[str, Any]]) -> None:
        with self._lock:
            if self._is_redis():
                redis = self._redis()
                redis.client.delete(orgshare_key(self.key_prefix))
            else:
                self._write_json_sidecar("shares.json", [])
            for share in shares:
                self.save_share(share)

    def export_full_snapshot(self) -> dict[str, Any]:
        settings = copy.deepcopy(self.read_settings())
        settings["organizations"] = [
            org
            for org in settings.get("organizations") or []
            if (org.get("created_by_type") or SUPER_ADMIN_TENANT_TYPE) == SUPER_ADMIN_TENANT_TYPE
        ]
        super_ctx = {
            "type": SUPER_ADMIN_TENANT_TYPE,
            "id": "super_admin",
            "scope_mode": "org_multi",
        }
        super_admin_tenant = copy.deepcopy(self.read_tenant(super_ctx, settings))
        users_payload: list[dict[str, Any]] = []
        for user in self.list_users():
            user_id = str(user.get("id") or "")
            if not user_id:
                continue
            user_ctx = {
                "type": "user",
                "id": user_id,
                "scope_mode": "user_single",
                "scope_root": user_scope_root(user_id),
            }
            tenant = copy.deepcopy(self.read_tenant(user_ctx, settings))
            users_payload.append(
                {
                    "profile": copy.deepcopy(user),
                    "tenant": tenant,
                    "organizations": copy.deepcopy(self.list_user_organizations(user_id)),
                    "shared_boards": copy.deepcopy(self.list_user_shared_boards(user_id)),
                    "shared_org_index": copy.deepcopy(self.list_user_shared_org_index(user_id)),
                }
            )
        return {
            "settings": settings,
            "super_admin_tenant": super_admin_tenant,
            "users": users_payload,
            "shares": copy.deepcopy(self.list_shares()),
        }

    def import_full_snapshot(self, snapshot: dict[str, Any]) -> None:
        settings = copy.deepcopy(snapshot.get("settings") or DEFAULT_DATA["settings"])
        global_orgs = settings.get("organizations") or []
        settings["organizations"] = [
            org for org in global_orgs if (org.get("created_by_type") or SUPER_ADMIN_TENANT_TYPE) == SUPER_ADMIN_TENANT_TYPE
        ]
        self.write_settings(settings)

        super_ctx = {
            "type": SUPER_ADMIN_TENANT_TYPE,
            "id": "super_admin",
            "scope_mode": "org_multi",
        }
        super_tenant = snapshot.get("super_admin_tenant") or {}
        self.write_tenant(
            super_ctx,
            {
                "boards": super_tenant.get("boards") or [],
                "lists": super_tenant.get("lists") or [],
                "cards": super_tenant.get("cards") or [],
                "meta": super_tenant.get("meta") or _clone_default_data()["meta"],
            },
            settings,
        )

        incoming_ids: set[str] = set()
        for entry in snapshot.get("users") or []:
            profile = entry.get("profile") or {}
            user_id = str(profile.get("id") or "")
            if not user_id:
                continue
            incoming_ids.add(user_id)
            self.save_user(profile)
            user_ctx = {
                "type": "user",
                "id": user_id,
                "scope_mode": "user_single",
                "scope_root": user_scope_root(user_id),
            }
            tenant = entry.get("tenant") or {}
            user_orgs = copy.deepcopy(entry.get("organizations") or [])
            if not user_orgs:
                user_orgs = [
                    copy.deepcopy(org)
                    for org in global_orgs
                    if org.get("created_by_type") == USER_TENANT_TYPE
                    and str(org.get("created_by_id") or "") == user_id
                ]
            self.write_user_organizations(user_id, user_orgs)
            self.write_tenant(
                user_ctx,
                {
                    "boards": tenant.get("boards") or [],
                    "lists": tenant.get("lists") or [],
                    "cards": tenant.get("cards") or [],
                    "meta": tenant.get("meta") or _clone_default_data()["meta"],
                },
                settings,
            )
            self.write_user_shared_boards(user_id, entry.get("shared_boards") or [])
            self.write_user_shared_org_index(user_id, entry.get("shared_org_index") or [])

        for existing in self.list_users():
            existing_id = str(existing.get("id") or "")
            if existing_id and existing_id not in incoming_ids:
                self.delete_user_tenant(existing_id)

        self.replace_all_shares(snapshot.get("shares") or [])

    def _iter_tenant_contexts(self, settings: dict[str, Any] | None = None) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        settings = settings or self.read_settings()
        contexts: list[tuple[dict[str, Any], dict[str, Any]]] = []
        super_ctx = {
            "type": SUPER_ADMIN_TENANT_TYPE,
            "id": "super_admin",
            "scope_mode": "org_multi",
        }
        contexts.append((super_ctx, copy.deepcopy(self.read_tenant(super_ctx, settings))))
        for user in self.list_users():
            user_id = str(user.get("id") or "")
            if not user_id:
                continue
            user_ctx = {
                "type": "user",
                "id": user_id,
                "scope_mode": "user_single",
                "scope_root": user_scope_root(user_id),
            }
            contexts.append((user_ctx, copy.deepcopy(self.read_tenant(user_ctx, settings))))
        return contexts

    def _organizations_for_owner(
        self,
        owner_type: str | None,
        owner_id: str | None,
        settings: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if owner_type == USER_TENANT_TYPE and owner_id:
            return self.list_user_organizations(str(owner_id))
        return [
            org
            for org in settings.get("organizations") or []
            if (org.get("created_by_type") or SUPER_ADMIN_TENANT_TYPE) == SUPER_ADMIN_TENANT_TYPE
        ]

    def export_organization_bundle(
        self,
        org_id: str,
        *,
        owner_type: str | None = None,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        settings = copy.deepcopy(self.read_settings())
        organizations = self._organizations_for_owner(owner_type, owner_id, settings)
        organization = next((item for item in organizations if str(item.get("id")) == org_id), None)
        org_name = (organization or {}).get("name") or ""
        if not organization and org_id == PERSONAL_ORG_ID:
            organization = {"id": PERSONAL_ORG_ID, "name": PERSONAL_BOARD_ORG_NAME, "note": "内置个人看板组织"}
            org_name = PERSONAL_BOARD_ORG_NAME

        def board_matches(board: dict[str, Any], tenant_ctx: dict[str, Any]) -> bool:
            tenant_type = str(tenant_ctx.get("type") or SUPER_ADMIN_TENANT_TYPE)
            tenant_id = str(tenant_ctx.get("id") or "super_admin")
            resolved = resolve_org_id(
                board.get("organization"),
                organizations,
                created_by_type=tenant_type,
                created_by_id=tenant_id,
            )
            board_org_name = (board.get("organization") or "").strip()
            return resolved == org_id or (org_name and board_org_name == org_name)

        boards: list[dict[str, Any]] = []
        lists: list[dict[str, Any]] = []
        cards: list[dict[str, Any]] = []
        board_owners: dict[str, dict[str, str]] = {}

        tenant_contexts = self._iter_tenant_contexts(settings)
        if owner_type and owner_id:
            tenant_contexts = [
                (ctx, data)
                for ctx, data in tenant_contexts
                if str(ctx.get("type") or "") == str(owner_type)
                and str(ctx.get("id") or "") == str(owner_id)
            ]

        for tenant_ctx, tenant_data in tenant_contexts:
            board_ids: set[str] = set()
            for board in tenant_data.get("boards") or []:
                if board.get("id") is None:
                    continue
                if board_matches(board, tenant_ctx):
                    board_id = str(board["id"])
                    board_ids.add(board_id)
                    boards.append(copy.deepcopy(board))
                    board_owners[board_id] = {
                        "type": str(tenant_ctx.get("type") or SUPER_ADMIN_TENANT_TYPE),
                        "id": str(tenant_ctx.get("id") or "super_admin"),
                    }
            for lst in tenant_data.get("lists") or []:
                if str(lst.get("board_id")) in board_ids:
                    lists.append(copy.deepcopy(lst))
            for card in tenant_data.get("cards") or []:
                if str(card.get("board_id")) in board_ids:
                    cards.append(copy.deepcopy(card))

        return {
            "organization": copy.deepcopy(organization or {"id": org_id, "name": org_name or org_id, "note": ""}),
            "boards": boards,
            "lists": lists,
            "cards": cards,
            "board_owners": board_owners,
        }

    def iter_clear_all_system_data(self) -> Iterator[dict[str, Any]]:
        def emit(step: str, message: str, percent: int, *, done: bool = False) -> dict[str, Any]:
            return {"step": step, "message": message, "percent": max(0, min(100, percent)), "done": done}

        with self._lock:
            users = self.list_users()
            user_ids = [str(user.get("id")) for user in users if user.get("id")]
            total_units = max(len(user_ids) + 4, 1)
            completed = 0

            yield emit("prepare", f"准备清理，共 {len(user_ids)} 个用户账号", 0)

            for index, user_id in enumerate(user_ids, start=1):
                username = next(
                    (user.get("username") or user.get("display_name") for user in users if str(user.get("id")) == user_id),
                    user_id,
                )
                self.delete_user_tenant(user_id)
                self.delete_user(user_id)
                completed += 1
                yield emit(
                    "users",
                    f"已清理用户 {username} ({index}/{len(user_ids)})",
                    int(completed / total_units * 100),
                )

            completed += 1
            yield emit("shares", "正在清理分享记录…", int(completed / total_units * 100))
            if self._is_redis():
                self._redis().client.delete(orgshare_key(self.key_prefix))
            else:
                self._write_json_sidecar("shares.json", [])

            completed += 1
            yield emit("tenants", "正在清理看板与组织数据…", int(completed / total_units * 100))
            if self._is_redis():
                redis = self._redis()
                for pattern, label in (
                    (f"{ORG_NAMESPACE}:*", "组织"),
                    (f"{USER_NAMESPACE}:*", "用户空间"),
                    (f"{self.settings_key}:user:*", "旧版用户索引"),
                ):
                    deleted = 0
                    batch: list[str] = []
                    for key in redis.client.scan_iter(match=pattern, count=200):
                        batch.append(key)
                        if len(batch) >= 100:
                            redis.client.delete(*batch)
                            deleted += len(batch)
                            batch = []
                    if batch:
                        redis.client.delete(*batch)
                        deleted += len(batch)
                    if deleted:
                        yield emit(
                            "tenants",
                            f"已删除 {deleted} 个{label} Redis 键",
                            int(completed / total_units * 100),
                        )
                pipeline = redis.client.pipeline()
                redis._delete_legacy_flat_keys(pipeline)
                pipeline.execute()
                redis.client.delete(settings_users_key(self.settings_key))
            else:
                tenants_dir = self._json_base_dir() / "tenants"
                if tenants_dir.exists():
                    for path in tenants_dir.glob("*.json"):
                        path.unlink()
                for pattern in ("user_orgs_*.json", "user_shared_orgs_*.json", "user_shared_boards_*.json", "user_shared_org_index_*.json"):
                    for path in self._json_base_dir().glob(pattern):
                        path.unlink()
                self._write_json_sidecar("users.json", [])
                if isinstance(self._resolve_backend(), JsonStorage):
                    self._backend.write(_clone_default_data())

            completed += 1
            default_settings = copy.deepcopy(DEFAULT_DATA["settings"])
            yield emit("settings", "正在恢复默认系统设置…", int(completed / total_units * 100))
            self.write_settings(default_settings)

            super_ctx = {
                "type": SUPER_ADMIN_TENANT_TYPE,
                "id": "super_admin",
                "scope_mode": "org_multi",
            }
            empty = _clone_default_data()
            self.write_tenant(
                super_ctx,
                {
                    "boards": [],
                    "lists": [],
                    "cards": [],
                    "meta": empty["meta"],
                },
                default_settings,
            )

            yield emit("done", "所有系统数据已清理完成", 100, done=True)

    @staticmethod
    def _loads_dict(raw: str | None) -> dict[str, Any] | None:
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None


def create_boardflow_storage(config: dict[str, Any]):
    from services.storage import create_storage

    backend = create_storage(config)
    return BoardFlowStorage(backend, config)
