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

from .kill_switch_state import panic_seq, panic_state, record_panic, send_gate

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


def _raise_flag() -> str:
    """Record a panic and raise the flag, under send_gate() (loop guard included)."""
    with send_gate():
        panics_now = panic_count_last_hour()
        if panics_now >= PANIC_RATE_LIMIT and not is_locked():
            _lock_file().write_text(_now_iso())
            log.warning("kill-switch loop guard engaged: %d panics in %ds window",
                        panics_now, PANIC_WINDOW_S)
        record_panic()
        flag = _flag_file()
        if flag.exists():
            return "already_engaged"
        flag.write_text(_now_iso())
        return "engaged"


def _clear_flag(*, confirmed: bool, reason: str, observed_seq: int | None,
                sent_at: float | None) -> tuple[str, bool]:
    """Check and clear in one step under send_gate(), the lock trigger() takes.

    Returns (outcome, had_escalation_lock); outcome is "resumed", "no_op",
    "escalation_lock_active" or "newer_panic" (a panic recorded after the
    caller observed observed_seq, or after the command was sent at sent_at)."""
    with send_gate():
        locked = is_locked()
        if locked and not (confirmed and reason):
            return "escalation_lock_active", locked
        seq, at = panic_state() or (2**63, float("inf"))  # unreadable: refuse
        if ((observed_seq is not None and seq > observed_seq)
                or (sent_at is not None and at > sent_at)):
            return "newer_panic", locked
        flag = _flag_file()
        outcome = "no_op"
        if flag.exists():
            flag.unlink()
            outcome = "resumed"
        if locked:
            _lock_file().unlink()
        return outcome, locked


def handle_command(text: str, *, observed_seq: int | None = None,
                   sent_at: float | None = None) -> str | None:
    """Apply a Telegram /panic, /resume-confirm or /resume; return which, else None.

    Shared by the CoS poller and the production webhook so both behave the same.
    `observed_seq` (panic_seq() when the command was received) and `sent_at`
    (the message's own date) let resume() refuse to clear a newer panic.
    """
    text = text.strip()
    lower = text.lower()
    if lower.startswith("/panic"):
        trigger("telegram_panic", reason=text[len("/panic"):].strip() or "operator-initiated")
        return "panic"
    if lower.startswith("/resume-confirm"):
        out = resume("telegram_resume_confirm", confirmed=True, observed_seq=observed_seq,
                     sent_at=sent_at,
                     reason=text[len("/resume-confirm"):].strip() or "manual recovery")
        return "resume-confirm" if "error" not in out else f"refused: {out['error']}"
    if lower.startswith("/resume"):
        out = resume("telegram_resume", reason=text[len("/resume"):].strip(),
                     observed_seq=observed_seq, sent_at=sent_at)
        return "resume" if "error" not in out else f"refused: {out['error']}"
    return None


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

    # Loop guard, panic sequence and flag, under send_gate() (see _raise_flag)
    action = _raise_flag()

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
    observed_seq: int | None = None,
    sent_at: float | None = None,
) -> dict[str, Any]:
    """Disengage the kill switch, unless a newer panic has been recorded.

    If escalation lock is active, requires `confirmed=True` AND `reason`
    to be non-empty (mirrors `/resume-confirm <reason>` semantics). Every
    caller passes `observed_seq`, the panic_seq() it saw when it decided to
    resume; the check and the clear are one step under send_gate().
    """
    action, locked = _clear_flag(confirmed=confirmed, reason=reason,
                                 observed_seq=observed_seq, sent_at=sent_at)
    if action == "escalation_lock_active":
        return {"error": action, "fix": "delete .harness/swarm/kill_switch.flag manually AND "
                                        "call resume(source, reason='<why>', confirmed=True)"}
    if action == "newer_panic":
        log.warning("kill-switch resume by %s REFUSED: a newer panic was recorded", source)
        return {"error": action, "fix": "re-send the resume after checking why it panicked"}

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


__all__ = ["handle_command", "is_active", "is_locked", "panic_count_last_hour",
           "panic_seq", "resume", "send_gate", "trigger"]
