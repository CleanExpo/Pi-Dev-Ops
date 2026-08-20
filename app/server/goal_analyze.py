"""Turn a stated goal into draft Linear tickets. Never writes to Linear."""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

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
CompleteFn = Callable[..., Awaitable[tuple[str, float]]]
ContextFn = Callable[[str, str], dict[str, Any]]

_SYSTEM = """You are a senior software engineer, product engineer, and technical product manager.
Inspect the provided repo excerpt (if any). Do not invent files, APIs, or tables that are not in the excerpt.
Do not duplicate existing behaviour. Reuse existing patterns. Split into the smallest set of
implementation-ready Linear tickets that can ship independently. Not one ticket per sentence.
If the excerpt is missing, say so in goal_analysis and mark every ticket's context with the limitation.
Do not mention Ready for Pi-Dev or pi-dev:autonomous. Do not claim Linear was written.
If the goal is UI, cover hierarchy, spacing, responsive, a11y, loading/empty/error/success,
keyboard, confirmation, dark and light themes via existing tokens (no hardcoded theme), and tests.
Do not redesign unrelated surfaces.
Return JSON only:
{
  "summary": "what is actually required",
  "split_reason": "why these tickets, not more, not fewer",
  "tickets": [
    {
      "title": "human-written imperative title <= 80 chars",
      "context": "where this sits in the product",
      "user_story": "As a … I want … so that … (omit if not useful)",
      "current_behaviour": "what happens today",
      "expected_behaviour": "what must happen after this ticket",
      "technical_requirements": "concrete surfaces, APIs, data, reuse",
      "acceptance": "testable Given/When/Then or numbered checks",
      "edge_cases": "failures, empty, permissions, mobile",
      "testing": "what to test and how",
      "dependencies": "tickets or systems this needs",
      "rationale": "why this is its own ticket"
    }
  ]
}
At most 6 tickets. Language: natural, direct, no filler.
"""

_TEXT_KEYS = (
    "context", "user_story", "current_behaviour", "expected_behaviour",
    "technical_requirements", "edge_cases", "testing", "dependencies", "rationale",
)


def _as_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(x).strip() for x in value if str(x).strip())
    return str(value or "").strip()


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
            "technical_requirements": "Verify pages, APIs, auth, and data in the target repo. Do not assume new tables or routes exist.",
            "edge_cases": "Cover loading, empty, error, auth, and theme if this is a UI change.",
            "testing": "Add tests that match the acceptance once the real surface is confirmed.",
            "dependencies": "",
            "rationale": "Single draft because analysis could not complete a grounded split.",
        }
    ]


def _clean_draft(item: dict[str, Any], goal: str, acceptance: str) -> dict[str, str] | None:
    expected = _as_text(item.get("expected_behaviour"))
    ticket_goal = _as_text(item.get("goal")) or expected
    ticket_acc = _as_text(item.get("acceptance")) or _as_text(item.get("acceptance_criteria"))
    if len(ticket_goal) < _MIN_TEXT or len(ticket_acc) < _MIN_TEXT:
        return None
    title = _as_text(item.get("title")) or title_from_goal(goal)
    out: dict[str, str] = {
        "title": title[:200],
        "goal": ticket_goal,
        "acceptance": ticket_acc,
    }
    for key in _TEXT_KEYS:
        out[key] = _as_text(item.get(key))
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


def _prompt(goal: str, slug: str, acceptance: str, ctx: dict[str, Any]) -> str:
    parts = [
        f"Goal:\n{goal.strip()}",
        f"Repo:\n{slug}",
        f"Acceptance:\n{acceptance.strip()}",
    ]
    if ctx.get("ok") and ctx.get("excerpt"):
        parts.append("Repo excerpt (source of truth):\n" + str(ctx["excerpt"]))
    else:
        parts.append(
            "CODE INSPECTION UNAVAILABLE.\n"
            + str(ctx.get("limitation") or "No repo excerpt.")
            + "\nDo not invent file paths. State the limitation in summary."
        )
    return "\n\n".join(parts)


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
            prompt=_prompt(goal, slug, acceptance, ctx),
            system=_SYSTEM,
            role="goal_analyst",
            max_tokens=4096,
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
    src = payload or {}
    summary = str(src.get("summary") or "").strip()
    if fallback and not summary:
        summary = limitation or "Analysis fell back. Repo inspection was not used as a completed review."
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
        "summary": summary,
        "split_reason": str(src.get("split_reason") or "").strip(),
        "tickets": tickets,
    }
