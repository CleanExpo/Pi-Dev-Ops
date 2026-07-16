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
import urllib.error
import urllib.request
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
        # app/workspaces/ is gitignored (.gitignore:77) — it is live runtime state on
        # the Railway host and never exists in a CI checkout, which is where this job
        # runs. Reporting "no sessions" here would be indistinguishable from a genuinely
        # quiet night, i.e. it would read as good news while measuring nothing.
        return "  ⚠️ Unavailable — app/workspaces/ is runtime state, absent in CI."

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

    return "\n".join(summaries) if summaries else "  None started in the last 12h."


def _zte_score() -> str:
    summary_path = REPO_ROOT / ".harness" / "executive-summary.md"
    if not summary_path.exists():
        return "  ⚠️ Unavailable — .harness/executive-summary.md not found."
    for line in summary_path.read_text().splitlines():
        if "ZTE" in line and "/" in line:
            # This is a checked-in static file, not a live score. It carries its own
            # "Updated:" stamp; surface that rather than presenting the number as today's.
            return (
                f"  {line.strip().lstrip('#').strip()}\n"
                "  ⚠️ Static file, not a live score — trust the Updated: date above."
            )
    return "  ⚠️ ZTE line not found in executive-summary.md."


def _monitor_digest() -> str:
    digest_dir = REPO_ROOT / ".harness" / "monitor-digests"
    if not digest_dir.exists():
        # Gitignored (.gitignore:112) — runtime state on the host, never in a CI checkout.
        return "  ⚠️ Unavailable — .harness/monitor-digests/ is runtime state, absent in CI."
    digests = sorted(digest_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not digests:
        return "No monitor digest found."
    latest = digests[0]
    lines = latest.read_text().splitlines()
    # Return first 5 non-empty lines as summary
    preview = [l.strip() for l in lines if l.strip()][:5]
    return "\n".join(f"  {l}" for l in preview) + f"\n  (from {latest.name})"


def _open_prs() -> str:
    """Open PRs, from the GitHub API.

    Previously grepped .harness/sprint_plan.md for lines containing "PR #". That file
    is checked in and was last updated 2026-04-16, so this section reported "No open
    PRs found in sprint plan" every morning regardless of how many were actually open
    — a constant that read as good news. Ask GitHub instead.
    """
    repo = os.environ.get("GITHUB_REPOSITORY", "CleanExpo/Pi-Dev-Ops")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        return "  ⚠️ Unavailable — no GITHUB_TOKEN in this job's env."

    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=30",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "pi-ceo-morning-briefing",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            prs = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        # Loud on purpose: a silent failure here is what this fix exists to remove.
        return f"  ⚠️ Unavailable — GitHub API error: {exc}"

    if not prs:
        return "  None open."

    lines = []
    for pr in prs[:8]:
        flag = " [draft]" if pr.get("draft") else ""
        title = (pr.get("title") or "")[:60]
        author = (pr.get("user") or {}).get("login", "?")
        lines.append(f"  • #{pr.get('number')}{flag} — {title} ({author})")
    if len(prs) > 8:
        lines.append(f"  … and {len(prs) - 8} more")
    return "\n".join(lines)


def build_brief() -> str:
    now = datetime.now().strftime("%A %-d %B %Y, %-I:%M %p")
    parts = [
        f"🌅 *Pi-CEO Morning Brief*\n_{now}_\n",
        _section("ZTE Score", _zte_score()),
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
