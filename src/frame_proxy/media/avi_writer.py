from __future__ import annotations

import struct
from collections.abc import Iterable


DEFAULT_SCENES = (5, 4, 5, 3)
SCENE_COLORS = (
    (214, 66, 48),
    (44, 151, 168),
    (222, 183, 53),
    (71, 166, 91),
)


def _chunk(tag: bytes, payload: bytes) -> bytes:
    if len(tag) != 4:
        raise ValueError("chunk tag must be four bytes")
    padding = b"\x00" if len(payload) & 1 else b""
    return tag + struct.pack("<I", len(payload)) + payload + padding


def _list_chunk(kind: bytes, children: Iterable[bytes]) -> bytes:
    payload = kind + b"".join(children)
    return _chunk(b"LIST", payload)


def _frame_bytes(
    width: int,
    height: int,
    row_stride: int,
    color: tuple[int, int, int],
    phase: int,
) -> bytes:
    rows = bytearray()
    red, green, blue = color
    for y in range(height - 1, -1, -1):
        row = bytearray()
        for x in range(width):
            drift = ((x * 3 + y * 5 + phase * 11) % 19) - 9
            row.extend(
                (
                    max(0, min(255, blue + drift)),
                    max(0, min(255, green + drift // 2)),
                    max(0, min(255, red + drift)),
                )
            )
        row.extend(b"\x00" * (row_stride - len(row)))
        rows.extend(row)
    return bytes(rows)


def build_sample_avi(
    *,
    width: int = 128,
    height: int = 72,
    fps: int = 12,
    scene_lengths: tuple[int, ...] = DEFAULT_SCENES,
) -> bytes:
    if width <= 0 or height <= 0 or fps <= 0:
        raise ValueError("sample geometry and frame rate must be positive")
    if not scene_lengths or any(length <= 0 for length in scene_lengths):
        raise ValueError("scene lengths must be positive")
    row_stride = ((width * 3 + 3) // 4) * 4
    frame_size = row_stride * height
    frame_count = sum(scene_lengths)

    avih = struct.pack(
        "<14I",
        1_000_000 // fps,
        frame_size * fps,
        0,
        0x10,
        frame_count,
        0,
        1,
        frame_size,
        width,
        height,
        0,
        0,
        0,
        0,
    )
    strh = struct.pack(
        "<4s4sIHHIIIIIIIIhhhh",
        b"vids",
        b"DIB ",
        0,
        0,
        0,
        0,
        1,
        fps,
        0,
        frame_count,
        frame_size,
        0,
        frame_size,
        0,
        0,
        width,
        height,
    )
    strf = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,
        1,
        24,
        0,
        frame_size,
        2835,
        2835,
        0,
        0,
    )
    stream_header = _list_chunk(
        b"strl",
        (
            _chunk(b"strh", strh),
            _chunk(b"strf", strf),
        ),
    )
    header_list = _list_chunk(
        b"hdrl",
        (
            _chunk(b"avih", avih),
            stream_header,
        ),
    )

    media_chunks: list[bytes] = []
    frame_number = 0
    for scene_index, length in enumerate(scene_lengths):
        color = SCENE_COLORS[scene_index % len(SCENE_COLORS)]
        for _ in range(length):
            payload = _frame_bytes(
                width,
                height,
                row_stride,
                color,
                frame_number,
            )
            media_chunks.append(_chunk(b"00db", payload))
            frame_number += 1
    media_list = _list_chunk(b"movi", media_chunks)

    body = b"AVI " + header_list + media_list
    return b"RIFF" + struct.pack("<I", len(body)) + body

