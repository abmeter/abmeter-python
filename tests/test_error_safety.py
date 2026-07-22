from __future__ import annotations

import abmeter
from abmeter.config import Config
from abmeter.error_safety import error_safe


def test_decorated_function_swallows_and_returns_none(monkeypatch):
    calls: list[Exception] = []
    config = Config(api_key="k", error_callback=calls.append)
    monkeypatch.setattr(abmeter, "_config", config)

    @error_safe
    def boom():
        raise RuntimeError("kaboom")

    assert boom() is None
    assert len(calls) == 1
    assert isinstance(calls[0], RuntimeError)


def test_decorated_function_passes_through_on_success(monkeypatch):
    monkeypatch.setattr(abmeter, "_config", Config(api_key="k"))

    @error_safe
    def ok(x):
        return x * 2

    assert ok(21) == 42


def test_callback_error_is_also_swallowed(monkeypatch):
    def bad_callback(_error):
        raise ValueError("callback blew up")

    monkeypatch.setattr(abmeter, "_config", Config(api_key="k", error_callback=bad_callback))

    @error_safe
    def boom():
        raise RuntimeError("kaboom")

    # Neither the original nor the callback error escapes.
    assert boom() is None
