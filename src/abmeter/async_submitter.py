"""Background submitter for exposures and events.

A process-wide singleton (class-level state): a daemon worker thread drains a
``queue.Queue`` every ``flush_interval`` seconds, batches by type, and submits
via the HTTP client. Retryable failures go to a bounded retry queue; validation
failures are dropped. A 429 pauses all submits for its ``Retry-After`` without
counting as an attempt. An ``atexit`` hook flushes on interpreter shutdown.

Not ``asyncio``: FastAPI/Flask/Django consumers run their own loop, and a
thread keeps the SDK threading-model-agnostic.
"""

from __future__ import annotations

import atexit
import logging
import queue
import threading
import time
from datetime import UTC, datetime
from typing import Any

from .api_error import APIError
from .client import Client
from .config import Config
from .constants import (
    BATCH_SIZE,
    DEFAULT_FLUSH_INTERVAL,
    DEFAULT_RETRY_AFTER,
    DEFAULT_SHUTDOWN_TIMEOUT,
    MAX_RETRY_QUEUE_SIZE,
    MAX_SUBMIT_ATTEMPTS,
)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class AsyncSubmitter:
    _queue: queue.Queue[dict[str, Any]] = queue.Queue()
    _retry_queue: list[dict[str, Any]] = []
    _lock = threading.Lock()
    _api_client: Client | None = None
    _worker: threading.Thread | None = None
    _stop = threading.Event()
    # Seconds between flushes; float so sub-second intervals work (fed to _stop.wait).
    _flush_interval: float = DEFAULT_FLUSH_INTERVAL
    _logger: logging.Logger | None = None
    _atexit_registered = False
    # Monotonic time before which a flush submits nothing (set by a 429).
    _paused_until: float | None = None

    @classmethod
    def configure(cls, api_client: Client, config: Config) -> None:
        cls._api_client = api_client
        cls._flush_interval = config.flush_interval or DEFAULT_FLUSH_INTERVAL
        cls._logger = config.logger

    @classmethod
    def start(cls) -> None:
        if cls._worker is not None and cls._worker.is_alive():
            return
        cls._stop.clear()
        cls._worker = threading.Thread(target=cls._run, name="abmeter-submitter", daemon=True)
        cls._worker.start()
        if not cls._atexit_registered:
            atexit.register(cls.shutdown)
            cls._atexit_registered = True

    @classmethod
    def queue_exposure(cls, exposure: dict[str, Any]) -> None:
        cls._queue.put({"type": "exposure", "data": exposure})

    @classmethod
    def queue_event(cls, event_slug: str, user_id: str, custom_fields: dict[str, Any]) -> None:
        cls._queue.put(
            {
                "type": "event",
                "data": {
                    "event_slug": event_slug,
                    "user_id": user_id,
                    "occurred_at": _now_iso(),
                    "custom_fields": custom_fields,
                },
            }
        )

    @classmethod
    def flush(cls) -> None:
        items: list[dict[str, Any]] = []
        with cls._lock:
            if cls._paused():
                return
            cls._process_retry_queue()
            if cls._paused():
                return
            while not cls._queue.empty() and len(items) < BATCH_SIZE:
                items.append(cls._queue.get())

        if not items:
            return

        exposures = [i["data"] for i in items if i["type"] == "exposure"]
        events = [i["data"] for i in items if i["type"] == "event"]
        if exposures:
            cls._submit_batch("exposure", exposures)
        if events:
            cls._submit_batch("event", events)

    @classmethod
    def shutdown(cls, timeout: float = DEFAULT_SHUTDOWN_TIMEOUT) -> bool:
        """Graceful stop: join the worker (bounded), then drain the queue.

        Returns True on a clean stop, False if the worker did not finish
        within ``timeout`` (it is abandoned as a daemon thread).
        """
        deadline = cls._monotonic() + timeout
        cls._stop.set()
        worker = cls._worker
        clean = True
        if worker is not None and worker.is_alive():
            worker.join(timeout=timeout)
            clean = not worker.is_alive()
        cls._worker = None
        while not cls._queue.empty() or cls._retry_queue:
            paused_until = cls._paused_until
            if paused_until is not None and cls._monotonic() < paused_until:
                if paused_until > deadline:
                    left = cls._queue.qsize() + len(cls._retry_queue)
                    cls._log(f"Shutdown timed out while rate limited, {left} items not submitted")
                    return False
                cls._sleep(paused_until - cls._monotonic())
                continue
            cls.flush()
        return clean

    @classmethod
    def reset(cls, timeout: float = DEFAULT_SHUTDOWN_TIMEOUT, force: bool = False) -> bool:
        """Tear down submitter state.

        Graceful by default (flushes; bounded by ``timeout``). With
        ``force=True``: discard queued work immediately, no network I/O.
        """
        if force:
            cls._stop.set()
            cls._worker = None  # daemon thread; exits on its own
            clean = True
        else:
            clean = cls.shutdown(timeout=timeout)
        cls._queue = queue.Queue()
        cls._retry_queue = []
        cls._paused_until = None
        cls._api_client = None
        cls._flush_interval = DEFAULT_FLUSH_INTERVAL
        cls._logger = None
        return clean

    @classmethod
    def queue_size(cls) -> int:
        return cls._queue.qsize()

    @classmethod
    def worker_alive(cls) -> bool:
        return cls._worker is not None and cls._worker.is_alive()

    # --- internals -------------------------------------------------------

    @classmethod
    def _run(cls) -> None:
        while not cls._stop.wait(cls._flush_interval):
            try:
                cls.flush()
            except Exception as error:  # noqa: BLE001 - keep the worker alive
                cls._log(f"Worker error: {error}")

    @classmethod
    def _monotonic(cls) -> float:
        return time.monotonic()

    @classmethod
    def _sleep(cls, seconds: float) -> None:
        time.sleep(max(seconds, 0.0))

    @classmethod
    def _paused(cls) -> bool:
        return cls._paused_until is not None and cls._monotonic() < cls._paused_until

    @classmethod
    def _pause(cls, error: APIError, count: int, kind: str) -> None:
        seconds = error.retry_after if error.retry_after is not None else DEFAULT_RETRY_AFTER
        until = cls._monotonic() + seconds
        cls._paused_until = max(until, cls._paused_until or until)
        cls._warn(f"Rate limited, pausing submits for {seconds:g}s with {count} {kind}s to retry")

    @classmethod
    def _submit_batch(cls, kind: str, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        if cls._api_client is None:
            cls._log(f"Cannot submit {len(items)} {kind}s - API client not configured")
            return
        if cls._paused():
            cls._add_to_retry_queue(kind, items)
            return
        try:
            cls._send(kind, items)
        except APIError as error:
            if error.rate_limited():
                cls._pause(error, len(items), kind)
                cls._add_to_retry_queue(kind, items)
            elif error.retryable():
                cls._log(f"Retryable error submitting {len(items)} {kind}s: {error.message}")
                cls._add_to_retry_queue(kind, items)
            elif error.partial_failure():
                cls._log(f"{error.failure_count()} out of {len(items)} {kind}s failed validation")
            else:
                cls._log(f"Permanent error submitting {kind}s: {error.message}")
        except Exception as error:  # noqa: BLE001 - unknown cause; do not retry
            cls._log(f"Failed to submit {len(items)} {kind}s: {error}")

    @classmethod
    def _send(cls, kind: str, items: list[dict[str, Any]]) -> None:
        assert cls._api_client is not None
        if kind == "exposure":
            cls._api_client.submit_exposures(items)
        else:
            cls._api_client.track_events(items)

    @classmethod
    def _add_to_retry_queue(cls, kind: str, items: list[dict[str, Any]]) -> None:
        with cls._lock:
            room = max(MAX_RETRY_QUEUE_SIZE - len(cls._retry_queue), 0)
            cls._retry_queue.extend(
                {"type": kind, "data": item, "attempts": 0} for item in items[:room]
            )
        dropped = len(items) - room
        if dropped > 0:
            cls._log(f"Retry queue full, dropping {dropped} {kind}s")

    @classmethod
    def _process_retry_queue(cls) -> None:
        # Called while holding the lock.
        if not cls._retry_queue:
            return
        pending = cls._retry_queue
        cls._retry_queue = []
        failed: list[dict[str, Any]] = []
        for kind in ("exposure", "event"):
            failed.extend(cls._process_retry_batch(kind, [i for i in pending if i["type"] == kind]))
        cls._retry_queue = failed

    @classmethod
    def _process_retry_batch(
        cls, kind: str, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Retry one batch of previously-failed items; return those still to re-queue.

        Bumps each item's ``attempts`` and drops any that hit
        ``MAX_SUBMIT_ATTEMPTS``, then resubmits the rest. Returns the items to keep
        for a future retry (empty when nothing should be retried): kept only on a
        retryable API error, or — for exposures but not events — an unknown network
        error. Validation and permanent failures are dropped. While paused, or on
        a 429, items come back with ``attempts`` unchanged.
        """
        if not items:
            return []
        if cls._paused():
            return items
        active: list[dict[str, Any]] = []
        for item in items:
            item["attempts"] += 1
            if item["attempts"] >= MAX_SUBMIT_ATTEMPTS:
                cls._log(f"Max retries exceeded for {kind}, dropping item")
            else:
                active.append(item)

        if not active or cls._api_client is None:
            return []

        data = [item["data"] for item in active]
        try:
            cls._send(kind, data)
            return []
        except APIError as error:
            if error.rate_limited():
                for item in active:
                    item["attempts"] -= 1
                cls._pause(error, len(active), kind)
                return active
            if error.retryable():
                cls._log(f"Retry failed (retryable) for {len(data)} {kind}s: {error.message}")
                return active
            if error.partial_failure():
                cls._log(f"Retry: {error.failure_count()} of {len(data)} {kind}s failed validation")
                return []
            cls._log(f"Retry failed with permanent error for {kind}s: {error.message}")
            return []
        except Exception as error:  # noqa: BLE001
            if kind == "event":
                cls._log(f"Retry failed with network error for {len(data)} {kind}s: {error}")
                return []
            cls._log(f"Failed to submit {len(data)} {kind}s: {error}")
            return active

    @classmethod
    def _log(cls, message: str) -> None:
        if cls._logger is not None:
            cls._logger.error("AsyncSubmitter: %s", message)

    @classmethod
    def _warn(cls, message: str) -> None:
        if cls._logger is not None:
            cls._logger.warning("AsyncSubmitter: %s", message)
