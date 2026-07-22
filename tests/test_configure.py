from __future__ import annotations

import pytest

import abmeter
from abmeter.config import Config


def test_configure_requires_api_key():
    with pytest.raises(ValueError, match="No API key"):
        Config().validate()


def test_configure_accepts_static_config_without_api_key():
    # static_config is the JSON-mode escape hatch; no api_key required.
    Config(static_config='{"spaces":[],"parameters":[],"feature_flags":[],"experiments":[]}').validate()


def test_resolve_without_configure_returns_none_via_error_safe():
    # Public API is error-safe: calling before configure swallows and returns None.
    assert abmeter.resolve_parameter(abmeter.User("u", "e@x.com"), "p") is None


def test_reset_clears_configuration():
    abmeter.configure(
        static_config='{"spaces":[{"id":1,"salt":"s"}],'
        '"parameters":[{"id":1,"slug":"p","parameter_type":"String",'
        '"default_value":"d","space_id":1}],'
        '"feature_flags":[],"experiments":[]}'
    )
    assert abmeter.resolve_parameter(abmeter.User("u", "e@x.com"), "p") == "d"
    abmeter.reset()
    assert abmeter.resolve_parameter(abmeter.User("u", "e@x.com"), "p") is None
