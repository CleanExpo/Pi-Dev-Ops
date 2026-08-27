"""Turn a stated goal into draft Linear tickets. Never writes to Linear."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.server.goal_analyze_fields import (
    analysis_overlay,
    as_text,
    flatten_ticket,
    parse_analyze_payload,
)
from app.server.goal_projects import format_brief, get_project
from app.server.goal_ticket import _MIN_TEXT, title_from_goal

from app.server.spec_pipeline.llm import complete

log = logging.getLogger("pi-ceo.goal_analyze")

_MAX_TICKETS = 6
_MAX_TOKENS = 2048
# Stay inside the dashboard proxy window (100s). A 16k completion was still
# running when Vercel returned "Analyze can take up to a minute."
_ANALYZE_BUDGET_S = 70.0
_PROMPT_PATH = Path(__file__).with_name("goal_analyze_prompt.txt")
_SYSTEM = (
    "JSON only. Omit empty keys. One short sentence per field. "
    "Do not invent repositories or file paths."
)
_PLACEHOLDERS = (
    "human-written imperative title",
    "given ... when ... then ...",
    "as a ... i want ... so that ...",
)
CompleteFn = Callable[..., Awaitable[tuple[str, float]]]


def fallback_drafts(goal: str, acceptance: str, limitation: str) -> list[dict[str, str]]:
    """One editable draft when the model does not return tickets."""
    limit = limitation or "Analysis could not complete a grounded split."
    return [
        {
            "title": title_from_goal(goal),
            "goal": goal.strip(),
            "acceptance": acceptance.strip(),
            "context": limit,
            "user_story": "",
            "current_behaviour": "Unknown until the project brief and goal are applied.",
            "expected_behaviour": goal.strip(),
            "technical_requirements": "Describe behaviour from the project brief. Do not invent files.",
            "edge_cases": "Cover empty, error, and permission cases that the audience will hit.",
            "testing": "Add tests that match the acceptance.",
            "dependencies": "None.",
            "rationale": "Single draft because analysis could not complete a grounded split.",
            "ticket_id": "T1",
            "priority": "P0",
            "summary": "",
            "scope": "",
            "user_flow": "",
            "technical_flow": "",
            "examples": "",
            "implementation_notes": "",
            "risks": "",
            "review": "",
            "ui_ux": "",
            "data_state": "",
            "affected_surfaces": "",
            "tasks": "",
            "sub_tasks": "",
            "sub_tasks_json": "",
            "scenarios": "",
            "junior_notes": "",
        }
    ]


def _is_placeholder(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in _PLACEHOLDERS)


def _clean_draft(item: dict[str, Any], goal: str, acceptance: str) -> dict[str, str] | None:
    flat = flatten_ticket(item)
    title = as_text(item.get("title")) or title_from_goal(goal)
    if _is_placeholder(title):
        return None
    ticket_goal = (
        as_text(item.get("goal"))
        or flat["expected_behaviour"]
        or flat["summary"]
    )
    ticket_acc = flat["acceptance"] or as_text(acceptance)
    if _is_placeholder(ticket_goal) or _is_placeholder(ticket_acc):
        return None
    if len(ticket_goal) < _MIN_TEXT or len(ticket_acc) < _MIN_TEXT:
        return None
    out = {
        **flat,
        "title": title[:200],
        "goal": ticket_goal,
        "acceptance": ticket_acc,
    }
    if not out["expected_behaviour"]:
        out["expected_behaviour"] = ticket_goal
    return out


def cleaned_drafts(
    payload: dict[str, Any] | None,
    goal: str,
    acceptance: str,
) -> list[dict[str, str]]:
    raw = (payload or {}).get("tickets")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cleaned = _clean_draft(item, goal, acceptance)
        if cleaned:
            out.append(cleaned)
        if len(out) >= _MAX_TICKETS:
            break
    return out


def drafts_from_payload(
    payload: dict[str, Any] | None,
    goal: str,
    acceptance: str,
    limitation: str = "",
) -> list[dict[str, str]]:
    return cleaned_drafts(payload, goal, acceptance) or fallback_drafts(
        goal, acceptance, limitation
    )


def fallback_overlay(limitation: str, reason: str) -> dict[str, Any]:
    summary = " ".join(part for part in (reason, limitation) if part)
    return {
        "summary": summary,
        "split_reason": (
            "Analysis did not return implementable tickets, so this is one editable "
            "draft from the stated goal rather than an invented split."
        ),
        "goal_analysis": {
            "summary": summary,
            "unknowns": [],
            "risk": "High",
            "repo_limitations": [],
            "overall_risk": "High",
        },
        "user_flow": {},
        "technical_flow": {},
        "implementation_order": [],
        "final_review": {},
    }


def render_analyze_prompt(goal: str, acceptance: str, project: dict[str, str]) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{{GOAL}}", goal.strip())
        .replace("{{ACCEPTANCE}}", acceptance.strip())
        .replace("{{PROJECT}}", format_brief(project))
    )


def validate_analyze(goal: str, acceptance: str, project_id: str) -> list[str]:
    missing: list[str] = []
    if len((goal or "").strip()) < _MIN_TEXT:
        missing.append("goal")
    if len((acceptance or "").strip()) < _MIN_TEXT:
        missing.append("acceptance")
    if not (project_id or "").strip():
        missing.append("project_id")
    return missing


async def analyze_goal(
    goal: str,
    acceptance: str,
    project_id: str,
    *,
    complete_fn: CompleteFn | None = None,
) -> dict[str, Any]:
    """Propose tickets from the project brief. Never calls Linear or GitHub."""
    missing = validate_analyze(goal, acceptance, project_id)
    if missing:
        return {"error": "validation", "fields": missing}
    project = get_project(project_id)
    if not project:
        return {"error": "unknown_project", "project_id": project_id}

    payload: dict[str, Any] | None = None
    fallback = False
    model_reason = ""
    cost = 0.0
    try:
        fn = complete_fn or complete
        text, cost = await asyncio.wait_for(
            fn(
                prompt=render_analyze_prompt(goal, acceptance, project),
                system=_SYSTEM,
                role="goal_analyst",
                max_tokens=_MAX_TOKENS,
            ),
            timeout=_ANALYZE_BUDGET_S,
        )
        payload = parse_analyze_payload(text)
        if payload is None:
            fallback = True
            model_reason = "The model did not return a usable ticket plan."
            log.warning("goal analyze: no usable JSON in model output")
    except TimeoutError:
        fallback = True
        model_reason = (
            "Analysis hit the time budget. Drafts below are from the stated goal."
        )
        log.warning("goal analyze: timed out after %.0fs", _ANALYZE_BUDGET_S)
    except Exception as exc:
        fallback = True
        model_reason = f"The model call failed ({type(exc).__name__})."
        log.warning("goal analyze: model failed: %s", type(exc).__name__)

    tickets = cleaned_drafts(payload, goal, acceptance)
    if not tickets:
        fallback = True
        if not model_reason:
            model_reason = "The model JSON had no implementable tickets."
        tickets = fallback_drafts(goal, acceptance, model_reason)
        overlay = analysis_overlay(payload)
        if not overlay["summary"]:
            overlay = fallback_overlay("", model_reason)
    else:
        overlay = analysis_overlay(payload)
    return {
        "status": "proposed",
        "filed": False,
        "fallback": fallback,
        "code_inspected": False,
        "code_limitation": "",
        "cost_usd": cost,
        "project_id": project["id"],
        "project_title": project["title"],
        "tickets": tickets,
        **overlay,
    }
