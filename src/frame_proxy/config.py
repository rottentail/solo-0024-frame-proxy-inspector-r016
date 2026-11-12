from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    data_root: Path
    max_clip_bytes: int = 64 * 1024 * 1024
    max_upload_bytes: int = 64 * 1024 * 1024
    max_json_bytes: int = 128 * 1024
    max_frame_width: int = 1920
    max_frame_height: int = 1080
    max_frame_count: int = 3000
    max_sheet_pixels: int = 250_000
    max_sheet_scenes: int = 36
    request_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "Settings":
        data_root = Path(
            os.environ.get("FRAME_PROXY_DATA_DIR", ".frame-proxy-data")
        ).expanduser()
        return cls(data_root=data_root)

    def ensure_ready(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
