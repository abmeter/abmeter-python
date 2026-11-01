# Changelog

## 0.3.0 (2026-11-01)

- When a config refresh fails, the SDK keeps serving the last known config, reports the error through `error_callback` and retries after `fetch_interval`.
- On a 429 the submitter pauses for the response's `Retry-After` (30 seconds when the header is missing or unreadable, at least 1 second, at most 600) and keeps the batch queued instead of dropping it. The wait does not count as a retry attempt.
- The package metadata no longer lists a contact email.
