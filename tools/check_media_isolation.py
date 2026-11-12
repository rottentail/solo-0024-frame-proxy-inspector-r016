"""Cross-task media isolation check.

Reproduces the two reported review contaminations against the real HTTP
service and verifies that media results stay isolated per request:

1. Frame buffer ownership (deterministic, in-process): a decoded frame held
   by one task must not change when another clip with identical geometry is
   decoded afterwards.

2. Sequential shot inspections (no concurrency): two different clips that
   share frame dimensions, frame count, and container layout must produce
   scene facts from their own pixels, not from the clip inspected earlier.

3. Concurrent contact sheets (single clip, fresh service): two sheets of
   one indexed inspection composed at the same time must not share canvas
   or frame buffers. Every tile is checked pixel-for-pixel against the
   source frame declared in its tile map, and the gutter must contain only
   the sheet's own background. The record digest is also checked against
   the delivered bytes, documenting that a self-consistent digest alone
   does not prove the pixels belong to the request.

Run with: PYTHONPATH=src:. python3 tools/check_media_isolation.py
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any

from frame_proxy.media.avi import probe_avi
from frame_proxy.media.avi_writer import SCENE_COLORS, build_sample_avi
from frame_proxy.media.frames import decode_frame_at
from frame_proxy.media.ppm import parse_ppm_header
from tools.harness import RunningService, require, require_status, success

WIDTH = 128
HEIGHT = 72
FPS = 12
SCENE_LENGTHS = (5, 4, 5, 3)

# Same geometry and scene boundaries as the production palette, different
# pixel content. Every scene color is far from the production one in RGB.
PALETTE_B = (
    (25, 35, 170),
    (225, 120, 60),
    (60, 25, 30),
    (200, 200, 90),
)
# Strongly alternating luma so every two-frame scene boundary is a cut.
PALETTE_C = (
    (20, 30, 160),
    (230, 180, 70),
    (60, 25, 30),
    (210, 90, 200),
    (30, 45, 25),
    (90, 210, 220),
)

SHEET_ROUNDS = 8
INSPECTION_REQUEST = {
    "sensitivity": 0.55,
    "sample_stride": 1,
    "min_scene_frames": 2,
}


def _solid_frame(
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


def _recolor_avi(
    media: bytes,
    scene_lengths: tuple[int, ...],
    palette: tuple[tuple[int, int, int], ...],
) -> bytes:
    """Rewrite frame payloads in place, preserving geometry and offsets."""
    descriptor = probe_avi(media)
    buffer = bytearray(media)
    frame_number = 0
    for scene_index, length in enumerate(scene_lengths):
        color = palette[scene_index % len(palette)]
        for _ in range(length):
            payload = _solid_frame(
                descriptor.width,
                descriptor.height,
                descriptor.row_stride,
                color,
                frame_number,
            )
            offset = descriptor.frame_offsets[frame_number]
            buffer[offset : offset + len(payload)] = payload
            frame_number += 1
    return bytes(buffer)


def _resize_nearest_rgb(
    rgb: bytes | bytearray,
    source_width: int,
    source_height: int,
    width: int,
    height: int,
) -> bytes:
    output = bytearray(width * height * 3)
    destination = 0
    for y in range(height):
        source_y = min(source_height - 1, y * source_height // height)
        source_row = source_y * source_width * 3
        for x in range(width):
            source_x = min(source_width - 1, x * source_width // width)
            source = source_row + source_x * 3
            output[destination : destination + 3] = rgb[source : source + 3]
            destination += 3
    return bytes(output)


def _extract_tile(
    pixels: bytes,
    image_width: int,
    left: int,
    top: int,
    width: int,
    height: int,
) -> bytes:
    rows = []
    for row in range(height):
        start = ((top + row) * image_width + left) * 3
        rows.append(pixels[start : start + width * 3])
    return b"".join(rows)


def _gutter_offenses(
    pixels: bytes,
    image_width: int,
    image_height: int,
    gutter: int,
    background: tuple[int, int, int],
    foreign: tuple[int, int, int],
) -> dict[str, int]:
    own = bytes(background)
    other = bytes(foreign)
    non_background = 0
    foreign_background = 0

    def scan(x: int, y: int) -> None:
        nonlocal non_background, foreign_background
        start = (y * image_width + x) * 3
        pixel = pixels[start : start + 3]
        if pixel == other:
            foreign_background += 1
        elif pixel != own:
            non_background += 1

    for y in range(gutter):
        for x in range(image_width):
            scan(x, y)
            scan(x, image_height - 1 - y)
    for y in range(image_height):
        for x in range(gutter):
            scan(x, y)
            scan(image_width - 1 - x, y)
    return {
        "non_background": non_background,
        "foreign_background": foreign_background,
    }


def _start_inspection(
    service: RunningService,
    clip_id: str,
    inspection_id: str,
) -> dict[str, Any]:
    response = service.request_json(
        "POST",
        f"/v1/clips/{clip_id}/inspections",
        {"inspection_id": inspection_id, **INSPECTION_REQUEST},
    )
    require_status(response, 201, f"inspection {inspection_id}")
    return response.json()["inspection"]


def check_frame_buffer_ownership() -> None:
    media_a = build_sample_avi(
        width=WIDTH, height=HEIGHT, fps=FPS, scene_lengths=SCENE_LENGTHS
    )
    media_b = _recolor_avi(media_a, SCENE_LENGTHS, PALETTE_B)
    descriptor_a = probe_avi(media_a)
    descriptor_b = probe_avi(media_b)
    held = decode_frame_at(media_a, descriptor_a, 3)
    snapshot = bytes(held.rgb)
    other = decode_frame_at(media_b, descriptor_b, 3)
    require(
        bytes(held.rgb) == snapshot,
        "a frame held by one task changed after another clip decoded the "
        "same geometry slot",
    )
    require(
        bytes(other.rgb) != snapshot,
        "distinct clips returned identical frame bytes for one geometry slot",
    )
    success(
        "frame-buffer-ownership",
        {"frame_index": 3, "held_frame_stable": True},
    )


def check_sequential_inspection_isolation() -> None:
    media_a = build_sample_avi(
        width=WIDTH, height=HEIGHT, fps=FPS, scene_lengths=SCENE_LENGTHS
    )
    media_b = _recolor_avi(media_a, SCENE_LENGTHS, PALETTE_B)
    require(
        hashlib.sha256(media_a).hexdigest() != hashlib.sha256(media_b).hexdigest(),
        "the two clips must be different media with identical geometry",
    )
    descriptor_a = probe_avi(media_a)
    descriptor_b = probe_avi(media_b)
    require(
        descriptor_a.frame_offsets == descriptor_b.frame_offsets
        and descriptor_a.frame_payload_size == descriptor_b.frame_payload_size,
        "the two clips must share container layout for this reproduction",
    )

    with RunningService() as service:
        upload_a = service.request(
            "PUT", "/v1/clips/clip-iso-a", media_a, "application/x-avi"
        )
        require_status(upload_a, 201, "clip A intake")
        inspection_a = _start_inspection(service, "clip-iso-a", "ins-iso-a")

        upload_b = service.request(
            "PUT", "/v1/clips/clip-iso-b", media_b, "application/x-avi"
        )
        require_status(upload_b, 201, "clip B intake")
        inspection_b = _start_inspection(service, "clip-iso-b", "ins-iso-b")

        inspection_a2 = _start_inspection(service, "clip-iso-a", "ins-iso-a2")

    require(
        inspection_a["cut_frames"] == [5, 9, 14],
        f"unexpected cuts for clip A: {inspection_a['cut_frames']}",
    )
    require(
        inspection_b["cut_frames"] == [5, 9, 14],
        "shared scene lengths legitimately share cut positions: "
        f"{inspection_b['cut_frames']}",
    )
    evidence = []
    for index, scene in enumerate(inspection_b["scenes"]):
        reported = tuple(scene["dominant_rgb"])
        expected_own = PALETTE_B[index]
        other_clip = SCENE_COLORS[index]
        close_to_own = all(
            abs(reported[channel] - expected_own[channel]) <= 8
            for channel in range(3)
        )
        far_from_other = any(
            abs(reported[channel] - other_clip[channel]) >= 40
            for channel in range(3)
        )
        evidence.append(
            {
                "scene": index,
                "reported": list(reported),
                "own_palette": list(expected_own),
                "other_clip_palette": list(other_clip),
            }
        )
        require(
            close_to_own,
            f"scene {index} color {reported} does not come from its own "
            f"clip (expected near {expected_own})",
        )
        require(
            far_from_other,
            f"scene {index} color {reported} matches the clip inspected "
            "earlier, not its own media",
        )
    require(
        [scene["dominant_rgb"] for scene in inspection_a2["scenes"]]
        == [scene["dominant_rgb"] for scene in inspection_a["scenes"]],
        "a repeat inspection of one clip must stay coherent",
    )
    success("sequential-inspection-isolation", {"scenes": evidence})


def _compose_pair(
    service: RunningService,
    inspection_id: str,
    round_index: int,
    layouts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    barrier = threading.Barrier(2)
    outcomes: dict[str, Any] = {}

    def compose(tag: str) -> None:
        sheet_id = f"sheet-{tag}-{round_index}"
        try:
            barrier.wait(timeout=10)
            response = service.request_json(
                "POST",
                f"/v1/inspections/{inspection_id}/contact-sheets",
                {"sheet_id": sheet_id, **layouts[tag]},
            )
            require_status(response, 201, f"contact sheet {sheet_id}")
            record = response.json()["contact_sheet"]
            require(
                record["state"] == "ready",
                f"contact sheet {sheet_id} did not become ready",
            )
            artifact = service.request(
                "GET", f"/v1/contact-sheets/{sheet_id}/artifact"
            )
            require_status(artifact, 200, f"artifact {sheet_id}")
            outcomes[tag] = (sheet_id, record, artifact.body)
        except BaseException as exc:  # surface thread failures in the main thread
            outcomes[tag] = exc

    threads = [
        threading.Thread(target=compose, args=(tag,), daemon=True)
        for tag in ("x", "y")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    for tag in ("x", "y"):
        outcome = outcomes.get(tag)
        require(
            outcome is not None and not isinstance(outcome, BaseException),
            f"contact sheet thread {tag} failed: {outcome!r}",
        )
    return outcomes


def _verify_sheet(
    record: dict[str, Any],
    body: bytes,
    source_frames: dict[int, bytes],
    own_background: tuple[int, int, int],
    foreign_background: tuple[int, int, int],
) -> dict[str, Any]:
    header = parse_ppm_header(body)
    require(
        header.width == record["image_width"]
        and header.height == record["image_height"],
        "artifact geometry differs from its record",
    )
    digest_ok = hashlib.sha256(body).hexdigest() == record["artifact_digest"]
    pixels = body[header.pixel_offset :]
    gutter = _gutter_offenses(
        pixels,
        header.width,
        header.height,
        record["gutter"],
        own_background,
        foreign_background,
    )
    tile_mismatches = []
    for entry in record["tile_map"]:
        expected = _resize_nearest_rgb(
            source_frames[entry["source_frame"]],
            WIDTH,
            HEIGHT,
            entry["width"],
            entry["height"],
        )
        actual = _extract_tile(
            pixels,
            header.width,
            entry["left"],
            entry["top"],
            entry["width"],
            entry["height"],
        )
        if actual != expected:
            tile_mismatches.append(entry["tile_index"])
    return {
        "digest_ok": digest_ok,
        "gutter": gutter,
        "tile_mismatches": tile_mismatches,
    }


def check_concurrent_contact_sheet_isolation() -> None:
    scene_lengths = (2,) * 12
    media = _recolor_avi(
        build_sample_avi(
            width=WIDTH, height=HEIGHT, fps=FPS, scene_lengths=scene_lengths
        ),
        scene_lengths,
        PALETTE_C,
    )
    descriptor = probe_avi(media)
    source_frames = {
        index: bytes(decode_frame_at(media, descriptor, index).rgb)
        for index in range(descriptor.frame_count)
    }
    layouts = {
        "x": {
            "columns": 4,
            "tile_width": 96,
            "gutter": 6,
            "selection": "first",
            "background": "#0d1420",
        },
        "y": {
            "columns": 3,
            "tile_width": 160,
            "gutter": 4,
            "selection": "midpoint",
            "background": "#f2e3c9",
        },
    }
    backgrounds = {"x": (0x0D, 0x14, 0x20), "y": (0xF2, 0xE3, 0xC9)}

    with RunningService() as service:
        upload = service.request(
            "PUT", "/v1/clips/clip-iso-c", media, "application/x-avi"
        )
        require_status(upload, 201, "clip C intake")
        inspection = _start_inspection(service, "clip-iso-c", "ins-iso-c")
        require(
            len(inspection["scenes"]) == 12,
            f"expected twelve indexed scenes, got {len(inspection['scenes'])}",
        )

        contaminated: list[str] = []
        digest_failures: list[str] = []
        first_artifacts: dict[str, bytes] = {}
        for round_index in range(SHEET_ROUNDS):
            outcomes = _compose_pair(service, "ins-iso-c", round_index, layouts)
            for tag in ("x", "y"):
                sheet_id, record, body = outcomes[tag]
                foreign = backgrounds["y" if tag == "x" else "x"]
                verdict = _verify_sheet(
                    record, body, source_frames, backgrounds[tag], foreign
                )
                if round_index == 0:
                    first_artifacts[sheet_id] = body
                if not verdict["digest_ok"]:
                    digest_failures.append(sheet_id)
                dirty = (
                    verdict["gutter"]["non_background"]
                    or verdict["gutter"]["foreign_background"]
                    or verdict["tile_mismatches"]
                )
                if dirty:
                    contaminated.append(
                        f"{sheet_id} gutter={verdict['gutter']} "
                        f"tiles={verdict['tile_mismatches']}"
                    )
                print(
                    f"round {round_index} {sheet_id}: "
                    f"digest_ok={verdict['digest_ok']} "
                    f"gutter={verdict['gutter']} "
                    f"tile_mismatches={verdict['tile_mismatches']}",
                    flush=True,
                )

        for sheet_id, body in first_artifacts.items():
            again = service.request(
                "GET", f"/v1/contact-sheets/{sheet_id}/artifact"
            )
            require_status(again, 200, f"re-fetch {sheet_id}")
            require(
                again.body == body,
                f"published artifact {sheet_id} changed after later compositions",
            )
        require(
            not digest_failures,
            f"artifact digests disagreed with their records: {digest_failures}",
        )
        require(
            not contaminated,
            "contact sheets contained pixels from another concurrent "
            f"request: {contaminated}",
        )
    success(
        "concurrent-contact-sheet-isolation",
        {
            "rounds": SHEET_ROUNDS,
            "tiles_verified": SHEET_ROUNDS * 24,
            "contaminated_rounds": len(contaminated),
        },
    )


def main() -> int:
    check_frame_buffer_ownership()
    check_sequential_inspection_isolation()
    check_concurrent_contact_sheet_isolation()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
