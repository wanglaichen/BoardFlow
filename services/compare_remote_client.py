"""跨实例 Federation HTTP 客户端。"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from services.compare_remote_security import assert_remote_host_allowed
from services.federation_service import DEFAULT_ACCOUNTS_PAGE_SIZE, DEFAULT_BOARDS_PAGE_SIZE, DEFAULT_CARDS_PAGE_SIZE


class CompareRemoteError(Exception):
    pass


def normalize_remote_base_url(raw: str) -> str:
    value = (raw or "").strip().rstrip("/")
    if not value:
        raise ValueError("远程地址不能为空")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("远程地址必须以 http:// 或 https:// 开头")
    if not parsed.netloc:
        raise ValueError("远程地址格式无效")
    return value


class CompareRemoteClient:
    def __init__(self, config: dict[str, Any], base_url: str, token: str) -> None:
        self.config = config
        self.base_url = normalize_remote_base_url(base_url)
        self.token = (token or "").strip()
        if not self.token:
            raise ValueError("远程联邦令牌不能为空")
        assert_remote_host_allowed(config, self.base_url)
        self.timeout = float(config.get("COMPARE_REMOTE_TIMEOUT_SEC") or 30)
        self.retry_count = int(config.get("COMPARE_REMOTE_RETRY_COUNT") or 2)

    def _should_retry(self, error: Exception) -> bool:
        if isinstance(error, HTTPError):
            return error.code in (408, 429, 500, 502, 503, 504)
        if isinstance(error, URLError):
            return True
        if isinstance(error, CompareRemoteError):
            message = str(error)
            return "无法连接远程实例" in message or "远程请求失败（5" in message
        return False

    def _request_json_once(
        self,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        method: str = "GET",
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query_pairs = {key: value for key, value in (query or {}).items() if value is not None and value != ""}
        url = f"{self.base_url}{path}"
        if query_pairs:
            url = f"{url}?{urlencode(query_pairs)}"
        headers = {
            "Accept": "application/json",
            "X-Federation-Token": self.token,
        }
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            url,
            data=data,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(detail)
                message = payload.get("message") or detail
            except json.JSONDecodeError:
                message = detail or str(error)
            raise CompareRemoteError(f"远程请求失败（{error.code}）：{message}") from error
        except URLError as error:
            raise CompareRemoteError(f"无法连接远程实例：{error.reason}") from error

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as error:
            raise CompareRemoteError("远程响应不是有效 JSON") from error
        if not isinstance(payload, dict):
            raise CompareRemoteError("远程响应格式无效")
        return payload

    def _request_json(
        self,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        method: str = "GET",
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                return self._request_json_once(path, query=query, method=method, body=body)
            except (HTTPError, URLError, CompareRemoteError) as error:
                last_error = error
                if attempt >= self.retry_count or not self._should_retry(error):
                    if isinstance(error, CompareRemoteError):
                        raise
                    if isinstance(error, HTTPError):
                        detail = error.read().decode("utf-8", errors="replace")
                        try:
                            payload = json.loads(detail)
                            message = payload.get("message") or detail
                        except json.JSONDecodeError:
                            message = detail or str(error)
                        raise CompareRemoteError(f"远程请求失败（{error.code}）：{message}") from error
                    raise CompareRemoteError(f"无法连接远程实例：{error.reason}") from error
                time.sleep(0.4 * (attempt + 1))
        if last_error:
            raise last_error
        raise CompareRemoteError("远程请求失败")

    def health(self) -> dict[str, Any]:
        return self._request_json("/api/federation/health")

    def list_accounts_page(self, *, cursor: str | None = None, limit: int = DEFAULT_ACCOUNTS_PAGE_SIZE) -> dict[str, Any]:
        return self._request_json(
            "/api/federation/accounts",
            query={"cursor": cursor, "limit": limit},
        )

    def list_boards_page(
        self,
        tenant_type: str,
        tenant_id: str,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_BOARDS_PAGE_SIZE,
    ) -> dict[str, Any]:
        return self._request_json(
            f"/api/federation/accounts/{tenant_type}/{tenant_id}/boards",
            query={"cursor": cursor, "limit": limit},
        )

    def get_board_meta(self, tenant_type: str, tenant_id: str, board_id: str) -> dict[str, Any]:
        return self._request_json(
            f"/api/federation/accounts/{tenant_type}/{tenant_id}/boards/{board_id}/meta",
        )

    def get_board_lists(self, tenant_type: str, tenant_id: str, board_id: str) -> dict[str, Any]:
        return self._request_json(
            f"/api/federation/accounts/{tenant_type}/{tenant_id}/boards/{board_id}/lists",
        )

    def list_cards_page(
        self,
        tenant_type: str,
        tenant_id: str,
        board_id: str,
        list_id: str,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_CARDS_PAGE_SIZE,
        include_description: bool = False,
    ) -> dict[str, Any]:
        return self._request_json(
            f"/api/federation/accounts/{tenant_type}/{tenant_id}/boards/{board_id}/lists/{list_id}/cards",
            query={
                "cursor": cursor,
                "limit": limit,
                "include_description": "1" if include_description else None,
            },
        )

    def load_board_full_sync_payload(self, tenant_type: str, tenant_id: str, board_id: str) -> dict[str, Any]:
        payload = self._request_json(
            f"/api/federation/accounts/{tenant_type}/{tenant_id}/boards/{board_id}/export",
        )
        return payload.get("payload") or payload

    def apply_board_sync(
        self,
        tenant_type: str,
        tenant_id: str,
        sync_payload: dict[str, Any],
        *,
        target_board_id: str | None = None,
        mode: str = "replace",
    ) -> dict[str, Any]:
        return self._request_json(
            f"/api/federation/accounts/{tenant_type}/{tenant_id}/boards/sync",
            method="POST",
            body={
                "payload": sync_payload,
                "target_board_id": target_board_id,
                "mode": mode,
            },
        )

    def load_board_compare_snapshot(
        self,
        tenant_type: str,
        tenant_id: str,
        board_id: str,
        *,
        include_description: bool = False,
    ) -> dict[str, Any]:
        meta = self.get_board_meta(tenant_type, tenant_id, board_id)
        lists_payload = self.get_board_lists(tenant_type, tenant_id, board_id)
        cards_by_list: dict[str, list[dict[str, Any]]] = {}
        for lst in lists_payload.get("lists") or []:
            list_id = str(lst.get("id"))
            cards: list[dict[str, Any]] = []
            cursor = None
            while True:
                page = self.list_cards_page(
                    tenant_type,
                    tenant_id,
                    board_id,
                    list_id,
                    cursor=cursor,
                    limit=DEFAULT_CARDS_PAGE_SIZE,
                    include_description=include_description,
                )
                cards.extend(page.get("items") or [])
                if page.get("done"):
                    break
                cursor = page.get("next_cursor")
                if not cursor:
                    break
            cards_by_list[list_id] = cards
        return {
            "board": meta.get("board") or {},
            "lists": lists_payload.get("lists") or [],
            "cards_by_list": cards_by_list,
        }

    def iter_accounts(self, *, limit: int = DEFAULT_ACCOUNTS_PAGE_SIZE):
        cursor = None
        while True:
            page = self.list_accounts_page(cursor=cursor, limit=limit)
            items = page.get("items") or []
            if items:
                yield items
            if page.get("done"):
                break
            cursor = page.get("next_cursor")
            if not cursor:
                break

    def iter_boards(self, tenant_type: str, tenant_id: str, *, limit: int = DEFAULT_BOARDS_PAGE_SIZE):
        cursor = None
        while True:
            page = self.list_boards_page(tenant_type, tenant_id, cursor=cursor, limit=limit)
            items = page.get("items") or []
            if items:
                yield items
            if page.get("done"):
                break
            cursor = page.get("next_cursor")
            if not cursor:
                break
