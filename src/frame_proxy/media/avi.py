from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Iterator

from frame_proxy.domain.errors import ErrorCode, MediaValidationError


@dataclass(frozen=True, slots=True)
class AviDescriptor:
    width: int
    height: int
    frame_count: int
    fps_numerator: int
    fps_denominator: int
    row_stride: int
    frame_payload_size: int
    top_down: bool
    frame_offsets: tuple[int, ...]
    handler: str


@dataclass(frozen=True, slots=True)
class _Chunk:
    tag: bytes
    payload_offset: int
    payload_size: int
    end_offset: int


def _fail(message: str, code: ErrorCode = ErrorCode.MEDIA_FORMAT) -> None:
    raise MediaValidationError(message, code=code)


def _require_bounds(buffer: bytes, offset: int, size: int) -> None:
    if offset < 0 or size < 0 or offset + size > len(buffer):
        _fail("AVI chunk extends beyond the payload")


def _iter_chunks(buffer: bytes, start: int, end: int) -> Iterator[_Chunk]:
    cursor = start
    while cursor < end:
        if cursor + 8 > end:
            _fail("AVI chunk header is truncated")
        tag = buffer[cursor : cursor + 4]
        size = struct.unpack_from("<I", buffer, cursor + 4)[0]
        payload_offset = cursor + 8
        payload_end = payload_offset + size
        if payload_end > end:
            _fail("AVI chunk payload is truncated")
        padded_end = payload_end + (size & 1)
        if padded_end > end:
            _fail("AVI chunk padding is truncated")
        yield _Chunk(tag, payload_offset, size, padded_end)
        cursor = padded_end


def _find_chunk(
    buffer: bytes,
    start: int,
    end: int,
    wanted: bytes,
) -> _Chunk | None:
    for chunk in _iter_chunks(buffer, start, end):
        if chunk.tag == wanted:
            return chunk
    return None


def _list_payload(buffer: bytes, chunk: _Chunk, list_type: bytes) -> tuple[int, int]:
    if chunk.payload_size < 4:
        _fail("AVI list is missing its type")
    actual = buffer[chunk.payload_offset : chunk.payload_offset + 4]
    if actual != list_type:
        _fail(f"expected AVI list {list_type!r}, found {actual!r}")
    return chunk.payload_offset + 4, chunk.payload_offset + chunk.payload_size


def _parse_avih(buffer: bytes, chunk: _Chunk) -> tuple[int, int, int, int]:
    if chunk.payload_size < 56:
        _fail("AVI main header is too short")
    fields = struct.unpack_from("<14I", buffer, chunk.payload_offset)
    total_frames = fields[4]
    streams = fields[6]
    width = fields[8]
    height = fields[9]
    if streams != 1:
        _fail("exactly one video stream is supported")
    if total_frames <= 0:
        _fail("AVI frame count must be positive")
    return total_frames, streams, width, height


def _parse_strh(buffer: bytes, chunk: _Chunk) -> tuple[int, int, int, int]:
    if chunk.payload_size < 56:
        _fail("AVI stream header is too short")
    fields = struct.unpack_from("<4s4sIHHIIIIIIIIhhhh", buffer, chunk.payload_offset)
    stream_type = fields[0]
    scale = fields[6]
    rate = fields[7]
    length = fields[9]
    if stream_type != b"vids":
        _fail("the only stream must be video")
    if scale <= 0 or rate <= 0:
        _fail("AVI frame rate ratio must be positive")
    if length <= 0:
        _fail("AVI stream length must be positive")
    return scale, rate, length, fields[2]


def _parse_strf(
    buffer: bytes,
    chunk: _Chunk,
) -> tuple[int, int, int, int, int, int]:
    if chunk.payload_size < 40:
        _fail("AVI bitmap header is too short")
    fields = struct.unpack_from("<IiiHHIIiiII", buffer, chunk.payload_offset)
    header_size = fields[0]
    width = fields[1]
    signed_height = fields[2]
    planes = fields[3]
    bit_count = fields[4]
    compression = fields[5]
    image_size = fields[6]
    if header_size < 40:
        _fail("unsupported bitmap header")
    if width <= 0 or signed_height == 0:
        _fail("AVI image dimensions must be non-zero")
    if planes != 1:
        _fail("AVI image plane count must be one")
    if bit_count != 24:
        _fail("only 24-bit BGR frames are supported")
    if compression != 0:
        _fail("compressed AVI frames are not supported")
    return width, abs(signed_height), bit_count, compression, image_size, signed_height


