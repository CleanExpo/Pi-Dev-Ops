"""Plaud Actions — sub-project 2 of 3. Reads ingested wiki/plaud/ pages, extracts
action items via Anthropic Haiku 4.5, files Linear tickets, posts ONE Telegram
digest per cron batch. Spec: docs/superpowers/specs/2026-05-17-plaud-actions-design.md
"""
from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, Optional

# Local import: linear_helpers lives in the same scripts/ directory
sys.path.insert(0, str(Path(__file__).parent))
from linear_helpers import create_linear_issue, TicketRef


log = logging.getLogger("plaud_actions")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MODEL = "claude-haiku-4-5"

PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "action_extraction.md").read_text()

PROJECTS_JSON = Path(__file__).resolve().parent.parent / ".harness" / "projects.json"
DEFAULT_PORTFOLIO_ID = "pi-dev-ops"  # fallback when LLM picks unknown


# ── Dataclasses ────────────────────────────────────────────────────────────

@dataclass
class Action:
    title: str
    description: str
    priority: int = 3  # Linear: 0=None, 1=Urgent, 2=High, 3=Normal, 4=Low


@dataclass
class ActionExtraction:
    portfolio: str
    confidence: float
    reasoning: str
    actions: list[Action] = field(default_factory=list)


@dataclass
class BatchResult:
    plaud_id: str
    title: str
    wiki_path: str
    portfolio: str
    tickets: list[TicketRef] = field(default_factory=list)
    status: str = "ok"  # ok | partial | no_actions | parse_failed | skipped


class LinearRoute(NamedTuple):
    team_id: str
    project_id: str
    status: str  # matched | fallback_unknown | fallback_low_confidence


# ── Portfolio routing ──────────────────────────────────────────────────────

def resolve_linear_route(portfolio: str, *, projects_json_path: Path = PROJECTS_JSON) -> LinearRoute:
    """Look up team_id + project_id for a portfolio. Falls back to pi-dev-ops if
    portfolio is unknown or not in the registry. Raises if the registry itself is
    missing or doesn't contain the pi-dev-ops fallback entry."""
    data = json.loads(projects_json_path.read_text())
    projects = {p["id"]: p for p in data.get("projects", [])}

    if portfolio in projects:
        p = projects[portfolio]
        return LinearRoute(
            team_id=p["linear_team_id"],
            project_id=p["linear_project_id"],
            status="matched",
        )

    default = projects.get(DEFAULT_PORTFOLIO_ID)
    if not default:
        raise RuntimeError(
            f"projects.json missing default portfolio '{DEFAULT_PORTFOLIO_ID}'"
        )
    return LinearRoute(
        team_id=default["linear_team_id"],
        project_id=default["linear_project_id"],
        status="fallback_unknown",
    )
