"""``APIError`` — raised for non-success responses from the ABMeter API."""

from __future__ import annotations

from typing import Any


class APIError(Exception):
    def __init__(self, status: int, body: Any) -> None:
        self.status = status
        if isinstance(body, dict):
            self._message: str = str(body.get("error", "Unknown error"))
            self.code = body.get("code")
            self.details: dict[str, Any] = body.get("details") or {}
        else:
            self._message = str(body)
            self.code = None
            self.details = {}
        super().__init__(self._message)

    @property
    def message(self) -> str:
        return self._message

    def retryable(self) -> bool:
        return self.status >= 500 or self.status in (408, 429)

    def partial_failure(self) -> bool:
        return (
            self.status == 400
            and isinstance(self.details, dict)
            and bool(self.details.get("failures"))
        )

    def failure_count(self) -> int:
        if isinstance(self.details, dict):
            return int(self.details.get("invalid_count", 0))
        return 0
