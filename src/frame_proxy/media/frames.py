from __future__ import annotations

from dataclasses import dataclass
from collections import OrderedDict
from threading import Lock

from frame_proxy.domain.errors import ErrorCode, MediaValidationError
from frame_proxy.media.avi import AviDescriptor


@dataclass(frozen=True, slots=True)
class Frame:
    index: int
    width: int
    height: int
    rgb: bytes | bytearray


class _DecodeWorkspace:
    def __init__(self, capacity: int = 16) -> None:
        self._capacity = capacity
        self._slots: OrderedDict[tuple[int, int, int], bytearray] = OrderedDict()
        self._guard = Lock()

    def publish(
        self, width: int, height: int, frame_index: int, rows: list[bytes]
    ) -> bytearray:
        key = (width, height, frame_index)
        required = width * height * 3
        with self._guard:
            pixels = self._slots.pop(key, None)
            if pixels is None or len(pixels) != required:
                pixels = bytearray(required)
            destination = 0
            for row in rows:
                next_destination = destination + len(row)
                pixels[destination:next_destination] = row
                destination = next_destination
            if destination != required:
                raise ValueError("decoded rows do not match frame geometry")
            self._slots[key] = pixels
            while len(self._slots) > self._capacity:
                self._slots.popitem(last=False)
            return pixels


_DECODE_WORKSPACE = _DecodeWorkspace()


def decode_frame_at(
    buffer: bytes,
    descriptor: AviDescriptor,
    frame_index: int,
) -> Frame:
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
        rgb=_DECODE_WORKSPACE.publish(
            descriptor.width, descriptor.height, frame_index, rgb_rows
        ),
    )

