"""Assignment-config value objects (deserialize-only).

These objects provide **only** the ``from_dict`` deserializers. Serialization
is intentionally absent: only the platform serializes config (it is what
``GET /assignment-config`` emits); a client only ever parses it.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .types import cast


@dataclass(frozen=True)
class Range:
    """Inclusive integer range: both ``begin`` and ``end`` are members."""

    begin: int
    end: int

    def contains(self, value: int) -> bool:
        return self.begin <= value <= self.end

    @classmethod
    def from_pair(cls, pair: list[int]) -> Range:
        return cls(begin=pair[0], end=pair[1])


@dataclass(frozen=True)
class Space:
    id: int
    salt: str

    @classmethod
    def from_list(cls, payload: list[dict[str, Any]]) -> list[Space]:
        return [cls(id=s["id"], salt=s["salt"]) for s in payload]


@dataclass(frozen=True)
class Parameter:
    id: int
    slug: str
    parameter_type: str
    default_value: Any
    space_id: int

    @classmethod
    def from_list(cls, payload: list[dict[str, Any]]) -> list[Parameter]:
        return [
            cls(
                id=p["id"],
                slug=p["slug"],
                parameter_type=p["parameter_type"],
                default_value=cast(p["default_value"], p["parameter_type"]),
                space_id=p["space_id"],
            )
            for p in payload
        ]


@dataclass(frozen=True)
class Variant:
    id: int
    parameter_values: dict[str, Any]

    def parameter_value(self, parameter_slug: str) -> Any:
        return self.parameter_values.get(parameter_slug)

    def controls_parameter(self, parameter_slug: str) -> bool:
        return parameter_slug in self.parameter_values

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Variant:
        values = {pv["slug"]: pv["value"] for pv in payload["parameter_values"]}
        return cls(id=payload["id"], parameter_values=values)


class Audience(ABC):
    """Base audience. Subclasses implement ``matches``."""

    def __init__(self, id: int, type: str) -> None:
        self.id = id
        self.type = type

    @abstractmethod
    def matches(self, user: Any) -> bool: ...

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Audience:
        kind = payload["type"]
        if kind == "user_list":
            return UserListAudience(id=payload["id"], user_ids=payload["user_ids"])
        if kind == "predicate":
            return PredicateAudience(id=payload["id"], predicate=payload["predicate"])
        if kind == "random":
            return RandomAudience(id=payload["id"], range=Range.from_pair(payload["range"]))
        raise ValueError(f"Unknown audience type: {kind}")


class UserListAudience(Audience):
    def __init__(self, id: int, user_ids: list[str]) -> None:
        super().__init__(id=id, type="user_list")
        self.user_ids = user_ids

    def matches(self, user: Any) -> bool:
        return user.user_id in self.user_ids


class PredicateAudience(Audience):
    def __init__(self, id: int, predicate: str) -> None:
        super().__init__(id=id, type="predicate")
        self.predicate = predicate

    def matches(self, user: Any) -> bool:
        # The predicate is an unanchored regex searched against the email.
        return re.search(self.predicate, user.email) is not None


class RandomAudience(Audience):
    def __init__(self, id: int, range: Range) -> None:
        super().__init__(id=id, type="random")
        self.range = range

    def matches(self, user: Any) -> bool:  # pragma: no cover - allocation via range
        return False


@dataclass(frozen=True)
class FeatureFlag:
    id: int
    audience: Audience
    variant: Variant

    @classmethod
    def from_list(cls, payload: list[dict[str, Any]]) -> list[FeatureFlag]:
        return [
            cls(
                id=f["id"],
                audience=Audience.from_dict(f["audience"]),
                variant=Variant.from_dict(f["variant"]),
            )
            for f in payload
        ]


@dataclass(frozen=True)
class Experiment:
    id: int
    range: Range
    # (audience, variant-or-None) pairs; variant is None for control.
    audience_variants: list[tuple[Audience, Variant | None]]
    space_id: int
    salt: str
    space_salt: str

    @classmethod
    def from_list(
        cls, payload: list[dict[str, Any]], space_salts: dict[int, str]
    ) -> list[Experiment]:
        experiments: list[Experiment] = []
        for exp in payload:
            space_salt = space_salts.get(exp["space_id"])
            if space_salt is None:
                raise ValueError(f"Space with id {exp['space_id']} not found")
            audience_variants = [
                (
                    Audience.from_dict(av["audience"]),
                    Variant.from_dict(av["variant"]) if av.get("variant") else None,
                )
                for av in exp["audience_variants"]
            ]
            experiments.append(
                cls(
                    id=exp["id"],
                    range=Range.from_pair(exp["range"]),
                    audience_variants=audience_variants,
                    space_id=exp["space_id"],
                    salt=exp["salt"],
                    space_salt=space_salt,
                )
            )
        return experiments


@dataclass(frozen=True)
class Config:
    spaces: list[Space] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
    feature_flags: list[FeatureFlag] = field(default_factory=list)
    experiments: list[Experiment] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Config:
        spaces = Space.from_list(payload.get("spaces", []))
        space_salts = {space.id: space.salt for space in spaces}
        parameters = Parameter.from_list(payload.get("parameters", []))
        feature_flags = FeatureFlag.from_list(payload.get("feature_flags", []))
        experiments = Experiment.from_list(payload.get("experiments", []), space_salts)
        return cls(
            spaces=spaces,
            parameters=parameters,
            feature_flags=feature_flags,
            experiments=experiments,
        )
