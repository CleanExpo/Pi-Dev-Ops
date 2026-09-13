"""Judge tick + coverage gate for tao_loop (UNI-2650).

Kept out of tao_loop.py so the runner stays under the 300-line ratchet.
"""
from __future__ import annotations

import logging
from typing import Callable

from .coverage_gate import workspace_coverage_failed
from .tao_judge import JudgeState, JudgeVerdict

log = logging.getLogger("pi-ceo.tao_loop")

EventCallback = Callable[[dict], None]


def abort_reason(reason: str, coverage_blocked: bool) -> str:
    """Prefer the coverage miss over a later budget abort."""
    if coverage_blocked and reason in {"MAX_ITERS", "MAX_COST"}:
        return "COVERAGE_INCOMPLETE"
    return reason


def iter_event(
    action: str, iters: int, verdict: JudgeVerdict, rc: int,
) -> dict:
    return {
        "action": action,
        "iters": iters,
        "score": verdict.score,
        "reason_hint": verdict.reason,
        "rc": rc,
    }


def emit(on_event: EventCallback | None, payload: dict) -> None:
    if on_event is None:
        return
    try:
        on_event(payload)
    except Exception as exc:  # pragma: no cover — never let callback kill loop
        log.warning("tao_loop on_event callback raised: %s", exc)


async def judge_tick(
    *,
    goal: str,
    workspace: str,
    state: JudgeState,
    session_id: str,
    iters: int,
    every: int,
    dod_path: str | None,
    project_id: str | None,
    on_event: EventCallback | None,
    rc: int,
    judge_history: list[JudgeVerdict],
) -> tuple[JudgeVerdict | None, bool, bool]:
    """Periodic judge + coverage gate. Returns (verdict, complete, blocked)."""
    # Import from tao_loop so tests that patch `tao_loop.judge` still bind.
    from .tao_loop import judge as judge_fn

    if iters % every != 0:
        return None, False, False
    verdict = await judge_fn(
        goal=goal, workspace=workspace, state=state,
        timeout_s=60, session_id=session_id,
    )
    judge_history.append(verdict)
    if not verdict.done:
        return verdict, False, False
    if workspace_coverage_failed(workspace, dod_path, project_id):
        emit(on_event, iter_event("coverage_incomplete", iters, verdict, rc))
        return verdict, False, True
    emit(on_event, iter_event("iter_complete", iters, verdict, rc))
    return verdict, True, False
