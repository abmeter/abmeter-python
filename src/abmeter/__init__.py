"""ABMeter Python SDK — public API.

Thin client: configure once, then ``resolve_parameter`` / ``get_exposure`` /
``track_event``.
"""

from __future__ import annotations

from typing import Any

from .async_submitter import AsyncSubmitter
from .client import Client
from .config import Config
from .constants import DEFAULT_SHUTDOWN_TIMEOUT
from .error_safety import error_safe
from .resolver_provider import ResolverProvider
from .user import User
from .version import __version__

__all__ = [
    "User",
    "Config",
    "configure",
    "resolve_parameter",
    "get_exposure",
    "track_event",
    "reset",
    "__version__",
]

_config: Config | None = None
_client: Client | None = None
_resolver_provider: ResolverProvider | None = None


def _current_config() -> Config | None:
    """Accessor used by the ``@error_safe`` boundary (avoids a circular import)."""
    return _config


def configure(**kwargs: Any) -> None:
    """Configure the SDK singleton and start the background submitter.

    Accepts ``api_key``, ``base_url``, ``static_config``, ``flush_interval``,
    ``fetch_interval``, ``logger``, ``error_callback`` — see :class:`Config`.
    """
    global _config, _client, _resolver_provider

    config = Config(**kwargs)
    config.validate()
    _config = config

    if config.static_config:
        _client = None
        _resolver_provider = ResolverProvider(config=config)
        return

    assert config.api_key is not None
    _client = Client(base_url=config.base_url, api_key=config.api_key)
    _resolver_provider = ResolverProvider(config=config, api_client=_client)
    AsyncSubmitter.configure(api_client=_client, config=config)
    AsyncSubmitter.start()


def _require_resolver_provider() -> ResolverProvider:
    if _resolver_provider is None:
        raise RuntimeError("ABMeter not configured. Call abmeter.configure(...) first.")
    return _resolver_provider


@error_safe
def resolve_parameter(user: User, parameter_slug: str) -> Any:
    """Resolve ``parameter_slug`` for ``user`` and record the exposure."""
    return _require_resolver_provider().resolve_parameter(user, parameter_slug)


@error_safe
def get_exposure(user: User, parameter_slug: str) -> Any:
    """Evaluate the full exposure detail **without** submitting it."""
    return _require_resolver_provider().get_exposure(user, parameter_slug)


@error_safe
def track_event(event_name: str, user_id: str, data: dict[str, Any]) -> None:
    """Queue an event for background submission."""
    AsyncSubmitter.queue_event(event_name, user_id, data)
    return None


def reset(timeout: float = DEFAULT_SHUTDOWN_TIMEOUT, force: bool = False) -> bool:
    """Tear down the SDK singleton.

    Graceful by default: flush queued exposures/events, blocking at most
    ``timeout`` seconds; returns True on a clean stop. With ``force=True``:
    discard queued work immediately with no network I/O — data loss by design.
    """
    global _config, _client, _resolver_provider
    clean = AsyncSubmitter.reset(timeout=timeout, force=force)
    if _client is not None:
        _client.close()
    _config = None
    _client = None
    _resolver_provider = None
    return clean
