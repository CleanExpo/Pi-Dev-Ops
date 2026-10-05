"""Process-local Linear quota state shared by the poller and live panel."""

import threading
import time

_RATE_LIMIT_SECONDS = 3600
_rate_limited_until = 0.0
_lock = threading.Lock()


class LinearRateLimitError(RuntimeError):
    """A sanitized signal to stop reading the exhausted Linear key."""


def linear_rate_limited() -> bool:
    with _lock:
        return time.monotonic() < _rate_limited_until


def mark_linear_rate_limited() -> LinearRateLimitError:
    global _rate_limited_until
    with _lock:
        _rate_limited_until = max(_rate_limited_until, time.monotonic() + _RATE_LIMIT_SECONDS)
    return LinearRateLimitError("Linear rate limited; retry after cooldown")


def has_linear_rate_limit_error(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    errors = payload.get("errors")
    if not isinstance(errors, list):
        return False
    return any(
        isinstance(error, dict)
        and isinstance(error.get("extensions"), dict)
        and error["extensions"].get("code") == "RATELIMITED"
        for error in errors
    )
