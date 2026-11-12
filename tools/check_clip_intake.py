from __future__ import annotations

import hashlib

from frame_proxy.media.avi_writer import build_sample_avi
from tools.harness import RunningService, require, require_status, success


def main() -> int:
    payload = build_sample_avi()
    with RunningService() as service:
        response = service.upload_clip("clip-intake-a", payload)
        require_status(response, 201, "clip intake")
        clip = response.json()["clip"]
        require(clip["state"] == "registered", "clip did not reach registered state")
        require(
            clip["digest"] == hashlib.sha256(payload).hexdigest(),
            "clip digest does not match the uploaded bytes",
        )
        require(clip["frame_count"] == 17, "unexpected frame count")
        require(len(clip["frame_offsets"]) == 17, "frame offsets are incomplete")

        read_response = service.request("GET", "/v1/clips/clip-intake-a")
        require_status(read_response, 200, "clip lookup")
        stored = read_response.json()["clip"]
        require(stored["digest"] == clip["digest"], "stored clip changed")

        truncated = service.upload_clip("clip-intake-b", payload[:-20])
        require_status(truncated, 422, "truncated clip rejection")
        missing = service.request("GET", "/v1/clips/clip-intake-b")
        require_status(missing, 404, "partial clip visibility")

    success(
        "register-video-clip",
        {
            "digest": clip["digest"],
            "frames": clip["frame_count"],
            "truncated_status": truncated.status,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

