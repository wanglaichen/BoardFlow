from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from services.collaboration_settings import merge_settings_collaboration, normalize_collaboration


class LockHeldError(Exception):
    def __init__(self, message: str = "资源正在被其他人编辑", *, holder: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.holder = holder or {}


class EditLockRequiredError(Exception):
    pass


class InvalidLockTokenError(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class EditLockService:
    """卡片编辑器独占锁：Redis SET NX EX，无 Redis 时进程内 TTL 字典。"""

    def __init__(self, storage, config: dict[str, Any]) -> None:
        self.storage = storage
        self.key_prefix = (config.get("REDIS_KEY_PREFIX") or "jjob:boardflow").rstrip(":")
        self._memory_lock = threading.RLock()
        self._memory: dict[str, tuple[str, float]] = {}

    def _collaboration(self) -> dict[str, Any]:
        settings = self.storage.read_settings()
        return merge_settings_collaboration(settings)

    def _lease_ttl(self) -> int:
        return int(self._collaboration().get("lease_ttl_sec") or 300)

    def lock_key(
        self,
        *,
        tenant_type: str,
        tenant_id: str,
        board_id: str,
        card_id: str,
        scope: str,
    ) -> str:
        return (
            f"{self.key_prefix}:edit_lock:"
            f"{tenant_type}:{tenant_id}:{board_id}:{card_id}:{scope}"
        )

    def _redis_client(self):
        backend = getattr(self.storage, "_backend", None)
        if backend is None:
            return None
        primary = getattr(backend, "primary", backend)
        if hasattr(primary, "client"):
            return primary.client
        if hasattr(backend, "client"):
            return backend.client
        return None

    def _read_lock(self, key: str) -> dict[str, Any] | None:
        client = self._redis_client()
        if client is not None:
            raw = client.get(key)
            if not raw:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                return None
            return payload if isinstance(payload, dict) else None

        now = time.time()
        with self._memory_lock:
            entry = self._memory.get(key)
            if not entry:
                return None
            raw, expires_at = entry
            if expires_at <= now:
                self._memory.pop(key, None)
                return None
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                self._memory.pop(key, None)
                return None
            return payload if isinstance(payload, dict) else None

    def _write_lock(self, key: str, payload: dict[str, Any], ttl_sec: int) -> None:
        raw = json.dumps(payload, ensure_ascii=False)
        client = self._redis_client()
        if client is not None:
            client.set(key, raw, ex=max(1, ttl_sec))
            return

        expires_at = time.time() + ttl_sec
        with self._memory_lock:
            self._memory[key] = (raw, expires_at)

    def _delete_lock(self, key: str) -> None:
        client = self._redis_client()
        if client is not None:
            client.delete(key)
            return
        with self._memory_lock:
            self._memory.pop(key, None)

    def get_lock(
        self,
        *,
        tenant_type: str,
        tenant_id: str,
        board_id: str,
        card_id: str,
        scope: str,
    ) -> dict[str, Any] | None:
        key = self.lock_key(
            tenant_type=tenant_type,
            tenant_id=tenant_id,
            board_id=board_id,
            card_id=card_id,
            scope=scope,
        )
        payload = self._read_lock(key)
        if not payload:
            return None
        ttl = self._lease_ttl()
        return {
            "scope": scope,
            "holder": {
                "user_id": payload.get("user_id"),
                "display_name": payload.get("display_name") or "其他用户",
                "client_id": payload.get("client_id"),
                "acquired_at": payload.get("acquired_at"),
                "last_heartbeat_at": payload.get("last_heartbeat_at"),
            },
            "expires_in_sec": ttl,
        }

    def acquire_lock(
        self,
        *,
        tenant_type: str,
        tenant_id: str,
        board_id: str,
        card_id: str,
        scope: str,
        user: dict[str, Any],
        client_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        config = self._collaboration()
        if not config.get("enabled") or not config.get("editor_exclusive_lock"):
            return {
                "token": "",
                "disabled": True,
                "heartbeat_interval_sec": config.get("heartbeat_interval_sec", 60),
            }

        key = self.lock_key(
            tenant_type=tenant_type,
            tenant_id=tenant_id,
            board_id=board_id,
            card_id=card_id,
            scope=scope,
        )
        ttl = self._lease_ttl()
        existing = self._read_lock(key)
        token = str(uuid.uuid4())
        now = _now_iso()
        user_id = str(user.get("id") or "")
        display_name = (user.get("display_name") or user.get("username") or "用户").strip()
        normalized_client_id = (client_id or str(uuid.uuid4())).strip()

        if existing:
            same_holder = str(existing.get("user_id") or "") == user_id
            if not force and not same_holder:
                raise LockHeldError(
                    holder={
                        "user_id": existing.get("user_id"),
                        "display_name": existing.get("display_name") or "其他用户",
                        "acquired_at": existing.get("acquired_at"),
                        "last_heartbeat_at": existing.get("last_heartbeat_at"),
                    }
                )
            if not force and same_holder and str(existing.get("client_id") or "") != normalized_client_id:
                raise LockHeldError(
                    message="你已在其他窗口编辑此内容",
                    holder={
                        "user_id": existing.get("user_id"),
                        "display_name": existing.get("display_name") or display_name,
                        "acquired_at": existing.get("acquired_at"),
                        "last_heartbeat_at": existing.get("last_heartbeat_at"),
                    },
                )
            token = str(existing.get("token") or token)

        payload = {
            "token": token,
            "user_id": user_id,
            "display_name": display_name,
            "client_id": normalized_client_id,
            "acquired_at": existing.get("acquired_at") if existing and force else now,
            "last_heartbeat_at": now,
        }
        self._write_lock(key, payload, ttl)
        return {
            "token": token,
            "client_id": normalized_client_id,
            "heartbeat_interval_sec": config.get("heartbeat_interval_sec", 60),
            "lease_ttl_sec": ttl,
        }

    def heartbeat(
        self,
        *,
        tenant_type: str,
        tenant_id: str,
        board_id: str,
        card_id: str,
        scope: str,
        token: str,
        user: dict[str, Any],
    ) -> dict[str, Any]:
        key = self.lock_key(
            tenant_type=tenant_type,
            tenant_id=tenant_id,
            board_id=board_id,
            card_id=card_id,
            scope=scope,
        )
        existing = self._read_lock(key)
        if not existing or str(existing.get("token") or "") != str(token or ""):
            raise InvalidLockTokenError("编辑锁已失效，请重新打开编辑器")
        if str(existing.get("user_id") or "") != str(user.get("id") or ""):
            raise InvalidLockTokenError("编辑锁不属于当前用户")

        existing["last_heartbeat_at"] = _now_iso()
        ttl = self._lease_ttl()
        self._write_lock(key, existing, ttl)
        return {"ok": True, "lease_ttl_sec": ttl}

    def release_lock(
        self,
        *,
        tenant_type: str,
        tenant_id: str,
        board_id: str,
        card_id: str,
        scope: str,
        token: str,
        user: dict[str, Any] | None = None,
    ) -> bool:
        key = self.lock_key(
            tenant_type=tenant_type,
            tenant_id=tenant_id,
            board_id=board_id,
            card_id=card_id,
            scope=scope,
        )
        existing = self._read_lock(key)
        if not existing:
            return False
        if str(existing.get("token") or "") != str(token or ""):
            return False
        if user and str(existing.get("user_id") or "") != str(user.get("id") or ""):
            return False
        self._delete_lock(key)
        return True

    def require_valid_lock(
        self,
        *,
        tenant_type: str,
        tenant_id: str,
        board_id: str,
        card_id: str,
        scope: str,
        token: str | None,
        user: dict[str, Any],
        enabled: bool,
    ) -> None:
        if not enabled:
            return
        if not token:
            raise EditLockRequiredError("缺少编辑锁，无法保存")
        key = self.lock_key(
            tenant_type=tenant_type,
            tenant_id=tenant_id,
            board_id=board_id,
            card_id=card_id,
            scope=scope,
        )
        existing = self._read_lock(key)
        if not existing or str(existing.get("token") or "") != str(token):
            raise InvalidLockTokenError("编辑锁已失效，请重新打开编辑器")
        if str(existing.get("user_id") or "") != str(user.get("id") or ""):
            raise InvalidLockTokenError("编辑锁不属于当前用户")

    def list_board_locks(
        self,
        *,
        tenant_type: str,
        tenant_id: str,
        board_id: str,
        card_ids: list[str],
        scopes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        scopes = scopes or ["canvas", "mindmap", "table"]
        items: list[dict[str, Any]] = []
        for card_id in card_ids:
            for scope in scopes:
                lock = self.get_lock(
                    tenant_type=tenant_type,
                    tenant_id=tenant_id,
                    board_id=board_id,
                    card_id=card_id,
                    scope=scope,
                )
                if lock:
                    lock["card_id"] = card_id
                    items.append(lock)
        return items
