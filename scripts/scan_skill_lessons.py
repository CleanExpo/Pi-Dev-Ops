"""
scan_skill_lessons.py — Threshold-scan job for skill-process self-improvement (RA-continuous-moa §6.2)

Reads .harness/lessons.jsonl, filters entries carrying `applies_to_skill`,
groups by skill name, and flags any skill whose grouped entries within the
last `window_days` days reach `min_count`. Mirrors scripts/analyse_lessons.py's
load/cluster/threshold shape, applied to skill-process lessons instead of
domain-category lessons.

Usage:
    python scripts/scan_skill_lessons.py [--min-count N] [--window-days N] [--dry-run]

Not scheduled by this script — the orchestrator (scripts/skill_self_update.py)
calls find_flagged_skills() directly within a session-bound loop, per the
design's "no standing cron" constraint (design spec §2, §3).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root is on sys.path so scripts.* imports work
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pi-ceo.scan-skill-lessons")

_HARNESS = _ROOT / ".harness"
_LESSONS_FILE = _HARNESS / "lessons.jsonl"

_DEFAULT_MIN_COUNT = 3
_DEFAULT_WINDOW_DAYS = 30


# ─── lesson loading ────────────────────────────────────────────────────────────


def load_skill_lessons(path: Path) -> list[dict]:
    """Load lessons.jsonl entries that carry a non-empty `applies_to_skill` field."""
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
            except json.JSONDecodeError:
                continue
            if entry.get("applies_to_skill"):
                lessons.append(entry)
    log.info("Loaded %d skill-process lessons", len(lessons))
    return lessons


# ─── grouping ──────────────────────────────────────────────────────────────────


def group_by_skill(lessons: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for entry in lessons:
        groups[entry["applies_to_skill"]].append(entry)
    return dict(groups)


# ─── threshold scan ────────────────────────────────────────────────────────────


def _within_window(entry: dict, window_days: int) -> bool:
    ts_raw = entry.get("ts", "")
    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    return ts >= cutoff


def find_flagged_skills(
    groups: dict[str, list[dict]],
    min_count: int = _DEFAULT_MIN_COUNT,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> dict[str, list[dict]]:
    """Return {skill_name: [entries]} for every skill whose entries within
    `window_days` reach `min_count`. Only the in-window entries are returned.
    """
    flagged: dict[str, list[dict]] = {}
    for skill, entries in groups.items():
        recent = [e for e in entries if _within_window(e, window_days)]
        if len(recent) >= min_count:
            flagged[skill] = recent
    return flagged


def main() -> None:
    parser = argparse.ArgumentParser(description="Skill-process lesson threshold scan")
    parser.add_argument("--min-count", type=int, default=_DEFAULT_MIN_COUNT, help="Min lesson count to flag a skill (default 3)")
    parser.add_argument("--window-days", type=int, default=_DEFAULT_WINDOW_DAYS, help="Recency window in days (default 30)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lessons = load_skill_lessons(_LESSONS_FILE)
    groups = group_by_skill(lessons)
    flagged = find_flagged_skills(groups, min_count=args.min_count, window_days=args.window_days)

    if not flagged:
        log.info("No skills flagged (min_count=%d, window_days=%d)", args.min_count, args.window_days)
        sys.exit(0)

    for skill, entries in flagged.items():
        log.info("FLAGGED: %s — %d lessons in last %d days", skill, len(entries), args.window_days)

    if args.dry_run:
        log.info("[DRY RUN] Would hand off %d flagged skill(s) to draft_skill_diff.py", len(flagged))


if __name__ == "__main__":
    main()
