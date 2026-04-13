"""
analyse_lessons.py — Self-improvement loop for Pi Dev Ops (RA-552)

Reads .harness/lessons.jsonl, clusters entries by category, identifies
recurring patterns (≥2 entries), writes improvement proposals to
.harness/improvement-proposals/, and optionally creates Linear tickets.

Usage:
    python scripts/analyse_lessons.py [--dry-run] [--min-count N]

Scheduled: weekly, Sunday 16:00 UTC (= 02:00 AEST) via cron-triggers.json.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path so app.server.* imports work
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import app.server.config  # noqa: F401,E402 — triggers dotenv load
from app.server.triage import LinearClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pi-ceo.analyse-lessons")

_HARNESS = _ROOT / ".harness"
_LESSONS_FILE = _HARNESS / "lessons.jsonl"
_PROPOSALS_DIR = _HARNESS / "improvement-proposals"
_CRON_FILE = _HARNESS / "cron-triggers.json"

# Categories that map to skill updates vs CLAUDE.md sections
_SKILL_CATEGORIES = {"security", "architecture", "claude", "deployment"}
_CLAUDE_MD_CATEGORIES = {"persistence", "rate-limit", "gc", "windows", "auth"}

_LINEAR_TEAM_ID = os.environ.get("LINEAR_TEAM_ID", "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673")
_LINEAR_PROJECT_ID = "f45212be-3259-4bfb-89b1-54c122c939a7"  # Pi - Dev -Ops


# ─── lesson loading ────────────────────────────────────────────────────────────


def load_lessons(path: Path) -> list[dict]:
    lessons: list[dict] = []
    if not path.exists():
        log.warning("lessons.jsonl not found at %s", path)
        return lessons
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("category") == "smoke-test":
                    continue
                lessons.append(entry)
            except json.JSONDecodeError:
                pass
    log.info("Loaded %d lessons (smoke-test excluded)", len(lessons))
    return lessons


# ─── clustering ───────────────────────────────────────────────────────────────


def cluster_by_category(lessons: list[dict]) -> dict[str, list[dict]]:
    clusters: dict[str, list[dict]] = defaultdict(list)
    for entry in lessons:
        clusters[entry.get("category", "unknown")].append(entry)
    return dict(clusters)


def find_recurring_patterns(clusters: dict[str, list[dict]], min_count: int = 2) -> dict[str, list[dict]]:
    return {cat: entries for cat, entries in clusters.items() if len(entries) >= min_count}


# ─── proposal generation ──────────────────────────────────────────────────────


def _proposal_type(category: str) -> str:
    if category in _SKILL_CATEGORIES:
        return "skill"
    return "claude_md"


def _severity_emoji(severity: str) -> str:
    return {"warn": "⚠️", "error": "🔴", "info": "ℹ️"}.get(severity, "•")


def build_proposal(category: str, entries: list[dict]) -> str:
    """Generate a markdown proposal document for a recurring lesson category."""
    ptype = _proposal_type(category)
    warn_count = sum(1 for e in entries if e.get("severity") in ("warn", "error"))
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if ptype == "skill":
        target = f"new skill file: `skills/{category.upper()}.md`"
        action = "Create a SKILL.md entry"
    else:
        target = f"CLAUDE.md section: `## {category.replace('-', ' ').title()} Guidelines`"
        action = "Add a CLAUDE.md section"

    lines = [
        f"# Improvement Proposal: {category.replace('-', ' ').title()}",
        "",
        f"**Generated:** {date_str}  ",
        f"**Source:** lessons.jsonl — {len(entries)} entries ({warn_count} warnings)  ",
        f"**Proposed action:** {action}  ",
        f"**Target:** {target}",
        "",
        f"## Recurring Lessons ({len(entries)} occurrences)",
        "",
    ]
    for e in entries:
        emoji = _severity_emoji(e.get("severity", "info"))
        source = e.get("source", "unknown")
        lines.append(f"- {emoji} **[{source}]** {e['lesson']}")

    lines += [
        "",
        "## Proposed Content",
        "",
    ]

    if ptype == "skill":
        lines += [
            f"Add a new skill or expand an existing one covering these {category} patterns:",
            "",
            "```markdown",
            f"# SKILL: {category.replace('-', ' ').title()} Best Practices",
            "",
            "## When to apply",
            f"Whenever code touches {category}-related logic.",
            "",
            "## Rules",
        ]
        for e in entries:
            lines.append(f"- {e['lesson']}")
        lines += [
            "```",
        ]
    else:
        lines += [
            "Add the following section to CLAUDE.md:",
            "",
            "```markdown",
            f"## {category.replace('-', ' ').title()} Guidelines",
            "",
        ]
        for e in entries:
            lines.append(f"- {e['lesson']}")
        lines += [
            "```",
        ]

    lines += [
        "",
        "## Review Required",
        "",
        "This proposal was auto-generated. A human must review and apply it.",
        "Close this Linear ticket when applied or explicitly rejected.",
    ]
    return "\n".join(lines)


# ─── output ──────────────────────────────────────────────────────────────────


def write_proposal(category: str, content: str) -> Path:
    _PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"{category}-{date_str}.md"
    path = _PROPOSALS_DIR / filename
    path.write_text(content)
    log.info("Wrote proposal: %s", path)
    return path


_TERMINAL_STATES = {"done", "cancelled", "duplicate"}


def _has_open_ticket(client: LinearClient, title: str) -> bool:
    """Return True if an open (non-done, non-cancelled) ticket with this exact
    title already exists.  Prevents duplicate tickets when the script fires
    multiple times on the same day."""
    try:
        issues = client.search_issues(team_id=_LINEAR_TEAM_ID, title_contains=title)
        for issue in issues:
            if issue.get("title") != title:
                continue  # containsIgnoreCase can return partial matches
            state_name = (issue.get("state") or {}).get("name", "").lower()
            if state_name not in _TERMINAL_STATES:
                log.info(
                    "Skipping duplicate ticket — open issue %s already exists: %s",
                    issue.get("identifier"), title,
                )
                return True
    except Exception as exc:  # noqa: BLE001
        # Dedup check failure: log and proceed to create rather than silently skip.
        log.warning("Dedup check failed (%s) — proceeding with ticket creation", exc)
    return False


def create_linear_ticket(client: LinearClient, category: str, content: str) -> dict | None:
    title = f"[Self-Improvement] Review {category.replace('-', ' ').title()} lessons pattern"
    if _has_open_ticket(client, title):
        return None
    try:
        issue = client.create_issue(
            team_id=_LINEAR_TEAM_ID,
            title=title,
            description=content,
            priority=3,  # Normal
            project_id=_LINEAR_PROJECT_ID,
        )
        log.info("Created Linear ticket: %s — %s", issue.get("identifier"), title)
        return issue
    except RuntimeError as exc:
        log.error("Failed to create Linear ticket for %s: %s", category, exc)
        return None


# ─── cron registration ────────────────────────────────────────────────────────


def register_cron_trigger() -> None:
    triggers: list[dict] = []
    if _CRON_FILE.exists():
        try:
            triggers = json.loads(_CRON_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            triggers = []

    trigger_id = "analyse-lessons-weekly"
    if any(t["id"] == trigger_id for t in triggers):
        log.info("Cron trigger '%s' already registered", trigger_id)
        return

    triggers.append({
        "id": trigger_id,
        "type": "analyse_lessons",
        "name": "Self-improvement: lesson pattern analyser — Sunday 16:00 UTC (02:00 AEST)",
        "script": "scripts/analyse_lessons.py",
        "weekday": 6,   # Sunday (0=Monday)
        "hour": 16,
        "minute": 0,
        "enabled": True,
        "created_at": int(time.time()),
        "last_fired_at": None,
    })
    _CRON_FILE.write_text(json.dumps(triggers, indent=2))
    log.info("Registered cron trigger: %s", trigger_id)


# ─── main ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Pi Dev Ops self-improvement loop")
    parser.add_argument("--dry-run", action="store_true", help="Skip Linear ticket creation and cron registration")
    parser.add_argument("--min-count", type=int, default=2, help="Min lesson count to trigger a proposal (default 2)")
    args = parser.parse_args()

    lessons = load_lessons(_LESSONS_FILE)
    if not lessons:
        log.error("No lessons found — nothing to analyse")
        sys.exit(1)

    clusters = cluster_by_category(lessons)
    recurring = find_recurring_patterns(clusters, min_count=args.min_count)

    if not recurring:
        log.info("No recurring patterns found with min_count=%d", args.min_count)
        sys.exit(0)

    log.info("Found %d recurring categories: %s", len(recurring), list(recurring))

    api_key = os.environ.get("LINEAR_API_KEY", "")
    client = LinearClient(api_key) if (api_key and not args.dry_run) else None

    proposals_written = 0
    for category, entries in sorted(recurring.items(), key=lambda x: -len(x[1])):
        content = build_proposal(category, entries)
        write_proposal(category, content)
        proposals_written += 1

        if client:
            create_linear_ticket(client, category, content)
        else:
            log.info("[DRY RUN] Would create Linear ticket for category: %s", category)

    if not args.dry_run:
        register_cron_trigger()
    else:
        log.info("[DRY RUN] Would register cron trigger (skipped)")

    log.info("Done. %d proposals written to %s", proposals_written, _PROPOSALS_DIR)


if __name__ == "__main__":
    main()
