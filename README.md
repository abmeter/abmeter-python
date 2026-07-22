# ABMeter Python SDK

A simple A/B testing and feature-flag client library for Python applications.

## Supported Python versions

`abmeter` supports **Python 3.11 and newer** (tested against 3.11, 3.12, 3.13).

## Installation

```bash
pip install abmeter
```

## Usage

```python
import abmeter

# Configure the client once at startup.
abmeter.configure(api_key="your-api-key")

# Somewhere in the rendering code:
user = abmeter.User(user_id=current_user.id, email=current_user.email)
text = abmeter.resolve_parameter(user, "welcome_text")

# Somewhere in the model code:
abmeter.track_event(
    "user_purchases_plan",
    current_user.id,
    {"plan": purchased_plan.name, "price": purchased_plan.price},
)
```

`resolve_parameter` fetches the assignment config from the platform and
resolves the variant **client-side** (no per-call server round-trip), then
records the exposure in the background. `get_exposure` evaluates the same
resolution with full detail **without** submitting, which is useful for
debugging.

## What this SDK is

A **thin client**: it fetches the assignment config, resolves parameters
locally, and submits exposures/events. It deliberately does **not** contain
the platform-side concerns of the Ruby gem (config serialization, allocation
range-building, type-validation registry). Those live in the ABMeter API.

## Development

The package uses [uv](https://docs.astral.sh/uv/). It is a pure client library,
so the unit suite needs no database or any other running service.

```bash
uv sync --extra dev   # install dependencies
uv run pytest         # tests
uv run ruff check .   # lint
uv run mypy           # type check
```

## License

Available as open source under the terms of the
[MIT License](https://opensource.org/licenses/MIT).
