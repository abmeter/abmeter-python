from __future__ import annotations

import pytest

from abmeter import User
from abmeter.core import build_resolver_from_json
from abmeter.core.utils import to_percentage
from tests.conftest import EXPERIMENT_SALT


def _resolver(config_json: str):
    return build_resolver_from_json(config_json)


def _arm_for(user_id: str) -> str:
    pct = to_percentage(EXPERIMENT_SALT, user_id)
    return "control" if pct <= 50 else "treatment"


def _find_user(arm: str) -> str:
    for i in range(10_000):
        uid = f"user_{i}"
        if _arm_for(uid) == arm:
            return uid
    raise AssertionError(f"no user found for arm {arm}")


def test_experiment_control_resolves_default_value(config_json):
    resolver = _resolver(config_json)
    uid = _find_user("control")
    user = User(user_id=uid, email="x@example.com")
    exposure = resolver.exposure_for(user, "sdk-py-button-color")
    assert exposure["resolved_value"] == "blue"
    assert exposure["exposable_type"] == "Experiment"
    assert exposure["exposable_id"] == 10
    assert exposure["audience_id"] == 100
    assert exposure["user_id"] == uid


def test_experiment_treatment_resolves_variant_value(config_json):
    resolver = _resolver(config_json)
    uid = _find_user("treatment")
    user = User(user_id=uid, email="x@example.com")
    exposure = resolver.exposure_for(user, "sdk-py-button-color")
    assert exposure["resolved_value"] == "green"
    assert exposure["exposable_type"] == "Experiment"
    assert exposure["audience_id"] == 101


def test_resolution_is_stable_per_user(config_json):
    resolver = _resolver(config_json)
    user = User(user_id="user_42", email="x@example.com")
    first = resolver.exposure_for(user, "sdk-py-button-color")["resolved_value"]
    second = resolver.exposure_for(user, "sdk-py-button-color")["resolved_value"]
    assert first == second


def test_feature_flag_predicate_audience(config_json):
    resolver = _resolver(config_json)
    exposure = resolver.exposure_for(
        User(user_id="anyone", email="jo@beta.example.com"), "welcome-text"
    )
    assert exposure["resolved_value"] == "hi beta"
    assert exposure["exposable_type"] == "FeatureFlag"
    assert exposure["exposable_id"] == 20
    assert exposure["audience_id"] == 200


def test_feature_flag_predicate_miss_falls_to_default(config_json):
    resolver = _resolver(config_json)
    exposure = resolver.exposure_for(
        User(user_id="anyone", email="jo@example.com"), "welcome-text"
    )
    assert exposure["resolved_value"] == "hello"
    assert exposure["exposable_type"] is None
    assert exposure["exposable_id"] is None


def test_feature_flag_user_list_audience(config_json):
    resolver = _resolver(config_json)
    exposure = resolver.exposure_for(User(user_id="vip-1", email="v@x.com"), "beta-banner")
    assert exposure["resolved_value"] == "on"
    assert exposure["exposable_id"] == 21
    assert exposure["audience_id"] == 201


def test_user_list_miss_falls_to_default(config_json):
    resolver = _resolver(config_json)
    exposure = resolver.exposure_for(User(user_id="nobody", email="n@x.com"), "beta-banner")
    assert exposure["resolved_value"] == "off"
    assert exposure["exposable_id"] is None


@pytest.mark.parametrize(
    ("param_type", "falsy_value"),
    [("Boolean", False), ("Integer", 0), ("Float", 0.0), ("String", "")],
)
def test_variant_falsy_override_wins_over_default(param_type, falsy_value):
    # A variant that explicitly overrides a parameter to a falsy value must win.
    # The platform wire format casts values to their native type, so truthiness
    # (`if value`) would wrongly drop it and fall back to the default.
    import json

    config = {
        "spaces": [{"id": 1, "salt": "s"}],
        "parameters": [
            {"id": 1, "slug": "p", "parameter_type": param_type,
             "default_value": "1" if param_type != "String" else "default", "space_id": 1},
        ],
        "feature_flags": [
            {"id": 1,
             "audience": {"id": 1, "type": "user_list", "user_ids": ["u"]},
             "variant": {"id": 1, "parameter_values": [{"slug": "p", "value": falsy_value}]}},
        ],
        "experiments": [],
    }
    resolver = _resolver(json.dumps(config))
    exposure = resolver.exposure_for(User(user_id="u", email="e@x.com"), "p")
    assert exposure["exposable_type"] == "FeatureFlag"
    assert exposure["resolved_value"] == falsy_value


def test_unknown_parameter_raises(config_json):
    resolver = _resolver(config_json)
    with pytest.raises(ValueError, match="not found"):
        resolver.exposure_for(User(user_id="u", email="e@x.com"), "no-such-param")


# Email is an optional targeting field, not part of identity. A user built with
# only a user_id resolves through every non-predicate path normally, and simply
# never matches an email predicate.
def test_no_email_predicate_audience_falls_to_default(config_json):
    resolver = _resolver(config_json)
    exposure = resolver.exposure_for(User(user_id="anyone"), "welcome-text")
    assert exposure["resolved_value"] == "hello"
    assert exposure["exposable_type"] is None


def test_no_email_user_list_audience_resolves(config_json):
    resolver = _resolver(config_json)
    exposure = resolver.exposure_for(User(user_id="vip-1"), "beta-banner")
    assert exposure["resolved_value"] == "on"
    assert exposure["exposable_id"] == 21


def test_no_email_experiment_resolves(config_json):
    resolver = _resolver(config_json)
    uid = _find_user("treatment")
    exposure = resolver.exposure_for(User(user_id=uid), "sdk-py-button-color")
    assert exposure["resolved_value"] == "green"
    assert exposure["exposable_type"] == "Experiment"


def test_user_without_attributes_raises(config_json):
    resolver = _resolver(config_json)

    class Bad:
        pass

    with pytest.raises(ValueError):
        resolver.exposure_for(Bad(), "sdk-py-button-color")
