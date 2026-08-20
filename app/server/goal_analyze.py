"""Turn a stated goal into draft Linear tickets. Never writes to Linear."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.server.goal_analyze_fields import analysis_overlay, as_text, flatten_ticket
from app.server.goal_repo_context import gather_repo_context
from app.server.goal_ticket import (
    _MIN_TEXT,
    normalize_repo,
    resolve_project,
    title_from_goal,
    validate_goal,
)
from app.server.spec_pipeline.llm import complete, try_parse_json_object

log = logging.getLogger("pi-ceo.goal_analyze")

_MAX_TICKETS = 6
_MAX_TOKENS = 8192
_PROMPT_PATH = Path(__file__).with_name("goal_analyze_prompt.txt")
CompleteFn = Callable[..., Awaitable[tuple[str, float]]]
ContextFn = Callable[[str, str], dict[str, Any]]


def fallback_drafts(goal: str, acceptance: str, limitation: str) -> list[dict[str, str]]:
    """Structured draft that does not claim repo inspection happened."""
    limit = limitation or "Repo/code analysis was unavailable."
    return [
        {
            "title": title_from_goal(goal),
            "goal": goal.strip(),
            "acceptance": acceptance.strip(),
            "context": f"{limit} Confirm current behaviour in the repo before building.",
            "user_story": "",
            "current_behaviour": "Unknown without inspecting the product.",
            "expected_behaviour": goal.strip(),
            "technical_requirements": (
                "Verify pages, APIs, auth, and data in the target repo. "
                "Do not assume new tables or routes exist."
            ),
            "edge_cases": "Cover loading, empty, error, auth, and theme if this is a UI change.",
            "testing": "Add tests that match the acceptance once the real surface is confirmed.",
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
        }
    ]


def _clean_draft(item: dict[str, Any], goal: str, acceptance: str) -> dict[str, str] | None:
    flat = flatten_ticket(item)
    expected = flat["expected_behaviour"]
    ticket_goal = as_text(item.get("goal")) or expected
    ticket_acc = flat["acceptance"]
    if len(ticket_goal) < _MIN_TEXT or len(ticket_acc) < _MIN_TEXT:
        return None
    title = as_text(item.get("title")) or title_from_goal(goal)
    out = {
        **flat,
        "title": title[:200],
        "goal": ticket_goal,
        "acceptance": ticket_acc,
    }
    if not out["expected_behaviour"]:
        out["expected_behaviour"] = ticket_goal
    return out


def drafts_from_payload(
    payload: dict[str, Any] | None,
    goal: str,
    acceptance: str,
    limitation: str = "",
) -> list[dict[str, str]]:
    raw = (payload or {}).get("tickets")
    if not isinstance(raw, list):
        return fallback_drafts(goal, acceptance, limitation)
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cleaned = _clean_draft(item, goal, acceptance)
        if cleaned:
            out.append(cleaned)
        if len(out) >= _MAX_TICKETS:
            break
    return out or fallback_drafts(goal, acceptance, limitation)


def render_analyze_prompt(goal: str, slug: str, acceptance: str, ctx: dict[str, Any]) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    if ctx.get("ok") and ctx.get("excerpt"):
        repo_context = str(ctx["excerpt"])
    else:
        repo_context = (
            "CODE INSPECTION UNAVAILABLE.\n"
            + str(ctx.get("limitation") or "No repo excerpt.")
            + "\nDo not invent file paths. State the limitation in goal_analysis.repo_limitations."
        )
    return (
        template.replace("{{GOAL}}", goal.strip())
        .replace("{{ACCEPTANCE}}", acceptance.strip())
        .replace("{{REPO}}", slug)
        .replace("{{REPO_CONTEXT}}", repo_context)
    )


async def analyze_goal(
    goal: str,
    repo: str,
    acceptance: str,
    *,
    complete_fn: CompleteFn | None = None,
    context_fn: ContextFn | None = None,
) -> dict[str, Any]:
    """Propose tickets. Never calls Linear."""
    missing = validate_goal(goal, repo, acceptance)
    if missing:
        return {"error": "validation", "fields": missing}
    slug = normalize_repo(repo)
    project = resolve_project(slug)
    if not project:
        return {"error": "unknown_repo", "repo": slug}

    ctx = (context_fn or gather_repo_context)(slug, goal)
    inspected = bool(ctx.get("ok"))
    limitation = str(ctx.get("limitation") or "")
    payload: dict[str, Any] | None = None
    fallback = False
    cost = 0.0
    try:
        fn = complete_fn or complete
        text, cost = await fn(
            prompt=render_analyze_prompt(goal, slug, acceptance, ctx),
            system="",
            role="goal_analyst",
            max_tokens=_MAX_TOKENS,
        )
        payload = try_parse_json_object(text)
        if payload is None:
            fallback = True
            log.warning("goal analyze: no JSON in model output")
    except Exception as exc:
        fallback = True
        log.warning("goal analyze: model failed: %s", type(exc).__name__)

    tickets = drafts_from_payload(payload, goal, acceptance, limitation)
    if fallback:
        tickets = fallback_drafts(goal, acceptance, limitation)
    overlay = analysis_overlay(None if fallback else payload)
    if fallback and not overlay["summary"]:
        overlay["summary"] = (
            limitation or "Analysis fell back. Repo inspection was not used as a completed review."
        )
    return {
        "status": "proposed",
        "filed": False,
        "fallback": fallback,
        "code_inspected": inspected and not fallback,
        "code_limitation": "" if (inspected and not fallback) else limitation,
        "cost_usd": cost,
        "repo": slug,
        "project_id": project["project_id"],
        "registry_id": project["registry_id"],
        "tickets": tickets,
        **overlay,
    }
