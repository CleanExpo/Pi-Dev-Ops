"""
app/server/kill_switch.py — RA-1966: TAO-level kill-switch primitive.

Distinct from swarm/kill_switch.py (which gates the per-cycle bot orchestrator
via .harness/swarm/kill_switch.flag for /panic /resume). This module is the
INNER loop guard for a single TAO session — planner → generator → evaluator
iteration loops, and the future tao-judge / tao-loop ports from RA-1970.

Three independent abort axes:

  * TAO_MAX_ITERS         — count cap on loop iterations (default 25)
  * TAO_MAX_COST_USD      — cumulative-cost cap in USD (default 5.00)
  * TAO_HARD_STOP_FILE    — path; existence = abort (default ~/.claude/HARD_STOP)

Public API:

    counter = LoopCounter()                  # per-loop instance
    counter.tick(cost_delta_usd=0.012)       # raises KillSwitchAbort on any limit

    check_hard_stop()                        # raises if hard-stop file exists
    snapshot()                               # diagnostic dict

Reason codes returned in the exception:
  "MAX_ITERS" / "MAX_COST" / "HARD_STOP"

The module deliberately does NOT integrate audit_emit or Telegram side-effects.
That is the swarm-level kill switch's responsibility. This one is a pure
in-process gate so that callers (orchestrator wave-poll, evaluator retry,
future tao-loop body) can call .tick() in the hot path with zero I/O when no
limit is breached.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

log = logging.getLogger("pi-ceo.kill_switch")

# Defaults are intentionally generous. Production overrides via env or
# config.py constants below.
DEFAULT_MAX_ITERS: Final[int] = 25
DEFAULT_MAX_COST_USD: Final[float] = 5.00
DEFAULT_HARD_STOP_FILE: Final[str] = str(Path.home() / ".claude" / "HARD_STOP")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except ValueError:
        log.warning("invalid %s=%r — falling back to %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = float(raw)
        return v if v > 0 else default
    except ValueError:
        log.warning("invalid %s=%r — falling back to %s", name, raw, default)
        return default


def _env_path(name: str, default: str) -> str:
    raw = os.environ.get(name, "").strip()
    return raw or default


def max_iters() -> int:
    return _env_int("TAO_MAX_ITERS", DEFAULT_MAX_ITERS)


def max_cost_usd() -> float:
    return _env_float("TAO_MAX_COST_USD", DEFAULT_MAX_COST_USD)


def hard_stop_file() -> str:
    return _env_path("TAO_HARD_STOP_FILE", DEFAULT_HARD_STOP_FILE)


class KillSwitchAbort(RuntimeError):
    """Raised by LoopCounter.tick() / check_hard_stop() when a limit is breached.

    Attributes:
        reason: one of "MAX_ITERS" / "MAX_COST" / "HARD_STOP"
        snapshot: diagnostic dict of the state at abort time
    """

    def __init__(self, reason: str, snapshot: dict) -> None:
        super().__init__(f"TAO kill-switch tripped: reason={reason} snapshot={snapshot}")
        self.reason = reason
        self.snapshot = snapshot


def check_hard_stop() -> None:
    """Raise KillSwitchAbort if TAO_HARD_STOP_FILE exists. Cheap; safe to spam."""
    p = hard_stop_file()
    if os.path.exists(p):
        snap = {"hard_stop_file": p, "iters": None, "cost_usd": None}
        raise KillSwitchAbort("HARD_STOP", snap)


@dataclass
class LoopCounter:
    """Per-loop iteration + cost guard. Construct one per loop scope.

    Reads the env limits ONCE at construction. This makes a long-running loop
    deterministic — operators flipping env vars mid-loop don't change a loop
    that has already started. To pick up new limits, construct a fresh counter.
    """

    iters: int = 0
    cost_usd: float = 0.0
    _limit_iters: int = field(default_factory=max_iters)
    _limit_cost_usd: float = field(default_factory=max_cost_usd)
    _hard_stop_path: str = field(default_factory=hard_stop_file)

    def tick(self, cost_delta_usd: float = 0.0) -> None:
        """Advance one iteration. Raises KillSwitchAbort on any limit breach.

        Order: HARD_STOP first (cheap file check), then MAX_ITERS (after
        increment), then MAX_COST (after addition). HARD_STOP is checked
        first so a panic flag never gets blocked behind a counter check.
        """
        # 1. HARD_STOP — cheap file existence check, takes precedence.
        if os.path.exists(self._hard_stop_path):
            raise KillSwitchAbort("HARD_STOP", self.snapshot())

        # 2. Iteration cap.
        self.iters += 1
        if self.iters > self._limit_iters:
            raise KillSwitchAbort("MAX_ITERS", self.snapshot())

        # 3. Cost cap.
        if cost_delta_usd:
            self.cost_usd += float(cost_delta_usd)
        if self.cost_usd > self._limit_cost_usd:
            raise KillSwitchAbort("MAX_COST", self.snapshot())

    def snapshot(self) -> dict:
        return {
            "iters": self.iters,
            "limit_iters": self._limit_iters,
            "cost_usd": round(self.cost_usd, 4),
            "limit_cost_usd": self._limit_cost_usd,
            "hard_stop_file": self._hard_stop_path,
            "hard_stop_exists": os.path.exists(self._hard_stop_path),
        }


def snapshot() -> dict:
    """Module-level diagnostic — returns current limits + hard-stop state.

    Useful for /health endpoints and for logging at the start of a loop.
    """
    p = hard_stop_file()
    return {
        "max_iters": max_iters(),
        "max_cost_usd": max_cost_usd(),
        "hard_stop_file": p,
        "hard_stop_exists": os.path.exists(p),
    }


__all__ = [
    "DEFAULT_MAX_ITERS",
    "DEFAULT_MAX_COST_USD",
    "DEFAULT_HARD_STOP_FILE",
    "KillSwitchAbort",
    "LoopCounter",
    "check_hard_stop",
    "hard_stop_file",
    "max_cost_usd",
    "max_iters",
    "snapshot",
]
