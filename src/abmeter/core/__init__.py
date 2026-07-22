"""Client-only assignment core (deserialize → resolve → build exposure)."""

from __future__ import annotations

import json
from typing import Any

from .assignment_config import Config
from .resolver import UserParameterResolver
from .types import cast
from .utils import to_percentage

__all__ = [
    "Config",
    "UserParameterResolver",
    "cast",
    "to_percentage",
    "build_resolver_from_json",
]


def build_resolver_from_json(config_json: str | dict[str, Any]) -> UserParameterResolver:
    """Build a resolver from the config payload returned by the platform.

    Accepts either the raw JSON string (as ``GET /assignment-config`` returns
    in its ``config`` field) or an already-parsed dict.
    """
    payload = json.loads(config_json) if isinstance(config_json, str) else config_json
    return UserParameterResolver(Config.from_dict(payload))
