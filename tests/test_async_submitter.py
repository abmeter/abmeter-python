from __future__ import annotations

import logging

import pytest

from abmeter.api_error import APIError
from abmeter.async_submitter import AsyncSubmitter
from abmeter.config import Config
from abmeter.constants import BATCH_SIZE, MAX_RETRY_QUEUE_SIZE, MAX_SUBMIT_ATTEMPTS


class FakeClient:
    def __init__(self, exposure_error=None, event_error=None):
        self.exposures: list[dict] = []
        self.events: list[dict] = []
        self.exposure_error = exposure_error
        self.event_error = event_error
        self.exposure_calls = 0
        self.event_calls = 0

    def submit_exposures(self, exposures):
        self.exposure_calls += 1
        if self.exposure_error is not None:
            raise self.exposure_error
        self.exposures.extend(exposures)

    def track_events(self, events):
        self.event_calls += 1
        if self.event_error is not None:
            raise self.event_error
        self.events.extend(events)


def _api_error(status: int, details=None) -> APIError:
    return APIError(status, {"error": "x", "details": details or {}})


@pytest.fixture
def submitter():
    AsyncSubmitter.reset()
    yield AsyncSubmitter
    AsyncSubmitter.reset()


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(AsyncSubmitter, "_monotonic", classmethod(lambda cls: fake.now))
    monkeypatch.setattr(AsyncSubmitter, "_sleep", classmethod(lambda cls, s: fake.sleep(s)))
    return fake


def _rate_limited(retry_after: str = "10") -> APIError:
    return APIError(429, {"error": "Rate limit exceeded"}, headers={"Retry-After": retry_after})


def _configure(client) -> None:
    AsyncSubmitter.configure(api_client=client, config=Config(api_key="k"))


def test_queue_and_flush_exposures(submitter):
    client = FakeClient()
    _configure(client)
    submitter.queue_exposure({"parameter_id": 1})
    submitter.queue_event("sdk-py-purchase", "u1", {"price": 1})
    submitter.flush()
    assert client.exposures == [{"parameter_id": 1}]
    assert client.events[0]["event_slug"] == "sdk-py-purchase"
    assert client.events[0]["user_id"] == "u1"
    assert "occurred_at" in client.events[0]


def test_flush_drains_at_most_batch_size(submitter):
    client = FakeClient()
    _configure(client)
    for i in range(BATCH_SIZE + 25):
        submitter.queue_exposure({"parameter_id": i})
    submitter.flush()
    assert len(client.exposures) == BATCH_SIZE
    assert submitter.queue_size() == 25


def test_retryable_failure_requeues_then_succeeds(submitter):
    client = FakeClient(exposure_error=_api_error(503))
    _configure(client)
    submitter.queue_exposure({"parameter_id": 1})
    submitter.flush()  # fails, goes to retry queue
    assert client.exposures == []
    client.exposure_error = None
    submitter.flush()  # retry succeeds
    assert client.exposures == [{"parameter_id": 1}]


def test_validation_failure_is_not_retried(submitter):
    err = _api_error(400, {"invalid_count": 1, "failures": [{"index": 0}]})
    client = FakeClient(exposure_error=err)
    _configure(client)
    submitter.queue_exposure({"parameter_id": 1})
    submitter.flush()
    submitter.flush()
    # One submit attempt; validation failures are dropped, never retried.
    assert client.exposure_calls == 1


def test_retry_queue_is_bounded(submitter):
    client = FakeClient(exposure_error=_api_error(503))
    _configure(client)
    for i in range(MAX_RETRY_QUEUE_SIZE + 50):
        submitter.queue_exposure({"parameter_id": i})
    # Drain everything through flushes; retry queue must never exceed the cap.
    for _ in range(20):
        submitter.flush()
        assert len(AsyncSubmitter._retry_queue) <= MAX_RETRY_QUEUE_SIZE


def test_shutdown_flushes_remaining(submitter):
    client = FakeClient()
    _configure(client)
    submitter.queue_exposure({"parameter_id": 7})
    assert submitter.shutdown() is True
    assert client.exposures == [{"parameter_id": 7}]


def test_shutdown_drains_retry_queue(submitter):
    # A retryable failure strands items in the retry queue while the main
    # queue is empty; shutdown must give them a final attempt (Ruby parity).
    client = FakeClient(exposure_error=_api_error(503))
    _configure(client)
    submitter.queue_exposure({"parameter_id": 9})
    submitter.flush()  # fails, moves to retry queue; main queue now empty
    assert client.exposures == []
    assert AsyncSubmitter._retry_queue
    client.exposure_error = None
    assert submitter.shutdown() is True
    assert client.exposures == [{"parameter_id": 9}]
    assert AsyncSubmitter._retry_queue == []


