"""Turn a stated goal into draft Linear tickets. Never writes to Linear."""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

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
CompleteFn = Callable[..., Awaitable[tuple[str, float]]]

_SYSTEM = """You are a senior software engineer and a senior product engineer.
Split the goal into the smallest set of Linear tickets that can ship independently.
Keep one ticket when the work is a single atomic change.
Each ticket must be implementable without the others being done first, or must
name its dependency in rationale.
Do not invent a different repo. Do not mention Ready for Pi-Dev or pi-dev:autonomous.
Do not file, create, or claim anything was written to Linear.
Return JSON only:
{
  "summary": "one paragraph",
  "product": "product reading: user outcome, scope, what not to build",
  "engineering": "engineering reading: likely surfaces, risks, sequencing",
  "split_reason": "why 1 ticket vs N",
  "tickets": [
    {
      "title": "short imperative title",
      "goal": "what exists when this ticket is done",
      "acceptance": "how a stranger verifies it is done",
      "rationale": "why this is its own ticket"
    }
  ]
}
At most 6 tickets. Titles <= 80 characters.
"""


def fallback_drafts(goal: str, acceptance: str) -> list[dict[str, str]]:
    """Single ticket from the stated goal — used when the model fails."""
    return [
        {
            "title": title_from_goal(goal),
            "goal": goal.strip(),
            "acceptance": acceptance.strip(),
            "rationale": "Kept as one ticket because analysis was unavailable.",
        }
    ]


def _clean_draft(item: dict[str, Any], goal: str, acceptance: str) -> dict[str, str] | None:
    title = str(item.get("title") or "").strip() or title_from_goal(goal)
    ticket_goal = str(item.get("goal") or "").strip()
    ticket_acc = str(item.get("acceptance") or "").strip()
    if len(ticket_goal) < _MIN_TEXT or len(ticket_acc) < _MIN_TEXT:
        return None
    return {
        "title": title[:200],
        "goal": ticket_goal,
        "acceptance": ticket_acc,
        "rationale": str(item.get("rationale") or "").strip(),
    }


def drafts_from_payload(
    payload: dict[str, Any] | None,
    goal: str,
    acceptance: str,
) -> list[dict[str, str]]:
    raw = (payload or {}).get("tickets")
    if not isinstance(raw, list):
        return fallback_drafts(goal, acceptance)
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cleaned = _clean_draft(item, goal, acceptance)
        if cleaned:
            out.append(cleaned)
        if len(out) >= _MAX_TICKETS:
            break
    return out or fallback_drafts(goal, acceptance)


def _analysis_fields(payload: dict[str, Any] | None, fallback: bool) -> dict[str, str]:
    src = payload or {}
    return {
        "summary": str(src.get("summary") or "").strip(),
        "product": str(src.get("product") or "").strip(),
        "engineering": str(src.get("engineering") or "").strip(),
        "split_reason": str(src.get("split_reason") or ("fallback_single" if fallback else "")).strip(),
    }


async def analyze_goal(
    goal: str,
    repo: str,
    acceptance: str,
    *,
    complete_fn: CompleteFn | None = None,
) -> dict[str, Any]:
    """Propose tickets. Never calls Linear."""
    missing = validate_goal(goal, repo, acceptance)
    if missing:
        return {"error": "validation", "fields": missing}
    slug = normalize_repo(repo)
    project = resolve_project(slug)
    if not project:
        return {"error": "unknown_repo", "repo": slug}

    payload: dict[str, Any] | None = None
    fallback = False
    cost = 0.0
    try:
        fn = complete_fn or complete
        prompt = (
            f"Goal:\n{goal.strip()}\n\n"
            f"Repo:\n{slug}\n\n"
            f"Acceptance:\n{acceptance.strip()}\n"
        )
        text, cost = await fn(
            prompt=prompt,
            system=_SYSTEM,
            role="goal_analyst",
            max_tokens=2048,
        )
        payload = try_parse_json_object(text)
        if payload is None:
            fallback = True
            log.warning("goal analyze: no JSON in model output")
    except Exception as exc:
        fallback = True
        log.warning("goal analyze: model failed: %s", type(exc).__name__)

    tickets = drafts_from_payload(payload, goal, acceptance)
    if fallback:
        tickets = fallback_drafts(goal, acceptance)
    fields = _analysis_fields(payload, fallback)
    return {
        "status": "proposed",
        "filed": False,
        "fallback": fallback,
        "cost_usd": cost,
        "repo": slug,
        "project_id": project["project_id"],
        "registry_id": project["registry_id"],
        **fields,
        "tickets": tickets,
    }
