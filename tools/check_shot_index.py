from __future__ import annotations

from tools.harness import RunningService, require, require_status, success


def main() -> int:
    with RunningService() as service:
        inspection = service.prepare_inspection(
            clip_id="clip-index-a",
            inspection_id="inspection-index-a",
        )
        require(inspection["state"] == "indexed", "inspection did not become indexed")
        require(
            inspection["cut_frames"] == [5, 9, 14],
            f"unexpected cuts: {inspection['cut_frames']}",
        )
        scenes = inspection["scenes"]
        require(len(scenes) == 4, "expected four generated scenes")
        require(scenes[0]["start_frame"] == 0, "first scene must start at zero")
        require(scenes[-1]["end_frame"] == 17, "last scene must end at frame count")
        for left, right in zip(scenes, scenes[1:]):
            require(
                left["end_frame"] == right["start_frame"],
                "scene ranges are not contiguous",
            )
        require(
            [item["representative_frame"] for item in scenes] == [2, 7, 11, 15],
            "representative frames do not follow scene midpoints",
        )

        read_response = service.request(
            "GET",
            "/v1/inspections/inspection-index-a",
        )
        require_status(read_response, 200, "inspection lookup")
        require(
            read_response.json()["inspection"]["state"] == "indexed",
            "stored inspection state changed",
        )

        duplicate = service.request_json(
            "POST",
            "/v1/clips/clip-index-a/inspections",
            {
                "inspection_id": "inspection-index-a",
                "sensitivity": 0.55,
                "sample_stride": 1,
                "min_scene_frames": 2,
            },
        )
        require_status(duplicate, 409, "duplicate inspection rejection")

    success(
        "index-shot-boundaries",
        {
            "cuts": inspection["cut_frames"],
            "scenes": len(scenes),
            "state": inspection["state"],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

