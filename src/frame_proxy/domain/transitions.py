from __future__ import annotations

from typing import Any

from frame_proxy.domain.errors import StateError
from frame_proxy.domain.models import Transition, utc_now


CLIP_TRANSITIONS: dict[str, set[str]] = {
    "probing": {"registered"},
}

INSPECTION_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"scanning", "failed"},
    "scanning": {"indexed", "failed"},
    "indexed": set(),
    "failed": set(),
}

CONTACT_SHEET_TRANSITIONS: dict[str, set[str]] = {
    "planned": {"compositing", "failed"},
    "compositing": {"ready", "failed"},
    "ready": set(),
    "failed": set(),
}


def _move(
    record: Any,
    target: str,
    allowed: dict[str, set[str]],
    *,
    reason: str | None = None,
) -> None:
    current = str(record.state)
    if target not in allowed.get(current, set()):
        raise StateError(
            f"cannot move state from {current} to {target}",
            details={"from": current, "to": target},
        )
    at = utc_now()
    record.state = target
    record.transitions.append(
        Transition(
            from_state=current,
            to_state=target,
            at=at,
            reason=reason,
        )
    )
    if hasattr(record, "updated_at"):
        record.updated_at = at


def transition_clip(record: Any, target: str, *, reason: str | None = None) -> None:
    _move(record, target, CLIP_TRANSITIONS, reason=reason)


def transition_inspection(
    record: Any,
    target: str,
    *,
    reason: str | None = None,
) -> None:
    _move(record, target, INSPECTION_TRANSITIONS, reason=reason)


def transition_contact_sheet(
    record: Any,
    target: str,
    *,
    reason: str | None = None,
) -> None:
    _move(record, target, CONTACT_SHEET_TRANSITIONS, reason=reason)
