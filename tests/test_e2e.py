"""Live end-to-end smoke test — the real wire round-trip.

Skipped unless an API key and URL are present in the environment, so CI (which
has no running platform) skips it cleanly. When it does run, it proves transport
+ auth + submission against a live platform — something the MockTransport unit
suite cannot. It does **not** prove statistical recovery; that is the N-sweep gate
(``canonical-apps/`` — see ``canonical-apps/README.md``).

Enable locally with a running API + seeded platform, e.g.:
    ABMETER_API_KEY=test-api-key ABMETER_API_URL=http://localhost:3001 \
        uv run pytest tests/test_e2e.py
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest

import abmeter

API_KEY = os.environ.get("ABMETER_API_KEY") or os.environ.get("QA_BOT_API_KEY")
API_URL = os.environ.get("ABMETER_API_URL")

pytestmark = pytest.mark.skipif(
    not (API_KEY and API_URL),
    reason="live e2e needs ABMETER_API_KEY (or QA_BOT_API_KEY) and ABMETER_API_URL",
)

# The python-sdk scenario slugs live in the shared definition
# (canonical-apps/scenarios/recovery.json); the seed rake task provisions them.
PARAMETER_SLUG = "sdk-py-button-color"
EVENT_SLUG = "sdk-py-purchase"
EXPERIMENT_SLUG = "sdk-py-button-experiment"
METRIC_SLUG = "sdk-py-conversion-count"
SPACE_SLUG = "python-sdk"

# sdk-python/tests/test_e2e.py -> repo root -> api
API_DIR = Path(__file__).resolve().parents[2] / "api"


@pytest.fixture(scope="module")
def _seeded():
    try:
        subprocess.run(
            ["bundle", "exec", "rails", "abmeter:sdk_recovery:seed[python]"],
            cwd=API_DIR,
            check=True,
        )
    except (FileNotFoundError, OSError) as error:
        pytest.skip(f"could not seed scenario (no rails toolchain?): {error}")
    yield


def test_resolve_track_roundtrip(_seeded):
    abmeter.configure(api_key=API_KEY, base_url=API_URL, flush_interval=1)
    user_id = "e2e_user_1"
    user = abmeter.User(user_id=user_id, email=f"{user_id}@example.com")

    color = abmeter.resolve_parameter(user, PARAMETER_SLUG)
    assert color in ("blue", "green")

    abmeter.track_event(EVENT_SLUG, user_id, {"price": 4.99})
    abmeter.reset()  # flush exposures + events synchronously
    time.sleep(1.0)

    exposures = httpx.get(
        f"{API_URL}/api/v1/exposures",
        params={"user_id": user_id, "parameter_slug": PARAMETER_SLUG},
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=30.0,
    )
    exposures.raise_for_status()
    records = exposures.json()
    assert any(r["resolved_value"] == color for r in records)

    effects = httpx.get(
        f"{API_URL}/api/v1/experiments/{EXPERIMENT_SLUG}/effects",
        params={"metric_slug": METRIC_SLUG, "space_slug": SPACE_SLUG},
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=30.0,
    )
    assert effects.status_code == 200
