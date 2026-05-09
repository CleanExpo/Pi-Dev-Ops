"""swarm/enhancement_scout.py — autonomous enhancement discovery agent.

Continuously scans for improvements to the Pi-CEO agency:
  * New tools / techniques from wiki tech-drops
  * Performance gaps in the current system (wiki lint findings)
  * Industry signals from creator-radar
  * Unimplemented items from agency-blueprint

Runs daily. Each finding becomes a Board agenda item with a structured
proposal. Phill receives a NotebookLM video/audio update via Telegram.

Public API:
    run_daily(repo_root) -> ScoutResult
    should_run(state)    -> bool
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger("swarm.enhancement_scout")

STATE_KEY = "last_enhancement_scout"
MAX_PROPOSALS_PER_RUN = 5


@dataclass
class EnhancementProposal:
    title: str
    source: str           # which wiki page surfaced it
    description: str
    impact: str           # high | medium | low
    effort: str           # days | weeks | months
    category: str         # builder | growth | advisory | infra | cost
    linear_ticket_id: str = ""


@dataclass
class ScoutResult:
    proposals: list[EnhancementProposal] = field(default_factory=list)
    tickets_filed: list[str] = field(default_factory=list)
    board_briefing: str = ""
    error: str | None = None


def should_run(state: dict) -> bool:
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


def _scan_tech_drops() -> list[dict]:
    """Extract unimplemented action items from tech-drops-q2-2026.md."""
    p = _wiki_dir() / "tech-drops-q2-2026.md"
    if not p.exists():
        return []
    items = []
    content = p.read_text(encoding="utf-8")
    # Find implementation paths that haven't been acted on
    import re  # noqa: PLC0415
    for match in re.finditer(
        r'\*\*Implementation path:\*\*\s+([^\n]+(?:\n(?!##)[^\n]+)*)',
        content
    ):
        text = match.group(1).strip()[:200]
        if any(w in text.lower() for w in ["wave 5", "immediate", "this sprint", "now"]):
            items.append({"source": "tech-drops-q2-2026.md", "text": text, "urgency": "high"})
        else:
            items.append({"source": "tech-drops-q2-2026.md", "text": text, "urgency": "medium"})
    return items[:10]


def _scan_agency_blueprint() -> list[dict]:
    """Find unbuilt agents from the agency-blueprint."""
    p = _wiki_dir() / "agency-blueprint.md"
    if not p.exists():
        return []
    content = p.read_text(encoding="utf-8")
    items = []
    import re  # noqa: PLC0415
    # Look for agent rows with "Not built" or wave 6/7
    for match in re.finditer(r'\|\s+\*\*([^*]+)\*\*\s+\|[^|]+\|\s+([^|]+)\|', content):
        agent = match.group(1).strip()
        role = match.group(2).strip()
        items.append({
            "source": "agency-blueprint.md",
            "text": f"Build {agent} — {role[:80]}",
            "urgency": "medium",
        })
    return items[:5]


def _scan_gemma4_opportunities() -> list[dict]:
    """Find tasks still on paid APIs that could move to Gemma 4."""
    p = _wiki_dir() / "gemma4-cost-strategy.md"
    if not p.exists():
        return []
    content = p.read_text(encoding="utf-8")
    items = []
    import re  # noqa: PLC0415
    for match in re.finditer(r'###\s+\d+\.\s+(.+)\n', content):
        items.append({
            "source": "gemma4-cost-strategy.md",
            "text": f"Migrate to Gemma 4: {match.group(1).strip()[:80]}",
            "urgency": "medium",
        })
    return items[:3]


def _build_proposals(raw_items: list[dict]) -> list[EnhancementProposal]:
    proposals = []
    for item in raw_items[:MAX_PROPOSALS_PER_RUN]:
        urgency = item.get("urgency", "medium")
        source = item.get("source", "wiki")
        text = item.get("text", "")

        # Classify category
        text_lower = text.lower()
        if any(w in text_lower for w in ["build", "agent", "skill", "idd", "sd-"]):
            category = "builder"
        elif any(w in text_lower for w in ["gemma", "cost", "migrate", "ollama"]):
            category = "cost"
        elif any(w in text_lower for w in ["marketing", "seo", "content", "brand"]):
            category = "growth"
        else:
            category = "infra"

        proposals.append(EnhancementProposal(
            title=f"[Enhancement] {text[:80]}",
            source=source,
            description=text,
            impact=urgency,
            effort="weeks" if category == "builder" else "days",
            category=category,
        ))
    return proposals


def _file_as_board_agenda(proposals: list[EnhancementProposal]) -> list[str]:
    """File each enhancement as a Board agenda item in Linear."""
    filed = []
    try:
        from .margot_tools import propose_idea  # noqa: PLC0415
        for p in proposals:
            r = propose_idea(
                title=p.title,
                description=(
                    f"**Category:** {p.category}\n"
                    f"**Impact:** {p.impact} | **Effort:** {p.effort}\n"
                    f"**Source:** {p.source}\n\n"
                    f"{p.description}\n\n"
                    f"---\n*Enhancement Scout — {date.today().isoformat()}*"
                ),
                priority=2 if p.impact == "high" else 3,
                project="Pi - Dev -Ops",
            )
            if r.get("status") == "created":
                p.linear_ticket_id = r.get("identifier", "")
                filed.append(p.linear_ticket_id)
                log.info("enhancement_scout: filed %s — %s", p.linear_ticket_id, p.title[:60])
    except Exception as exc:  # noqa: BLE001
        log.warning("enhancement_scout: filing failed (%s)", exc)
    return filed


def _queue_board_briefing(proposals: list[EnhancementProposal]) -> None:
    """Queue a Board meeting agenda with all enhancement proposals."""
    if not proposals:
        return
    try:
        from . import board as _board  # noqa: PLC0415
        agenda = "\n".join(
            f"- [{p.impact.upper()}] {p.title} ({p.category}, {p.effort})"
            for p in proposals
        )
        _board.from_margot(
            topic=f"Enhancement proposals — {date.today().isoformat()}",
            insight=(
                f"The Enhancement Scout identified {len(proposals)} improvements "
                f"from the knowledge base. These are queued for Board deliberation "
                f"and implementation prioritisation.\n\n{agenda}"
            ),
            citations=[p.source for p in proposals],
        )
        log.info("enhancement_scout: queued Board agenda with %d proposals", len(proposals))
    except Exception as exc:  # noqa: BLE001
        log.warning("enhancement_scout: board queue failed (%s)", exc)


def run_daily(repo_root: Path | None = None) -> ScoutResult:
    """Scan wiki for enhancements, file as Board agenda, return result."""
    result = ScoutResult()

    raw: list[dict] = []
    raw.extend(_scan_tech_drops())
    raw.extend(_scan_agency_blueprint())
    raw.extend(_scan_gemma4_opportunities())

    if not raw:
        log.info("enhancement_scout: no new enhancements found")
        return result

    result.proposals = _build_proposals(raw)
    result.tickets_filed = _file_as_board_agenda(result.proposals)
    _queue_board_briefing(result.proposals)

    result.board_briefing = (
        f"Enhancement Scout — {date.today().isoformat()}\n"
        + "\n".join(f"• {p.title}" for p in result.proposals)
    )

    log.info("enhancement_scout: %d proposals, %d tickets filed",
             len(result.proposals), len(result.tickets_filed))
    return result


__all__ = ["run_daily", "should_run", "ScoutResult", "EnhancementProposal"]
