"""``APIError`` against the API's golden error envelope samples.

The fixture is a copy of ``api/spec/fixtures/error_envelope.json`` and must stay identical to it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from abmeter.api_error import APIError
from abmeter.client import Client

FIXTURE = Path(__file__).parent / "fixtures" / "error_envelope.json"
SAMPLES: list[dict[str, Any]] = json.loads(FIXTURE.read_text())["samples"]


def _raise_for(sample: dict[str, Any]) -> APIError:
    response = httpx.Response(sample["status"], text=sample["body"])
    with pytest.raises(APIError) as excinfo:
        Client._raise_unless_success(response)
    return excinfo.value


@pytest.mark.parametrize("sample", SAMPLES, ids=[s["name"] for s in SAMPLES])
def test_parses_the_sample(sample: dict[str, Any]) -> None:
    error = _raise_for(sample)
    expected = sample["expected"]

    if expected["message"] is not None:
        assert error.message == expected["message"]
    assert error.code == expected["code"]
    assert error.details == expected["details"]
    assert error.retryable() is expected["retryable"]
    assert error.partial_failure() is expected["partial_failure"]
    assert error.failure_count() == expected["failure_count"]
