"""``APIError`` — raised for non-success responses from the ABMeter API."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .constants import DEFAULT_RETRY_AFTER, MAX_RETRY_AFTER, MIN_RETRY_AFTER

RATE_LIMITED_STATUS = 429
_DELTA_SECONDS = re.compile(r"\d+", re.ASCII)


class APIError(Exception):
    def __init__(self, status: int, body: Any, headers: Mapping[str, str] | None = None) -> None:
        self.status = status
        if isinstance(body, dict):
            self._message: str = str(body.get("error", "Unknown error"))
            self.code = body.get("code")
            self.details: dict[str, Any] = body.get("details") or {}
        else:
            self._message = str(body)
            self.code = None
            self.details = {}
        self.retry_after: float | None = (
            _parse_retry_after(headers) if status == RATE_LIMITED_STATUS else None
        )
        super().__init__(self._message)

    @property
    def message(self) -> str:
        return self._message

    def retryable(self) -> bool:
        return self.status >= 500 or self.status in (408, RATE_LIMITED_STATUS)

    def rate_limited(self) -> bool:
        return self.status == RATE_LIMITED_STATUS

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


def _parse_retry_after(headers: Mapping[str, str] | None) -> float:
    """Seconds from a delta-seconds ``Retry-After``, capped; the default otherwise."""
    value = next(
        (v for k, v in (headers or {}).items() if k.lower() == "retry-after"),
        None,
    )
    if value is None or not _DELTA_SECONDS.fullmatch(value.strip()):
        return DEFAULT_RETRY_AFTER
    return min(max(float(value.strip()), MIN_RETRY_AFTER), MAX_RETRY_AFTER)