def test_reset_force_discards_without_network(submitter):
    client = FakeClient()
    _configure(client)
    submitter.queue_exposure({"parameter_id": 7})
    submitter.reset(force=True)
    assert client.exposures == []
    assert submitter.queue_size() == 0


def test_rate_limit_pauses_then_delivers_everything(submitter, clock):
    client = FakeClient(exposure_error=_rate_limited("10"))
    _configure(client)
    submitter.queue_exposure({"parameter_id": 1})
    submitter.queue_event("sdk-py-purchase", "u1", {})
    submitter.flush()
    # The event batch was taken in the same flush; it waits without being sent.
    assert client.exposure_calls == 1
    assert client.event_calls == 0
    assert len(AsyncSubmitter._retry_queue) == 2

    client.exposure_error = None
    submitter.queue_exposure({"parameter_id": 2})
    clock.now += 9
    submitter.flush()
    assert client.exposure_calls == 1
    assert client.event_calls == 0
    assert submitter.queue_size() == 1

    clock.now += 1
    submitter.flush()
    submitter.flush()
    assert client.exposures == [{"parameter_id": 1}, {"parameter_id": 2}]
    assert len(client.events) == 1
    assert AsyncSubmitter._retry_queue == []


def test_consecutive_rate_limits_never_count_as_attempts(submitter, clock):
    client = FakeClient(exposure_error=_rate_limited("5"))
    _configure(client)
    submitter.queue_exposure({"parameter_id": 1})
    submitter.flush()
    for _ in range(MAX_SUBMIT_ATTEMPTS + 2):
        clock.now += 5
        submitter.flush()
        assert AsyncSubmitter._retry_queue[0]["attempts"] == 0
    assert client.exposure_calls == MAX_SUBMIT_ATTEMPTS + 3

    client.exposure_error = None
    clock.now += 5
    submitter.flush()
    assert client.exposures == [{"parameter_id": 1}]
    assert AsyncSubmitter._retry_queue == []


def test_rate_limit_logs_one_warning(submitter, clock, caplog):
    client = FakeClient(exposure_error=_rate_limited("10"))
    _configure(client)
    for i in range(3):
        submitter.queue_exposure({"parameter_id": i})
    with caplog.at_level(logging.WARNING, logger="abmeter"):
        submitter.flush()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "10s" in warnings[0].getMessage()
    assert "3 exposures" in warnings[0].getMessage()


def test_full_retry_queue_drops_and_logs_count_once(submitter, clock, caplog):
    client = FakeClient(exposure_error=_rate_limited("10"))
    _configure(client)
    AsyncSubmitter._retry_queue = [
        {"type": "event", "data": {}, "attempts": 0} for _ in range(MAX_RETRY_QUEUE_SIZE - 2)
    ]
    with caplog.at_level(logging.ERROR, logger="abmeter"):
        submitter._submit_batch("exposure", [{"parameter_id": i} for i in range(5)])
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "dropping 3 exposures" in errors[0].getMessage()
    assert len(AsyncSubmitter._retry_queue) == MAX_RETRY_QUEUE_SIZE


def test_server_error_still_drops_after_max_attempts(submitter, clock):
    client = FakeClient(exposure_error=_api_error(503))
    _configure(client)
    submitter.queue_exposure({"parameter_id": 1})
    for _ in range(MAX_SUBMIT_ATTEMPTS + 2):
        submitter.flush()
    # First submit plus retries until the attempt cap; no pause for a 5xx.
    assert client.exposure_calls == MAX_SUBMIT_ATTEMPTS
    assert AsyncSubmitter._retry_queue == []
    assert AsyncSubmitter._paused_until is None


def test_shutdown_waits_out_a_short_pause(submitter, clock):
    client = FakeClient(exposure_error=_rate_limited("2"))
    _configure(client)
    submitter.queue_exposure({"parameter_id": 1})
    submitter.flush()
    client.exposure_error = None
    assert submitter.shutdown(timeout=5) is True
    assert clock.slept == [2]
    assert client.exposures == [{"parameter_id": 1}]


def test_shutdown_stops_when_pause_outlasts_timeout(submitter, clock, caplog):
    client = FakeClient(exposure_error=_rate_limited("600"))
    _configure(client)
    submitter.queue_exposure({"parameter_id": 1})
    submitter.flush()
    submitter.queue_exposure({"parameter_id": 2})
    client.exposure_error = None
    with caplog.at_level(logging.ERROR, logger="abmeter"):
        assert submitter.shutdown(timeout=5) is False
    assert clock.slept == []
    assert client.exposures == []
    assert "2 items not submitted" in caplog.text


def test_reset_clears_pause(submitter, clock):
    client = FakeClient(exposure_error=_rate_limited("600"))
    _configure(client)
    submitter.queue_exposure({"parameter_id": 1})
    submitter.flush()
    submitter.reset(force=True)
    assert AsyncSubmitter._paused_until is None
