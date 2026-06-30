"""app/server/tao_planner.py — lookahead planner for the autonomous loop.

Gives ``tao_loop.run_until_done`` a 15-20 move planning horizon. Instead of
reacting one generator step at a time, decompose the goal into an ordered plan
of concrete steps (via the Opus ``planner`` role — RA-1099 allows Opus only for
``planner``/``orchestrator``), execute the active step each iteration, advance
on completion, and re-plan when the judge stalls or the horizon is exhausted.

Pure logic + a single SDK call (``make_plan``). JSON parsing is isolated in
``_parse_steps`` so it is unit-testable without the SDK. Fails safe: any
planner failure (bad JSON, rc!=0, empty output) degrades to a single-step plan
``[goal]`` — i.e. exactly the existing reactive behaviour, never a crash.

The planner prompt forces JSON-only and never requests human confirmation,
mirroring ``tao_judge``'s prompt discipline (see CLAUDE.md "Planning prompt
forces JSON-only").
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Final

from .model_policy import select_model
from .session_sdk import _run_claude_via_sdk

log = logging.getLogger("pi-ceo.tao_planner")

PLANNER_ROLE: Final[str] = "planner"
DEFAULT_HORIZON: Final[int] = 15
MAX_HORIZON: Final[int] = 20

_PENDING: Final[str] = "pending"
_ACTIVE: Final[str] = "active"
_DONE: Final[str] = "done"


# ============================================================
# Plan shape
# ============================================================

@dataclass
class PlanStep:
    index: int
    description: str
    status: str = _PENDING


@dataclass
class Plan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    horizon: int = DEFAULT_HORIZON

    @classmethod
    def from_steps(cls, goal: str, descriptions: list[str], *, horizon: int) -> "Plan":
        """Build a plan, marking the first step active. Empty -> [goal]."""
        descs = descriptions or [goal]
        steps = [PlanStep(index=i, description=d) for i, d in enumerate(descs)]
        steps[0].status = _ACTIVE
        return cls(goal=goal, steps=steps, horizon=horizon)

    def active_step(self) -> PlanStep | None:
        for step in self.steps:
            if step.status == _ACTIVE:
                return step
        return None

    def advance(self) -> PlanStep | None:
        """Mark the active step done and activate the next pending one.

        Returns the newly-active step, or None when the plan is exhausted.
        """
        current = self.active_step()
        if current is not None:
            current.status = _DONE
        for step in self.steps:
            if step.status == _PENDING:
                step.status = _ACTIVE
                return step
        return None

    def is_exhausted(self) -> bool:
        return self.active_step() is None


# ============================================================
# Parsing (SDK-free, unit-tested)
# ============================================================

def _parse_steps(out: str, horizon: int) -> list[str]:
    """Extract an ordered list of step strings from the planner's JSON.

    Tolerant of prose around the JSON object. On any failure returns ``[]``
    so the caller can fall back to a single-step plan.
    """
    stripped = (out or "").strip()
    start = stripped.find("{")
    end = stripped.rfind("}") + 1
    if start < 0 or end <= start:
        return []
    try:
        obj = json.loads(stripped[start:end])
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(obj, dict):
        return []
    raw_steps = obj.get("steps")
    if not isinstance(raw_steps, list):
        return []
    cleaned = [s.strip() for s in raw_steps if isinstance(s, str) and s.strip()]
    return cleaned[:horizon]


def _build_prompt(goal: str, horizon: int) -> str:
    return (
        "You are the planner. Decompose the goal into an ordered, concrete "
        f"execution plan of at most {horizon} steps. Each step is one discrete "
        "action a coding worker can complete in a single iteration.\n\n"
        f"GOAL:\n{goal}\n\n"
        "Rules:\n"
        "- Output JSON ONLY. First character '{', last character '}'.\n"
        '- Shape: {"steps": ["<step 1>", "<step 2>", ...]}\n'
        "- Order steps so each builds on the previous.\n"
        "- Be specific and actionable; no vague placeholders.\n"
        "- Never ask for confirmation; assume reasonable defaults on ambiguity.\n"
    )


# ============================================================
# The planner call
# ============================================================

async def make_plan(
    goal: str,
    workspace: str,
    *,
    horizon: int = DEFAULT_HORIZON,
    timeout_s: int = 120,
    session_id: str = "",
) -> Plan:
    """Produce an ordered ``Plan`` for ``goal`` via the Opus planner role.

    Fails safe to a single-step plan (``[goal]``) on any SDK error, non-zero
    rc, empty output, or unparseable JSON — so the loop degrades to its
    existing reactive behaviour rather than crashing.
    """
    horizon = max(1, min(int(horizon), MAX_HORIZON))
    prompt = _build_prompt(goal, horizon)
    try:
        rc, out, _cost = await _run_claude_via_sdk(
            prompt=prompt,
            model=select_model(PLANNER_ROLE),
            workspace=workspace,
            timeout=timeout_s,
            session_id=session_id,
            phase=f"{PLANNER_ROLE}.tao_planner",
        )
    except Exception as exc:  # pragma: no cover — defensive; never kill the loop
        log.warning("tao_planner SDK failure: %s — falling back to single step", exc)
        return Plan.from_steps(goal, [], horizon=horizon)

    if rc != 0 or not (out or "").strip():
        log.info("tao_planner rc=%s/empty — falling back to single step", rc)
        return Plan.from_steps(goal, [], horizon=horizon)

    steps = _parse_steps(out, horizon)
    return Plan.from_steps(goal, steps, horizon=horizon)


def format_step_goal(plan: Plan, overall_goal: str) -> str:
    """Render the worker prompt for the plan's active step.

    Folds the overall goal, the active step, its position, and the remaining
    outline into one prompt. With no active step (exhausted), returns the
    overall goal unchanged so the worker still has something to act on.
    """
    step = plan.active_step()
    if step is None:
        return overall_goal
    total = len(plan.steps)
    remaining = [s.description for s in plan.steps if s.status != _DONE]
    outline = "\n".join(f"  - {d}" for d in remaining)
    return (
        f"OVERALL GOAL:\n{overall_goal}\n\n"
        f"CURRENT STEP {step.index + 1}/{total}:\n{step.description}\n\n"
        f"REMAINING PLAN:\n{outline}\n\n"
        "Do the current step now. Stay within its scope."
    )


__all__ = [
    "DEFAULT_HORIZON",
    "MAX_HORIZON",
    "PLANNER_ROLE",
    "Plan",
    "PlanStep",
    "format_step_goal",
    "make_plan",
    "select_model",
]
