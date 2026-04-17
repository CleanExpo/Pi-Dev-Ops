#!/usr/bin/env python3
"""
process_ideas_inbox.py — RA-1102 — drain the Telegram /idea inbox into Linear.

Walks `.harness/ideas-from-phone/*.jsonl`, for each unprocessed entry creates
a Linear ticket in the Pi-Dev-Ops project (default triage queue), then marks
the entry processed=true so the next run skips it.

Designed to run as a daily GitHub Actions cron (always-on path per
CLAUDE.md). Linear API call is idempotent in practice because the JSONL
file holds the canonical "processed" flag — re-runs of unprocessed entries
double-create only if a Linear API call succeeded but the JSONL write
failed (rare).

Future v2 enhancements (out of scope today):
- Detect URLs in idea text, fetch via Perplexity, summarise, attach to ticket
- Heuristic project routing (keyword match → CARSI / Synthex / etc projects)
- Senior PM agent (Opus 4.7 per RA-1099) classifies intent + suggests phase
- Auto-add to next-board-meeting agenda for the routed project

Exit codes:
    0 — at least one idea processed (or no unprocessed ideas to start with)
    1 — Linear API failure on at least one idea (re-runnable)
    2 — fatal config error (no LINEAR_API_KEY etc.)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
INBOX_DIR    = PROJECT_ROOT / ".harness" / "ideas-from-phone"

LINEAR_API   = "https://api.linear.app/graphql"
# Pi-Dev-Ops project — default triage destination (per CLAUDE.md)
DEFAULT_TEAM_ID    = "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673"  # RestoreAssist team
DEFAULT_PROJECT_ID = "f45212be-3259-4bfb-89b1-54c122c939a7"  # Pi - Dev - Ops project


# ── Linear client ──────────────────────────────────────────────────────────
def linear_create_issue(api_key: str, title: str, description: str) -> Optional[str]:
    """Create a Linear issue. Returns the issue identifier (e.g. RA-1234) or None."""
    query = """
    mutation IssueCreate($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success
        issue { id identifier title }
      }
    }
    """
    variables = {
        "input": {
            "teamId":      DEFAULT_TEAM_ID,
            "projectId":   DEFAULT_PROJECT_ID,
            "title":       title[:250],  # Linear caps title length
            "description": description,
            # Priority 0=None, 1=Urgent, 2=High, 3=Normal, 4=Low. Triage default = Normal.
            "priority":    3,
        }
    }
    payload = json.dumps({"query": query, "variables": variables}).encode()

    req = urllib.request.Request(
        LINEAR_API,
        data=payload,
        headers={
            "Authorization": api_key,
            "Content-Type":  "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        if "errors" in data:
            print(f"[error] Linear API errors: {data['errors']}", file=sys.stderr)
            return None
        result = data.get("data", {}).get("issueCreate", {}) or {}
        if result.get("success"):
            issue = result.get("issue") or {}
            return issue.get("identifier")
        return None
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        print(f"[error] Linear API call failed: {exc}", file=sys.stderr)
        return None


# ── Inbox processing ───────────────────────────────────────────────────────
def _build_ticket(idea: dict) -> tuple[str, str]:
    """Return (title, markdown_description) for a Linear ticket from an idea record."""
    text = (idea.get("text") or "").strip()
    user_name = idea.get("user_name", "unknown")
    ts = idea.get("ts", "")

    # First sentence (or first 80 chars) becomes the title
    first_sentence = text.split(".")[0].strip() if text else "Untitled idea"
    title = f"💡 [Idea] {first_sentence[:140]}"

    body_parts = [
        f"**Captured via Telegram /idea** · {user_name} · {ts}",
        "",
        text,
    ]

    # Surface URLs the user included so the reviewer sees the source quickly
    urls = [w for w in text.split() if w.startswith(("http://", "https://"))]
    if urls:
        body_parts.append("")
        body_parts.append("**Sources referenced:**")
        for url in urls:
            body_parts.append(f"- {url}")

    body_parts.append("")
    body_parts.append("---")
    body_parts.append(
        "_Auto-imported from `.harness/ideas-from-phone/` by `process_ideas_inbox.py`. "
        "Please triage: route to the correct project, set priority, add labels, then "
        "either schedule into the next board meeting agenda or close as duplicate._"
    )

    return title, "\n".join(body_parts)


def process_file(path: Path, api_key: str, *, dry_run: bool) -> tuple[int, int, int]:
    """Process one daily JSONL file. Returns (already_done, created, failed)."""
    already_done = created = failed = 0
    if not path.is_file():
        return (0, 0, 0)

    lines: list[dict] = []
    with path.open() as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                print(f"[warn] {path.name}: skipping malformed line: {exc}", file=sys.stderr)

    for idea in lines:
        if idea.get("processed"):
            already_done += 1
            continue

        title, body = _build_ticket(idea)
        if dry_run:
            print(f"[dry-run] would create: {title}")
            idea["processed"] = True
            idea["linear_identifier"] = "dry-run"
            created += 1
            continue

        identifier = linear_create_issue(api_key, title, body)
        if identifier:
            idea["processed"] = True
            idea["linear_identifier"] = identifier
            idea["processed_at"] = datetime.now(timezone.utc).isoformat()
            created += 1
            print(f"[ok] {idea.get('user_name', '?')}: {title[:60]} → {identifier}")
        else:
            failed += 1
            print(f"[fail] {title[:80]}", file=sys.stderr)

    # Re-write the file atomically — same tmp+replace pattern used elsewhere in repo
    if created and not dry_run:
        tmp = path.with_suffix(".jsonl.tmp")
        with tmp.open("w") as f:
            for line in lines:
                f.write(json.dumps(line) + "\n")
        tmp.replace(path)

    return (already_done, created, failed)


def main() -> int:
    if not INBOX_DIR.is_dir():
        print(f"[info] No inbox at {INBOX_DIR} — nothing to process.")
        return 0

    dry_run = os.environ.get("IDEAS_INBOX_DRY_RUN", "0") == "1"

    api_key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not api_key and not dry_run:
        print("[fatal] LINEAR_API_KEY env var not set", file=sys.stderr)
        return 2

    files = sorted(INBOX_DIR.glob("*.jsonl"))
    if not files:
        print(f"[info] No idea files in {INBOX_DIR}.")
        return 0

    total_done = total_created = total_failed = 0
    for f in files:
        d, c, fl = process_file(f, api_key, dry_run=dry_run)
        total_done += d
        total_created += c
        total_failed += fl
        if c or fl:
            print(f"[summary] {f.name}: already_done={d} created={c} failed={fl}")

    print()
    print(f"=== Total: already_done={total_done} created={total_created} failed={total_failed} ===")
    return 1 if total_failed else 0


if __name__ == "__main__":
    sys.exit(main())
