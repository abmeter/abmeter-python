from __future__ import annotations

import json
from pathlib import Path

from abmeter.core.utils import to_percentage

FIXTURE = Path(__file__).parent / "fixtures" / "num_utils_parity.json"


def test_matches_ruby_generated_percentages():
    rows = json.loads(FIXTURE.read_text())
    assert len(rows) == 1000
    mismatches = [
        (salt, user_id, expected, to_percentage(salt, user_id))
        for salt, user_id, expected in rows
        if to_percentage(salt, user_id) != expected
    ]
    assert mismatches == []


def test_percentage_is_in_1_to_100_range():
    for i in range(500):
        pct = to_percentage("salt", f"user_{i}")
        assert 1 <= pct <= 100
