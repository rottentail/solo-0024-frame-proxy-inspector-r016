from __future__ import annotations

import json
from typing import Any

from frame_proxy.config import Settings
from frame_proxy.domain.errors import ApplicationError, ErrorCode, ValidationError
from frame_proxy.domain.policies import (
    validate_clip_id,
    validate_contact_sheet_request,
    validate_inspection_request,
)
from frame_proxy.http.types import ResponseData
from frame_proxy.service.clips import ClipService
from frame_proxy.service.contact_sheets import ContactSheetService
from frame_proxy.service.inspections import InspectionService


class RequestRouter:
    def __init__(
        self,
        *,
        settings: Settings,
        clips: ClipService,
        inspections: InspectionService,
        contact_sheets: ContactSheetService,
    ) -> None:
        self._settings = settings
        self._clips = clips
        self._inspections = inspections
        self._contact_sheets = contact_sheets

    def handle(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
    ) -> ResponseData:
        try:
            return self._route(method.upper(), path, headers, body)
        except ApplicationError as exc:
            return ResponseData.json(exc.status, exc.as_dict())
        except Exception:
            error = ApplicationError(
                code=ErrorCode.INTERNAL,
                message="unexpected server failure",
                status=500,
            )
            return ResponseData.json(500, error.as_dict())

    def _route(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
    ) -> ResponseData:
        if path == "/health" and method == "GET":
            return ResponseData.json(200, {"status": "ok"})

        parts = [segment for segment in path.split("/") if segment]
        if len(parts) < 3 or parts[0] != "v1":
            return self._not_found(path)

        if parts[1] == "clips":
            clip_id = validate_clip_id(parts[2])
            if len(parts) == 3 and method == "PUT":
                content_type = headers.get("content-type", "").split(";")[0].strip()
                if content_type not in {"application/x-avi", "application/octet-stream"}:
                    raise ValidationError(
                        "clip upload requires application/x-avi or application/octet-stream"
                    )
                record = self._clips.admit(clip_id, body)
                return ResponseData.json(201, {"clip": record.as_dict()})
            if len(parts) == 3 and method == "GET":
                record = self._clips.get(clip_id)
                return ResponseData.json(200, {"clip": record.as_dict()})
            if len(parts) == 4 and parts[3] == "inspections" and method == "POST":
                request = validate_inspection_request(self._decode_json(body))
                record = self._inspections.create(clip_id, request)
                return ResponseData.json(201, {"inspection": record.as_dict()})

        if parts[1] == "inspections" and len(parts) >= 3:
            inspection_id = parts[2]
            if len(parts) == 3 and method == "GET":
                record = self._inspections.get(inspection_id)
                return ResponseData.json(200, {"inspection": record.as_dict()})
            if (
                len(parts) == 4
                and parts[3] == "contact-sheets"
                and method == "POST"
            ):
                request = validate_contact_sheet_request(self._decode_json(body))
                record = self._contact_sheets.create(inspection_id, request)
                return ResponseData.json(201, {"contact_sheet": record.as_dict()})

        if parts[1] == "contact-sheets" and len(parts) >= 3:
            sheet_id = parts[2]
            if len(parts) == 3 and method == "GET":
                record = self._contact_sheets.get(sheet_id)
                return ResponseData.json(200, {"contact_sheet": record.as_dict()})
            if len(parts) == 4 and parts[3] == "artifact" and method == "GET":
                payload = self._contact_sheets.get_artifact(sheet_id)
                return ResponseData.binary(
                    200,
                    payload,
                    "image/x-portable-pixmap",
                )

        return self._not_found(path)

    def _decode_json(self, body: bytes) -> Any:
        if len(body) > self._settings.max_json_bytes:
            raise ValidationError("JSON request body is too large")
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("request body must contain valid UTF-8 JSON") from exc

    def _not_found(self, path: str) -> ResponseData:
        error = ApplicationError(
            code=ErrorCode.INVALID_REQUEST,
            message="route was not found",
            status=404,
            details={"path": path},
        )
        return ResponseData.json(404, error.as_dict())
