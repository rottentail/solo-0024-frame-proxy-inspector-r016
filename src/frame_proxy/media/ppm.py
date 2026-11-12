from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PpmHeader:
    width: int
    height: int
    maximum: int
    pixel_offset: int


def encode_ppm(width: int, height: int, pixels: bytes) -> bytes:
    if width <= 0 or height <= 0:
        raise ValueError("PPM dimensions must be positive")
    if len(pixels) != width * height * 3:
        raise ValueError("PPM pixel length does not match dimensions")
    return f"P6\n{width} {height}\n255\n".encode("ascii") + pixels


def parse_ppm_header(data: bytes) -> PpmHeader:
    if len(data) < 11 or data[0:2] != b"P6":
        raise ValueError("payload is not a binary PPM")
    cursor = 2
    tokens: list[bytes] = []
    while len(tokens) < 3:
        while cursor < len(data) and data[cursor] in b" \t\r\n":
            cursor += 1
        if cursor >= len(data):
            raise ValueError("PPM header is truncated")
        if data[cursor : cursor + 1] == b"#":
            while cursor < len(data) and data[cursor] not in b"\r\n":
                cursor += 1
            continue
        start = cursor
        while cursor < len(data) and data[cursor] not in b" \t\r\n":
            cursor += 1
        tokens.append(data[start:cursor])
    if cursor >= len(data) or data[cursor] not in b" \t\r\n":
        raise ValueError("PPM header is missing its final separator")
    if data[cursor : cursor + 2] == b"\r\n":
        cursor += 2
    else:
        cursor += 1
    width = int(tokens[0])
    height = int(tokens[1])
    maximum = int(tokens[2])
    expected = width * height * 3
    if width <= 0 or height <= 0 or maximum != 255:
        raise ValueError("PPM header values are out of range")
    if len(data) - cursor != expected:
        raise ValueError("PPM payload length does not match its header")
    return PpmHeader(
        width=width,
        height=height,
        maximum=maximum,
        pixel_offset=cursor,
    )
