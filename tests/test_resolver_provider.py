from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

import pytest

from abmeter import User
from abmeter import resolver_provider as resolver_provider_module
from abmeter.config import Config
from abmeter.resolver_provider import ResolverProvider

FETCH_INTERVAL = 300.0
SLUG = "sdk-py-button-color"
# Lands in the treatment arm of the fixture experiment, so it resolves to "green".
TREATED_USER = User(user_id="u-0")


class StubClient:
    def __init__(self, config_json: str) -> None:
        self.calls = 0
        self.response: dict[str, Any] = {"config": config_json}
        self.error: Exception | None = None

    def get_assignment_config(self) -> dict[str, Any]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def travel(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    fake_time = SimpleNamespace(monotonic=clock.monotonic)
    monkeypatch.setattr(resolver_provider_module, "time", fake_time)
    return clock


@pytest.fixture
def errors() -> list[Exception]:
    return []


@pytest.fixture
def config(errors: list[Exception]) -> Config:
    return Config(api_key="k", fetch_interval=FETCH_INTERVAL, error_callback=errors.append)


@pytest.fixture
def client(config_json: str) -> StubClient:
    return StubClient(config_json)


@pytest.fixture
def provider(config: Config, client: StubClient) -> ResolverProvider:
    return ResolverProvider(config=config, api_client=client)  # type: ignore[arg-type]


@pytest.fixture
def failing_refresh(
    clock: Clock, provider: ResolverProvider, client: StubClient
) -> RuntimeError:
    provider.get_exposure(TREATED_USER, SLUG)
    error = RuntimeError("API down")
    client.error = error
    clock.travel(FETCH_INTERVAL + 1)
    return error


def test_failed_first_fetch_raises(clock: Clock, provider: ResolverProvider, client: StubClient):
    client.error = RuntimeError("API down")
    with pytest.raises(RuntimeError, match="API down"):
        provider.get_exposure(TREATED_USER, SLUG)


def test_failed_first_fetch_retries_on_next_call(
    clock: Clock, provider: ResolverProvider, client: StubClient
):
    client.error = RuntimeError("API down")
    for _ in range(2):
        with pytest.raises(RuntimeError):
            provider.get_exposure(TREATED_USER, SLUG)
    assert client.calls == 2


@pytest.mark.usefixtures("failing_refresh")
def test_failed_refresh_serves_last_known_config(provider: ResolverProvider):
    assert provider.get_exposure(TREATED_USER, SLUG)["resolved_value"] == "green"


def test_failed_refresh_calls_error_callback(
    provider: ResolverProvider, failing_refresh: RuntimeError, errors: list[Exception]
):
    provider.get_exposure(TREATED_USER, SLUG)
    assert errors == [failing_refresh]


@pytest.mark.usefixtures("failing_refresh")
def test_failed_refresh_is_logged(provider: ResolverProvider, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.ERROR, logger="abmeter"):
        provider.get_exposure(TREATED_USER, SLUG)
    assert caplog.messages == [
        "Failed to refresh assignment config, serving last known config: RuntimeError - API down"
    ]


@pytest.mark.usefixtures("failing_refresh")
def test_failed_refresh_waits_a_fetch_interval_before_retrying(
    clock: Clock, provider: ResolverProvider, client: StubClient
):
    provider.get_exposure(TREATED_USER, SLUG)
    clock.travel(FETCH_INTERVAL - 1)
    provider.get_exposure(TREATED_USER, SLUG)
    assert client.calls == 2
    clock.travel(2)
    provider.get_exposure(TREATED_USER, SLUG)
    assert client.calls == 3


@pytest.mark.usefixtures("failing_refresh")
def test_next_good_refresh_replaces_config(
    clock: Clock, provider: ResolverProvider, client: StubClient, config_dict: dict
):
    provider.get_exposure(TREATED_USER, SLUG)
    config_dict["experiments"] = []
    client.error = None
    client.response = {"config": json.dumps(config_dict)}
    clock.travel(FETCH_INTERVAL + 1)
    assert provider.get_exposure(TREATED_USER, SLUG)["resolved_value"] == "blue"
