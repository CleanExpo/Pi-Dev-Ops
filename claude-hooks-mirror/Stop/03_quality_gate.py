"""Stop-hook L6 Tier-1: Haiku-3 minority-veto quality gate.

Per Pi-CEO Board memo 2026-05-15 (Supabase board_directives id
a3c493cc-055f-44ef-b646-28950e1b55ee). Layer 6 of the enforcement
loop. Closes the TPR>96%/TNR<25% TNR gap identified in research
finding Q1.5 by running 3 specialist reviewers in parallel with
minority-veto aggregation.

Mechanism:
  1. Read last assistant emit from transcript
  2. Fork 3 background subprocesses, one per reviewer role
     (qa-lead, brand-guardian, contrarian) via reviewer.py
  3. Each subprocess writes its verdict to reviewer-verdict.jsonl
  4. Subprocess also writes to pending-rewrite.json if its verdict
     was the deciding NO (minority-veto)
  5. The UserPromptSubmit hook (decision_rights_matrix.py) reads
     pending-rewrite.json on the next prompt and injects a REWRITE
     instruction into additionalContext

This hook itself exits in milliseconds (fork-and-forget) — the
reviewers complete async over the next 10-60 seconds while the
user is reading the original emit. By the time the user submits
their next prompt (or autonomous-continue fires), verdicts are
typically ready.

Stdlib only. Default-safe: any unexpected error → silent exit 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SWARM_DIR = Path.home() / "Pi-CEO" / ".harness" / "swarm"
VERDICT_PATH = SWARM_DIR / "reviewer-verdict.jsonl"
PENDING_PATH = SWARM_DIR / "pending-rewrite.json"
REVIEWER_SCRIPT = Path.home() / ".claude" / "hooks" / "discipline" / "reviewer.py"
DRAFT_STAGE_DIR = SWARM_DIR / "drafts"
ROLES = ("qa-lead", "brand-guardian", "contrarian")
TIMEOUT_S = 90
MIN_DRAFT_LEN = 200  # skip gate for trivial emits

SKIP_PHRASES = (
    "brief received. convening the board",
    "holding. research agent",
    "stage 1.5 skipped",
)


def _read_stdin_json() -> dict:
    if sys.stdin.isatty():
        return {}
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _last_assistant_text(transcript_path: str | None) -> str:
    if not transcript_path:
        return ""
    p = Path(transcript_path).expanduser()
    if not p.exists():
        return ""
    last = ""
    try:
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "assistant":
                msg = obj.get("message", {})
                for part in msg.get("content", []):
                    if part.get("type") == "text":
                        last = part.get("text", "")
    except OSError:
        return ""
    return last


def _should_skip(text: str) -> str | None:
    """Return skip reason if gate should NOT fire for this emit, else None."""
    if len(text) < MIN_DRAFT_LEN:
        return f"draft-too-short ({len(text)} < {MIN_DRAFT_LEN})"
    lower = text.strip().lower()
    for phrase in SKIP_PHRASES:
        if phrase in lower[:200]:
            return f"skip-phrase: {phrase}"
    return None


def _stage_draft(draft: str) -> Path:
    DRAFT_STAGE_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"draft-{int(time.time())}-{os.getpid()}.txt"
    path = DRAFT_STAGE_DIR / fname
    path.write_text(draft)
    return path


def _spawn_reviewer(role: str, draft_path: Path, session_id: str) -> None:
    """Fork a background subprocess that runs reviewer.py for this role
    and appends its verdict to reviewer-verdict.jsonl."""
    wrapper = f"""
import json, subprocess, sys, time
from pathlib import Path

DRAFT = Path("{draft_path}").read_text()
SCRIPT = "{REVIEWER_SCRIPT}"
VERDICT = "{VERDICT_PATH}"
ROLE = "{role}"
SESSION = "{session_id}"

started = time.time()
try:
    r = subprocess.run(
        ["/usr/bin/env", "python3", SCRIPT, "--role", ROLE, "--timeout", "{TIMEOUT_S}"],
        input=DRAFT, capture_output=True, text=True, timeout={TIMEOUT_S + 5},
    )
    try:
        v = json.loads(r.stdout)
    except Exception:
        v = {{"reviewer": ROLE, "verdict": "NO", "confidence": "low",
              "reason": "reviewer wrapper json parse failed", "_raw": r.stdout[:300]}}
except Exception as e:
    v = {{"reviewer": ROLE, "verdict": "NO", "confidence": "low",
          "reason": f"reviewer wrapper error: {{type(e).__name__}}"}}

v["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
v["session_id"] = SESSION
v["draft_path"] = "{draft_path}"
v["_elapsed_s"] = round(time.time() - started, 1)

try:
    with open(VERDICT, "a") as f:
        f.write(json.dumps(v) + "\\n")
except Exception:
    pass

# Apply minority-veto by reading recent verdicts for this draft.
try:
    related = []
    for line in open(VERDICT).read().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("draft_path") == "{draft_path}":
            related.append(rec)
    no_high = [x for x in related if x.get("verdict") == "NO" and x.get("confidence") in ("high", "medium")]
    if no_high and len(related) >= 1:
        pending = {{
            "draft_path": "{draft_path}",
            "session_id": SESSION,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "verdicts": related,
            "veto_by": [x["reviewer"] for x in no_high],
        }}
        Path("{PENDING_PATH}").write_text(json.dumps(pending, indent=2))
except Exception:
    pass
"""
    subprocess.Popen(
        ["/usr/bin/env", "python3", "-c", wrapper],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )


def main() -> int:
    try:
        SWARM_DIR.mkdir(parents=True, exist_ok=True)
        session = _read_stdin_json()
        tp = session.get("transcript_path") or os.environ.get("CLAUDE_TRANSCRIPT_PATH")
        text = _last_assistant_text(tp)
        if not text:
            return 0
        skip_reason = _should_skip(text)
        if skip_reason:
            return 0
        draft_path = _stage_draft(text)
        sid = session.get("session_id", "unknown")
        for role in ROLES:
            _spawn_reviewer(role, draft_path, sid)
        return 0
    except Exception:  # noqa: BLE001 — default-safe
        return 0


if __name__ == "__main__":
    sys.exit(main())
