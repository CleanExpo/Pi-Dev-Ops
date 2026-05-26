"""Terminal Orchestrator T1 — observer (read-only).

Public surface (the ONLY functions a swarm bot or operator CLI should touch):

    list()                              -> dict snapshot of all sessions
    status(session=None)                -> health snapshot with redacted output
    tail(session, window=None, pane=None, lines=100) -> redacted pane capture

All output passes through swarm.tmux_validator.redact_secrets BEFORE being
returned to caller OR written to the audit ledger (single redaction pass).

Pane addressing uses libtmux's stable `Pane.id` (`%N`), never the volatile
display index. The Hermes-protected pane snapshot lives at
`.harness/tmux-protected-panes.json` — written by `snapshot_hermes_panes()`
at startup; consumed by T2+ enforcement (T1 only writes, doesn't enforce).

CLI: `python3 -m swarm.tmux_observer {list|status|tail} [args]`
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from swarm import tmux_audit
from swarm.tmux_validator import redact_secrets

# Lazy import — libtmux is optional at test time when stubs are used
try:
    import libtmux  # type: ignore
    _LIBTMUX_AVAILABLE = True
except ImportError:  # pragma: no cover
    libtmux = None  # type: ignore
    _LIBTMUX_AVAILABLE = False


# ---------------------------------------------------------------------------
# Module config
# ---------------------------------------------------------------------------

DEFAULT_SOCKET_NAME: str | None = None  # None = default socket
MAX_TAIL_LINES = 4096
DEFAULT_TAIL_LINES = 100
PROTECTED_PANES_FILE = Path(os.environ.get(
    "HERMES_PROTECTED_PANES_FILE",
    str(Path.home() / "Pi-CEO" / ".harness" / "tmux-protected-panes.json"),
))
HERMES_PID_FILE = Path(os.environ.get(
    "HERMES_GATEWAY_PID",
    str(Path.home() / ".hermes" / "gateway.pid"),
))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_server(socket_name: str | None = None):
    """Return a libtmux Server. Tests pass their own."""
    if not _LIBTMUX_AVAILABLE:
        raise RuntimeError("libtmux not installed; add `libtmux>=0.31` to pyproject")
    sock = socket_name if socket_name is not None else DEFAULT_SOCKET_NAME
    if sock is not None:
        return libtmux.Server(socket_name=sock)
    return libtmux.Server()


def _pane_snapshot(pane) -> dict:
    """Extract the stable pane fields we care about."""
    return {
        "id": pane.id,                          # %N — STABLE
        "index": int(pane.index) if pane.index is not None else None,
        "pid": int(pane.pid) if pane.pid else 0,
        "current_command": pane.pane_current_command or "",
        "current_path": pane.pane_current_path or "",
        "is_active": pane.pane_active == "1",
        "is_dead": pane.pane_dead == "1",
        "history_size": int(pane.history_size) if pane.history_size else 0,
    }


def _window_snapshot(window) -> dict:
    return {
        "index": int(window.window_index) if window.window_index else 0,
        "name": window.window_name or "",
        "panes": [_pane_snapshot(p) for p in window.panes],
    }


def _session_snapshot(session) -> dict:
    return {
        "name": session.name,
        "id": session.session_id,
        "windows": [_window_snapshot(w) for w in session.windows],
        "attached": session.session_attached == "1" if session.session_attached else False,
        "created_at": session.session_created or "",
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_hermes_pane_id(server) -> str | None:
    """Find the pane_id whose process tree contains the Hermes gateway pid."""
    if not HERMES_PID_FILE.exists():
        return None
    try:
        hermes_pid = int(HERMES_PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None
    # Walk every pane; check whether the pane's process tree includes hermes_pid
    for session in server.sessions:
        for window in session.windows:
            for pane in window.panes:
                pane_pid = int(pane.pid) if pane.pid else 0
                if pane_pid and _pid_in_tree(hermes_pid, pane_pid):
                    return pane.id
    return None


def _pid_in_tree(target_pid: int, root_pid: int) -> bool:
    """True if target_pid descends from root_pid (or equals it)."""
    if target_pid == root_pid:
        return True
    try:
        result = subprocess.run(
            ["pgrep", "-P", str(root_pid)],
            capture_output=True, timeout=2, text=True, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    if result.returncode != 0:
        return False
    for line in result.stdout.split():
        try:
            child = int(line)
        except ValueError:
            continue
        if _pid_in_tree(target_pid, child):
            return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_sessions(*, server=None, socket_name: str | None = None) -> dict:
    """Return a structured snapshot of all sessions/windows/panes.

    Note: avoid naming conflict with builtin `list` — caller-facing CLI
    subcommand is still `list` (see main()).
    """
    server = server or _get_server(socket_name=socket_name)
    sessions = [_session_snapshot(s) for s in server.sessions]
    result = {
        "sessions": sessions,
        "captured_at": _now_iso(),
    }
    audit_id = tmux_audit.append({
        "actor": _resolve_actor(),
        "command": "tmux:list",
        "args": {},
        "policy_level": "L1",
        "result": "ok",
        "session_count": len(sessions),
        "pane_count": sum(len(w["panes"]) for s in sessions for w in s["windows"]),
    })
    result["audit_id"] = audit_id
    return result


def status(session: str | None = None, *, server=None, socket_name: str | None = None) -> dict:
    """Return a per-pane health snapshot with redacted last-20-lines output."""
    server = server or _get_server(socket_name=socket_name)
    sessions_data = []
    for s in server.sessions:
        if session is not None and s.name != session:
            continue
        s_snap = _session_snapshot(s)
        for w in s_snap["windows"]:
            for p in w["panes"]:
                health = "healthy"
                if p["is_dead"] or p["pid"] == 0:
                    health = "dead"
                elif not p["current_command"]:
                    health = "stale"
                p["health"] = health
                # Last 20 lines, redacted
                tail_result = _capture_pane_lines(server, p["id"], lines=20)
                p["last_lines_redacted"] = tail_result["text"]
                p["secret_redactions"] = tail_result["secret_redactions"]
        sessions_data.append(s_snap)
    result = {
        "sessions": sessions_data,
        "captured_at": _now_iso(),
    }
    audit_id = tmux_audit.append({
        "actor": _resolve_actor(),
        "command": "tmux:status",
        "args": {"session": session},
        "policy_level": "L1",
        "result": "ok",
    })
    result["audit_id"] = audit_id
    return result


def tail(
    session: str,
    window: str | None = None,
    pane: int | None = None,
    lines: int = DEFAULT_TAIL_LINES,
    *,
    server=None,
    socket_name: str | None = None,
) -> dict:
    """Capture last N lines of a pane, with redaction applied in ONE pass."""
    lines = min(max(1, lines), MAX_TAIL_LINES)
    server = server or _get_server(socket_name=socket_name)

    # Resolve to pane_id
    pane_id = _resolve_pane_id(server, session, window, pane)
    if pane_id is None:
        raise ValueError(
            f"pane not found: session={session!r}, window={window!r}, pane={pane!r}"
        )

    result = _capture_pane_lines(server, pane_id, lines=lines)
    audit_id = tmux_audit.append({
        "actor": _resolve_actor(),
        "command": "tmux:tail",
        "args": {
            "session": session,
            "window": window,
            "pane": pane,
            "lines": lines,
            "pane_id": pane_id,
        },
        "policy_level": "L1",
        "result": "ok",
        "secret_redactions": result["secret_redactions"],
    })
    return {
        **result,
        "pane_id": pane_id,
        "audit_id": audit_id,
    }


def snapshot_hermes_panes(*, server=None, socket_name: str | None = None) -> dict:
    """Write current Hermes-protected pane_ids to PROTECTED_PANES_FILE."""
    server = server or _get_server(socket_name=socket_name)
    hermes_pane_id = _resolve_hermes_pane_id(server)
    snapshot = {
        "captured_at": _now_iso(),
        "hermes_gateway_pid_file": str(HERMES_PID_FILE),
        "protected_pane_ids": [hermes_pane_id] if hermes_pane_id else [],
    }
    PROTECTED_PANES_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROTECTED_PANES_FILE.write_text(json.dumps(snapshot, indent=2))
    return snapshot


# ---------------------------------------------------------------------------
# Internal: pane resolution + capture
# ---------------------------------------------------------------------------

def _resolve_pane_id(server, session_name: str, window_name: str | None, pane_index: int | None) -> str | None:
    for s in server.sessions:
        if s.name != session_name:
            continue
        for w in s.windows:
            if window_name is not None and w.window_name != window_name:
                continue
            for p in w.panes:
                if pane_index is not None and int(p.index) != pane_index:
                    continue
                return p.id
    return None


def _capture_pane_lines(server, pane_id: str, *, lines: int) -> dict:
    """Use tmux capture-pane to read the pane buffer. Returns redacted text."""
    # libtmux exposes Pane.capture_pane(); to be socket-correct we go through
    # the server's cmd interface so the socket_name is honoured.
    try:
        result = server.cmd("capture-pane", "-p", "-S", f"-{lines}", "-t", pane_id)
        raw_lines = result.stdout if hasattr(result, "stdout") else []
        raw = "\n".join(raw_lines) if isinstance(raw_lines, list) else str(raw_lines)
    except Exception as exc:  # noqa: BLE001 — libtmux raises various; we surface them
        return {
            "text": "",
            "lines_returned": 0,
            "truncated": False,
            "secret_redactions": {},
            "capture_error": str(exc),
        }
    truncated = False
    if raw.count("\n") > lines:
        raw = "\n".join(raw.split("\n")[-lines:])
        truncated = True
    redacted, counts = redact_secrets(raw)
    return {
        "text": redacted,
        "lines_returned": redacted.count("\n") + (1 if redacted else 0),
        "truncated": truncated,
        "secret_redactions": counts,
    }


def _resolve_actor() -> str:
    return os.environ.get("HERMES_TMUX_ACTOR", "operator-cli")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _print_json(d: Any) -> None:
    print(json.dumps(d, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swarm.tmux_observer")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="snapshot all sessions/windows/panes")

    p_status = sub.add_parser("status", help="health rollup with redacted tail")
    p_status.add_argument("--session", default=None)

    p_tail = sub.add_parser("tail", help="capture last N lines of a pane")
    p_tail.add_argument("--session", required=True)
    p_tail.add_argument("--window", default=None)
    p_tail.add_argument("--pane", type=int, default=None)
    p_tail.add_argument("--lines", type=int, default=DEFAULT_TAIL_LINES)

    sub.add_parser("snapshot-hermes", help="write protected pane_ids snapshot file")
    sub.add_parser("ensure-append-only", help="startup: create audit dir + flag")

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    # Ensure audit dir exists before any state-changing call.
    tmux_audit.ensure_append_only()

    if args.cmd == "list":
        _print_json(list_sessions())
        return 0
    if args.cmd == "status":
        _print_json(status(session=args.session))
        return 0
    if args.cmd == "tail":
        _print_json(tail(
            session=args.session, window=args.window,
            pane=args.pane, lines=args.lines,
        ))
        return 0
    if args.cmd == "snapshot-hermes":
        _print_json(snapshot_hermes_panes())
        return 0
    if args.cmd == "ensure-append-only":
        _print_json(tmux_audit.ensure_append_only())
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
