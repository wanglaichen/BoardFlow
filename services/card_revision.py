from __future__ import annotations

from typing import Any


class ConflictError(Exception):
    def __init__(
        self,
        message: str = "卡片已被其他人更新",
        *,
        current: dict[str, Any] | None = None,
        base_revision: int | None = None,
    ) -> None:
        super().__init__(message)
        self.current = current or {}
        self.base_revision = base_revision


def card_revision(card: dict[str, Any]) -> int:
    try:
        return int(card.get("revision") or 0)
    except (TypeError, ValueError):
        return 0


def ensure_revision(card: dict[str, Any]) -> None:
    if "revision" not in card:
        card["revision"] = card_revision(card)


def bump_revision(card: dict[str, Any]) -> int:
    next_revision = card_revision(card) + 1
    card["revision"] = next_revision
    return next_revision


def assert_revision(
    card: dict[str, Any],
    base_revision: Any,
    *,
    enabled: bool = True,
    force: bool = False,
) -> None:
    if not enabled or force:
        return
    if base_revision is None:
        return

    try:
        expected = int(base_revision)
    except (TypeError, ValueError):
        raise ValueError("base_revision 无效")

    current = card_revision(card)
    if expected != current:
        raise ConflictError(
            current=dict(card),
            base_revision=expected,
        )
