#!/usr/bin/env python3
"""marathon_heartbeat.py — single-shot status heartbeat to Telegram.

No external dependencies. No LLM tools required. Designed to run from cron or a
scheduled-tasks MCP task as a single `python3` invocation so no permission
prompts can stall the run.

Reads:
  - .harness/monitor-digests/ (newest file)
  - .harness/lessons.jsonl (last 5 lines)
  - pytest exit code

Writes:
  - Nothing to disk. One Telegram message.

Exit codes:
  0 — heartbeat sent
  1 — dry-run (TAO_HEARTBEAT_DRY=1)
  2 — Telegram push failed
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIGEST_DIR = REPO_ROOT / ".harness" / "monitor-digests"
LESSONS_FILE = REPO_ROOT / ".harness" / "lessons.jsonl"
SEND_SCRIPT = REPO_ROOT / "scripts" / "send_telegram.py"


def _latest_digest() -> str:
    if not DIGEST_DIR.exists():
        return "no digest"
    files = sorted(DIGEST_DIR.glob("dryrun-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].name if files else "no digest"


def _portfolio_health() -> str:
    """Extract portfolio health score from newest digest."""
    if not DIGEST_DIR.exists():
        return "unknown"
    files = sorted(DIGEST_DIR.glob("dryrun-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return "unknown"
    try:
        text = files[0].read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            low = line.lower()
            if "portfolio health" in low:
                digits = "".join(c for c in line if c.isdigit() or c == "/")
                if digits:
                    return digits
    except Exception:
        pass
    return "unknown"


def _critical_count() -> int:
    """Count critical findings in newest digest."""
    if not DIGEST_DIR.exists():
        return 0
    files = sorted(DIGEST_DIR.glob("dryrun-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return 0
    try:
        text = files[0].read_text(encoding="utf-8", errors="replace").lower()
        # Look for patterns like "6 critical" or "critical findings: 6"
        import re
        m = re.search(r"(\d+)\s*critical", text)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0


def _last_lesson() -> str:
    if not LESSONS_FILE.exists():
        return "no lessons"
    try:
        lines = LESSONS_FILE.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return "no lessons"
        last = json.loads(lines[-1])
        lesson = last.get("lesson", "")
        return lesson[:120] + ("..." if len(lesson) > 120 else "")
    except Exception as e:
        return f"lesson parse error: {e}"


def _run_tests() -> tuple[int, str]:
    """Run pytest, return (passing_count, status_string)."""
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-q", "--tb=no"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        text = (result.stdout + result.stderr).strip().splitlines()
        # Find the last line with "passed" or "failed"
        for line in reversed(text):
            if "passed" in line or "failed" in line or "error" in line:
                return (result.returncode, line.strip())
        return (result.returncode, "no result line")
    except subprocess.TimeoutExpired:
        return (124, "pytest timeout")
    except Exception as e:
        return (1, f"pytest error: {e}")


def _compose(test_rc: int, test_summary: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
    alert = ""
    if test_rc != 0:
        alert = "ALERT: "

    crit = _critical_count()
    if crit > 0 and not alert:
        alert = f"ALERT ({crit} critical): "

    lines = [
        f"{alert}PI-CEO HEARTBEAT [{ts}]",
        f"Tests: {test_summary}",
        f"Portfolio health: {_portfolio_health()}",
        f"Open critical findings: {crit}",
        f"Latest digest: {_latest_digest()}",
        f"Last lesson: {_last_lesson()}",
        "Marathon continues. Next heartbeat in 3h.",
    ]
    return "\n".join(lines)


def main() -> int:
    test_rc, test_summary = _run_tests()
    message = _compose(test_rc, test_summary)

    if os.environ.get("TAO_HEARTBEAT_DRY", "0") == "1":
        print(message)
        return 1

    if not SEND_SCRIPT.exists():
        print(f"ERROR: {SEND_SCRIPT} missing", file=sys.stderr)
        return 2

    result = subprocess.run(
        ["python3", str(SEND_SCRIPT), message],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"Telegram push failed: {result.stderr}", file=sys.stderr)
        return 2
    print(result.stdout.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
