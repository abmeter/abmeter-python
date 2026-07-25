# ABMeter Python SDK

[ABMeter](https://abmeter.ai) is a feature-flag and A/B-testing platform. You define parameters, experiments, and feature flags in the ABMeter Lab; this package reads the value assigned to each user in your Python app and reports events back.

## Supported Python versions

`abmeter` supports **Python 3.11 and newer** (tested against 3.11, 3.12, 3.13).

## Installation

```bash
pip install abmeter
```

## Getting an API key

Sign up at [abmeter.ai](https://abmeter.ai), then in the **Lab** open **API Keys** and create one. Pass it to `configure` (e.g. from an environment variable).

## Usage

Configure the client once at startup:

```python
import abmeter

abmeter.configure(api_key="your-api-key")
```

The example below assumes a parameter `welcome_text` (in a space, with a variant, controlled by a running experiment or feature flag) and an event type `user_purchases_plan` already exist — create them through the ABMeter API or, more easily, your AI assistant over MCP. Until they do, `resolve_parameter` just returns the parameter's default and `track_event` rejects unknown event types.

```python
# In request handling: read the value assigned to this user. `user_id` is the
# only required field; an optional `email=` is available for predicate-based
# (email-pattern) audience targeting.
user = abmeter.User(user_id=current_user.id)
text = abmeter.resolve_parameter(user, "welcome_text")

# In business logic: record an action that feeds a metric.
abmeter.track_event(
    "user_purchases_plan",
    current_user.id,
    {"plan": purchased_plan.name, "price": purchased_plan.price},
)
```

The two calls are one loop: the experiment varies `welcome_text`, and the event feeds a metric whose effect the experiment measures across variants. Note that `resolve_parameter` is **not** a pure read — it fetches the assignment config, resolves the variant **client-side** (no per-call round-trip), and records an exposure in the background; use `get_exposure` for the same resolution without submitting (useful for debugging). Full guides live at [abmeter.ai](https://abmeter.ai).

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
