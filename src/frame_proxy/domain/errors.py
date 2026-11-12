from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    INVALID_IDENTIFIER = "invalid_identifier"
    INVALID_REQUEST = "invalid_request"
    CLIP_NOT_FOUND = "clip_not_found"
    INSPECTION_NOT_FOUND = "inspection_not_found"
    CONTACT_SHEET_NOT_FOUND = "contact_sheet_not_found"
    CONFLICT = "conflict"
    MEDIA_FORMAT = "media_format_not_supported"
    MEDIA_BOUNDS = "media_bounds_exceeded"
    FRAME_DECODE = "frame_decode_failed"
    CONTACT_SHEET_BUDGET = "contact_sheet_budget_exceeded"
    INVALID_STATE = "invalid_state_transition"
    STORAGE = "storage_failure"
    INTERNAL = "internal_failure"


class ApplicationError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "error": {
                "code": self.code.value,
                "message": self.message,
            }
        }
        if self.details:
            body["error"]["details"] = self.details
        return body


class ValidationError(ApplicationError):
    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.INVALID_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code, message, status=400, details=details)


class NotFoundError(ApplicationError):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code, message, status=404, details=details)


class ConflictError(ApplicationError):
    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(ErrorCode.CONFLICT, message, status=409, details=details)


class MediaValidationError(ApplicationError):
    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.MEDIA_FORMAT,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code, message, status=422, details=details)


class StateError(ApplicationError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            ErrorCode.INVALID_STATE,
            message,
            status=409,
            details=details,
        )

