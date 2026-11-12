from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from frame_proxy.domain.errors import ErrorCode, ValidationError


IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,47}$")
HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True, slots=True)
class InspectionRequest:
    inspection_id: str
    sensitivity: float
    sample_stride: int
    min_scene_frames: int


@dataclass(frozen=True, slots=True)
class ContactSheetRequest:
    sheet_id: str
    columns: int
    tile_width: int
    gutter: int
    selection: str
    background_rgb: tuple[int, int, int]


def validate_identifier(value: str, field_name: str) -> str:
    text = value.strip().lower()
    if not IDENTIFIER_PATTERN.fullmatch(text):
        raise ValidationError(
            f"{field_name} must match {IDENTIFIER_PATTERN.pattern}",
            code=ErrorCode.INVALID_IDENTIFIER,
            details={"field": field_name},
        )
    return text


def validate_clip_id(value: str) -> str:
    return validate_identifier(value, "clip_id")


def _require_object(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise ValidationError("request body must be a JSON object")
    return body


def _number(
    body: dict[str, Any],
    key: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    raw = body.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValidationError(f"{key} must be numeric", details={"field": key})
    value = float(raw)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValidationError(
            f"{key} must be between {minimum} and {maximum}",
            details={"field": key},
        )
    return value


def _integer(
    body: dict[str, Any],
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = body.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValidationError(f"{key} must be an integer", details={"field": key})
    if not minimum <= raw <= maximum:
        raise ValidationError(
            f"{key} must be between {minimum} and {maximum}",
            details={"field": key},
        )
    return raw


def validate_inspection_request(body: Any) -> InspectionRequest:
    value = _require_object(body)
    inspection_id = validate_identifier(
        str(value.get("inspection_id", "")),
        "inspection_id",
    )
    return InspectionRequest(
        inspection_id=inspection_id,
        sensitivity=_number(value, "sensitivity", 0.55, 0.05, 0.95),
        sample_stride=_integer(value, "sample_stride", 1, 1, 4),
        min_scene_frames=_integer(value, "min_scene_frames", 2, 1, 300),
    )


def _parse_color(raw: Any) -> tuple[int, int, int]:
    text = str(raw or "#20252c")
    if not HEX_COLOR_PATTERN.fullmatch(text):
        raise ValidationError(
            "background must use #RRGGBB notation",
            details={"field": "background"},
        )
    return (
        int(text[1:3], 16),
        int(text[3:5], 16),
        int(text[5:7], 16),
    )


def validate_contact_sheet_request(body: Any) -> ContactSheetRequest:
    value = _require_object(body)
    selection = str(value.get("selection", "stored"))
    if selection not in {"stored", "midpoint", "first"}:
        raise ValidationError(
            "selection must be stored, midpoint, or first",
            details={"field": "selection"},
        )
    return ContactSheetRequest(
        sheet_id=validate_identifier(str(value.get("sheet_id", "")), "sheet_id"),
        columns=_integer(value, "columns", 3, 1, 6),
        tile_width=_integer(value, "tile_width", 160, 32, 320),
        gutter=_integer(value, "gutter", 6, 0, 20),
        selection=selection,
        background_rgb=_parse_color(value.get("background", "#20252c")),
    )

