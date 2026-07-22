from __future__ import annotations

import pytest

from abmeter.api_error import APIError
from abmeter.async_submitter import AsyncSubmitter
from abmeter.config import Config
from abmeter.constants import BATCH_SIZE, MAX_RETRY_QUEUE_SIZE


class FakeClient:
    def __init__(self, exposure_error=None, event_error=None):
        self.exposures: list[dict] = []
        self.events: list[dict] = []
        self.exposure_error = exposure_error
        self.event_error = event_error
        self.exposure_calls = 0

    def submit_exposures(self, exposures):
        self.exposure_calls += 1
        if self.exposure_error is not None:
            raise self.exposure_error
        self.exposures.extend(exposures)

    def track_events(self, events):
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
