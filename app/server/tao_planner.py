"""app/server/tao_planner.py — lookahead planner for the autonomous loop.

Gives ``tao_loop.run_until_done`` a planning horizon: instead of reacting one
generator step at a time, decompose the goal into an ordered plan, execute the
active step each iteration, advance on completion, and re-plan when the horizon
is exhausted.

The planning brain is the EXISTING orchestrator decomposition
(``orchestrator._decompose_brief``) — one planning vocabulary for the whole
codebase, not a second divergent one. This module is a thin adapter: it calls
``_decompose_brief``, topologically orders the resulting task DAG (reusing the
orchestrator's wave sort), and folds it into the linear ``Plan`` the loop
consumes. ``_decompose_brief`` runs on the Opus ``orchestrator`` role
(RA-1099-allowed) and forces JSON-only output.

Fails safe: any planner failure (SDK error, unparseable output, empty result)
degrades to a single-step plan ``[goal]`` — exactly the reactive behaviour —
never a crash.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from typing import Final

log = logging.getLogger("pi-ceo.tao_planner")

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
# Decomposition-backed planning (SDK-free helpers are unit-tested)
# ============================================================

def _git_remote(workspace: str) -> str:
    """Best-effort origin URL for planner context; '' on any failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", workspace, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return (proc.stdout or "").strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _plan_descriptions(tasks, horizon: int) -> list[str]:
    """Flatten ``_decompose_brief`` output into an ordered list of step briefs.

    Rich dict tasks are topologically ordered (via the orchestrator's wave
    sort) and rendered with their test scenarios; plain-string fallbacks are
    used as-is. Clamped to ``horizon``. Empty input -> [] so the caller falls
    back to a single-step plan.
    """
    if not tasks:
        return []
    if isinstance(tasks[0], dict):
        # Lazy import: avoid any import cycle and the heavy orchestrator deps
        # on the default (planner-off) path.
        from .orchestrator import _topological_sort, _task_brief
        ordered = [t for wave in _topological_sort(tasks) for t in wave]
        descs = [_task_brief(t) for t in ordered]
    else:
        descs = [str(t) for t in tasks]
    cleaned = [d.strip() for d in descs if d and d.strip()]
    return cleaned[:horizon]


async def make_plan(
    goal: str,
    workspace: str,
    *,
    horizon: int = DEFAULT_HORIZON,
    session_id: str = "",
) -> Plan:
    """Produce an ordered ``Plan`` for ``goal`` via ``_decompose_brief``.

    Fails safe to a single-step plan (``[goal]``) on any error so the loop
    degrades to its reactive behaviour rather than crashing. ``session_id`` is
    accepted for caller compatibility; ``_decompose_brief`` manages its own.
    """
    horizon = max(1, min(int(horizon), MAX_HORIZON))
    try:
        from .orchestrator import _decompose_brief  # lazy: avoid import cycle
        tasks = await _decompose_brief(
            goal, n_workers=horizon, repo_url=_git_remote(workspace), workspace=workspace,
        )
    except Exception as exc:  # pragma: no cover — defensive; never kill the loop
        log.warning("tao_planner decompose failure: %s — single-step fallback", exc)
        return Plan.from_steps(goal, [], horizon=horizon)
    return Plan.from_steps(goal, _plan_descriptions(tasks, horizon), horizon=horizon)


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


def resolve_planner_horizon(*, explicit: int | None = None) -> int | None:
    """Return active planner horizon (1-20) or None for reactive mode.

    Precedence: explicit arg > TAO_PLANNER_HORIZON > OM-1 default (15).
    """
    from . import config  # noqa: PLC0415

    if explicit is not None:
        value = max(0, min(int(explicit), MAX_HORIZON))
        return value or None
    if config.TAO_PLANNER_HORIZON > 0:
        return config.TAO_PLANNER_HORIZON
    if config.TAO_OM1_ENABLED:
        return DEFAULT_HORIZON
    return None


def resolve_planner_loop_kwargs(
    *,
    planner_horizon: int | None = None,
    max_replans: int | None = None,
) -> dict[str, int | None]:
    """Shared kwargs for ``run_until_done`` planner wiring (OM-1)."""
    from . import config  # noqa: PLC0415

    return {
        "planner_horizon": resolve_planner_horizon(explicit=planner_horizon),
        "max_replans": (
            config.TAO_PLANNER_MAX_REPLANS
            if max_replans is None
            else max(0, int(max_replans))
        ),
    }


def planner_runtime_status() -> dict[str, int | bool | str | None]:
    """Surface OM-1 / lookahead planner state for health + autonomy."""
    from . import config  # noqa: PLC0415

    effective = resolve_planner_horizon()
    return {
        "om1_enabled": config.TAO_OM1_ENABLED,
        "configured_horizon": config.TAO_PLANNER_HORIZON,
        "effective_horizon": effective,
        "max_replans": config.TAO_PLANNER_MAX_REPLANS,
        "mode": "lookahead" if effective else "reactive",
        "default_horizon_when_om1": DEFAULT_HORIZON,
        "max_horizon": MAX_HORIZON,
    }


__all__ = [
    "DEFAULT_HORIZON",
    "MAX_HORIZON",
    "Plan",
    "PlanStep",
    "format_step_goal",
    "make_plan",
    "planner_runtime_status",
    "resolve_planner_horizon",
    "resolve_planner_loop_kwargs",
]
