"""
swarm/kill_switch.py — RA-1839: file-flag kill switch + Telegram /panic /resume.

The existing TAO_SWARM_ENABLED env flag halts the orchestrator on the
NEXT cycle. That's good but env vars don't propagate into a running
process — meaning a `/panic` from Telegram couldn't actually halt a
running swarm. This module adds a file-flag (.harness/swarm/kill_switch.flag)
which the orchestrator reads every cycle.

Three entry points (per skills/kill-switch-binding/SKILL.md):
  1. Telegram /panic from operator chat → trigger()
  2. Dashboard 2-of-N + 2FA → trigger() (with approver list)
  3. Telegram /resume from operator chat → resume()

Loop guard: 5 panics/hour → escalate to "manual recovery only"; resume
blocked until the flag is deleted by hand AND a `/resume-confirm <reason>`
posted from the operator chat.

Public API:
  is_active() -> bool
  trigger(source, reason="", approvers=None) -> dict
  resume(source, reason="", confirmed=False) -> dict
  panic_count_last_hour() -> int
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.kill_switch")

PANIC_RATE_LIMIT = 5         # max panics per hour before escalation lock
PANIC_WINDOW_S = 3600


def _config():
    from . import config as _cfg
    return _cfg


def _flag_file() -> Path:
    cfg = _config()
    cfg.SWARM_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return cfg.SWARM_LOG_DIR / "kill_switch.flag"


def _history_file() -> Path:
    cfg = _config()
    cfg.SWARM_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return cfg.SWARM_LOG_DIR / "kill_switch_history.jsonl"


def _lock_file() -> Path:
    cfg = _config()
    return cfg.SWARM_LOG_DIR / "kill_switch.escalation_lock"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_history(record: dict[str, Any]) -> None:
    with _history_file().open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def is_active() -> bool:
    """Return True if the kill switch is engaged (flag file exists)."""
    return _flag_file().exists()


def is_locked() -> bool:
    """Return True if escalation lock prevents /resume until manual recovery."""
    return _lock_file().exists()


def panic_count_last_hour() -> int:
    """Count `kill_switch_triggered` events in the rolling 1h window."""
    p = _history_file()
    if not p.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=PANIC_WINDOW_S)
    count = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("event") != "trigger":
            continue
        try:
            ts = datetime.fromisoformat(rec["ts"])
        except Exception:
            continue
        if ts >= cutoff:
            count += 1
    return count


def trigger(
    source: str,
    *,
    reason: str = "",
    approvers: list[str] | None = None,
) -> dict[str, Any]:
    """Engage the kill switch. Idempotent if already active.

    `source`: "telegram_panic" | "dashboard_2fa" | "ci"
    `approvers`: required if source == "dashboard_2fa", min 2.
    """
    if source == "dashboard_2fa" and len(approvers or []) < 2:
        return {"error": "dashboard_2fa requires >=2 approvers",
                "approvers_received": approvers}

    # Loop guard: too many panics → engage lock and require manual recovery
    panics_now = panic_count_last_hour()
    if panics_now >= PANIC_RATE_LIMIT and not is_locked():
        _lock_file().write_text(_now_iso())
        log.warning("kill-switch loop guard engaged: %d panics in %ds window",
                   panics_now, PANIC_WINDOW_S)

    flag = _flag_file()
    if not flag.exists():
        flag.write_text(_now_iso())
        action = "engaged"
    else:
        action = "already_engaged"

    record = {
        "ts": _now_iso(),
        "event": "trigger",
        "source": source,
        "reason": reason,
        "approvers": approvers or [],
        "action": action,
        "loop_guard_locked": is_locked(),
    }
    _append_history(record)

    # Audit-emit so the row lands in the central audit boundary too
    try:
        from . import audit_emit
        audit_emit.row(
            "kill_switch_triggered",
            actor_role="CoS" if source == "telegram_panic" else "Dashboard",
            trigger_source=source,
            reason=reason,
            approvers=approvers or [],
            action=action,
            loop_guard_locked=is_locked(),
        )
    except Exception as exc:
        log.debug("audit_emit failed for trigger: %s", exc)

    log.warning("kill-switch %s by %s — reason=%s", action, source, reason or "(none)")
    return record


def resume(
    source: str,
    *,
    reason: str = "",
    confirmed: bool = False,
) -> dict[str, Any]:
    """Disengage the kill switch.

    If escalation lock is active, requires `confirmed=True` AND `reason`
    to be non-empty (mirrors `/resume-confirm <reason>` semantics).
    """
    locked = is_locked()
    if locked and not (confirmed and reason):
        return {"error": "escalation_lock_active",
                "fix": "delete .harness/swarm/kill_switch.flag manually AND "
                       "call resume(source, reason='<why>', confirmed=True)"}

    flag = _flag_file()
    action = "no_op"
    if flag.exists():
        flag.unlink()
        action = "resumed"
    if locked:
        _lock_file().unlink()

    record = {
        "ts": _now_iso(),
        "event": "resume",
        "source": source,
        "reason": reason,
        "action": action,
        "had_escalation_lock": locked,
    }
    _append_history(record)

    try:
        from . import audit_emit
        audit_emit.row(
            "kill_switch_resumed",
            actor_role="CoS" if source.startswith("telegram") else "Dashboard",
            trigger_source=source,
            reason=reason,
            action=action,
            had_escalation_lock=locked,
        )
    except Exception as exc:
        log.debug("audit_emit failed for resume: %s", exc)

    log.info("kill-switch %s by %s — reason=%s", action, source, reason or "(none)")
    return record


__all__ = ["is_active", "is_locked", "panic_count_last_hour",
           "trigger", "resume"]
