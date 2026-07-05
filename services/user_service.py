from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from services.tenant_keys import USER_TENANT_TYPE, build_tenant_context

_PASSWORD_PATTERN = re.compile(r"^[A-Za-z0-9]+$")


def _validate_password(password: str) -> None:
    if not password:
        raise ValueError("密码不能为空")
    if len(password) <= 1:
        raise ValueError("密码至少 2 个字符")
    if not _PASSWORD_PATTERN.match(password):
        raise ValueError("密码只能包含英文字母和数字")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class UserService:
    def __init__(self, storage, auth_service) -> None:
        self.storage = storage
        self.auth_service = auth_service

    def list_users(self) -> list[dict[str, Any]]:
        return [self.public_user(item) for item in self.storage.list_users()]

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        user = self.storage.get_user(user_id)
        return self.public_user(user) if user else None

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        return self.storage.get_user_by_username((username or "").strip())

    def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        display_name = (payload.get("display_name") or username).strip()
        if not username:
            raise ValueError("用户名不能为空")
        if len(username) < 2:
            raise ValueError("用户名至少 2 个字符")
        _validate_password(password)
        if self.get_user_by_username(username):
            raise ValueError("用户名已存在")
        if self.auth_service.super_admin_username and username == self.auth_service.super_admin_username:
            raise ValueError("不能使用超级管理员用户名")

        user_id = f"user_{uuid.uuid4().hex[:8]}"
        user = {
            "id": user_id,
            "username": username,
            "display_name": display_name,
            "password_hash": self.auth_service.hash_password(password),
            "friends": [],
            "status": "active",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        self.storage.save_user(user)
        self.ensure_user_tenant(user_id)
        return self.public_user(user)

    def update_user(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        user = self.storage.get_user(user_id)
        if not user:
            raise ValueError("用户不存在")

        if "display_name" in payload:
            display_name = (payload.get("display_name") or "").strip()
            if not display_name:
                raise ValueError("显示名称不能为空")
            user["display_name"] = display_name

        if "password" in payload and payload.get("password"):
            _validate_password(payload["password"])
            user["password_hash"] = self.auth_service.hash_password(payload["password"])

        if "status" in payload:
            status = (payload.get("status") or "active").strip()
            if status not in {"active", "disabled"}:
                raise ValueError("无效的用户状态")
            user["status"] = status

        user["updated_at"] = _now_iso()
        self.storage.save_user(user)
        return self.public_user(user)

    def delete_user(self, user_id: str) -> None:
        user = self.storage.get_user(user_id)
        if not user:
            raise ValueError("用户不存在")
        self.storage.delete_user(user_id)
        self.storage.delete_user_tenant(user_id)

    def search_users(self, query: str, current_user_id: str) -> list[dict[str, Any]]:
        keyword = (query or "").strip().lower()
        if not keyword:
            return []
        results: list[dict[str, Any]] = []
        for user in self.storage.list_users():
            if user.get("id") == current_user_id:
                continue
            if user.get("status") == "disabled":
                continue
            haystack = f"{user.get('username', '')} {user.get('display_name', '')}".lower()
            if keyword in haystack:
                results.append(self.public_user(user))
        return results[:20]

    def list_friends(self, user_id: str) -> list[dict[str, Any]]:
        user = self.storage.get_user(user_id)
        if not user:
            return []
        friends = user.get("friends") or []
        return [dict(item) for item in friends if isinstance(item, dict)]

    def add_friend(self, user_id: str, friend_username: str) -> list[dict[str, Any]]:
        user = self.storage.get_user(user_id)
        if not user:
            raise ValueError("当前用户不存在")
        friend = self.get_user_by_username(friend_username)
        if not friend:
            raise ValueError("未找到该用户")
        if friend["id"] == user_id:
            raise ValueError("不能添加自己为好友")
        if friend.get("status") == "disabled":
            raise ValueError("该用户不可用")

        self._append_friend(user, friend)
        self._append_friend(friend, user)
        return self.list_friends(user_id)

    def remove_friend(self, user_id: str, friend_user_id: str) -> list[dict[str, Any]]:
        user = self.storage.get_user(user_id)
        friend = self.storage.get_user(friend_user_id)
        if not user:
            raise ValueError("当前用户不存在")
        if friend:
            self._remove_friend(user, friend_user_id)
            self._remove_friend(friend, user_id)
        else:
            self._remove_friend(user, friend_user_id)
        return self.list_friends(user_id)

    def ensure_user_tenant(self, user_id: str) -> None:
        tenant_ctx = build_tenant_context(
            {"id": user_id, "is_super_admin": False, "username": "", "display_name": ""}
        )
        self.storage.ensure_tenant(tenant_ctx)

    def _append_friend(self, owner: dict[str, Any], friend: dict[str, Any]) -> None:
        friends = owner.setdefault("friends", [])
        if any(item.get("user_id") == friend["id"] for item in friends):
            return
        friends.append(
            {
                "user_id": friend["id"],
                "username": friend.get("username"),
                "display_name": friend.get("display_name") or friend.get("username"),
                "added_at": _now_iso(),
            }
        )
        owner["updated_at"] = _now_iso()
        self.storage.save_user(owner)

    def _remove_friend(self, owner: dict[str, Any], friend_user_id: str) -> None:
        friends = owner.get("friends") or []
        owner["friends"] = [item for item in friends if item.get("user_id") != friend_user_id]
        owner["updated_at"] = _now_iso()
        self.storage.save_user(owner)

    @staticmethod
    def public_user(user: dict[str, Any] | None) -> dict[str, Any]:
        if not user:
            return {}
        return {
            "id": user.get("id"),
            "username": user.get("username"),
            "display_name": user.get("display_name") or user.get("username"),
            "status": user.get("status", "active"),
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
        }
