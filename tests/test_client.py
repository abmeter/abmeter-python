from __future__ import annotations

import httpx
import pytest

from abmeter.api_error import APIError
from abmeter.client import Client


def _client(handler) -> Client:
    return Client(
        base_url="https://api.test", api_key="key", transport=httpx.MockTransport(handler)
    )


def test_get_assignment_config_returns_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer key"
        assert request.url.path == "/api/v1/assignment-config"
        return httpx.Response(200, json={"version": "v1", "config": "{}"})

    result = _client(handler).get_assignment_config()
    assert result == {"version": "v1", "config": "{}"}


def test_submit_exposures_posts_array():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(201, json={"recorded_count": 1, "invalid_count": 0})

    _client(handler).submit_exposures([{"parameter_id": 1}])
    assert seen["path"] == "/api/v1/exposures"


def test_empty_batches_do_not_hit_network():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not be called")

    client = _client(handler)
    client.submit_exposures([])
    client.track_events([])


def test_partial_failure_raises_apierror():
    body = {
        "error": "Failed",
        "status": 400,
        "details": {"invalid_count": 2, "failures": [{"index": 1}]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json=body)

    with pytest.raises(APIError) as exc:
        _client(handler).submit_exposures([{"x": 1}])
    assert exc.value.partial_failure() is True
    assert exc.value.failure_count() == 2
    assert exc.value.retryable() is False


def test_server_error_is_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    with pytest.raises(APIError) as exc:
        _client(handler).track_events([{"event_slug": "x"}])
    assert exc.value.retryable() is True


def test_network_error_propagates():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(httpx.ConnectError):
        _client(handler).get_assignment_config()
