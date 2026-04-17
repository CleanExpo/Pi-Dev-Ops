#!/usr/bin/env python3
"""
supervisor.py — Watches a tmux-hosted Claude Code session and auto-continues
when it goes silent.

Usage:
    supervisor.py --session claude_pc1 [--stall-seconds 30] [--max-nudges 20]

Flow (per RA-1291):
    Claude Code in tmux pane `claude_pc1` goes silent or emits a prose pause
        ↓
    supervisor polls the pane every 5 s, computing a stall signal
        ↓
    When stall > threshold, tail of the pane is piped to a local Ollama
    (mistral) model with a fixed rubric — the model picks one canonical
    nudge from {continue, yes, proceed, skip, abort}
        ↓
    nudge is typed into the pane via `tmux send-keys` + Enter
        ↓
    Claude resumes; the intervention is logged to ~/.pi-ceo/supervisor.jsonl

Kill switch: `touch ~/.pi-ceo/supervisor.stop` — loop exits on next tick.

Free LLM requirement: `ollama serve` must be running locally, with the
`mistral` model pulled (~4 GB). Any decision costs $0 — no API key needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

OLLAMA_URL     = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL   = os.environ.get("OLLAMA_MODEL", "mistral")
LOG_PATH       = Path(os.environ.get("PI_CEO_HOME", Path.home() / ".pi-ceo")) / "supervisor.jsonl"
STOP_FLAG      = Path(os.environ.get("PI_CEO_HOME", Path.home() / ".pi-ceo")) / "supervisor.stop"

POLL_SECONDS   = 5
TAIL_LINES     = 60   # enough context for the LLM to judge, small enough to keep latency low
CANONICAL_NUDGES = {"continue", "yes", "proceed", "skip", "abort"}

DECISION_PROMPT = """You monitor a Claude Code session inside a terminal. The user wants Claude to keep working autonomously. Your ONE job: look at the last 60 lines of terminal output and pick the shortest unblocking nudge.

Rules:
- Respond with EXACTLY ONE of these tokens, nothing else: continue, yes, proceed, skip, abort
- "continue" — Claude looks mid-task and went silent.
- "yes" — Claude asked a yes/no question and the obvious answer is yes.
- "proceed" — Claude is waiting for a permission/confirmation prompt.
- "skip" — the current subtask seems truly stuck; move to the next item.
- "abort" — the session is looping, crashing, or burning tokens with no progress. Rare.

Terminal tail:
<<<
{tail}
>>>

Nudge token:"""


# -----------------------------------------------------------------------------
# tmux helpers
# -----------------------------------------------------------------------------

def tmux_capture(session: str) -> str:
    """Return the current pane contents, -32 rows of scrollback."""
    try:
        out = subprocess.check_output(
            ["tmux", "capture-pane", "-p", "-S", f"-{TAIL_LINES}", "-t", session],
            text=True, timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise SystemExit(f"tmux capture-pane failed: {exc}")
    return out


def tmux_send(session: str, text: str) -> None:
    """Type `text` into the pane then press Enter."""
    subprocess.check_call(
        ["tmux", "send-keys", "-t", session, text, "Enter"],
        timeout=5,
    )


# -----------------------------------------------------------------------------
# Ollama decision layer
# -----------------------------------------------------------------------------

def decide(tail: str) -> str:
    """Ask Ollama which canonical nudge to send. Falls back to 'continue' on error."""
    prompt  = DECISION_PROMPT.format(tail=tail[-4000:])  # clamp prompt size
    payload = json.dumps({
        "model":   OLLAMA_MODEL,
        "prompt":  prompt,
        "stream":  False,
        "options": {"temperature": 0.0, "num_predict": 8},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload, method="POST",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        _log({"action": "decide_error", "error": str(exc)})
        return "continue"  # safest default
    raw = (data.get("response") or "").strip().lower()
    # Keep only the first word, strip trailing punctuation
    token = raw.split()[0].strip(".,!?:;\"'") if raw else "continue"
    return token if token in CANONICAL_NUDGES else "continue"


# -----------------------------------------------------------------------------
# Stall detection
# -----------------------------------------------------------------------------

def snapshot_hash(text: str) -> str:
    return hashlib.sha256(text.encode(errors="replace")).hexdigest()


def is_stalled(session: str, state: dict, stall_seconds: int) -> tuple[bool, str]:
    """Returns (stalled, current_tail)."""
    tail = tmux_capture(session)
    h = snapshot_hash(tail.rstrip())
    now = time.time()
    if state.get("last_hash") != h:
        state["last_hash"]   = h
        state["changed_at"]  = now
        return False, tail
    age = now - state.get("changed_at", now)
    return age >= stall_seconds, tail


# -----------------------------------------------------------------------------
# Log
# -----------------------------------------------------------------------------

def _log(event: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {**event, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# -----------------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session",       required=True, help="tmux session name, e.g. claude_pc1")
    ap.add_argument("--stall-seconds", type=int, default=30)
    ap.add_argument("--max-nudges",    type=int, default=20,
                    help="Global cap — after N nudges per session, escalate instead of nudging.")
    args = ap.parse_args()

    if STOP_FLAG.exists():
        print(f"Stop flag present at {STOP_FLAG} — exiting.", file=sys.stderr)
        return 0

    _log({"action": "start", "session": args.session, "stall_s": args.stall_seconds})
    print(f"Supervisor watching tmux session '{args.session}' (stall={args.stall_seconds}s)",
          file=sys.stderr)

    state: dict   = {}
    nudge_count   = 0
    last_nudge_at = 0.0

    while True:
        if STOP_FLAG.exists():
            _log({"action": "stop_flag_hit"})
            return 0
        try:
            stalled, tail = is_stalled(args.session, state, args.stall_seconds)
        except SystemExit as exc:
            _log({"action": "capture_error", "error": str(exc)})
            time.sleep(POLL_SECONDS)
            continue

        # Debounce: at most one nudge per 15 s regardless of detection
        now = time.time()
        if stalled and (now - last_nudge_at) > 15:
            if nudge_count >= args.max_nudges:
                _log({"action": "cap_hit", "count": nudge_count})
                print(f"Nudge cap {args.max_nudges} reached — escalate manually.", file=sys.stderr)
                return 2
            token = decide(tail)
            try:
                tmux_send(args.session, token)
            except subprocess.SubprocessError as exc:
                _log({"action": "send_error", "error": str(exc)})
            else:
                nudge_count  += 1
                last_nudge_at = now
                _log({"action": "nudge", "token": token, "count": nudge_count,
                      "tail_hash": state["last_hash"][:12]})
                print(f"[nudge #{nudge_count}] sent '{token}'", file=sys.stderr)
            # Reset the "changed_at" so we don't double-nudge before Claude reacts
            state["changed_at"] = now

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
