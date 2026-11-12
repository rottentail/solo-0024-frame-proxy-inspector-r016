from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ResponseData:
    status: int
    body: bytes
    content_type: str
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def json(
        cls,
        status: int,
        value: dict[str, Any],
    ) -> "ResponseData":
        return cls(
            status=status,
            body=json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            content_type="application/json; charset=utf-8",
            headers={"Cache-Control": "private, max-age=0"},
        )

    @classmethod
    def binary(
        cls,
        status: int,
        payload: bytes,
        content_type: str,
    ) -> "ResponseData":
        return cls(
            status=status,
            body=payload,
            content_type=content_type,
            headers={"Cache-Control": "private, max-age=0"},
        )
