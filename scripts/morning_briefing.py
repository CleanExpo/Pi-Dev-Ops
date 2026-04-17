#!/usr/bin/env python3
"""
morning_briefing.py — 7am daily briefing sent to Telegram.

Compiles overnight Pi-CEO activity into a concise brief and pushes it to
Phill's Telegram via piceoagent_bot.

Sections:
  1. Open Linear tickets (Urgent / High priority, not Done)
  2. Overnight Pi-CEO sessions (last 12h)
  3. Latest ZTE score
  4. Any open PRs awaiting merge
  5. Monitor digest (last entry)

Usage:
    python3 scripts/morning_briefing.py

Environment (required — read from telegram-bot/.env or process env):
    TELEGRAM_BOT_TOKEN
    ALLOWED_USERS or TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Repo root (scripts/ is one level down)
REPO_ROOT = Path(__file__).resolve().parent.parent


def _read_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _section(title: str, body: str) -> str:
    return f"*{title}*\n{body}\n"


def _open_sessions_last_12h() -> str:
    sessions_dir = REPO_ROOT / "app" / "workspaces"
    if not sessions_dir.exists():
        return "No workspace data."

    cutoff = datetime.now(timezone.utc) - timedelta(hours=12)
    summaries = []
    for meta_file in sorted(sessions_dir.glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
        meta = _read_json(meta_file)
        if not meta:
            continue
        started = meta.get("started_at", "")
        try:
            ts = datetime.fromisoformat(started.replace("Z", "+00:00"))
        except Exception:
            continue
        if ts < cutoff:
            continue
        repo = meta.get("repo", "?")
        status = meta.get("status", "?")
        sid = meta.get("session_id", "?")[:8]
        score = meta.get("eval_score")
        score_str = f" ({score}/10)" if score else ""
        summaries.append(f"  • {sid} [{status}]{score_str} — {repo}")

    return "\n".join(summaries) if summaries else "No sessions in last 12h."


def _zte_score() -> str:
    summary_path = REPO_ROOT / ".harness" / "executive-summary.md"
    if not summary_path.exists():
        return "No ZTE data."
    for line in summary_path.read_text().splitlines():
        if "ZTE" in line and "/" in line:
            return line.strip().lstrip("#").strip()
    return "ZTE data not found in executive-summary.md"


def _monitor_digest() -> str:
    digest_dir = REPO_ROOT / ".harness" / "monitor-digests"
    if not digest_dir.exists():
        return "No monitor digest."
    digests = sorted(digest_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not digests:
        return "No monitor digest found."
    latest = digests[0]
    lines = latest.read_text().splitlines()
    # Return first 5 non-empty lines as summary
    preview = [l.strip() for l in lines if l.strip()][:5]
    return "\n".join(f"  {l}" for l in preview) + f"\n  (from {latest.name})"


def _open_prs() -> str:
    sprint_path = REPO_ROOT / ".harness" / "sprint_plan.md"
    if not sprint_path.exists():
        return "No sprint plan found."
    lines = sprint_path.read_text().splitlines()
    prs = [l.strip() for l in lines if "PR #" in l and ("open" in l.lower() or "await" in l.lower() or "review" in l.lower())]
    return "\n".join(f"  {p}" for p in prs[:8]) if prs else "No open PRs found in sprint plan."


def build_brief() -> str:
    now = datetime.now().strftime("%A %-d %B %Y, %-I:%M %p")
    parts = [
        f"🌅 *Pi-CEO Morning Brief*\n_{now}_\n",
        _section("ZTE Score", f"  {_zte_score()}"),
        _section("Overnight Sessions (last 12h)", _open_sessions_last_12h()),
        _section("Open PRs Awaiting Merge", _open_prs()),
        _section("Monitor Digest", _monitor_digest()),
    ]
    return "\n".join(parts)


def main() -> int:
    brief = build_brief()

    # Import send_telegram from this repo
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from scripts.send_telegram import send_telegram
    except ImportError:
        print("ERROR: could not import send_telegram", file=sys.stderr)
        return 1

    try:
        ids = send_telegram(brief, parse_mode="Markdown")
        print(f"Morning brief sent. Message IDs: {ids}")
        return 0
    except Exception as exc:
        print(f"Failed to send brief: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
