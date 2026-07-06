#!/usr/bin/env python3
"""对比 + 同步 API 自测：登录 → 探测 → 对比 → 按差异类型测 sync / sync-account。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import urllib.error
import urllib.request
from collections import defaultdict
from http.cookiejar import CookieJar
from typing import Any, Protocol

REMOTE_URL = "https://board-flow-wheat.vercel.app"
REMOTE_TOKEN = "chenwl"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"


class ApiClient(Protocol):
    def json(self, method: str, path: str, *, body: dict | None = None) -> tuple[int, dict]: ...

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        raw_body: bytes | None = None,
        headers: dict | None = None,
    ) -> tuple[int, str]: ...


class HttpClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        raw_body: bytes | None = None,
        headers: dict | None = None,
    ) -> tuple[int, str]:
        url = f"{self.base_url}{path}"
        req_headers = dict(headers or {})
        data = raw_body
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
        try:
            with self.opener.open(request, timeout=180) as response:
                return response.status, response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", errors="replace")

    def json(self, method: str, path: str, *, body: dict | None = None) -> tuple[int, dict]:
        status, text = self.request(method, path, body=body)
        return status, _parse_json(status, text)


class FlaskTestClient:
    def __init__(self) -> None:
        from app import app

        self.client = app.test_client()

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        raw_body: bytes | None = None,
        headers: dict | None = None,
    ) -> tuple[int, str]:
        kwargs: dict[str, Any] = {"method": method.upper(), "headers": headers or {}}
        if raw_body is not None:
            kwargs["data"] = raw_body
        elif body is not None:
            kwargs["json"] = body
        response = self.client.open(path, **kwargs)
        return response.status_code, response.get_data(as_text=True)

    def json(self, method: str, path: str, *, body: dict | None = None) -> tuple[int, dict]:
        status, text = self.request(method, path, body=body)
        return status, _parse_json(status, text)


def _parse_json(status: int, text: str) -> dict:
    try:
        payload = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        payload = {"message": text[:300]}
    if not isinstance(payload, dict):
        payload = {"message": str(payload)}
    return payload


def ok(label: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"  [PASS] {label}{suffix}")


def fail(label: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"  [FAIL] {label}{suffix}")


def run_compare(client: ApiClient, session_id: str) -> tuple[bool, dict]:
    status, raw = client.request("POST", f"/api/compare/sessions/{session_id}/run", body={})
    if status != 200:
        return False, {"message": raw[:200]}
    last_event: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last_event = json.loads(line)
        except json.JSONDecodeError:
            continue
    if last_event.get("error") or not last_event.get("done"):
        return False, last_event
    return True, last_event


def run_tests(client: ApiClient, mode_label: str) -> int:
    print(f"=== BoardFlow 对比/同步自测 ({mode_label}) ===\n")
    failures = 0

    status, payload = client.json("POST", "/api/auth/login", body={"username": ADMIN_USER, "password": ADMIN_PASS})
    if status != 200:
        print(f"登录失败 HTTP {status}: {payload.get('message')}")
        return 1
    ok("登录 super_admin")

    for path, body in (
        ("/api/compare/sessions/00000000-0000-0000-0000-000000000000/sync", {"pair_index": 0, "direction": "to_remote"}),
        (
            "/api/compare/sessions/00000000-0000-0000-0000-000000000000/sync-account",
            {"account_pair_index": 0, "direction": "to_remote"},
        ),
    ):
        status, payload = client.json("POST", path, body=body)
        if status == 404 and "requested URL was not found" in str(payload.get("message", "")):
            fail(f"路由 404 {path}", payload.get("message", ""))
            failures += 1
        elif status in (400, 404):
            ok(f"路由可达 {path}", f"HTTP {status}")
        else:
            fail(f"意外响应 {path}", f"HTTP {status} {payload.get('message')}")

    status, payload = client.json(
        "POST",
        "/api/compare/sessions",
        body={
            "remote_base_url": REMOTE_URL,
            "remote_token": REMOTE_TOKEN,
            "match_mode": "by_title",
            "options": {"compare_lists": True, "compare_cards": True, "compare_card_description": False},
        },
    )
    if status not in (200, 201):
        fail("创建对比会话", f"HTTP {status} {payload.get('message')}")
        return 1
    session_id = payload.get("session_id")
    ok("探测远程并创建会话", f"session={session_id[:8]}… remote={payload.get('remote_health', {}).get('label')}")

    passed, last_event = run_compare(client, session_id)
    if not passed:
        fail("运行对比", str(last_event.get("message") or last_event))
        return 1
    ok("对比完成", f"step={last_event.get('step')} percent={last_event.get('percent')}")
    totals = last_event.get("totals") or {}
    if totals:
        print(
            f"  统计: 看板={totals.get('queued_board_pairs')} "
            f"一致={totals.get('boards_equal')} 差异={totals.get('boards_changed')} "
            f"仅本地={totals.get('boards_only_local')} 仅远程={totals.get('boards_only_remote')}"
        )

    status, session = client.json("GET", f"/api/compare/sessions/{session_id}")
    if status != 200:
        fail("读取会话", f"HTTP {status} {payload.get('message')}")
        failures += 1
    else:
        progress = session.get("progress") or {}
        ok("读取会话", f"看板摘要 {len(progress.get('board_results_summary') or [])} 条")

    status, results_payload = client.json("GET", f"/api/compare/sessions/{session_id}/results")
    if status != 200:
        fail("读取对比结果", f"HTTP {status}")
        return 1
    board_results = results_payload.get("items") or []
    account_pairs = (session.get("progress") or {}).get("account_pairs") or [] if status == 200 else []

    groups: dict[str, list[dict]] = defaultdict(list)
    for item in board_results:
        groups[item.get("pair_status") or "matched"].append(
            {
                "pair_index": int(item.get("pair_index", -1)),
                "diff_status": item.get("status") or "unknown",
                "local_title": item.get("local_title"),
                "remote_title": item.get("remote_title"),
            }
        )

    print("\n--- 看板对分布 ---")
    for key in ("matched", "only_local", "only_remote"):
        items = groups.get(key) or []
        if items:
            print(f"  {key}: {len(items)}")

    def sync_board(pair_index: int, direction: str) -> tuple[bool, str]:
        status, payload = client.json(
            "POST",
            f"/api/compare/sessions/{session_id}/sync",
            body={"pair_index": pair_index, "direction": direction, "mode": "replace"},
        )
        message = str(payload.get("message") or payload)
        if status == 404 and "requested URL was not found" in message:
            return False, f"HTTP 404: {message}"
        if status != 200:
            return False, f"HTTP {status}: {message}"
        return True, message

    def sync_account(account_pair_index: int, direction: str) -> tuple[bool, str]:
        status, payload = client.json(
            "POST",
            f"/api/compare/sessions/{session_id}/sync-account",
            body={"account_pair_index": account_pair_index, "direction": direction, "mode": "replace"},
        )
        message = str(payload.get("message") or payload)
        if status == 404 and "requested URL was not found" in message:
            return False, f"HTTP 404: {message}"
        if status != 200:
            return False, f"HTTP {status}: {message}"
        return True, f"{message} (synced={payload.get('synced_count', 0)}, errors={payload.get('error_count', 0)})"

    print("\n--- 看板 sync ---")
    for qs, direction, expect_fail in (
        ("only_remote", "to_remote", True),
        ("only_local", "to_local", True),
    ):
        candidates = groups.get(qs) or []
        if not candidates:
            print(f"  [SKIP] 无 {qs}，跳过非法方向校验")
            continue
        pair_index = candidates[0]["pair_index"]
        status, payload = client.json(
            "POST",
            f"/api/compare/sessions/{session_id}/sync",
            body={"pair_index": pair_index, "direction": direction, "mode": "replace"},
        )
        if expect_fail and status == 400:
            ok(f"非法 sync {qs} {direction}", str(payload.get("message", ""))[:80])
        elif status == 404:
            fail(f"非法 sync 却 404 {qs} {direction}", str(payload.get("message", "")))
            failures += 1
        elif expect_fail:
            fail(f"非法 sync 应 400 {qs} {direction}", f"HTTP {status}")
            failures += 1

    sync_plan = (
        ("matched", "to_remote", "有匹配 → 远程"),
        ("matched", "to_local", "有匹配 ← 远程"),
        ("only_local", "to_remote", "仅本地 → 远程"),
        ("only_remote", "to_local", "仅远程 ← 本地"),
    )
    for qs, direction, label in sync_plan:
        candidates = groups.get(qs) or []
        if not candidates:
            print(f"  [SKIP] {label}：无 {qs} 样本")
            continue
        if qs == "matched":
            changed = [c for c in candidates if c["diff_status"] == "changed"]
            sample = changed[0] if changed else candidates[0]
        else:
            sample = candidates[0]
        passed, detail = sync_board(sample["pair_index"], direction)
        if passed:
            ok(f"{label} (#{sample['pair_index']})", detail)
        else:
            fail(f"{label} (#{sample['pair_index']})", detail)
            failures += 1

    print("\n--- 账号 sync-account ---")
    matched_accounts = [p for p in account_pairs if (p.get("status") or "matched") == "matched"]
    only_remote_accounts = [
        (index, pair) for index, pair in enumerate(account_pairs) if (pair.get("status") or "") == "only_remote"
    ]
    if matched_accounts:
        passed, detail = sync_account(0, "to_remote")
        if passed:
            ok("matched 账号批量 → 远程", detail)
        else:
            fail("matched 账号批量 → 远程", detail)
            failures += 1
    else:
        print("  [SKIP] 无 matched 账号对")

    if only_remote_accounts:
        account_pair_index = only_remote_accounts[0][0]
        remote = only_remote_accounts[0][1].get("remote") or {}
        tt, ti = str(remote.get("tenant_type") or ""), str(remote.get("tenant_id") or "")
        syncable = sum(
            1
            for item in board_results
            if item.get("pair_status") == "only_remote"
            and str(item.get("tenant_type") or "") == tt
            and str(item.get("tenant_id") or "") == ti
            and item.get("remote_board_id")
        )
        if syncable <= 0:
            print("  [SKIP] only_remote 账号无看板")
        else:
            passed, detail = sync_account(account_pair_index, "to_local")
            if passed:
                ok("only_remote 账号批量 ← 远程", detail)
            else:
                fail("only_remote 账号批量 ← 远程", detail)
                failures += 1
    else:
        print("  [SKIP] 无 only_remote 账号对")

    print("\n=== 结果 ===")
    if failures:
        print(f"失败 {failures} 项")
        return 1
    print("全部通过")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="BoardFlow 对比/同步自测")
    parser.add_argument("--live", action="store_true", help="请求运行中的 HTTP 服务（默认走 Flask test_client）")
    parser.add_argument("--base-url", default="http://127.0.0.1:9213", help="--live 模式下的服务地址")
    args = parser.parse_args()

    if args.live:
        return run_tests(HttpClient(args.base_url), f"HTTP {args.base_url}")
    return run_tests(FlaskTestClient(), "进程内 test_client")


if __name__ == "__main__":
    sys.exit(main())
