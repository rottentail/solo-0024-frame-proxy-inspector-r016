from __future__ import annotations

from dataclasses import dataclass

from frame_proxy.domain.errors import ErrorCode, MediaValidationError
from frame_proxy.domain.models import SceneRecord
from frame_proxy.media.fingerprint import FrameFingerprint, fingerprint_distance


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    sampled_frames: tuple[int, ...]
    cut_frames: tuple[int, ...]
    scenes: tuple[SceneRecord, ...]


def _threshold(sensitivity: float) -> float:
    return 0.50 - sensitivity * 0.30


def _detect_cut_frames(
    frame_count: int,
    sampled_frames: tuple[int, ...],
    fingerprints: tuple[FrameFingerprint, ...],
    sensitivity: float,
    min_scene_frames: int,
) -> list[int]:
    if len(sampled_frames) != len(fingerprints) or not sampled_frames:
        raise MediaValidationError(
            "sampled frames and fingerprints must be non-empty and aligned",
            code=ErrorCode.FRAME_DECODE,
        )
    threshold = _threshold(sensitivity)
    cuts: list[int] = []
    last_cut = 0
    for index in range(1, len(sampled_frames)):
        distance = fingerprint_distance(fingerprints[index - 1], fingerprints[index])
        candidate = sampled_frames[index]
        if distance < threshold:
            continue
        if candidate - last_cut < min_scene_frames:
            continue
        if frame_count - candidate < min_scene_frames:
            continue
        cuts.append(candidate)
        last_cut = candidate
    return cuts


def _scene_records(
    frame_count: int,
    sampled_frames: tuple[int, ...],
    fingerprints: tuple[FrameFingerprint, ...],
    cuts: list[int],
) -> tuple[SceneRecord, ...]:
    starts = [0, *cuts]
    ends = [*cuts, frame_count]
    fingerprint_by_frame = dict(zip(sampled_frames, fingerprints))
    scenes: list[SceneRecord] = []

    for scene_index, (start, end) in enumerate(zip(starts, ends)):
        in_scene = [
            (frame_index, fingerprint_by_frame[frame_index])
            for frame_index in sampled_frames
            if start <= frame_index < end
        ]
        midpoint = start + (end - start) // 2
        if in_scene:
            representative_frame, _ = min(
                in_scene,
                key=lambda item: abs(item[0] - midpoint),
            )
            count = len(in_scene)
            mean_luma = sum(item[1].mean_luma for item in in_scene) / count
            contrast = sum(item[1].contrast for item in in_scene) / count
            dominant = (
                round(sum(item[1].mean_red for item in in_scene) / count),
                round(sum(item[1].mean_green for item in in_scene) / count),
                round(sum(item[1].mean_blue for item in in_scene) / count),
            )
        else:
            representative_frame = midpoint
            nearest_index = min(
                range(len(sampled_frames)),
                key=lambda index: abs(sampled_frames[index] - midpoint),
            )
            fingerprint = fingerprints[nearest_index]
            mean_luma = fingerprint.mean_luma
            contrast = fingerprint.contrast
            dominant = (
                round(fingerprint.mean_red),
                round(fingerprint.mean_green),
                round(fingerprint.mean_blue),
            )
        scenes.append(
            SceneRecord(
                index=scene_index,
                start_frame=start,
                end_frame=end,
                representative_frame=representative_frame,
                mean_luma=mean_luma,
                contrast=contrast,
                dominant_rgb=dominant,
            )
        )
    return tuple(scenes)


def analyze_frames(
    frame_count: int,
    sampled_frames: tuple[int, ...],
    fingerprints: tuple[FrameFingerprint, ...],
    *,
    sensitivity: float,
    min_scene_frames: int,
) -> AnalysisResult:
    cuts = _detect_cut_frames(
        frame_count,
        sampled_frames,
        fingerprints,
        sensitivity,
        min_scene_frames,
    )
    scenes = _scene_records(frame_count, sampled_frames, fingerprints, cuts)
    if not scenes or scenes[0].start_frame != 0:
        raise MediaValidationError(
            "scene ranges must begin at frame zero",
            code=ErrorCode.FRAME_DECODE,
        )
    if scenes[-1].end_frame != frame_count:
        raise MediaValidationError(
            "scene ranges must end at the clip frame count",
            code=ErrorCode.FRAME_DECODE,
        )
    for left, right in zip(scenes, scenes[1:]):
        if left.end_frame != right.start_frame:
            raise MediaValidationError(
                "scene ranges must be contiguous",
                code=ErrorCode.FRAME_DECODE,
            )
    return AnalysisResult(
        sampled_frames=sampled_frames,
        cut_frames=tuple(cuts),
        scenes=scenes,
    )

