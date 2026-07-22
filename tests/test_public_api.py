from __future__ import annotations

import json

import pytest

import abmeter
from tests.conftest import CONFIG_DICT

BASE_URL = "https://api.test"


@pytest.fixture
def _mock_platform(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/v1/assignment-config",
        json={"version": "v1", "config": json.dumps(CONFIG_DICT)},
    )
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/api/v1/exposures", status_code=201, json={}
    )
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/api/v1/events", status_code=201, json={}
    )
    return httpx_mock


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
def test_configure_resolve_track_roundtrip(_mock_platform):
    abmeter.configure(api_key="test-key", base_url=BASE_URL, flush_interval=60)
    user = abmeter.User(user_id="user_42", email="u@example.com")

    color = abmeter.resolve_parameter(user, "sdk-py-button-color")
    assert color in ("blue", "green")

    abmeter.track_event("sdk-py-purchase", user.user_id, {"price": 4.99})

    # Flush synchronously and confirm the exposure + event reached the wire.
    abmeter.reset()
    requests = _mock_platform.get_requests()
    paths = [r.url.path for r in requests]
    assert "/api/v1/assignment-config" in paths
    assert "/api/v1/exposures" in paths
    assert "/api/v1/events" in paths


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
def test_get_exposure_does_not_submit(_mock_platform):
    abmeter.configure(api_key="test-key", base_url=BASE_URL, flush_interval=60)
    user = abmeter.User(user_id="user_7", email="u@example.com")

    exposure = abmeter.get_exposure(user, "sdk-py-button-color")
    assert exposure["resolved_value"] in ("blue", "green")

    abmeter.reset()
    paths = [r.url.path for r in _mock_platform.get_requests()]
    # get_exposure evaluates only; no exposure is submitted.
    assert "/api/v1/exposures" not in paths
