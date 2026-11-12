from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DataPaths:
    root: Path

    @property
    def clips(self) -> Path:
        return self.root / "clips"

    @property
    def inspections(self) -> Path:
        return self.root / "inspections"

    @property
    def contact_sheets(self) -> Path:
        return self.root / "contact-sheets"

    @property
    def locks(self) -> Path:
        return self.root / "locks"

    def clip_dir(self, clip_id: str) -> Path:
        return self.clips / clip_id

    def clip_media(self, clip_id: str) -> Path:
        return self.clip_dir(clip_id) / "clip.avi"

    def clip_record(self, clip_id: str) -> Path:
        return self.clip_dir(clip_id) / "record.json"

    def inspection_record(self, inspection_id: str) -> Path:
        return self.inspections / f"{inspection_id}.json"

    def contact_sheet_dir(self, sheet_id: str) -> Path:
        return self.contact_sheets / sheet_id

    def contact_sheet_record(self, sheet_id: str) -> Path:
        return self.contact_sheet_dir(sheet_id) / "record.json"

    def contact_sheet_artifact(self, sheet_id: str, name: str) -> Path:
        return self.contact_sheet_dir(sheet_id) / name

    def lock_path(self, kind: str, identifier: str) -> Path:
        return self.locks / f"{kind}-{identifier}.lock"

    def ensure_ready(self) -> None:
        for path in (
            self.root,
            self.clips,
            self.inspections,
            self.contact_sheets,
            self.locks,
        ):
            path.mkdir(parents=True, exist_ok=True)

