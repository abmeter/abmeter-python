"""``@error_safe`` — decorator that keeps SDK calls from raising into user code.

Wraps a function so any exception is swallowed: logged via the active config's
logger and forwarded to ``error_callback`` if set, then ``None`` is returned.
The wrapped call site never raises.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def error_safe(func: F) -> F:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as error:  # noqa: BLE001 - error-safe boundary by design
            _handle(func.__name__, error)
            return None

    return wrapper  # type: ignore[return-value]


def _handle(method_name: str, error: Exception) -> None:
    # Imported lazily to avoid a circular import with the package singleton.
    from . import _current_config

    config = _current_config()
    if config is None:
        return
    if config.logger is not None:
        config.logger.error(
            "Failed to execute %s: %s - %s", method_name, type(error).__name__, error
        )
    if config.error_callback is not None:
        try:
            config.error_callback(error)
        except Exception as callback_error:  # noqa: BLE001
            if config.logger is not None:
                config.logger.error("Error in error callback: %s", callback_error)
