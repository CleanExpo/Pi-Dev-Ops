"""swarm/gap_detector.py — wiki action queue → Linear tickets.

Runs once per day. Reads action queue tables from wiki pages (any page
with a "## Action queue" section), cross-references against open Linear
tickets to avoid duplicates, files up to GAP_TICKETS_PER_RUN new tickets
for unaddressed items.

Public API:
    run_daily(repo_root) -> GapResult
    should_run(state) -> bool
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path

log = logging.getLogger("swarm.gap_detector")

GAP_TICKETS_PER_RUN = 3          # max new Linear tickets per daily run
GAP_WIKI_PAGES = [               # pages the detector scans for action queues
    "tech-drops-q2-2026.md",
    "operational-priorities-q2-2026.md",
]
STATE_KEY = "last_gap_detect"


@dataclass
class GapResult:
    tickets_filed: list[str] = field(default_factory=list)
    already_covered: list[str] = field(default_factory=list)
    skipped: int = 0
    error: str | None = None


def should_run(state: dict) -> bool:
    """True if gap detection hasn't run today."""
    last = state.get(STATE_KEY)
    if not last:
        return True
    try:
        return date.fromisoformat(last[:10]) < date.today()
    except (ValueError, TypeError):
        return True


def _wiki_dir() -> Path:
    from . import config  # noqa: PLC0415
    return Path(config.BRAIN1_WIKI_DIR)


def _parse_action_items(content: str) -> list[dict]:
    """Extract rows from markdown action-queue tables.

    Looks for tables under ## Action queue headings.
    Returns list of {action, owner, timeline, description}.
    """
    items: list[dict] = []
    in_queue = False
    headers: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()
        if re.match(r'^#{1,3}\s+Action', stripped, re.IGNORECASE):
            in_queue = True
            headers = []
            continue
        if in_queue and re.match(r'^#{1,3}\s', stripped):
            in_queue = False
            continue
        if not in_queue:
            continue

        if stripped.startswith("|") and "---" not in stripped:
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if not headers:
                headers = [c.lower() for c in cols]
            elif len(cols) >= 2:
                row = dict(zip(headers, cols))
                # Extract the action text — first non-# column with real content
                action = (row.get("action") or row.get("build") or
                          row.get("priority") or cols[1] if len(cols) > 1 else "")
                action = re.sub(r'\*+', '', action).strip()
                if action and action != "#":
                    items.append({
                        "action": action,
                        "owner": row.get("owner", row.get("pi-ceo surface", "")),
                        "timeline": row.get("timeline", row.get("phase", "")),
                    })
    return items


def _existing_linear_titles() -> set[str]:
    """Fetch open Linear ticket titles for duplicate detection."""
    try:
        from .margot_tools import _linear_gql  # noqa: PLC0415
        res = _linear_gql(
            """query {
                issues(filter: {state: {type: {in: ["backlog","unstarted","started"]}}},
                       first: 200) {
                    nodes { title }
                }
            }"""
        )
        nodes = (res.get("data") or {}).get("issues", {}).get("nodes", [])
        return {n["title"].lower() for n in nodes if n.get("title")}
    except Exception as exc:  # noqa: BLE001
        log.warning("gap_detector: could not fetch Linear titles (%s) — filing blind", exc)
        return set()


def _title_covered(title: str, existing: set[str], threshold: float = 0.6) -> bool:
    """Fuzzy match: is this title close enough to an existing ticket?"""
    title_words = set(re.findall(r'\w+', title.lower()))
    for existing_title in existing:
        existing_words = set(re.findall(r'\w+', existing_title))
        if not title_words or not existing_words:
            continue
        overlap = len(title_words & existing_words) / len(title_words | existing_words)
        if overlap >= threshold:
            return True
    return False


def run_daily(repo_root: Path | None = None) -> GapResult:
    """Scan wiki action queues and file Linear tickets for unaddressed gaps.

    Called once per day from the orchestrator. Reads GAP_WIKI_PAGES,
    extracts action items, compares against open Linear tickets (fuzzy
    match), and files up to GAP_TICKETS_PER_RUN new tickets. Updates
    state[STATE_KEY] after running.
    """
    from . import config  # noqa: PLC0415
    result = GapResult()
    wdir = _wiki_dir()

    # Collect all action items from configured wiki pages
    all_items: list[dict] = []
    for page_name in GAP_WIKI_PAGES:
        p = wdir / page_name
        if not p.exists():
            log.debug("gap_detector: page %s not found — skipping", page_name)
            continue
        items = _parse_action_items(p.read_text(encoding="utf-8"))
        for item in items:
            item["source_page"] = page_name
        all_items.extend(items)

    if not all_items:
        log.debug("gap_detector: no action items found in wiki pages")
        return result

    existing = _existing_linear_titles()

    filed = 0
    for item in all_items:
        if filed >= GAP_TICKETS_PER_RUN:
            result.skipped += 1
            continue

        action = item["action"]
        if not action or len(action) < 5:
            continue

        title = f"[Gap] {action[:180]}"
        if _title_covered(action, existing):
            result.already_covered.append(action[:80])
            continue

        # File the ticket
        try:
            from .margot_tools import propose_idea  # noqa: PLC0415
            source = item.get("source_page", "wiki")
            owner = item.get("owner", "")
            timeline = item.get("timeline", "")
            description = (
                f"Gap detected by wiki gap_detector from `{source}`.\n\n"
                f"**Action:** {action}\n"
                + (f"**Owner:** {owner}\n" if owner else "")
                + (f"**Timeline:** {timeline}\n" if timeline else "")
                + f"\n---\n_Auto-filed by gap_detector on {date.today().isoformat()}_"
            )
            r = propose_idea(
                title=title,
                description=description,
                priority=3,
                project="Pi - Dev -Ops",
            )
            if r.get("status") == "created":
                result.tickets_filed.append(title)
                existing.add(action.lower())
                filed += 1
                log.info("gap_detector: filed %s", r.get("identifier"))
            else:
                log.warning("gap_detector: filing failed for %r — %s",
                            title[:60], r.get("error"))
        except Exception as exc:  # noqa: BLE001
            log.warning("gap_detector: propose_idea raised (%s)", exc)

    return result


__all__ = ["run_daily", "should_run", "GapResult"]
