from __future__ import annotations

import hashlib

from frame_proxy.config import Settings
from frame_proxy.domain.errors import (
    ApplicationError,
    ErrorCode,
    MediaValidationError,
)
from frame_proxy.domain.models import ClipRecord
from frame_proxy.domain.policies import validate_clip_id
from frame_proxy.domain.transitions import transition_clip
from frame_proxy.media.avi import probe_avi
from frame_proxy.storage.repository import FileRepository


class ClipService:
    def __init__(self, repository: FileRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def admit(self, clip_id: str, payload: bytes) -> ClipRecord:
        normalized_id = validate_clip_id(clip_id)
        if not payload:
            raise MediaValidationError("clip payload is empty")
        if len(payload) > self._settings.max_clip_bytes:
            raise MediaValidationError(
                "clip payload exceeds the configured limit",
                code=ErrorCode.MEDIA_BOUNDS,
                details={
                    "byte_size": len(payload),
                    "max_bytes": self._settings.max_clip_bytes,
                },
            )

        descriptor = probe_avi(payload)
        if descriptor.width > self._settings.max_frame_width:
            raise MediaValidationError(
                "clip width exceeds the configured limit",
                code=ErrorCode.MEDIA_BOUNDS,
            )
        if descriptor.height > self._settings.max_frame_height:
            raise MediaValidationError(
                "clip height exceeds the configured limit",
                code=ErrorCode.MEDIA_BOUNDS,
            )
        if descriptor.frame_count > self._settings.max_frame_count:
            raise MediaValidationError(
                "clip frame count exceeds the configured limit",
                code=ErrorCode.MEDIA_BOUNDS,
            )

        record = ClipRecord(
            clip_id=normalized_id,
            state="probing",
            digest=hashlib.sha256(payload).hexdigest(),
            byte_size=len(payload),
            width=descriptor.width,
            height=descriptor.height,
            frame_count=descriptor.frame_count,
            fps_numerator=descriptor.fps_numerator,
            fps_denominator=descriptor.fps_denominator,
            row_stride=descriptor.row_stride,
            frame_payload_size=descriptor.frame_payload_size,
            top_down=descriptor.top_down,
            frame_offsets=list(descriptor.frame_offsets),
            handler=descriptor.handler,
        )
        transition_clip(record, "registered", reason="container and geometry verified")
        try:
            self._repository.create_clip(record, payload)
        except ApplicationError:
            raise
        except OSError as exc:
            raise ApplicationError(
                ErrorCode.STORAGE,
                "clip storage could not be committed",
                status=500,
            ) from exc
        return record

    def get(self, clip_id: str) -> ClipRecord:
        return self._repository.get_clip(validate_clip_id(clip_id))

