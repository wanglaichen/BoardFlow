from __future__ import annotations

import secrets
from typing import Any

import bcrypt
from flask import session

from services.tenant_keys import SUPER_ADMIN_ID, build_tenant_context


SESSION_USER_KEY = "boardflow_user"


class AuthService:
    def __init__(self, config: dict[str, Any], user_service) -> None:
        self.config = config
        self.user_service = user_service
        self.super_admin_username = (config.get("SUPER_ADMIN_USERNAME") or "").strip()
        self.super_admin_password = config.get("SUPER_ADMIN_PASSWORD") or ""
        self.super_admin_password_hash = config.get("SUPER_ADMIN_PASSWORD_HASH") or ""

    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, password: str, password_hash: str) -> bool:
        if not password or not password_hash:
            return False
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except ValueError:
            return False

    def _verify_super_admin_password(self, password: str) -> bool:
        if self.super_admin_password_hash:
            return self.verify_password(password, self.super_admin_password_hash)
        return bool(self.super_admin_password) and secrets.compare_digest(password, self.super_admin_password)

    def login(self, username: str, password: str) -> dict[str, Any]:
        normalized_username = (username or "").strip()
        if not normalized_username or not password:
            raise ValueError("用户名和密码不能为空")

        if self.super_admin_username and normalized_username == self.super_admin_username:
            if not self._verify_super_admin_password(password):
                raise ValueError("用户名或密码错误")
            user = {
                "id": SUPER_ADMIN_ID,
                "username": self.super_admin_username,
                "display_name": "超级管理员",
                "is_super_admin": True,
                "status": "active",
            }
            session[SESSION_USER_KEY] = user
            return self.public_user(user)

        user = self.user_service.get_user_by_username(normalized_username)
        if not user or user.get("status") == "disabled":
            raise ValueError("用户名或密码错误")
        if not self.verify_password(password, user.get("password_hash") or ""):
            raise ValueError("用户名或密码错误")

        session_user = {
            "id": user["id"],
            "username": user["username"],
            "display_name": user.get("display_name") or user["username"],
            "is_super_admin": False,
            "status": user.get("status", "active"),
        }
        session[SESSION_USER_KEY] = session_user
        self.user_service.ensure_user_tenant(user["id"])
        return self.public_user(session_user)

    def logout(self) -> None:
        session.pop(SESSION_USER_KEY, None)

    def get_current_user(self) -> dict[str, Any] | None:
        user = session.get(SESSION_USER_KEY)
        if not isinstance(user, dict):
            return None
        return user

    def require_user(self) -> dict[str, Any]:
        user = self.get_current_user()
        if not user:
            raise PermissionError("请先登录")
        return user

    def require_super_admin(self) -> dict[str, Any]:
        user = self.require_user()
        if not user.get("is_super_admin"):
            raise PermissionError("仅超级管理员可执行此操作")
        return user

    def get_current_tenant(self) -> dict[str, Any]:
        user = self.require_user()
        return build_tenant_context(user)

    @staticmethod
    def public_user(user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": user.get("id"),
            "username": user.get("username"),
            "display_name": user.get("display_name") or user.get("username"),
            "is_super_admin": bool(user.get("is_super_admin")),
            "status": user.get("status", "active"),
        }
