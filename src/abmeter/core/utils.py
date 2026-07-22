"""Deterministic percentage assignment.

``to_percentage`` is the bucketing primitive: SHA-256 of ``"{salt}:{id}"``,
take the first 16 hex chars (64 bits) as an integer, then multiply-and-shift
into the 1..100 range. This is a cross-SDK contract — every language SDK must
produce identical percentages for the same ``(salt, id)`` (locked by the
parity fixture in ``tests/fixtures/num_utils_parity.json``).

Range precomputation is not part of the client: the platform emits ready-made
allocation ranges in the config JSON, so the client only maps a user to a
percentage and checks membership.
"""

from __future__ import annotations

import hashlib

_MASK_64 = (1 << 64) - 1


def to_percentage(salt: str, user_id: str) -> int:
    """Map ``(salt, user_id)`` uniformly onto the integer range ``1..100``."""
    digest = hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()
    num = int(digest[:16], 16) & _MASK_64
    return ((num * 100) >> 64) + 1
