"""User → parameter resolution.

Resolution order: feature flag → experiment → parameter default. Also builds
the exposure record returned to callers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .assignment_config import Config, Experiment, FeatureFlag, Parameter, Variant
from .utils import to_percentage


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_value(parameter: Parameter, variant: Variant | None) -> Any:
    # A variant's value for the parameter, falling back to the parameter default
    # only when the variant does not set it (None). An explicitly-set falsy value
    # (False, 0, 0.0, "") is a real override and must win — truthiness would
    # wrongly drop it.
    value = variant.parameter_value(parameter.slug) if variant is not None else None
    return parameter.default_value if value is None else value


class UserParameterResolver:
    def __init__(self, config: Config) -> None:
        self.config = config

    def exposure_for(self, user: Any, parameter_slug: str) -> dict[str, Any]:
        self._validate_user(user)

        parameter = next((p for p in self.config.parameters if p.slug == parameter_slug), None)
        if parameter is None:
            raise ValueError(f"Parameter '{parameter_slug}' not found")

        feature_flag = self._matching_feature_flag(user, parameter_slug)
        if feature_flag is not None:
            return self._make_exposure(
                user, parameter, "FeatureFlag", feature_flag.id,
                feature_flag.audience.id, feature_flag.variant,
            )

        experiment_match = self._matching_experiment_variant(user, parameter_slug)
        if experiment_match is not None:
            variant, experiment, audience_id = experiment_match
            return self._make_exposure(
                user, parameter, "Experiment", experiment.id, audience_id, variant,
            )

        return {
            "parameter_id": parameter.id,
            "space_id": parameter.space_id,
            "resolved_value": parameter.default_value,
            "user_id": None,
            "exposable_type": None,
            "exposable_id": None,
            "audience_id": None,
            "resolved_at": _now_iso(),
        }

    @staticmethod
    def _validate_user(user: Any) -> None:
        if not hasattr(user, "user_id"):
            raise ValueError("User must have user_id")
        if not hasattr(user, "email"):
            raise ValueError("User must have email")

    def _make_exposure(
        self,
        user: Any,
        parameter: Parameter,
        exposable_type: str,
        exposable_id: int,
        audience_id: int,
        variant: Variant | None,
    ) -> dict[str, Any]:
        return {
            "parameter_id": parameter.id,
            "space_id": parameter.space_id,
            "resolved_value": _resolve_value(parameter, variant),
            "user_id": user.user_id,
            "exposable_type": exposable_type,
            "exposable_id": exposable_id,
            "audience_id": audience_id,
            "resolved_at": _now_iso(),
        }

    def _matching_feature_flag(self, user: Any, parameter_slug: str) -> FeatureFlag | None:
        for flag in self.config.feature_flags:
            if flag.audience.matches(user) and flag.variant.controls_parameter(parameter_slug):
                return flag
        return None

    def _matching_experiment_variant(
        self, user: Any, parameter_slug: str
    ) -> tuple[Variant | None, Experiment, int] | None:
        for experiment in self.config.experiments:
            if not self._experiment_controls(experiment, parameter_slug):
                continue

            experiment_percentage = to_percentage(experiment.space_salt, user.user_id)
            if not experiment.range.contains(experiment_percentage):
                continue

            user_percentage = to_percentage(experiment.salt, user.user_id)
            for audience, variant in experiment.audience_variants:
                audience_range = getattr(audience, "range", None)
                if audience_range is not None and audience_range.contains(user_percentage):
                    return variant, experiment, audience.id
        return None

    @staticmethod
    def _experiment_controls(experiment: Experiment, parameter_slug: str) -> bool:
        return any(
            variant is not None and variant.controls_parameter(parameter_slug)
            for _, variant in experiment.audience_variants
        )
