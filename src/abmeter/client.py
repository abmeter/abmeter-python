"""HTTP client for the ABMeter API, built on ``httpx``."""

from __future__ import annotations

from typing import Any, cast

import httpx

from .api_error import APIError

ASSIGNMENT_CONFIG_PATH = "/api/v1/assignment-config"
EXPOSURES_PATH = "/api/v1/exposures"
EVENTS_PATH = "/api/v1/events"


class Client:
    def __init__(
        self, base_url: str, api_key: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
            transport=transport,
        )

    def get_assignment_config(self) -> dict[str, Any]:
        response = self._http.get(ASSIGNMENT_CONFIG_PATH)
        self._raise_unless_success(response)
        return cast(dict[str, Any], response.json())

    def submit_exposures(self, exposures: list[dict[str, Any]]) -> None:
        if not exposures:
            return
        response = self._http.post(EXPOSURES_PATH, json=exposures)
        self._raise_unless_success(response)

    def track_events(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        response = self._http.post(EVENTS_PATH, json=events)
        self._raise_unless_success(response)

    def close(self) -> None:
        self._http.close()

    @staticmethod
    def _raise_unless_success(response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text
        raise APIError(response.status_code, body)
