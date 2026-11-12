from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from frame_proxy.domain.errors import ErrorCode, ValidationError
from frame_proxy.domain.models import SceneRecord
from frame_proxy.domain.policies import ContactSheetRequest
from frame_proxy.media.frames import Frame
from frame_proxy.media.ppm import encode_ppm


@dataclass(frozen=True, slots=True)
class GridPlan:
    columns: int
    rows: int
    tile_width: int
    tile_height: int
    gutter: int
    image_width: int
    image_height: int


@dataclass(frozen=True, slots=True)
class GridResult:
    payload: bytes
    digest: str
    plan: GridPlan
    tile_map: tuple[dict[str, int], ...]


def plan_grid(
    *,
    scene_count: int,
    source_width: int,
    source_height: int,
    request: ContactSheetRequest,
    max_scenes: int,
    max_pixels: int,
) -> GridPlan:
    if scene_count <= 0:
        raise ValidationError("an indexed inspection must contain at least one scene")
    if scene_count > max_scenes:
        raise ValidationError(
            "scene count exceeds the contact sheet working-set limit",
            code=ErrorCode.CONTACT_SHEET_BUDGET,
            details={"scene_count": scene_count, "max_scenes": max_scenes},
        )
    rows = math.ceil(scene_count / request.columns)
    if rows > 12:
        raise ValidationError(
            "requested columns would create too many rows",
            code=ErrorCode.CONTACT_SHEET_BUDGET,
            details={"rows": rows, "max_rows": 12},
        )
    tile_height = max(
        24,
        min(360, round(request.tile_width * source_height / source_width)),
    )
    image_width = request.gutter + request.columns * (
        request.tile_width + request.gutter
    )
    image_height = request.gutter + rows * (tile_height + request.gutter)
    pixels = image_width * image_height
    if pixels > max_pixels:
        raise ValidationError(
            "contact sheet pixel budget is exceeded",
            code=ErrorCode.CONTACT_SHEET_BUDGET,
            details={
                "width": image_width,
                "height": image_height,
                "pixels": pixels,
                "max_pixels": max_pixels,
            },
        )
    return GridPlan(
        columns=request.columns,
        rows=rows,
        tile_width=request.tile_width,
        tile_height=tile_height,
        gutter=request.gutter,
        image_width=image_width,
        image_height=image_height,
    )


def _resize_nearest(frame: Frame, width: int, height: int) -> bytes:
    output = bytearray(width * height * 3)
    destination = 0
    for y in range(height):
        source_y = min(frame.height - 1, y * frame.height // height)
        source_row = source_y * frame.width * 3
        for x in range(width):
            source_x = min(frame.width - 1, x * frame.width // width)
            source = source_row + source_x * 3
            output[destination : destination + 3] = frame.rgb[source : source + 3]
            destination += 3
    return bytes(output)


def _copy_tile(
    canvas: bytearray | memoryview,
    canvas_width: int,
    tile: bytes,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
) -> None:
    for row in range(height):
        source_start = row * width * 3
        destination_start = ((top + row) * canvas_width + left) * 3
        canvas[destination_start : destination_start + width * 3] = tile[
            source_start : source_start + width * 3
        ]


def _selected_frame(scene: SceneRecord, selection: str) -> int:
    if selection == "first":
        return scene.start_frame
    if selection == "midpoint":
        return scene.start_frame + (scene.end_frame - scene.start_frame) // 2
    return scene.representative_frame


def compose_grid(
    *,
    plan: GridPlan,
    scenes: tuple[SceneRecord, ...],
    frames: dict[int, Frame],
    background_rgb: tuple[int, int, int],
    selection: str,
) -> GridResult:
    if len(scenes) > plan.columns * plan.rows:
        raise ValueError("scene count exceeds grid capacity")
    # The canvas is private to this composition: concurrent contact sheet
    # jobs never share pixel buffers. plan_grid has already bounded this
    # allocation with the configured pixel budget.
    pixels = bytearray(background_rgb) * (plan.image_width * plan.image_height)
    tile_map: list[dict[str, int]] = []

    for tile_index, scene in enumerate(scenes):
        row = tile_index // plan.columns
        column = tile_index % plan.columns
        source_frame = _selected_frame(scene, selection)
        frame = frames.get(source_frame)
        if frame is None:
            raise ValueError(f"selected frame {source_frame} was not decoded")
        tile = _resize_nearest(frame, plan.tile_width, plan.tile_height)
        left = plan.gutter + column * (plan.tile_width + plan.gutter)
        top = plan.gutter + row * (plan.tile_height + plan.gutter)
        _copy_tile(
            pixels,
            plan.image_width,
            tile,
            left=left,
            top=top,
            width=plan.tile_width,
            height=plan.tile_height,
        )
        tile_map.append(
            {
                "tile_index": tile_index,
                "scene_index": scene.index,
                "source_frame": source_frame,
                "row": row,
                "column": column,
                "left": left,
                "top": top,
                "width": plan.tile_width,
                "height": plan.tile_height,
            }
        )

    payload = encode_ppm(plan.image_width, plan.image_height, bytes(pixels))
    return GridResult(
        payload=payload,
        digest=hashlib.sha256(payload).hexdigest(),
        plan=plan,
        tile_map=tuple(tile_map),
    )

