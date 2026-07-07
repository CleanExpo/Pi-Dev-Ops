"""Terminal Orchestrator T2 — writer (state-changing). Slice 1: `send` (RA-7012).

The write tier of the Terminal Orchestrator. Every state-changing verb routes
`validate_command()` → `audit.append()` → libtmux act, **fail-closed**: a refused
command or an unwritable audit ledger aborts before any tmux side effect.

Autonomy leash (grill Q2, Sketches/09):
  - `send` / `open`  → L2 (auto, validator-gated + audited)
  - `close` / `kill_session` → L3 (human-gated; not in slice 1)

Slice 1 ships `send` only. `open` and the L3 `close` land in later slices.
Public surface: `send()`.
"""
from __future__ import annotations

import re

from swarm import tmux_audit
from swarm.tmux_observer import _get_server, _now_iso
from swarm.tmux_validator import Level, redact_secrets, validate_command

# A session name must be a safe identifier — no shell metacharacters, path
# separators, or tmux-target punctuation that could redirect the operation.
_SAFE_SESSION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

# Autonomy ceiling for a plain send. A command whose validator `level_required`
# exceeds this is refused (escalation is the caller's decision, not the writer's).
SEND_CEILING: Level = "L2"

_LEVEL_ORDER = {"L1": 1, "L2": 2, "L3": 3}


def _exceeds(required: Level, ceiling: Level) -> bool:
    return _LEVEL_ORDER[required] > _LEVEL_ORDER[ceiling]


def send(
    session: str,
    text: str,
    *,
    level: Level = SEND_CEILING,
    enter: bool = True,
    server=None,
    audit_dir=None,
) -> dict:
    """Send `text` to `session`'s active pane, gated + audited. Fail-closed.

    Returns a result dict: {ok, reason, audit_id?, level_required?}. Never raises
    for a policy refusal or a missing session — those are returned as ok=False.
    Only a genuinely unwritable audit ledger aborts (the fail-closed invariant).
    """
    redacted, _ = redact_secrets(text)

    # (1) POLICY GATE — validate before any side effect.
    vr = validate_command(text, level=level)
    if not vr.allowed or _exceeds(vr.level_required, level):
        reason = vr.reason or f"requires {vr.level_required} > ceiling {level}"
        _audit_safe(audit_dir, {
            "verb": "send", "session": session, "text": redacted,
            "result": "refused", "reason": reason,
            "level_required": vr.level_required, "ts": _now_iso(),
        })
        return {"ok": False, "reason": reason, "level_required": vr.level_required}

    # (2) AUDIT THE INTENT — fail-closed: if the ledger can't record it, don't act.
    try:
        audit_id = tmux_audit.append({
            "verb": "send", "session": session, "text": redacted,
            "result": "attempt", "ts": _now_iso(),
        }, audit_dir=audit_dir)
    except tmux_audit.AuditUnwritableError as exc:
        return {"ok": False, "reason": f"audit unwritable — aborted before send: {exc}"}

    # (3) ACT — resolve the pane and send.
    srv = server if server is not None else _get_server()
    sess = next((s for s in srv.sessions if s.name == session), None)
    if sess is None:
        _audit_safe(audit_dir, {
            "verb": "send", "session": session, "text": redacted,
            "result": "no-session", "audit_id": audit_id, "ts": _now_iso(),
        })
        return {"ok": False, "reason": f"session {session!r} not found", "audit_id": audit_id}

    pane = sess.active_pane if hasattr(sess, "active_pane") else sess.attached_pane
    pane.send_keys(text, enter=enter)

    _audit_safe(audit_dir, {
        "verb": "send", "session": session, "text": redacted,
        "result": "sent", "audit_id": audit_id, "ts": _now_iso(),
    })
    return {"ok": True, "reason": "sent", "audit_id": audit_id}


def open_session(
    name: str,
    *,
    level: Level = SEND_CEILING,
    server=None,
    audit_dir=None,
) -> dict:
    """Create a new tmux session `name`, gated + audited. Fail-closed. L2.

    Refuses an unsafe name, a name that fails the command validator, or a name
    that already exists (never clobbers a live session). Returns {ok, session,
    audit_id?, reason}.
    """
    # (1) NAME GATE — a session name is an identifier, not a shell command, so the
    # safe-identifier regex is the correct gate here (validate_command is for the
    # command strings that `send` carries, not for names).
    if not _SAFE_SESSION_NAME.match(name or ""):
        _audit_safe(audit_dir, {"verb": "open", "session": name, "result": "refused",
                                "reason": "unsafe session name", "ts": _now_iso()})
        return {"ok": False, "reason": "unsafe session name"}

    srv = server if server is not None else _get_server()
    if any(s.name == name for s in srv.sessions):
        _audit_safe(audit_dir, {"verb": "open", "session": name, "result": "exists",
                                "ts": _now_iso()})
        return {"ok": False, "reason": f"session {name!r} already exists"}

    # (2) AUDIT THE INTENT — fail-closed.
    try:
        audit_id = tmux_audit.append({"verb": "open", "session": name, "level": level,
                                      "result": "attempt", "ts": _now_iso()},
                                     audit_dir=audit_dir)
    except tmux_audit.AuditUnwritableError as exc:
        return {"ok": False, "reason": f"audit unwritable — aborted before open: {exc}"}

    # (3) ACT.
    srv.new_session(session_name=name, attach=False)
    _audit_safe(audit_dir, {"verb": "open", "session": name, "result": "opened",
                            "audit_id": audit_id, "ts": _now_iso()})
    return {"ok": True, "session": name, "audit_id": audit_id, "reason": "opened"}


def _audit_safe(audit_dir, event: dict) -> None:
    """Best-effort trailing audit (the intent row already made the action durable)."""
    try:
        tmux_audit.append(event, audit_dir=audit_dir)
    except tmux_audit.AuditUnwritableError:
        pass


__all__ = ["send", "open_session", "SEND_CEILING"]
