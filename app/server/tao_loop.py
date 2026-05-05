"""
app/server/tao_loop.py — RA-1970: judge-gated iteration loop runner.

Port of pi-until-done's `/goal ... Ralph` autonomous-coding loop with a single
metric termination gate (`tao_judge.judge`). One worker step per iteration,
optional judge call every N iters, three independent abort axes from
`kill_switch.LoopCounter` (MAX_ITERS, MAX_COST, HARD_STOP).

Public API:

    result = await run_until_done(
        goal="implement X",
        workspace="/path/to/repo",
        max_iters=None,                # honour TAO_MAX_ITERS env
        max_cost_usd=None,             # honour TAO_MAX_COST_USD env
        judge_every_n_iters=1,         # cost-control: don't judge every micro-step
        timeout_per_iter_s=600,
        on_event=callback,             # streamed progress dicts
    )

Deviation from spec: optional `max_iters` / `max_cost_usd` parameters override
the env-driven defaults via `_make_counter`. Document quirk: `LoopCounter`
freezes its limits at construction (see `kill_switch.LoopCounter`'s docstring),
so passing 0 or None falls through to the env defaults.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Final

from . import kill_switch as _ks
from .model_policy import select_model
from .session_sdk import _run_claude_via_sdk
from .tao_judge import JudgeState, JudgeVerdict, judge

log = logging.getLogger("pi-ceo.tao_loop")

GENERATOR_ROLE: Final[str] = "generator"
EventCallback = Callable[[dict], None]


@dataclass
class LoopResult:
    """Outcome of a `run_until_done` invocation.

    `reason` is one of: kill-switch reasons (`MAX_ITERS`, `MAX_COST`,
    `HARD_STOP`), or `GOAL_MET` / `MAX_ITERS_NO_GOAL` / `JUDGE_NEVER_SATISFIED`.
    """

    done: bool
    reason: str
    iters: int
    cost_usd: float
    judge_history: list[JudgeVerdict] = field(default_factory=list)
    final_state: JudgeState | None = None


def _make_counter(
    max_iters: int | None, max_cost_usd: float | None
) -> _ks.LoopCounter:
    """Construct LoopCounter, allowing explicit overrides over env defaults.

    LoopCounter freezes its limits at construction time — that is by design
    (see kill_switch.py). Caller-supplied overrides take effect ONLY if
    explicitly passed (truthy and positive); else env-driven defaults stand.
    """
    counter = _ks.LoopCounter()
    if max_iters and max_iters > 0:
        counter._limit_iters = int(max_iters)
    if max_cost_usd and max_cost_usd > 0:
        counter._limit_cost_usd = float(max_cost_usd)
    return counter


def _git_diff_stat(workspace: str) -> str:
    """Best-effort `git diff --stat HEAD`. Empty string on any error."""
    try:
        proc = subprocess.run(
            ["git", "-C", workspace, "diff", "--stat", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return (proc.stdout or "").strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _quick_pytest(workspace: str) -> str:
    """Best-effort short pytest invocation. Empty string when no tests/ dir."""
    if not (Path(workspace) / "tests").is_dir():
        return ""
    try:
        proc = subprocess.run(
            ["python", "-m", "pytest", "-x", "-q", "--tb=no", "tests/"],
            capture_output=True, text=True, timeout=120,
            cwd=workspace, check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return out[-1500:].strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _build_state(prev_iters: int, workspace: str) -> JudgeState:
    """Snapshot workspace into a JudgeState for the judge call."""
    return JudgeState(
        iters=prev_iters,
        last_test_output=_quick_pytest(workspace),
        last_diff=_git_diff_stat(workspace),
        notes=[],
    )


def _emit(on_event: EventCallback | None, payload: dict) -> None:
    if on_event is None:
        return
    try:
        on_event(payload)
    except Exception as exc:  # pragma: no cover — never let callback kill loop
        log.warning("tao_loop on_event callback raised: %s", exc)


async def _run_worker_step(
    goal: str, workspace: str, timeout_s: int, session_id: str,
) -> tuple[int, str, float]:
    """One generator step. Returns (rc, output, cost_estimate_usd).

    Cost is whatever the SDK reports — currently 0.0 (RA-1099 metrics path).
    Callers can substitute via mocks in tests.
    """
    return await _run_claude_via_sdk(
        prompt=goal,
        model=select_model(GENERATOR_ROLE),
        workspace=workspace,
        timeout=timeout_s,
        session_id=session_id,
        phase=f"{GENERATOR_ROLE}.tao_loop",
    )


async def run_until_done(
    goal: str,
    workspace: str,
    *,
    max_iters: int | None = None,
    max_cost_usd: float | None = None,
    judge_every_n_iters: int = 1,
    timeout_per_iter_s: int = 600,
    on_event: EventCallback | None = None,
    session_id: str = "",
) -> LoopResult:
    """Drive worker iterations until judge says done or kill-switch fires.

    See module docstring for the abort matrix. Returns a fully-populated
    LoopResult; never raises KillSwitchAbort to the caller (captured into
    the result).
    """
    counter = _make_counter(max_iters, max_cost_usd)
    judge_history: list[JudgeVerdict] = []
    final_state: JudgeState | None = None
    reason: str = "JUDGE_NEVER_SATISFIED"
    done: bool = False
    every = max(1, int(judge_every_n_iters))

    while True:
        # Cheap pre-check: HARD_STOP file precedes anything else.
        try:
            _ks.check_hard_stop()
        except _ks.KillSwitchAbort as abort:
            reason = abort.reason
            break

        rc, _out, cost_iter = await _run_worker_step(
            goal=goal, workspace=workspace,
            timeout_s=timeout_per_iter_s, session_id=session_id,
        )

        try:
            counter.tick(cost_delta_usd=float(cost_iter or 0.0))
        except _ks.KillSwitchAbort as abort:
            reason = abort.reason
            break

        state = _build_state(counter.iters, workspace)
        final_state = state

        verdict: JudgeVerdict | None = None
        if counter.iters % every == 0:
            verdict = await judge(
                goal=goal, workspace=workspace, state=state,
                timeout_s=60, session_id=session_id,
            )
            judge_history.append(verdict)
            if verdict.done:
                reason = "GOAL_MET"
                done = True
                _emit(on_event, {
                    "action": "iter_complete", "iters": counter.iters,
                    "score": verdict.score, "reason_hint": verdict.reason,
                    "rc": rc,
                })
                break

        _emit(on_event, {
            "action": "iter_complete", "iters": counter.iters,
            "score": verdict.score if verdict else None,
            "reason_hint": verdict.reason if verdict else "no-judge-this-iter",
            "rc": rc,
        })

    return LoopResult(
        done=done, reason=reason, iters=counter.iters,
        cost_usd=round(counter.cost_usd, 4),
        judge_history=judge_history, final_state=final_state,
    )


__all__ = [
    "EventCallback",
    "GENERATOR_ROLE",
    "LoopResult",
    "run_until_done",
]
