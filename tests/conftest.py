from __future__ import annotations

import json

import pytest

import abmeter
from abmeter.async_submitter import AsyncSubmitter

SPACE_SALT = "space-1-salt"
# The wire format includes a per-experiment salt; fixtures match that shape.
EXPERIMENT_SALT = "exp-10-salt"

# A hand-built assignment config exercising all three resolution paths:
# feature flag (predicate + user_list), experiment (random allocation), default.
CONFIG_DICT = {
    "spaces": [{"id": 1, "salt": SPACE_SALT}],
    "parameters": [
        {"id": 1, "slug": "sdk-py-button-color", "parameter_type": "String",
         "default_value": "blue", "space_id": 1},
        {"id": 2, "slug": "welcome-text", "parameter_type": "String",
         "default_value": "hello", "space_id": 1},
        {"id": 3, "slug": "beta-banner", "parameter_type": "String",
         "default_value": "off", "space_id": 1},
    ],
    "feature_flags": [
        {"id": 20,
         "audience": {"id": 200, "type": "predicate",
                      "predicate": "@beta\\.example\\.com$"},
         "variant": {"id": 300, "parameter_values": [
             {"slug": "welcome-text", "value": "hi beta"}]}},
        {"id": 21,
         "audience": {"id": 201, "type": "user_list", "user_ids": ["vip-1", "vip-2"]},
         "variant": {"id": 301, "parameter_values": [{"slug": "beta-banner", "value": "on"}]}},
    ],
    "experiments": [
        {"id": 10, "space_id": 1, "range": [1, 100], "salt": EXPERIMENT_SALT,
         "audience_variants": [
             {"audience": {"id": 100, "type": "random", "range": [1, 50]},
              "variant": None},
             {"audience": {"id": 101, "type": "random", "range": [51, 100]},
              "variant": {"id": 400, "parameter_values": [
                  {"slug": "sdk-py-button-color", "value": "green"}]}},
         ]},
    ],
}


@pytest.fixture
def config_dict() -> dict:
    return json.loads(json.dumps(CONFIG_DICT))


@pytest.fixture
def config_json(config_dict: dict) -> str:
    return json.dumps(config_dict)


@pytest.fixture(autouse=True)
def _reset_sdk_singletons():
    """Keep the process-wide SDK/submitter singletons clean between tests."""
    yield
    abmeter.reset()
    AsyncSubmitter.reset()
