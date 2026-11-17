"""internal_secret.py — the one owner of the X-Pi-CEO-Secret decision (RA-8408).

Every route that takes the `X-Pi-CEO-Secret` header asks this module whether the
presented value is accepted. It accepts the current key and, during a rotation, one
optional next key, so holders can be moved to a new key one at a time and the old
key retired with no outage. The two fleet read routes also accept the read-only
fleet key. The safe rotation order is docs/runbooks/fleet-key-rotation.md.

Slots, read on every call (nothing is cached at import):
  current    config.INTERNAL_WEBHOOK_SECRET, stripped
  next       TAO_INTERNAL_WEBHOOK_SECRET_NEXT, honoured only when it passes policy
  read-only  TAO_FLEET_READ_SECRET, stripped

No log line or error carries a key value, hash, prefix or length.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time

from . import config

log = logging.getLogger("pi-ceo.internal_secret")

CURRENT_ENV = "TAO_INTERNAL_WEBHOOK_SECRET"
NEXT_ENV = "TAO_INTERNAL_WEBHOOK_SECRET_NEXT"
READ_ONLY_ENV = "TAO_FLEET_READ_SECRET"
MIN_NEXT_LENGTH = 32
LOG_WINDOW_S = 600.0
ACCEPTED = frozenset({"current", "next", "read_only"})

# An empty slot is compared against this value and the result is thrown away, so
# every slot costs the same and an empty slot can never match. Random per process,
# so it cannot be known in advance or presented on purpose.
_DUMMY = os.urandom(32).hex()

# Patchable clock and per-process limiter for the accepted/rejected lines. A race
# can only duplicate a line; the window restarts on every deploy.
_now = time.monotonic
_last_logged: dict[tuple[str, str, str], float] = {}

STARTUP_CURRENT_EMPTY = "TAO_INTERNAL_WEBHOOK_SECRET not set — internal intake webhooks are disabled (503)"
STARTUP_LINES = {
    "unset": "internal_secret: next slot not set",
    "active": "internal_secret: next slot ACTIVE: rotation in progress, finish the swap "
              "(docs/runbooks/fleet-key-rotation.md)",
    "equals_current": "internal_secret: next slot equals current: swap applied, "
                      "now remove TAO_INTERNAL_WEBHOOK_SECRET_NEXT",
    "ignored": "internal_secret: TAO_INTERNAL_WEBHOOK_SECRET_NEXT is set but IGNORED (fails policy)",
}
STARTUP_FALLBACK = "internal_secret: current key comes from the TAO_WEBHOOK_SECRET fallback"
STARTUP_READ_ONLY_IS_WRITE_KEY = "internal_secret: read-only fleet key equals a write key"


def _printable(value: str) -> bool:
    return all(0x21 <= ord(ch) <= 0x7E for ch in value)


def effective_next(current: str, raw_next: str, read_only: str) -> str:
    """The next value to honour, or "" when it fails any policy rule."""
    candidate = (raw_next or "").strip()
    if not current or not candidate or not _printable(candidate):
        return ""
    if len(candidate) < MIN_NEXT_LENGTH or candidate == current or candidate == read_only:
        return ""
    return candidate


def next_state(current: str, raw_next: str, read_only: str) -> str:
    """One of "unset", "active", "equals_current" or "ignored"."""
    if not raw_next:
        return "unset"
    if effective_next(current, raw_next, read_only):
        return "active"
    if current and raw_next.strip() == current:
        return "equals_current"
    return "ignored"


def _slots() -> tuple[str, str, str]:
    current = (config.INTERNAL_WEBHOOK_SECRET or "").strip()
    read_only = os.environ.get(READ_ONLY_ENV, "").strip()
    return current, effective_next(current, os.environ.get(NEXT_ENV, ""), read_only), read_only


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).digest()


def _matches(presented: str, slots: tuple[str, str, str]) -> list[bool]:
    """Compare against every slot, always all of them; an empty slot never matches."""
    want = _digest(presented)
    results = []
    for slot in slots:
        same = hmac.compare_digest(want, _digest(slot or _DUMMY))
        results.append(bool(slot) and same)
    return results


def _should_log(kind: str, state: str, where: str) -> bool:
    key, now = (kind, state, where), _now()
    last = _last_logged.get(key)
    if last is not None and now - last < LOG_WINDOW_S:
        return False
    _last_logged[key] = now
    return True


def _record(result: str, where: str, next_honoured: bool) -> None:
    if result in ("missing", "mismatch"):
        if _should_log("rejected", result, where):
            log.warning("internal_secret: rejected reason=%s where=%s", result, where)
    elif result in ("current", "next") and next_honoured and _should_log("accepted", result, where):
        log.info("internal_secret: accepted slot=%s where=%s", result, where)


def classify(presented: str | None, where: str) -> str:
    """Decide a write route: unconfigured, missing, mismatch, current or next.

    A next value alone never opens anything: with no current key the answer is
    unconfigured. The presented value is never stripped.
    """
    slots = _slots()
    if not slots[0]:
        return "unconfigured"
    if presented is None or presented == "":
        result = "missing"
    else:
        is_current, is_next, _read_only = _matches(presented, slots)
        result = "current" if is_current else "next" if is_next else "mismatch"
    _record(result, where, bool(slots[1]))
    return result


def classify_fleet_read(presented: str | None) -> str:
    """Decide one of the two fleet read routes; also accepts the read-only key."""
    slots = _slots()
    if not any(slots):
        return "unconfigured"
    if presented is None or presented == "":
        result = "missing"
    else:
        is_current, is_next, is_read_only = _matches(presented, slots)
        result = ("current" if is_current else "next" if is_next
                  else "read_only" if is_read_only else "mismatch")
    _record(result, "fleet_read", bool(slots[1]))
    return result


def accepted(result: str) -> bool:
    """True only for an accepted slot. Wrappers branch on this, never on refusals."""
    return result in ACCEPTED


def log_startup_state(logger: logging.Logger) -> None:
    """One primary line for the key state, plus the two independent warnings."""
    current = (config.INTERNAL_WEBHOOK_SECRET or "").strip()
    raw_next = os.environ.get(NEXT_ENV, "")
    read_only = os.environ.get(READ_ONLY_ENV, "").strip()
    if not current:
        logger.warning(STARTUP_CURRENT_EMPTY)
    else:
        state = next_state(current, raw_next, read_only)
        (logger.info if state == "unset" else logger.warning)(STARTUP_LINES[state])
        if not os.environ.get(CURRENT_ENV, ""):
            logger.warning(STARTUP_FALLBACK)
    if read_only and read_only in (current, raw_next.strip()):
        logger.warning(STARTUP_READ_ONLY_IS_WRITE_KEY)


def _reset_log_state() -> None:
    """Tests only: forget which lines were logged."""
    _last_logged.clear()