def _simplify_ratio(numerator: int, denominator: int) -> tuple[int, int]:
    divisor = math.gcd(numerator, denominator)
    return numerator // divisor, denominator // divisor


def probe_avi(buffer: bytes) -> AviDescriptor:
    if len(buffer) < 12:
        _fail("payload is too short to be an AVI container")
    if buffer[0:4] != b"RIFF" or buffer[8:12] != b"AVI ":
        _fail("payload must be a RIFF/AVI container")
    riff_size = struct.unpack_from("<I", buffer, 4)[0]
    if riff_size + 8 != len(buffer):
        _fail(
            "RIFF size does not match the uploaded byte count",
            code=ErrorCode.MEDIA_BOUNDS,
        )

    hdrl = _find_chunk(buffer, 12, len(buffer), b"LIST")
    if hdrl is None:
        _fail("AVI header list is missing")
    hdrl_start, hdrl_end = _list_payload(buffer, hdrl, b"hdrl")

    avih = _find_chunk(buffer, hdrl_start, hdrl_end, b"avih")
    if avih is None:
        _fail("AVI main header chunk is missing")
    total_frames, _, avih_width, avih_height = _parse_avih(buffer, avih)

    stream_list: _Chunk | None = None
    for chunk in _iter_chunks(buffer, hdrl_start, hdrl_end):
        if chunk.tag == b"LIST":
            start, end = _list_payload(buffer, chunk, b"strl")
            if _find_chunk(buffer, start, end, b"strh") is not None:
                stream_list = chunk
                break
    if stream_list is None:
        _fail("AVI video stream list is missing")
    stream_start, stream_end = _list_payload(buffer, stream_list, b"strl")

    strh = _find_chunk(buffer, stream_start, stream_end, b"strh")
    strf = _find_chunk(buffer, stream_start, stream_end, b"strf")
    if strh is None or strf is None:
        _fail("AVI stream headers are incomplete")
    scale, rate, stream_length, _flags = _parse_strh(buffer, strh)
    (
        width,
        height,
        _bit_count,
        _compression,
        image_size,
        signed_height,
    ) = _parse_strf(buffer, strf)

    if width != avih_width or height != avih_height:
        _fail("AVI main and stream dimensions disagree")
    if total_frames != stream_length:
        _fail("AVI main and stream frame counts disagree")

    row_stride = ((width * 3 + 3) // 4) * 4
    frame_payload_size = row_stride * height
    if image_size not in (0, frame_payload_size):
        _fail("AVI bitmap image size does not match frame geometry")

    movi: _Chunk | None = None
    for chunk in _iter_chunks(buffer, 12, len(buffer)):
        if chunk.tag == b"LIST":
            actual = buffer[chunk.payload_offset : chunk.payload_offset + 4]
            if actual == b"movi":
                movi = chunk
                break
    if movi is None:
        _fail("AVI media list is missing")
    movi_start, movi_end = _list_payload(buffer, movi, b"movi")

    offsets: list[int] = []
    for chunk in _iter_chunks(buffer, movi_start, movi_end):
        if chunk.tag == b"JUNK":
            continue
        if chunk.tag != b"00db":
            _fail(f"unsupported AVI media chunk {chunk.tag!r}")
        if chunk.payload_size != frame_payload_size:
            _fail("AVI frame payload size does not match geometry")
        offsets.append(chunk.payload_offset)

    if len(offsets) != total_frames:
        _fail(
            "declared AVI frame count does not match media chunks",
            code=ErrorCode.MEDIA_BOUNDS,
        )

    fps_num, fps_den = _simplify_ratio(rate, scale)
    return AviDescriptor(
        width=width,
        height=height,
        frame_count=total_frames,
        fps_numerator=fps_num,
        fps_denominator=fps_den,
        row_stride=row_stride,
        frame_payload_size=frame_payload_size,
        top_down=signed_height < 0,
        frame_offsets=tuple(offsets),
        handler="DIB",
    )

