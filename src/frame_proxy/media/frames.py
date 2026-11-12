from __future__ import annotations

from dataclasses import dataclass

from frame_proxy.domain.errors import ErrorCode, MediaValidationError
from frame_proxy.media.avi import AviDescriptor


@dataclass(frozen=True, slots=True)
class Frame:
    index: int
    width: int
    height: int
    rgb: bytes | bytearray


def decode_frame_at(
    buffer: bytes,
    descriptor: AviDescriptor,
    frame_index: int,
) -> Frame:
    """Decode one frame into a private, immutable pixel buffer.

    Every call returns pixels owned solely by its caller. No decode reuses
    or overwrites a buffer another request may still hold, so frames from
    different clips or concurrent tasks can never alias each other.
    """
    if frame_index < 0 or frame_index >= descriptor.frame_count:
        raise MediaValidationError(
            "frame index is outside the clip",
            code=ErrorCode.MEDIA_BOUNDS,
            details={"frame_index": frame_index},
        )
    offset = descriptor.frame_offsets[frame_index]
    end = offset + descriptor.frame_payload_size
    if end > len(buffer):
        raise MediaValidationError(
            "frame payload is truncated",
            code=ErrorCode.FRAME_DECODE,
        )

    rgb_rows: list[bytes] = []
    for row_index in range(descriptor.height):
        source_row = row_index
        if not descriptor.top_down:
            source_row = descriptor.height - 1 - row_index
        row_start = offset + source_row * descriptor.row_stride
        row = buffer[row_start : row_start + descriptor.width * 3]
        converted = bytearray(len(row))
        converted[0::3] = row[2::3]
        converted[1::3] = row[1::3]
        converted[2::3] = row[0::3]
        rgb_rows.append(bytes(converted))
    return Frame(
        index=frame_index,
        width=descriptor.width,
        height=descriptor.height,
        rgb=b"".join(rgb_rows),
    )
