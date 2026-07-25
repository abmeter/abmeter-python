"""The ``User`` value object."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    user_id: str
    email: str | None = None
