"""多平台看板对比编排：会话管理与渐进式 NDJSON 事件流。"""

from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator

from config import read_app_version
from services.compare_diff import (
    build_board_compare_result,
    diff_board_meta,
    diff_cards,
    diff_lists,
)
from services.compare_remote_client import CompareRemoteClient, CompareRemoteError
from services.federation_service import (
    DEFAULT_ACCOUNTS_PAGE_SIZE,
    DEFAULT_BOARDS_PAGE_SIZE,
    FEDERATION_API_VERSION,
    load_board_compare_snapshot,
    paginate_federation_accounts,
    paginate_federation_boards,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_match_mode(value: str | None) -> str:
    mode = (value or "manual").strip().lower()
    if mode in ("manual", "by_title", "by_id"):
        return mode
    raise ValueError("match_mode 必须是 manual、by_title 或 by_id")


def _normalize_board_ref(raw: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    tenant_type = (raw.get("tenant_type") or "").strip()
    tenant_id = (raw.get("tenant_id") or "").strip()
    board_id = str(raw.get("board_id") or "").strip()
    if not tenant_type or not tenant_id or not board_id:
        return None
    return {
        "tenant_type": tenant_type,
        "tenant_id": tenant_id,
        "board_id": board_id,
    }


def _normalize_pairs(raw_pairs: Any) -> list[dict[str, dict[str, str]]]:
    if not isinstance(raw_pairs, list):
        return []
    pairs: list[dict[str, dict[str, str]]] = []
    for item in raw_pairs:
        if not isinstance(item, dict):
            continue
        local = _normalize_board_ref(item.get("local"))
        remote = _normalize_board_ref(item.get("remote"))
        if local and remote:
            pairs.append({"local": local, "remote": remote})
    return pairs


def _account_key(account: dict[str, Any]) -> tuple[str, str]:
    return (str(account.get("tenant_type") or ""), str(account.get("tenant_id") or ""))


def _account_map_key(tenant_type: str, tenant_id: str) -> str:
    return f"{tenant_type}:{tenant_id}"


def _lookup_remote_account(
    account_remote_map: dict[Any, Any],
    tenant_type: str,
    tenant_id: str,
) -> dict[str, Any] | None:
    string_key = _account_map_key(tenant_type, tenant_id)
    if string_key in account_remote_map:
        value = account_remote_map.get(string_key)
        return value if isinstance(value, dict) else None
    tuple_key = (tenant_type, tenant_id)
    value = account_remote_map.get(tuple_key)
    return value if isinstance(value, dict) else None


def _format_remote_sync_error(error: CompareRemoteError) -> str:
    message = str(error)
    if "404" in message or "405" in message:
        return (
            f"{message}。"
            "远程实例需部署 v0.2.6+ 且设置 FEDERATION_COMPARE_ENABLED=1 才支持看板同步写入。"
        )
    return message


def _match_accounts(local_accounts: list[dict[str, Any]], remote_accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    remote_map = {_account_key(item): item for item in remote_accounts}
    local_keys = set()
    pairs: list[dict[str, Any]] = []

    for local in local_accounts:
        key = _account_key(local)
        local_keys.add(key)
        remote = remote_map.get(key)
        if remote:
            pairs.append({"status": "matched", "local": local, "remote": remote})
        else:
            pairs.append({"status": "only_local", "local": local, "remote": None})

    for remote in remote_accounts:
        key = _account_key(remote)
        if key not in local_keys:
            pairs.append({"status": "only_remote", "local": None, "remote": remote})
    return pairs


def _normalize_title_key(title: str, organization: str) -> str:
    return f"{(title or '').strip().lower()}::{(organization or '').strip().lower()}"


def _queue_board_pairs_for_account(
    *,
    match_mode: str,
    manual_pairs: list[dict[str, dict[str, str]]],
    local_boards: list[dict[str, Any]],
    remote_boards: list[dict[str, Any]],
    tenant_type: str,
    tenant_id: str,
) -> list[dict[str, Any]]:
    if match_mode == "manual":
        queued: list[dict[str, Any]] = []
        for pair in manual_pairs:
            local = pair["local"]
            remote = pair["remote"]
            if local["tenant_type"] != tenant_type or local["tenant_id"] != tenant_id:
                continue
            queued.append(
                {
                    "match_mode": "manual",
                    "local_board_id": local["board_id"],
                    "remote_board_id": remote["board_id"],
                    "local": local,
                    "remote": remote,
                }
            )
        return queued

    remote_by_id = {str(item.get("id")): item for item in remote_boards}
    remote_by_title: dict[str, list[dict[str, Any]]] = {}
    for board in remote_boards:
        key = _normalize_title_key(board.get("title") or "", board.get("organization") or "")
        remote_by_title.setdefault(key, []).append(board)

    queued = []
    matched_remote_ids: set[str] = set()
    for local_board in local_boards:
        local_id = str(local_board.get("id"))
        remote_board = None
        if match_mode == "by_id":
            remote_board = remote_by_id.get(local_id)
        else:
            title_key = _normalize_title_key(local_board.get("title") or "", local_board.get("organization") or "")
            candidates = remote_by_title.get(title_key) or []
            if len(candidates) == 1:
                remote_board = candidates[0]

        if not remote_board:
            queued.append(
                {
                    "match_mode": match_mode,
                    "local_board_id": local_id,
                    "remote_board_id": None,
                    "status": "only_local",
                    "local_title": local_board.get("title") or "",
                    "local_organization": local_board.get("organization") or "",
                }
            )
            continue

        remote_id = str(remote_board.get("id"))
        matched_remote_ids.add(remote_id)
        queued.append(
            {
                "match_mode": match_mode,
                "local_board_id": local_id,
                "remote_board_id": remote_id,
                "status": "matched",
                "local_title": local_board.get("title") or "",
                "remote_title": remote_board.get("title") or "",
                "local_organization": local_board.get("organization") or "",
                "remote_organization": remote_board.get("organization") or "",
            }
        )

    for remote_board in remote_boards:
        remote_id = str(remote_board.get("id"))
        if remote_id in matched_remote_ids:
            continue
        queued.append(
            {
                "match_mode": match_mode,
                "local_board_id": None,
                "remote_board_id": remote_id,
                "status": "only_remote",
                "remote_title": remote_board.get("title") or "",
                "remote_organization": remote_board.get("organization") or "",
            }
        )
    return queued


def _queue_boards_for_unmatched_account(
    *,
    account_status: str,
    boards: list[dict[str, Any]],
    match_mode: str,
) -> list[dict[str, Any]]:
    queued: list[dict[str, Any]] = []
    for board in boards:
        board_id = str(board.get("id"))
        if account_status == "only_remote":
            queued.append(
                {
                    "match_mode": match_mode,
                    "local_board_id": None,
                    "remote_board_id": board_id,
                    "status": "only_remote",
                    "remote_title": board.get("title") or "",
                    "remote_organization": board.get("organization") or "",
                }
            )
        elif account_status == "only_local":
            queued.append(
                {
                    "match_mode": match_mode,
                    "local_board_id": board_id,
                    "remote_board_id": None,
                    "status": "only_local",
                    "local_title": board.get("title") or "",
                    "local_organization": board.get("organization") or "",
                }
            )
    return queued


def _build_account_remote_map(account_pairs: list[dict[str, Any]]) -> dict[str, Any]:
    account_remote_map: dict[str, Any] = {}
    for pair in account_pairs:
        status = pair.get("status") or "matched"
        if status == "matched" and pair.get("local") and pair.get("remote"):
            account_remote_map[
                _account_map_key(
                    str(pair["local"].get("tenant_type") or ""),
                    str(pair["local"].get("tenant_id") or ""),
                )
            ] = pair["remote"]
        elif status == "only_remote" and pair.get("remote"):
            remote = pair["remote"]
            account_remote_map[
                _account_map_key(
                    str(remote.get("tenant_type") or ""),
                    str(remote.get("tenant_id") or ""),
                )
            ] = remote
        elif status == "only_local" and pair.get("local"):
            local = pair["local"]
            account_remote_map[
                _account_map_key(
                    str(local.get("tenant_type") or ""),
                    str(local.get("tenant_id") or ""),
                )
            ] = local
    return account_remote_map


class CompareService:
    def __init__(self, config: dict[str, Any], storage) -> None:
        self.config = config
        self.storage = storage
        self._lock = threading.RLock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self.accounts_page_size = int(config.get("COMPARE_ACCOUNTS_PAGE_SIZE") or DEFAULT_ACCOUNTS_PAGE_SIZE)
        self.boards_page_size = int(config.get("COMPARE_BOARDS_PAGE_SIZE") or DEFAULT_BOARDS_PAGE_SIZE)
        self.session_ttl_sec = int(config.get("COMPARE_SESSION_TTL_SEC") or 3600)
        self.results_page_size = int(config.get("COMPARE_RESULTS_PAGE_SIZE") or 20)

    def _purge_expired_sessions(self) -> None:
        now = time.time()
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if float(session.get("expires_at") or 0) <= now
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        remote_base_url = (payload.get("remote_base_url") or "").strip()
        remote_token = (payload.get("remote_token") or "").strip()
        match_mode = _normalize_match_mode(payload.get("match_mode"))
        pairs = _normalize_pairs(payload.get("pairs"))
        options = {
            "compare_lists": True,
            "compare_cards": True,
            "compare_card_description": False,
            **copy.deepcopy(payload.get("options") or {}),
        }

        client = CompareRemoteClient(self.config, remote_base_url, remote_token)
        try:
            remote_health = client.health()
        except CompareRemoteError as error:
            raise ValueError(str(error)) from error

        federation = remote_health.get("federation") or {}
        if not federation.get("enabled"):
            raise ValueError("远程实例未启用联邦对比 API")
        remote_api_version = int(federation.get("api_version") or 0)
        if remote_api_version != FEDERATION_API_VERSION:
            raise ValueError(f"远程联邦 API 版本不兼容：{remote_api_version}")

        session_id = str(uuid.uuid4())
        now = time.time()
        session = {
            "session_id": session_id,
            "created_at": _now_iso(),
            "phase": "init",
            "remote_base_url": client.base_url,
            "remote_token": remote_token,
            "match_mode": match_mode,
            "pairs": pairs,
            "options": options,
            "remote_health": remote_health,
            "local_version": read_app_version(),
            "progress": {
                "percent": 0,
                "step": "init",
                "local_accounts": [],
                "remote_accounts": [],
                "account_pairs": [],
                "queued_board_pairs": [],
            },
            "expires_at": now + self.session_ttl_sec,
        }

        with self._lock:
            self._purge_expired_sessions()
            self._sessions[session_id] = session
            self._persist_session(session)

        return {
            "session_id": session_id,
            "phase": "init",
            "match_mode": match_mode,
            "remote_health": remote_health,
            "local_version": session["local_version"],
        }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._purge_expired_sessions()
            session = self._sessions.get(session_id)
            if not session:
                session = self._load_session_from_redis(session_id)
                if session:
                    self._sessions[session_id] = session
            if not session:
                return None
            return self._public_session(session)

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            existed = self._sessions.pop(session_id, None) is not None
        if existed and self._can_persist_sessions():
            self.storage._redis().client.delete(self._session_redis_key(session_id))
        return existed

    def _normalize_progress_for_public(self, progress: dict[str, Any]) -> dict[str, Any]:
        payload = copy.deepcopy(progress)
        account_remote_map = payload.get("account_remote_map") or {}
        if account_remote_map:
            normalized_map: dict[str, Any] = {}
            for key, value in account_remote_map.items():
                if isinstance(key, tuple) and len(key) == 2:
                    normalized_map[_account_map_key(str(key[0]), str(key[1]))] = value
                else:
                    normalized_map[str(key)] = value
            payload["account_remote_map"] = normalized_map
        return payload

    def _public_session(self, session: dict[str, Any]) -> dict[str, Any]:
        progress = self._normalize_progress_for_public(session.get("progress") or {})
        board_results = progress.get("board_results") or []
        progress["board_results_summary"] = [
            {
                "pair_index": item.get("pair_index"),
                "local_title": item.get("local_title"),
                "remote_title": item.get("remote_title"),
                "status": item.get("status"),
                "local_board_id": item.get("local_board_id"),
                "remote_board_id": item.get("remote_board_id"),
            }
            for item in board_results
        ]
        progress.pop("board_results", None)
        progress["can_resume"] = bool(
            session.get("phase") not in ("done", "init")
            and progress.get("queued_board_pairs")
            and progress.get("resume_checkpoint", 0) < len(progress.get("queued_board_pairs") or [])
        )
        progress["resume_from_pair_index"] = int(progress.get("resume_checkpoint") or len(board_results))
        return {
            "session_id": session["session_id"],
            "created_at": session["created_at"],
            "phase": session.get("phase") or "init",
            "match_mode": session.get("match_mode"),
            "remote_base_url": session.get("remote_base_url"),
            "remote_health": session.get("remote_health"),
            "local_version": session.get("local_version"),
            "progress": progress,
        }

    def get_session_results(
        self,
        session_id: str,
        *,
        pair_index: int | None = None,
        section: str | None = None,
        list_id: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> dict[str, Any]:
        session = self._get_session_or_raise(session_id)
        page_size = max(1, min(int(limit or self.results_page_size), 100))
        safe_offset = max(0, int(offset or 0))
        results = copy.deepcopy((session.get("progress") or {}).get("board_results") or [])
        if pair_index is not None:
            matched = next((item for item in results if int(item.get("pair_index", -1)) == pair_index), None)
            if not matched:
                raise ValueError("看板对比结果不存在")
            if section:
                if section == "meta":
                    return {"pair_index": pair_index, "section": section, "data": matched.get("meta")}
                if section == "lists":
                    return {"pair_index": pair_index, "section": section, "data": matched.get("lists")}
                if section == "cards":
                    cards = matched.get("cards") or {}
                    by_list = cards.get("by_list") or {}
                    if list_id:
                        list_diff = by_list.get(str(list_id))
                        if not list_diff:
                            raise ValueError("列表对比结果不存在")
                        changed = list_diff.get("changed") or []
                        page_items = changed[safe_offset : safe_offset + page_size]
                        return {
                            "pair_index": pair_index,
                            "section": section,
                            "list_id": str(list_id),
                            "offset": safe_offset,
                            "limit": page_size,
                            "total": len(changed),
                            "done": safe_offset + len(page_items) >= len(changed),
                            "data": list_diff,
                            "changed_page": page_items,
                        }
                    list_ids = sorted(by_list.keys())
                    page_ids = list_ids[safe_offset : safe_offset + page_size]
                    return {
                        "pair_index": pair_index,
                        "section": section,
                        "offset": safe_offset,
                        "limit": page_size,
                        "total": len(list_ids),
                        "done": safe_offset + len(page_ids) >= len(list_ids),
                        "data": {key: by_list[key] for key in page_ids},
                    }
                raise ValueError("section 必须是 meta、lists 或 cards")
            return matched
        page_items = results[safe_offset : safe_offset + page_size]
        return {
            "items": page_items,
            "total": len(results),
            "offset": safe_offset,
            "limit": page_size,
            "done": safe_offset + len(page_items) >= len(results),
        }

    def sync_board_pair(
        self,
        session_id: str,
        *,
        pair_index: int,
        direction: str,
        mode: str = "replace",
    ) -> dict[str, Any]:
        normalized_direction = (direction or "").strip().lower()
        if normalized_direction not in ("to_local", "to_remote"):
            raise ValueError("direction 必须是 to_local 或 to_remote")
        sync_mode = (mode or "replace").strip().lower()
        if sync_mode not in ("replace", "merge"):
            raise ValueError("mode 必须是 replace 或 merge")

        session = self._get_session_or_raise(session_id)
        client = CompareRemoteClient(self.config, session["remote_base_url"], session["remote_token"])
        progress = session.get("progress") or {}
        queued_pairs = progress.get("queued_board_pairs") or []
        if pair_index < 0 or pair_index >= len(queued_pairs):
            raise ValueError("看板对不存在")

        queued = queued_pairs[pair_index]
        account_remote_map = progress.get("account_remote_map") or {}
        remote_account = _lookup_remote_account(
            account_remote_map,
            str(queued.get("tenant_type") or ""),
            str(queued.get("tenant_id") or ""),
        ) or {
            "tenant_type": queued.get("tenant_type"),
            "tenant_id": queued.get("tenant_id"),
        }

        from services.compare_sync import apply_board_sync_payload, load_board_full_sync_payload

        pair_status = queued.get("status") or "matched"
        local_tenant_type = str(queued.get("tenant_type") or "")
        local_tenant_id = str(queued.get("tenant_id") or "")
        remote_tenant_type = str(remote_account.get("tenant_type") or local_tenant_type)
        remote_tenant_id = str(remote_account.get("tenant_id") or local_tenant_id)
        sync_result: dict[str, Any]

        try:
            if normalized_direction == "to_remote":
                if pair_status == "only_remote":
                    raise ValueError("该看板仅存在于远程，无法同步到远程")
                local_board_id = str(queued.get("local_board_id") or "").strip()
                if not local_board_id:
                    raise ValueError("缺少本地看板 ID")
                payload = load_board_full_sync_payload(self.storage, local_tenant_type, local_tenant_id, local_board_id)
                if pair_status == "only_local":
                    target_board_id = None
                    effective_mode = "merge"
                else:
                    target_board_id = str(queued.get("remote_board_id") or "").strip() or None
                    effective_mode = sync_mode if target_board_id else "merge"
                sync_result = client.apply_board_sync(
                    remote_tenant_type,
                    remote_tenant_id,
                    payload,
                    target_board_id=target_board_id,
                    mode=effective_mode,
                )
                remote_board_id = str(sync_result.get("board_id") or "").strip()
                if pair_status == "only_local" and remote_board_id:
                    queued["remote_board_id"] = remote_board_id
                    queued["remote_title"] = (payload.get("board") or {}).get("title") or queued.get("local_title")
                    queued["remote_organization"] = (payload.get("board") or {}).get("organization") or queued.get(
                        "local_organization"
                    )
                    queued["status"] = "matched"
            else:
                if pair_status == "only_local":
                    raise ValueError("该看板仅存在于本地，无法从远程同步")
                remote_board_id = str(queued.get("remote_board_id") or "").strip()
                if not remote_board_id:
                    raise ValueError("缺少远程看板 ID")
                payload = client.load_board_full_sync_payload(remote_tenant_type, remote_tenant_id, remote_board_id)
                if pair_status == "only_remote":
                    target_board_id = None
                    effective_mode = "merge"
                else:
                    target_board_id = str(queued.get("local_board_id") or "").strip() or None
                    effective_mode = sync_mode if target_board_id else "merge"
                sync_result = apply_board_sync_payload(
                    self.storage,
                    local_tenant_type,
                    local_tenant_id,
                    payload,
                    target_board_id=target_board_id,
                    mode=effective_mode,
                )
                local_board_id = str(sync_result.get("board_id") or "").strip()
                if pair_status == "only_remote" and local_board_id:
                    queued["local_board_id"] = local_board_id
                    queued["local_title"] = (payload.get("board") or {}).get("title") or queued.get("remote_title")
                    queued["local_organization"] = (payload.get("board") or {}).get("organization") or queued.get(
                        "remote_organization"
                    )
                    queued["status"] = "matched"
        except CompareRemoteError as error:
            raise ValueError(_format_remote_sync_error(error)) from error

        new_result = self._compute_board_pair_diff(
            client=client,
            session=session,
            queued=queued,
            pair_index=pair_index,
            remote_account=remote_account,
        )
        board_results = progress.get("board_results") or []
        updated = False
        for index, item in enumerate(board_results):
            if int(item.get("pair_index", -1)) == pair_index:
                board_results[index] = new_result
                updated = True
                break
        if not updated:
            board_results.append(new_result)

        queued_pairs[pair_index] = queued
        self._update_session_progress(
            session,
            queued_board_pairs=queued_pairs,
            board_results=board_results,
        )

        direction_label = "本地 → 远程" if normalized_direction == "to_remote" else "远程 → 本地"
        return {
            "message": f"{direction_label} 同步成功",
            "direction": normalized_direction,
            "mode": sync_mode,
            "sync": sync_result,
            "result": new_result,
            "queued": copy.deepcopy(queued),
        }

    def sync_account_pair(
        self,
        session_id: str,
        *,
        account_pair_index: int,
        direction: str,
        mode: str = "replace",
    ) -> dict[str, Any]:
        normalized_direction = (direction or "").strip().lower()
        if normalized_direction not in ("to_local", "to_remote"):
            raise ValueError("direction 必须是 to_local 或 to_remote")
        sync_mode = (mode or "replace").strip().lower()
        if sync_mode not in ("replace", "merge"):
            raise ValueError("mode 必须是 replace 或 merge")

        session = self._get_session_or_raise(session_id)
        progress = session.get("progress") or {}
        account_pairs = progress.get("account_pairs") or []
        if account_pair_index < 0 or account_pair_index >= len(account_pairs):
            raise ValueError("账号对不存在")

        account_pair = account_pairs[account_pair_index]
        account_status = account_pair.get("status") or "matched"
        if normalized_direction == "to_remote" and account_status == "only_remote":
            raise ValueError("该账号仅存在于远程，无法同步到远程")
        if normalized_direction == "to_local" and account_status == "only_local":
            raise ValueError("该账号仅存在于本地，无法从远程同步")

        local_account = account_pair.get("local") or {}
        remote_account = account_pair.get("remote") or {}
        if normalized_direction == "to_remote":
            tenant_type = str(local_account.get("tenant_type") or "")
            tenant_id = str(local_account.get("tenant_id") or "")
        else:
            tenant_type = str(remote_account.get("tenant_type") or local_account.get("tenant_type") or "")
            tenant_id = str(remote_account.get("tenant_id") or local_account.get("tenant_id") or "")

        if not tenant_type or not tenant_id:
            raise ValueError("账号信息不完整")

        queued_pairs = progress.get("queued_board_pairs") or []
        board_indices = [
            index
            for index, queued in enumerate(queued_pairs)
            if str(queued.get("tenant_type") or "") == tenant_type and str(queued.get("tenant_id") or "") == tenant_id
        ]
        if not board_indices:
            if account_status == "only_remote" and normalized_direction == "to_local":
                raise ValueError("该远程账号下暂无看板，无法同步")
            if account_status == "only_local" and normalized_direction == "to_remote":
                raise ValueError("该本地账号下暂无看板，无法同步")
            raise ValueError("该账号下没有可同步的看板")

        synced: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for pair_index in board_indices:
            queued = queued_pairs[pair_index]
            pair_status = queued.get("status") or "matched"
            if normalized_direction == "to_remote":
                if pair_status == "only_remote" or not queued.get("local_board_id"):
                    continue
            elif pair_status == "only_local" or not queued.get("remote_board_id"):
                continue
            try:
                item = self.sync_board_pair(
                    session_id,
                    pair_index=pair_index,
                    direction=normalized_direction,
                    mode=sync_mode,
                )
                synced.append(
                    {
                        "pair_index": pair_index,
                        "local_title": item.get("result", {}).get("local_title") or queued.get("local_title"),
                        "remote_title": item.get("result", {}).get("remote_title") or queued.get("remote_title"),
                        "status": item.get("result", {}).get("status"),
                    }
                )
            except ValueError as error:
                errors.append(
                    {
                        "pair_index": pair_index,
                        "local_title": queued.get("local_title"),
                        "remote_title": queued.get("remote_title"),
                        "message": str(error),
                    }
                )

        progress = session.get("progress") or {}
        if not synced:
            message = errors[0]["message"] if errors else "没有看板被同步"
            raise ValueError(message)

        direction_label = "本地 → 远程" if normalized_direction == "to_remote" else "远程 → 本地"
        summary = f"{direction_label}：已同步 {len(synced)} 个看板"
        if errors:
            summary += f"，{len(errors)} 个失败"

        return {
            "message": summary,
            "direction": normalized_direction,
            "mode": sync_mode,
            "account_pair_index": account_pair_index,
            "synced_count": len(synced),
            "error_count": len(errors),
            "synced": synced,
            "errors": errors,
            "board_pairs": copy.deepcopy(progress.get("queued_board_pairs") or []),
            "board_results": copy.deepcopy(progress.get("board_results") or []),
            "account_pair": copy.deepcopy(account_pairs[account_pair_index]),
        }

    def _remove_queued_board_pair(self, session: dict[str, Any], pair_index: int) -> None:
        progress = session.get("progress") or {}
        queued_pairs = list(progress.get("queued_board_pairs") or [])
        board_results = list(progress.get("board_results") or [])
        if pair_index < 0 or pair_index >= len(queued_pairs):
            raise ValueError("看板对不存在")
        queued_pairs.pop(pair_index)
        board_results = [item for item in board_results if int(item.get("pair_index", -1)) != pair_index]
        for item in board_results:
            current_index = int(item.get("pair_index", -1))
            if current_index > pair_index:
                item["pair_index"] = current_index - 1
        self._update_session_progress(
            session,
            queued_board_pairs=queued_pairs,
            board_results=board_results,
        )

    def delete_board_pair(
        self,
        session_id: str,
        *,
        pair_index: int,
        side: str,
    ) -> dict[str, Any]:
        normalized_side = (side or "").strip().lower()
        if normalized_side not in ("local", "remote"):
            raise ValueError("side 必须是 local 或 remote")

        session = self._get_session_or_raise(session_id)
        client = CompareRemoteClient(self.config, session["remote_base_url"], session["remote_token"])
        progress = session.get("progress") or {}
        queued_pairs = progress.get("queued_board_pairs") or []
        if pair_index < 0 or pair_index >= len(queued_pairs):
            raise ValueError("看板对不存在")

        queued = queued_pairs[pair_index]
        pair_status = queued.get("status") or "matched"
        if normalized_side == "local" and pair_status == "only_remote":
            raise ValueError("该看板仅存在于远程，无法删除本地副本")
        if normalized_side == "remote" and pair_status == "only_local":
            raise ValueError("该看板仅存在于本地，无法删除远程副本")
        if pair_status == "matched":
            raise ValueError("已匹配的看板请使用同步覆盖，不支持单独删除一侧")

        account_remote_map = progress.get("account_remote_map") or {}
        remote_account = _lookup_remote_account(
            account_remote_map,
            str(queued.get("tenant_type") or ""),
            str(queued.get("tenant_id") or ""),
        ) or {
            "tenant_type": queued.get("tenant_type"),
            "tenant_id": queued.get("tenant_id"),
        }
        local_tenant_type = str(queued.get("tenant_type") or "")
        local_tenant_id = str(queued.get("tenant_id") or "")
        remote_tenant_type = str(remote_account.get("tenant_type") or local_tenant_type)
        remote_tenant_id = str(remote_account.get("tenant_id") or local_tenant_id)
        title = queued.get("local_title") or queued.get("remote_title") or "看板"

        from services.compare_sync import delete_board_from_tenant

        try:
            if normalized_side == "local":
                board_id = str(queued.get("local_board_id") or "").strip()
                if not board_id:
                    raise ValueError("缺少本地看板 ID")
                delete_board_from_tenant(self.storage, local_tenant_type, local_tenant_id, board_id)
            else:
                board_id = str(queued.get("remote_board_id") or "").strip()
                if not board_id:
                    raise ValueError("缺少远程看板 ID")
                client.delete_board(remote_tenant_type, remote_tenant_id, board_id)
        except CompareRemoteError as error:
            raise ValueError(_format_remote_sync_error(error)) from error

        self._remove_queued_board_pair(session, pair_index)
        side_label = "本地" if normalized_side == "local" else "远程"
        progress = session.get("progress") or {}
        return {
            "message": f"已从{side_label}删除「{title}」",
            "side": normalized_side,
            "removed_pair_index": pair_index,
            "board_pairs": copy.deepcopy(progress.get("queued_board_pairs") or []),
            "board_results": copy.deepcopy(progress.get("board_results") or []),
        }

    def delete_account_boards(
        self,
        session_id: str,
        *,
        account_pair_index: int,
        side: str,
    ) -> dict[str, Any]:
        normalized_side = (side or "").strip().lower()
        if normalized_side not in ("local", "remote"):
            raise ValueError("side 必须是 local 或 remote")

        session = self._get_session_or_raise(session_id)
        progress = session.get("progress") or {}
        account_pairs = progress.get("account_pairs") or []
        if account_pair_index < 0 or account_pair_index >= len(account_pairs):
            raise ValueError("账号对不存在")

        account_pair = account_pairs[account_pair_index]
        account_status = account_pair.get("status") or "matched"
        if normalized_side == "local" and account_status == "only_remote":
            raise ValueError("该账号仅存在于远程，无法删除本地副本")
        if normalized_side == "remote" and account_status == "only_local":
            raise ValueError("该账号仅存在于本地，无法删除远程副本")
        if account_status == "matched":
            raise ValueError("已匹配的账号不支持批量删除，请逐条删除仅本地/仅远程看板")

        local_account = account_pair.get("local") or {}
        remote_account = account_pair.get("remote") or {}
        if normalized_side == "local":
            tenant_type = str(local_account.get("tenant_type") or "")
            tenant_id = str(local_account.get("tenant_id") or "")
            target_status = "only_local"
        else:
            tenant_type = str(remote_account.get("tenant_type") or local_account.get("tenant_type") or "")
            tenant_id = str(remote_account.get("tenant_id") or local_account.get("tenant_id") or "")
            target_status = "only_remote"

        if not tenant_type or not tenant_id:
            raise ValueError("账号信息不完整")

        queued_pairs = progress.get("queued_board_pairs") or []
        board_indices = [
            index
            for index, queued in enumerate(queued_pairs)
            if str(queued.get("tenant_type") or "") == tenant_type
            and str(queued.get("tenant_id") or "") == tenant_id
            and (queued.get("status") or "matched") == target_status
        ]
        if not board_indices:
            side_label = "本地" if normalized_side == "local" else "远程"
            raise ValueError(f"该{side_label}账号下没有可删除的看板")

        deleted: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for pair_index in sorted(board_indices, reverse=True):
            queued = queued_pairs[pair_index]
            try:
                result = self.delete_board_pair(session_id, pair_index=pair_index, side=normalized_side)
                deleted.append(
                    {
                        "pair_index": pair_index,
                        "title": queued.get("local_title") or queued.get("remote_title"),
                        "message": result.get("message"),
                    }
                )
                session = self._get_session_or_raise(session_id)
                progress = session.get("progress") or {}
                queued_pairs = progress.get("queued_board_pairs") or []
            except ValueError as error:
                errors.append(
                    {
                        "pair_index": pair_index,
                        "title": queued.get("local_title") or queued.get("remote_title"),
                        "message": str(error),
                    }
                )

        progress = session.get("progress") or {}
        if not deleted:
            message = errors[0]["message"] if errors else "没有看板被删除"
            raise ValueError(message)

        side_label = "本地" if normalized_side == "local" else "远程"
        summary = f"已从{side_label}删除 {len(deleted)} 个看板"
        if errors:
            summary += f"，{len(errors)} 个失败"

        return {
            "message": summary,
            "side": normalized_side,
            "account_pair_index": account_pair_index,
            "deleted_count": len(deleted),
            "error_count": len(errors),
            "deleted": deleted,
            "errors": errors,
            "board_pairs": copy.deepcopy(progress.get("queued_board_pairs") or []),
            "board_results": copy.deepcopy(progress.get("board_results") or []),
            "account_pair": copy.deepcopy(account_pairs[account_pair_index]),
        }

    def _session_redis_key(self, session_id: str) -> str:
        prefix = (self.config.get("REDIS_KEY_PREFIX") or "jjob:boardflow").strip()
        return f"{prefix}:compare:session:{session_id}"

    def _can_persist_sessions(self) -> bool:
        return hasattr(self.storage, "_is_redis") and self.storage._is_redis()

    def _normalize_session_for_storage(self, session: dict[str, Any]) -> dict[str, Any]:
        payload = copy.deepcopy(session)
        progress = payload.get("progress") or {}
        account_remote_map = progress.get("account_remote_map") or {}
        if account_remote_map:
            normalized_map: dict[str, Any] = {}
            for key, value in account_remote_map.items():
                if isinstance(key, tuple) and len(key) == 2:
                    normalized_map[_account_map_key(str(key[0]), str(key[1]))] = value
                else:
                    normalized_map[str(key)] = value
            progress["account_remote_map"] = normalized_map
            payload["progress"] = progress
        return payload

    def _persist_session(self, session: dict[str, Any]) -> None:
        if not self._can_persist_sessions():
            return
        session_id = str(session.get("session_id") or "").strip()
        if not session_id:
            return
        ttl = max(60, int(float(session.get("expires_at") or 0) - time.time()))
        payload = self._normalize_session_for_storage(session)
        self.storage._redis().client.setex(
            self._session_redis_key(session_id),
            ttl,
            json.dumps(payload, ensure_ascii=False),
        )

    def _load_session_from_redis(self, session_id: str) -> dict[str, Any] | None:
        if not self._can_persist_sessions():
            return None
        raw = self.storage._redis().client.get(self._session_redis_key(session_id))
        if not raw:
            return None
        try:
            session = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(session, dict):
            return None
        return session

    def _get_session_or_raise(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            self._purge_expired_sessions()
            session = self._sessions.get(session_id)
            if not session:
                session = self._load_session_from_redis(session_id)
                if session:
                    self._sessions[session_id] = session
            if not session:
                raise ValueError("对比会话不存在或已过期，请重新「探测远程连接」并「开始对比」")
            session["expires_at"] = time.time() + self.session_ttl_sec
            self._persist_session(session)
            return session

    def _update_session_progress(self, session: dict[str, Any], **kwargs: Any) -> None:
        progress = session.setdefault("progress", {})
        progress.update(kwargs)
        session["progress"] = progress
        self._persist_session(session)

    def _compute_board_pair_diff(
        self,
        *,
        client: CompareRemoteClient,
        session: dict[str, Any],
        queued: dict[str, Any],
        pair_index: int,
        remote_account: dict[str, Any],
    ) -> dict[str, Any]:
        options = session.get("options") or {}
        compare_lists = options.get("compare_lists", True) is not False
        compare_cards = options.get("compare_cards", True) is not False
        include_description = options.get("compare_card_description") is True
        extra_card_fields = ("description",) if include_description else ()
        pair_status = queued.get("status") or "matched"

        if pair_status in ("only_local", "only_remote"):
            return build_board_compare_result(pair_index=pair_index, queued=queued)

        tenant_type = str(queued.get("tenant_type") or "")
        tenant_id = str(queued.get("tenant_id") or "")
        local_board_id = str(queued.get("local_board_id") or "")
        remote_board_id = str(queued.get("remote_board_id") or "")
        remote_tenant_type = str(remote_account.get("tenant_type") or tenant_type)
        remote_tenant_id = str(remote_account.get("tenant_id") or tenant_id)

        try:
            local_snapshot = load_board_compare_snapshot(
                self.storage,
                tenant_type,
                tenant_id,
                local_board_id,
                include_description=include_description,
            )
            remote_snapshot = client.load_board_compare_snapshot(
                remote_tenant_type,
                remote_tenant_id,
                remote_board_id,
                include_description=include_description,
            )
        except (CompareRemoteError, ValueError) as error:
            return build_board_compare_result(pair_index=pair_index, queued=queued, error=str(error))

        meta_diff = diff_board_meta(local_snapshot.get("board"), remote_snapshot.get("board"))
        lists_diff = None
        if compare_lists:
            lists_diff = diff_lists(local_snapshot.get("lists") or [], remote_snapshot.get("lists") or [])

        cards_diff_by_list: dict[str, dict[str, Any]] = {}
        if compare_cards:
            local_cards_map = local_snapshot.get("cards_by_list") or {}
            remote_cards_map = remote_snapshot.get("cards_by_list") or {}
            list_ids = sorted(set(local_cards_map.keys()) | set(remote_cards_map.keys()))
            for list_id in list_ids:
                cards_diff_by_list[list_id] = diff_cards(
                    local_cards_map.get(list_id) or [],
                    remote_cards_map.get(list_id) or [],
                    extra_fields=extra_card_fields,
                )

        return build_board_compare_result(
            pair_index=pair_index,
            queued=queued,
            meta_diff=meta_diff,
            lists_diff=lists_diff,
            cards_diff_by_list=cards_diff_by_list,
        )

    def _iter_board_pair_diff(
        self,
        *,
        client: CompareRemoteClient,
        session: dict[str, Any],
        queued: dict[str, Any],
        pair_index: int,
        remote_account: dict[str, Any],
        percent: int,
    ) -> Iterator[dict[str, Any]]:
        options = session.get("options") or {}
        compare_lists = options.get("compare_lists", True) is not False
        compare_cards = options.get("compare_cards", True) is not False
        include_description = options.get("compare_card_description") is True
        extra_card_fields = ("description",) if include_description else ()
        pair_status = queued.get("status") or "matched"

        if pair_status in ("only_local", "only_remote"):
            result = build_board_compare_result(pair_index=pair_index, queued=queued)
            yield {
                "step": "board_pair_done",
                "pair_index": pair_index,
                "summary": result,
                "percent": percent,
                "done": False,
            }
            return result

        tenant_type = str(queued.get("tenant_type") or "")
        tenant_id = str(queued.get("tenant_id") or "")
        local_board_id = str(queued.get("local_board_id") or "")
        remote_board_id = str(queued.get("remote_board_id") or "")
        remote_tenant_type = str(remote_account.get("tenant_type") or tenant_type)
        remote_tenant_id = str(remote_account.get("tenant_id") or tenant_id)

        try:
            local_snapshot = load_board_compare_snapshot(
                self.storage,
                tenant_type,
                tenant_id,
                local_board_id,
                include_description=include_description,
            )
            remote_snapshot = client.load_board_compare_snapshot(
                remote_tenant_type,
                remote_tenant_id,
                remote_board_id,
                include_description=include_description,
            )
        except (CompareRemoteError, ValueError) as error:
            result = build_board_compare_result(pair_index=pair_index, queued=queued, error=str(error))
            yield {
                "step": "board_pair_done",
                "pair_index": pair_index,
                "summary": result,
                "percent": percent,
                "done": False,
                "error": True,
            }
            return result

        meta_diff = diff_board_meta(local_snapshot.get("board"), remote_snapshot.get("board"))
        yield {
            "step": "board_meta_diff",
            "pair_index": pair_index,
            "local_board_id": local_board_id,
            "remote_board_id": remote_board_id,
            "diff": meta_diff,
            "percent": percent,
            "done": False,
        }

        lists_diff = None
        if compare_lists:
            lists_diff = diff_lists(local_snapshot.get("lists") or [], remote_snapshot.get("lists") or [])
            yield {
                "step": "board_lists_diff",
                "pair_index": pair_index,
                "local_board_id": local_board_id,
                "remote_board_id": remote_board_id,
                "diff": lists_diff,
                "percent": percent + 1,
                "done": False,
            }

        cards_diff_by_list: dict[str, dict[str, Any]] = {}
        if compare_cards:
            local_cards_map = local_snapshot.get("cards_by_list") or {}
            remote_cards_map = remote_snapshot.get("cards_by_list") or {}
            list_ids = sorted(set(local_cards_map.keys()) | set(remote_cards_map.keys()))
            for list_id in list_ids:
                list_cards_diff = diff_cards(
                    local_cards_map.get(list_id) or [],
                    remote_cards_map.get(list_id) or [],
                    extra_fields=extra_card_fields,
                )
                cards_diff_by_list[list_id] = list_cards_diff
                yield {
                    "step": "board_cards_diff",
                    "pair_index": pair_index,
                    "local_board_id": local_board_id,
                    "remote_board_id": remote_board_id,
                    "list_id": list_id,
                    "diff": list_cards_diff,
                    "percent": percent + 2,
                    "done": False,
                }

        result = build_board_compare_result(
            pair_index=pair_index,
            queued=queued,
            meta_diff=meta_diff,
            lists_diff=lists_diff,
            cards_diff_by_list=cards_diff_by_list,
        )
        yield {
            "step": "board_pair_done",
            "pair_index": pair_index,
            "summary": result,
            "percent": min(99, percent + 3),
            "done": False,
        }
        return result

    def iter_run_session(self, session_id: str, *, run_options: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        session = self._get_session_or_raise(session_id)
        client = CompareRemoteClient(self.config, session["remote_base_url"], session["remote_token"])
        match_mode = session.get("match_mode") or "manual"
        manual_pairs = session.get("pairs") or []
        run_options = run_options or {}
        from_phase = (run_options.get("from_phase") or "").strip().lower()
        resume_from_pair_index = max(0, int(run_options.get("resume_from_pair_index") or 0))
        progress = session.get("progress") or {}
        skip_discovery = from_phase == "diff" and bool(progress.get("queued_board_pairs"))

        yield {
            "step": "session_started",
            "session_id": session_id,
            "match_mode": match_mode,
            "resumed": skip_discovery,
            "percent": 0,
            "done": False,
        }

        if skip_discovery:
            yield {
                "step": "session_resumed",
                "from_phase": "diff",
                "resume_from_pair_index": resume_from_pair_index,
                "percent": 50,
                "done": False,
            }
            local_accounts = progress.get("local_accounts") or []
            remote_accounts = progress.get("remote_accounts") or []
            account_pairs = progress.get("account_pairs") or []
            matched_accounts = [pair for pair in account_pairs if pair.get("status") == "matched"]
            queued_board_pairs = copy.deepcopy(progress.get("queued_board_pairs") or [])
            account_remote_map = progress.get("account_remote_map") or {}
            board_results = copy.deepcopy(progress.get("board_results") or [])
        else:
            local_accounts: list[dict[str, Any]] = []
            cursor = None
            while True:
                page = paginate_federation_accounts(
                    self.storage,
                    cursor=cursor,
                    limit=self.accounts_page_size,
                )
                batch = page.get("items") or []
                local_accounts.extend(batch)
                yield {
                    "step": "accounts_local",
                    "items": batch,
                    "cursor": page.get("next_cursor"),
                    "done": bool(page.get("done")),
                    "percent": 5,
                }
                if page.get("done"):
                    break
                cursor = page.get("next_cursor")
                if not cursor:
                    break

            remote_accounts: list[dict[str, Any]] = []
            cursor = None
            while True:
                try:
                    page = client.list_accounts_page(cursor=cursor, limit=self.accounts_page_size)
                except CompareRemoteError as error:
                    yield {
                        "step": "error",
                        "message": str(error),
                        "fatal": True,
                        "percent": 10,
                        "done": True,
                        "error": True,
                    }
                    return
                batch = page.get("items") or []
                remote_accounts.extend(batch)
                yield {
                    "step": "accounts_remote",
                    "items": batch,
                    "cursor": page.get("next_cursor"),
                    "done": bool(page.get("done")),
                    "percent": 15,
                }
                if page.get("done"):
                    break
                cursor = page.get("next_cursor")
                if not cursor:
                    break

            account_pairs = _match_accounts(local_accounts, remote_accounts)
            yield {
                "step": "accounts_matched",
                "pairs": account_pairs,
                "percent": 20,
                "done": False,
            }
            self._update_session_progress(
                session,
                step="accounts_matched",
                percent=20,
                local_accounts=local_accounts,
                remote_accounts=remote_accounts,
                account_pairs=account_pairs,
            )
            session["phase"] = "accounts"

            matched_accounts = [pair for pair in account_pairs if pair.get("status") == "matched"]
            total_accounts = max(len(account_pairs), 1)
            queued_board_pairs = []
            account_remote_map = _build_account_remote_map(account_pairs)

            for index, pair in enumerate(account_pairs):
                account_status = pair.get("status") or "matched"
                account_percent = 20 + int((index / total_accounts) * 30)

                if account_status == "matched":
                    local_account = pair["local"]
                    remote_account = pair["remote"]
                    tenant_type = str(local_account.get("tenant_type") or "")
                    tenant_id = str(local_account.get("tenant_id") or "")
                    display_name = local_account.get("display_name") or tenant_id

                    local_boards: list[dict[str, Any]] = []
                    cursor = None
                    while True:
                        page = paginate_federation_boards(
                            self.storage,
                            tenant_type,
                            tenant_id,
                            cursor=cursor,
                            limit=self.boards_page_size,
                        )
                        batch = page.get("items") or []
                        local_boards.extend(batch)
                        yield {
                            "step": "boards_local",
                            "tenant_type": tenant_type,
                            "tenant_id": tenant_id,
                            "display_name": display_name,
                            "items": batch,
                            "cursor": page.get("next_cursor"),
                            "done": bool(page.get("done")),
                            "percent": account_percent,
                        }
                        if page.get("done"):
                            break
                        cursor = page.get("next_cursor")
                        if not cursor:
                            break

                    remote_boards: list[dict[str, Any]] = []
                    cursor = None
                    while True:
                        try:
                            page = client.list_boards_page(
                                str(remote_account.get("tenant_type") or ""),
                                str(remote_account.get("tenant_id") or ""),
                                cursor=cursor,
                                limit=self.boards_page_size,
                            )
                        except CompareRemoteError as error:
                            yield {
                                "step": "error",
                                "message": str(error),
                                "fatal": False,
                                "tenant_type": tenant_type,
                                "tenant_id": tenant_id,
                                "percent": account_percent,
                                "done": False,
                                "error": True,
                            }
                            break
                        batch = page.get("items") or []
                        remote_boards.extend(batch)
                        yield {
                            "step": "boards_remote",
                            "tenant_type": tenant_type,
                            "tenant_id": tenant_id,
                            "display_name": display_name,
                            "items": batch,
                            "cursor": page.get("next_cursor"),
                            "done": bool(page.get("done")),
                            "percent": account_percent + 2,
                        }
                        if page.get("done"):
                            break
                        cursor = page.get("next_cursor")
                        if not cursor:
                            break

                    account_queue = _queue_board_pairs_for_account(
                        match_mode=match_mode,
                        manual_pairs=manual_pairs,
                        local_boards=local_boards,
                        remote_boards=remote_boards,
                        tenant_type=tenant_type,
                        tenant_id=tenant_id,
                    )
                elif account_status == "only_remote":
                    remote_account = pair.get("remote") or {}
                    tenant_type = str(remote_account.get("tenant_type") or "")
                    tenant_id = str(remote_account.get("tenant_id") or "")
                    display_name = remote_account.get("display_name") or tenant_id
                    remote_boards: list[dict[str, Any]] = []
                    cursor = None
                    while True:
                        try:
                            page = client.list_boards_page(
                                tenant_type,
                                tenant_id,
                                cursor=cursor,
                                limit=self.boards_page_size,
                            )
                        except CompareRemoteError as error:
                            yield {
                                "step": "error",
                                "message": str(error),
                                "fatal": False,
                                "tenant_type": tenant_type,
                                "tenant_id": tenant_id,
                                "percent": account_percent,
                                "done": False,
                                "error": True,
                            }
                            break
                        batch = page.get("items") or []
                        remote_boards.extend(batch)
                        yield {
                            "step": "boards_remote",
                            "tenant_type": tenant_type,
                            "tenant_id": tenant_id,
                            "display_name": display_name,
                            "items": batch,
                            "cursor": page.get("next_cursor"),
                            "done": bool(page.get("done")),
                            "percent": account_percent + 2,
                        }
                        if page.get("done"):
                            break
                        cursor = page.get("next_cursor")
                        if not cursor:
                            break
                    account_queue = _queue_boards_for_unmatched_account(
                        account_status=account_status,
                        boards=remote_boards,
                        match_mode=match_mode,
                    )
                elif account_status == "only_local":
                    local_account = pair.get("local") or {}
                    tenant_type = str(local_account.get("tenant_type") or "")
                    tenant_id = str(local_account.get("tenant_id") or "")
                    display_name = local_account.get("display_name") or tenant_id
                    local_boards: list[dict[str, Any]] = []
                    cursor = None
                    while True:
                        page = paginate_federation_boards(
                            self.storage,
                            tenant_type,
                            tenant_id,
                            cursor=cursor,
                            limit=self.boards_page_size,
                        )
                        batch = page.get("items") or []
                        local_boards.extend(batch)
                        yield {
                            "step": "boards_local",
                            "tenant_type": tenant_type,
                            "tenant_id": tenant_id,
                            "display_name": display_name,
                            "items": batch,
                            "cursor": page.get("next_cursor"),
                            "done": bool(page.get("done")),
                            "percent": account_percent,
                        }
                        if page.get("done"):
                            break
                        cursor = page.get("next_cursor")
                        if not cursor:
                            break
                    account_queue = _queue_boards_for_unmatched_account(
                        account_status=account_status,
                        boards=local_boards,
                        match_mode=match_mode,
                    )
                else:
                    continue

                for queued in account_queue:
                    queued["tenant_type"] = tenant_type
                    queued["tenant_id"] = tenant_id
                    queued["display_name"] = display_name
                    queued_board_pairs.append(queued)
                    yield {
                        "step": "board_pair_queued",
                        **queued,
                        "pair_index": len(queued_board_pairs) - 1,
                        "percent": min(50, account_percent + 5),
                        "done": False,
                    }

            board_results = []
            self._update_session_progress(
                session,
                step="boards_loaded",
                percent=50,
                queued_board_pairs=queued_board_pairs,
                account_remote_map=account_remote_map,
                board_results=board_results,
                resume_checkpoint=0,
            )
            session["phase"] = "boards"

            yield {
                "step": "phase_done",
                "phase": "boards",
                "percent": 50,
                "done": False,
                "totals": {
                    "local_accounts": len(local_accounts),
                    "remote_accounts": len(remote_accounts),
                    "matched_accounts": len(matched_accounts),
                    "queued_board_pairs": len(queued_board_pairs),
                },
            }

        if skip_discovery:
            board_results = [item for item in board_results if int(item.get("pair_index", -1)) < resume_from_pair_index]

        total_pairs = max(len(queued_board_pairs), 1)
        boards_equal = sum(1 for item in board_results if item.get("status") == "equal")
        boards_changed = sum(1 for item in board_results if item.get("status") == "changed")
        boards_only_local = sum(1 for item in board_results if item.get("status") == "only_local")
        boards_only_remote = sum(1 for item in board_results if item.get("status") == "only_remote")
        boards_error = sum(1 for item in board_results if item.get("status") == "error")

        for pair_index, queued in enumerate(queued_board_pairs):
            if pair_index < resume_from_pair_index:
                continue
            diff_percent = 50 + int((pair_index / total_pairs) * 45)
            remote_account = _lookup_remote_account(
                account_remote_map,
                str(queued.get("tenant_type") or ""),
                str(queued.get("tenant_id") or ""),
            ) or {
                "tenant_type": queued.get("tenant_type"),
                "tenant_id": queued.get("tenant_id"),
            }
            result = None
            for event in self._iter_board_pair_diff(
                client=client,
                session=session,
                queued=queued,
                pair_index=pair_index,
                remote_account=remote_account,
                percent=diff_percent,
            ):
                yield event
                if event.get("step") == "board_pair_done":
                    result = event.get("summary")

            if not result:
                continue
            board_results.append(result)
            status = result.get("status")
            if status == "equal":
                boards_equal += 1
            elif status == "changed":
                boards_changed += 1
            elif status == "only_local":
                boards_only_local += 1
            elif status == "only_remote":
                boards_only_remote += 1
            elif status == "error":
                boards_error += 1

            self._update_session_progress(
                session,
                board_results=board_results,
                resume_checkpoint=pair_index + 1,
            )

        self._update_session_progress(
            session,
            step="diff_done",
            percent=98,
            board_results=board_results,
            queued_board_pairs=queued_board_pairs,
        )
        session["phase"] = "diff"

        yield {
            "step": "phase_done",
            "phase": "diff",
            "percent": 98,
            "done": False,
            "totals": {
                "queued_board_pairs": len(queued_board_pairs),
                "boards_equal": boards_equal,
                "boards_changed": boards_changed,
                "boards_only_local": boards_only_local,
                "boards_only_remote": boards_only_remote,
                "boards_error": boards_error,
            },
        }

        yield {
            "step": "session_done",
            "phase": "diff",
            "percent": 100,
            "done": True,
            "totals": {
                "local_accounts": len(local_accounts),
                "remote_accounts": len(remote_accounts),
                "matched_accounts": len(matched_accounts),
                "queued_board_pairs": len(queued_board_pairs),
                "boards_equal": boards_equal,
                "boards_changed": boards_changed,
                "boards_only_local": boards_only_local,
                "boards_only_remote": boards_only_remote,
                "boards_error": boards_error,
            },
        }
        session["phase"] = "done"
        self._update_session_progress(session, step="session_done", percent=100, board_results=board_results)
