"""多平台看板对比编排：会话管理与渐进式 NDJSON 事件流。"""

from __future__ import annotations

import copy
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
            }
        )
    return queued


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
                return None
            return self._public_session(session)

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _public_session(self, session: dict[str, Any]) -> dict[str, Any]:
        progress = copy.deepcopy(session.get("progress") or {})
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

    def _get_session_or_raise(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            self._purge_expired_sessions()
            session = self._sessions.get(session_id)
            if not session:
                raise ValueError("对比会话不存在或已过期")
            session["expires_at"] = time.time() + self.session_ttl_sec
            return session

    def _update_session_progress(self, session: dict[str, Any], **kwargs: Any) -> None:
        progress = session.setdefault("progress", {})
        progress.update(kwargs)
        session["progress"] = progress

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
            total_accounts = max(len(matched_accounts), 1)
            queued_board_pairs = []
            account_remote_map = {
                _account_key(pair["local"]): pair["remote"]
                for pair in matched_accounts
                if pair.get("local") and pair.get("remote")
            }

            for index, pair in enumerate(matched_accounts):
                local_account = pair["local"]
                remote_account = pair["remote"]
                tenant_type = str(local_account.get("tenant_type") or "")
                tenant_id = str(local_account.get("tenant_id") or "")
                display_name = local_account.get("display_name") or tenant_id
                account_percent = 20 + int((index / total_accounts) * 30)

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
            remote_account = account_remote_map.get(_account_key({"tenant_type": queued.get("tenant_type"), "tenant_id": queued.get("tenant_id")})) or {
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
