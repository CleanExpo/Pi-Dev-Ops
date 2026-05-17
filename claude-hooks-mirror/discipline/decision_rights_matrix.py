"""UserPromptSubmit-hook: inject Decision-Rights Matrix + last-turn
violation summary into controller context.

Per Pi-CEO Board directive 2026-05-15 (Supabase board_directives id
6298d52f-a1c9-49bb-9180-0c1a48b9cd96). Layer 1+L2-feedback of the
four-layer enforcement loop: at every user prompt, write to stdout a
system context block the controller reads BEFORE generating its
response. Includes:

  1. The non-negotiable Decision-Rights Matrix (what the controller
     OWNS, ESCALATES, NEVER bounces to Phill).
  2. A summary of the last turn's violations from controller-
     violations.jsonl — so the controller sees its own recent failure
     mode at the top of every turn, not just on memory load.

Stdlib only. Output goes to stdout, prefixed with the additionalContext
schema Claude Code accepts.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

LOG_PATH = Path.home() / "Pi-CEO" / ".harness" / "swarm" / "controller-violations.jsonl"
PENDING_REWRITE_PATH = Path.home() / "Pi-CEO" / ".harness" / "swarm" / "pending-rewrite.json"
WINDOW_HOURS = 24


DRM = """## Decision-Rights Matrix (Pi-CEO Board directive 2026-05-15)

You OWN these decisions — make the call, do not ask Phill:
  - Which substrate to use (Claude / OpenAI Codex / Artlist / Hyperframes / Remotion etc.) within constraints already set by the Board
  - Which file/path layout to use within existing repos
  - Which prompt template / model to use for a known-class task
  - Whether to commit a non-destructive local change (always commit; never ask "should I commit?")
  - Whether to run a smoke test (always run when verifiable; never ask "should I verify?")
  - Whether to update wiki / memory after a learning (always update; never ask)
  - Whether to push a branch with completed work (push; never ask "should I push?")
  - Whether to draft an email/document (draft it; surface for Send, don't ask whether to draft)
  - Sequencing of independent next-steps when one is obviously highest-leverage

You ESCALATE to Board (not to Phill directly) for:
  - Strategic substrate changes (e.g. migrate Anthropic primary, drop a portfolio business)
  - Spend decisions above $1k
  - Decisions that violate a locked feedback memory (only if there's a genuine new constraint that contradicts it)
  - When two locked decisions appear to contradict and the resolution requires founder context

You NEVER bounce to Phill:
  - "Want me to also...", "Should I...", "Would you like me to...", "Do you want me to..." — these are forbidden tokens; if you find yourself typing them, the answer is YES, do the thing
  - Multi-option prompts ("Option A / B / C — which?") without an explicit default recommendation
  - "Want me to verify?" — always verify
  - "Want me to commit?" — always commit local non-destructive changes
  - Decisions Phill already gave a default for via a feedback memory (read the memory; honour it; only escalate if there's a genuine novel exception)

You also MAY NOT:
  - Write trailing summaries Phill didn't ask for
  - Add status tables when one sentence would do
  - Narrate your own thinking when output text is the only thing the user sees
  - Skip TaskCreate/TaskUpdate when you start/finish work — the trail matters
"""


def _recent_violations() -> list[dict]:
    """Return violations from the last WINDOW_HOURS, latest first."""
    if not LOG_PATH.exists():
        return []
    cutoff = time.time() - WINDOW_HOURS * 3600
    out = []
    try:
        for line in LOG_PATH.read_text().splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = rec.get("ts", "")
            try:
                t = time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
            except (ValueError, TypeError):
                continue
            if t >= cutoff:
                out.append(rec)
    except OSError:
        return []
    return out[-5:]  # last 5 max


def _violation_summary() -> str:
    recs = _recent_violations()
    if not recs:
        return ""
    lines = ["", "## Last-turn violation summary (you, last 24h):"]
    for r in recs:
        patterns = ", ".join(v["pattern"] for v in r.get("violations", []))
        lines.append(f"  - {r.get('ts', '?')} → {patterns}")
    lines.append("")
    lines.append("**Rewrite expectation:** if a forbidden token (want-me-to / should-i / would-you-like / do-you-want / shall-i / options-without-default) appears in your draft response, REWRITE before emitting. Make the call, do the thing.")
    return "\n".join(lines)


def _pending_rewrite(current_session_id: str | None = None) -> str:
    """If the L6 quality gate flagged the previous emit as FAIL, inject
    the verdict so the controller rewrites this turn instead of moving on.

    Filters by session_id to prevent cross-session pollution — pending
    rewrites from one Claude Code session don't leak into another."""
    if not PENDING_REWRITE_PATH.exists():
        return ""
    try:
        pending = json.loads(PENDING_REWRITE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    pending_sid = pending.get("session_id")
    # Skip cross-session pending: belongs to a different live session — leave it for that session
    if current_session_id and pending_sid and pending_sid != current_session_id:
        return ""
    # Consume the pending file — one rewrite per gate-flag for THIS session
    try:
        PENDING_REWRITE_PATH.unlink()
    except OSError:
        pass
    verdicts = pending.get("verdicts", [])
    veto_by = pending.get("veto_by", [])
    if not verdicts:
        return ""
    lines = ["", "## L6 QUALITY GATE: previous emit FAILED — REWRITE REQUIRED",
             "",
             f"Vetoed by: {', '.join(veto_by) if veto_by else '?'}",
             "",
             "Reviewer verdicts:"]
    for v in verdicts:
        lines.append(f"  - **{v.get('reviewer', '?')}** [{v.get('verdict', '?')}, {v.get('confidence', '?')}]: {v.get('reason', '?')}")
    lines.append("")
    lines.append("**Action required THIS turn:** rewrite the previous response addressing every NO verdict above. Do not move on to the next task until the rewrite is delivered. If you disagree with a NO verdict, state why explicitly with cited evidence — silent dismissal counts as a discipline violation.")
    return "\n".join(lines)


def _current_session_id() -> str | None:
    """Read the current session_id from the hook's stdin (Claude Code passes
    session metadata on UserPromptSubmit). Returns None if unavailable."""
    if sys.stdin.isatty():
        return None
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return None
        data = json.loads(raw)
        return data.get("session_id")
    except (OSError, json.JSONDecodeError):
        return None


def main() -> int:
    # Claude Code reads stdout JSON on UserPromptSubmit hooks
    sid = _current_session_id()
    additional = DRM + _violation_summary() + _pending_rewrite(sid)
    out = {"additionalContext": additional}
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
