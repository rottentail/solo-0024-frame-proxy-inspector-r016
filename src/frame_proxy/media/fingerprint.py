from __future__ import annotations

import math
from dataclasses import dataclass

from frame_proxy.media.frames import Frame


@dataclass(frozen=True, slots=True)
class FrameFingerprint:
    luma_histogram: tuple[float, ...]
    mean_red: float
    mean_green: float
    mean_blue: float
    mean_luma: float
    contrast: float


def fingerprint_frame(frame: Frame) -> FrameFingerprint:
    histogram = [0] * 16
    red_total = 0
    green_total = 0
    blue_total = 0
    luma_total = 0.0
    luma_square_total = 0.0
    sample_count = 0
    pixel_count = frame.width * frame.height
    step = max(1, pixel_count // 8192)
    pixels = frame.rgb

    for pixel_index in range(0, pixel_count, step):
        offset = pixel_index * 3
        red = pixels[offset]
        green = pixels[offset + 1]
        blue = pixels[offset + 2]
        luma = (299 * red + 587 * green + 114 * blue) / 1000.0
        red_total += red
        green_total += green
        blue_total += blue
        luma_total += luma
        luma_square_total += luma * luma
        histogram[min(15, int(luma / 16.0))] += 1
        sample_count += 1

    if sample_count == 0:
        sample_count = 1
    mean_luma = luma_total / sample_count
    variance = max(0.0, luma_square_total / sample_count - mean_luma * mean_luma)
    normalized_histogram = tuple(value / sample_count for value in histogram)
    return FrameFingerprint(
        luma_histogram=normalized_histogram,
        mean_red=red_total / sample_count,
        mean_green=green_total / sample_count,
        mean_blue=blue_total / sample_count,
        mean_luma=mean_luma,
        contrast=math.sqrt(variance),
    )


def fingerprint_distance(left: FrameFingerprint, right: FrameFingerprint) -> float:
    histogram_delta = sum(
        abs(a - b) for a, b in zip(left.luma_histogram, right.luma_histogram)
    )
    histogram_part = min(1.0, histogram_delta / 2.0)
    color_delta = math.sqrt(
        (left.mean_red - right.mean_red) ** 2
        + (left.mean_green - right.mean_green) ** 2
        + (left.mean_blue - right.mean_blue) ** 2
    )
    color_part = min(1.0, color_delta / 441.6729559300637)
    contrast_delta = min(1.0, abs(left.contrast - right.contrast) / 128.0)
    return min(1.0, histogram_part * 0.55 + color_part * 0.35 + contrast_delta * 0.10)

