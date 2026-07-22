"""SDK configuration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .constants import (
    DEFAULT_BASE_URL,
    DEFAULT_FETCH_INTERVAL,
    DEFAULT_FLUSH_INTERVAL,
)


def _default_logger() -> logging.Logger:
    logger = logging.getLogger("abmeter")
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
        logger.setLevel(logging.ERROR)
    return logger


@dataclass
class Config:
    api_key: str | None = None
    base_url: str = DEFAULT_BASE_URL
    static_config: str | None = None
    flush_interval: float = DEFAULT_FLUSH_INTERVAL
    fetch_interval: float = DEFAULT_FETCH_INTERVAL
    logger: logging.Logger = field(default_factory=_default_logger)
    error_callback: Callable[[Exception], Any] | None = None

    def validate(self) -> None:
        if self.static_config:
            return
        if self.api_key is None:
            raise ValueError("No API key provided")
        if self.base_url is None:
            raise ValueError("No API URL provided")
