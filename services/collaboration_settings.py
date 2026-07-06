from __future__ import annotations

import copy
from typing import Any

DEFAULT_COLLABORATION: dict[str, Any] = {
    "enabled": True,
    "card_optimistic_lock": True,
    "editor_exclusive_lock": True,
    "lease_ttl_sec": 300,
    "heartbeat_interval_sec": 60,
    "allow_force_takeover": False,
    "locked_editors": ["canvas", "mindmap", "table"],
}


def normalize_collaboration(raw: dict[str, Any] | None) -> dict[str, Any]:
    merged = copy.deepcopy(DEFAULT_COLLABORATION)
    if not isinstance(raw, dict):
        return merged

    for key in ("enabled", "card_optimistic_lock", "editor_exclusive_lock", "allow_force_takeover"):
        if key in raw:
            merged[key] = bool(raw[key])

    for key in ("lease_ttl_sec", "heartbeat_interval_sec"):
        if key in raw:
            try:
                value = int(raw[key])
            except (TypeError, ValueError):
                continue
            merged[key] = max(30, min(value, 3600))

    editors = raw.get("locked_editors")
    if isinstance(editors, list):
        cleaned = [str(item).strip() for item in editors if str(item).strip()]
        if cleaned:
            merged["locked_editors"] = cleaned

    return merged


def merge_settings_collaboration(settings: dict[str, Any] | None) -> dict[str, Any]:
    settings = settings if isinstance(settings, dict) else {}
    return normalize_collaboration(settings.get("collaboration"))


def is_editor_lock_enabled(config: dict[str, Any], editor_key: str) -> bool:
    if not config.get("enabled") or not config.get("editor_exclusive_lock"):
        return False
    return editor_key in (config.get("locked_editors") or [])


def is_card_optimistic_lock_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("enabled") and config.get("card_optimistic_lock"))
