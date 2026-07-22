"""Client-side value casting for resolved parameter values.

Only casting is needed on the client: the type-validation surface
(is-value-valid-for-type, numeric checks, type registry) is a server-side
parameter-validation concern and is intentionally not part of this SDK.
"""

from __future__ import annotations

from typing import Any

STRING = "String"
INTEGER = "Integer"
FLOAT = "Float"
BOOLEAN = "Boolean"

_TRUE = {True, "true", "TRUE", "t", "T", "1"}
_FALSE = {False, "false", "FALSE", "f", "F", "0", None, ""}


def _cast_boolean(value: Any) -> bool:
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"Cannot cast {value!r} to Boolean")


def cast(value: Any, parameter_type: str) -> Any:
    """Cast ``value`` to the given parameter type."""
    if parameter_type == STRING:
        return str(value)
    if parameter_type == INTEGER:
        return int(value)
    if parameter_type == FLOAT:
        return float(value)
    if parameter_type == BOOLEAN:
        return _cast_boolean(value)
    # Unknown type: pass through unchanged.
    return value
