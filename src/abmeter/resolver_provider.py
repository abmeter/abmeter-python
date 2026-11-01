"""``ResolverProvider`` — assignment-config lifecycle for the SDK.

Fetches and caches the assignment config on ``fetch_interval``, keeps serving
the last config when a refresh fails, delegates resolution to
:class:`UserParameterResolver`, and queues exposures for background submission.
"""

from __future__ import annotations

import time
from typing import Any

from .async_submitter import AsyncSubmitter
from .client import Client
from .config import Config
from .core import UserParameterResolver, build_resolver_from_json
from .error_safety import report_error

STALE_CONFIG_MESSAGE = "Failed to refresh assignment config, serving last known config"


class ResolverProvider:
    def __init__(self, config: Config, api_client: Client | None = None) -> None:
        if not (config.api_key or config.static_config):
            raise ValueError("Either api_key or static_config must be provided")
        self._config = config
        self._api_client = api_client
        self._static_config = config.static_config
        self._fetch_interval = config.fetch_interval
        self._resolver: UserParameterResolver | None = None
        self._last_fetched_at: float | None = None
        self._last_attempted_at: float | None = None
        if self._static_config:
            self._resolver = build_resolver_from_json(self._static_config)

    @property
    def resolver(self) -> UserParameterResolver:
        if not self._static_config:
            self._refresh_config_if_needed()
        if self._resolver is None:
            raise RuntimeError("Configuration not loaded")
        return self._resolver

    def resolve_parameter(self, user: Any, parameter_slug: str) -> Any:
        exposure = self.resolver.exposure_for(user, parameter_slug)
        if self._api_client is not None and exposure.get("exposable_id"):
            AsyncSubmitter.queue_exposure(exposure)
        return exposure["resolved_value"]

    def get_exposure(self, user: Any, parameter_slug: str) -> dict[str, Any]:
        return self.resolver.exposure_for(user, parameter_slug)

    def _refresh_config_if_needed(self) -> None:
        if self._static_config:
            return
        if self._resolver is not None and not self._time_to_refresh():
            return
        try:
            self._update_resolver()
        except Exception as error:
            if self._resolver is None:
                raise
            report_error(self._config, STALE_CONFIG_MESSAGE, error)

    def _time_to_refresh(self) -> bool:
        return (
            self._last_attempted_at is None
            or (time.monotonic() - self._last_attempted_at) > self._fetch_interval
        )

    def _update_resolver(self) -> None:
        assert self._api_client is not None
        self._last_attempted_at = time.monotonic()
        response = self._api_client.get_assignment_config()
        self._resolver = build_resolver_from_json(response["config"])
        self._last_fetched_at = time.monotonic()
