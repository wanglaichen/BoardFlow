from __future__ import annotations

import hashlib
from typing import Any

from services.org_keys import ORG_NAMESPACE, org_root, PERSONAL_ORG_ID

USER_NAMESPACE = "jjob:boardflow:user"
SUPER_ADMIN_TENANT_TYPE = "super_admin"
USER_TENANT_TYPE = "user"
SUPER_ADMIN_ID = "super_admin"


def user_scope_root(user_id: str) -> str:
    return f"{USER_NAMESPACE}:{user_id}"


def orgshare_key(key_prefix: str = "jjob:boardflow") -> str:
    return f"{key_prefix.rstrip(':')}:orgshare"


def user_shared_boards_key(user_id: str) -> str:
    """用户收到的分享看板快速索引（逐看板，非本人创建）。"""
    return f"{user_scope_root(user_id)}:shared_boards"


def user_shared_org_index_key(user_id: str) -> str:
    """用户收到的分享看板按组织分组的快速索引（便于侧边栏按组织浏览）。"""
    return f"{user_scope_root(user_id)}:shared_org_index"


def shared_org_index_entry_id(owner_tenant_type: str, owner_tenant_id: str, organization_id: str) -> str:
    raw = f"{owner_tenant_type}:{owner_tenant_id}:{organization_id}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"shared_org_{digest}"


def settings_users_key(settings_key: str) -> str:
    return f"{settings_key.rstrip(':')}:users"


def legacy_settings_user_organizations_key(settings_key: str, user_id: str) -> str:
    return f"{settings_key.rstrip(':')}:user:{user_id}:organizations"


def legacy_settings_user_shared_organizations_key(settings_key: str, user_id: str) -> str:
    return f"{settings_key.rstrip(':')}:user:{user_id}:shared_organizations"


def legacy_settings_user_shared_boards_key(settings_key: str, user_id: str) -> str:
    return f"{settings_key.rstrip(':')}:user:{user_id}:shared_boards"


def legacy_user_share_inbox_key(user_id: str) -> str:
    return f"{user_scope_root(user_id)}:share_inbox"


def shared_board_entry_id(owner_tenant_type: str, owner_tenant_id: str, board_id: str) -> str:
    raw = f"{owner_tenant_type}:{owner_tenant_id}:{board_id}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"shared_board_{digest}"


def scope_boards_key(scope_root: str) -> str:
    return f"{scope_root}:boards"


def scope_meta_key(scope_root: str) -> str:
    return f"{scope_root}:meta"


def scope_board_lists_key(scope_root: str, board_id: str) -> str:
    return f"{scope_root}:boards:{board_id}:lists"


def scope_list_cards_key(scope_root: str, board_id: str, list_id: str) -> str:
    return f"{scope_root}:boards:{board_id}:lists:{list_id}:cards"


def scope_list_state_key(scope_root: str, board_id: str, list_id: str) -> str:
    return f"{scope_root}:boards:{board_id}:lists:{list_id}:state"


def scope_card_detail_key(scope_root: str, board_id: str, list_id: str, card_id: str) -> str:
    return f"{scope_root}:boards:{board_id}:lists:{list_id}:detail:{card_id}"


def build_tenant_context(user_session: dict[str, Any]) -> dict[str, Any]:
    if user_session.get("is_super_admin"):
        return {
            "type": SUPER_ADMIN_TENANT_TYPE,
            "id": SUPER_ADMIN_ID,
            "scope_mode": "org_multi",
        }
    user_id = str(user_session.get("id") or "")
    return {
        "type": USER_TENANT_TYPE,
        "id": user_id,
        "scope_mode": "user_single",
        "scope_root": user_scope_root(user_id),
    }


def tenant_scope_roots(tenant_ctx: dict[str, Any], settings: dict[str, Any] | None = None) -> list[str]:
    if tenant_ctx.get("scope_mode") == "user_single":
        return [str(tenant_ctx.get("scope_root") or user_scope_root(tenant_ctx["id"]))]
    return [org_root(org_id) for org_id in _discover_admin_org_ids(settings or {})]


def _discover_admin_org_ids(settings: dict[str, Any]) -> set[str]:
    from services.org_keys import PERSONAL_ORG_ID

    org_ids = {PERSONAL_ORG_ID}
    for org in settings.get("organizations") or []:
        if not org.get("id"):
            continue
        creator_type = org.get("created_by_type") or SUPER_ADMIN_TENANT_TYPE
        if creator_type == SUPER_ADMIN_TENANT_TYPE:
            org_ids.add(str(org["id"]))
    return org_ids


def owner_tenant_scope_root(owner_tenant_type: str, owner_tenant_id: str) -> str:
    if owner_tenant_type == SUPER_ADMIN_TENANT_TYPE:
        return org_root(PERSONAL_ORG_ID)
    return user_scope_root(owner_tenant_id)
