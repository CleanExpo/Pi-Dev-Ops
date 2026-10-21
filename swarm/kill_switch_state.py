"""swarm/kill_switch_state.py — the send gate and the panic sequence.

Split out of kill_switch.py (file-length limit); kill_switch re-exports
send_gate and panic_seq, so callers are unchanged.

send_gate() is one flock. Outbound sends hold it from the last halt check
through the send; trigger() holds it while it records a panic and raises the
flag; resume() holds it while it checks and clears. So a send never starts
after a completed panic, and a resume never clears a panic recorded after
the caller observed panic_seq().
"""
from __future__ import annotations

import fcntl
import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger("swarm.kill_switch")


def _dir() -> Path:
    from . import config
    config.SWARM_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return config.SWARM_LOG_DIR


@contextmanager
def send_gate() -> Iterator[None]:
    """Hold from the last halt check through an outbound send.

    trigger() takes the same lock before raising the flag, so a panic either
    lands first (the send sees it and stops) or waits for the in-flight send
    to finish. A send never starts after a panic has completed. Not re-entrant.
    """
    with (_dir() / "kill_switch.send_gate.lock").open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def panic_state() -> tuple[int, float] | None:
    """(sequence, unix time) of the latest panic; (0, 0.0) if none; None if unreadable."""
    try:
        state = json.loads((_dir() / "kill_switch.panic_seq.json").read_text())
        return int(state["seq"]), float(state["at"])
    except FileNotFoundError:
        return 0, 0.0
    except Exception as exc:
        log.error("kill_switch.panic_seq.json unreadable (%s): resumes refused until a "
                  "panic rewrites it", exc)
        return None


def panic_seq() -> int:
    """Monotonic count of panics. A resume passes the value it saw when it decided."""
    return (panic_state() or (0, 0.0))[0]


def record_panic() -> None:
    """Bump the panic sequence and stamp its time (caller holds send_gate())."""
    path = _dir() / "kill_switch.panic_seq.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"seq": panic_seq() + 1, "at": time.time()}))
    tmp.replace(path)


__all__ = ["panic_seq", "panic_state", "record_panic", "send_gate"]
