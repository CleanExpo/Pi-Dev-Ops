"""
app/server/tao_judge.py — RA-1970: judge primitive for the TAO loop.

Single-scalar termination gate for `tao-loop`. Wraps a Sonnet evaluator call
that scores a goal-state pair and returns a structured verdict. The autoresearch
principle: the autonomy mandate gives intent, this `judge()` callable gives a
measurable termination condition.

Public API:

    verdict = await judge(
        goal="implement X",
        workspace="/path/to/repo",
        state=JudgeState(iters=3, last_test_output="...", last_diff="...", notes=[]),
        timeout_s=60,
        session_id="...",
    )

JSON-only model output: first char `{`, last char `}`. Mirrors the planner's
`_decompose_brief` JSON-discipline pattern from `orchestrator.py`. KillSwitchAbort
from the SDK chain bubbles up — never swallowed.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Final

from .kill_switch import KillSwitchAbort
from .model_policy import select_model
from .session_sdk import _run_claude_via_sdk

log = logging.getLogger("pi-ceo.tao_judge")

VALID_REASONS: Final[frozenset[str]] = frozenset(
    {"GOAL_MET", "INSUFFICIENT_PROGRESS", "TESTS_FAIL", "TIMEOUT", "STILL_WORKING"}
)
JUDGE_ROLE: Final[str] = "evaluator"  # RA-1099: sonnet allowed; opus blocked.


@dataclass
class JudgeState:
    """State summary handed to the judge each call. Kept small on purpose —
    long transcripts go through `tao_context_vcc.compact_for_sdk` upstream."""

    iters: int = 0
    last_test_output: str = ""
    last_diff: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class JudgeVerdict:
    """Single-scalar termination gate output.

    `score` ∈ [0.0, 1.0] is the autoresearch envelope's primary metric: a
    higher score means closer to GOAL_MET. `reason` is one of VALID_REASONS.
    """

    done: bool
    reason: str
    score: float
    next_action_hint: str


def _build_prompt(goal: str, state: JudgeState | None) -> str:
    """Tight scoring prompt. Forces JSON-only output."""
    s = state or JudgeState()
    notes_blob = "\n".join(f"- {n}" for n in s.notes) if s.notes else "(none)"
    schema = (
        '{"done": <true|false>, '
        '"reason": "<GOAL_MET|INSUFFICIENT_PROGRESS|TESTS_FAIL|TIMEOUT|STILL_WORKING>", '
        '"score": <float 0.0..1.0>, '
        '"next_action_hint": "<short next-step suggestion>"}'
    )
    return (
        "You are a goal-completion evaluator for an autonomous coding loop.\n"
        "Score whether the worker has met the goal. Output JSON ONLY — no prose, "
        "no markdown fences. First character must be '{', last must be '}'.\n\n"
        f"Goal: {goal}\n\n"
        f"Iterations so far: {s.iters}\n"
        f"Last test output (truncated):\n{s.last_test_output[:2000]}\n\n"
        f"Last diff stat (truncated):\n{s.last_diff[:1000]}\n\n"
        f"Worker notes:\n{notes_blob}\n\n"
        "Rules:\n"
        "- done=true ONLY when reason='GOAL_MET' and tests pass.\n"
        "- TESTS_FAIL: tests are failing now.\n"
        "- INSUFFICIENT_PROGRESS: many iters with no diff or no score gain.\n"
        "- STILL_WORKING: progress is happening, keep going.\n"
        "- TIMEOUT: exceeded an external time bound (rare for this caller).\n"
        f"- score is your scalar confidence the goal is met (0.0..1.0).\n\n"
        f"Respond with JSON matching this schema exactly:\n{schema}\n"
    )


def _parse_verdict(out: str) -> JudgeVerdict:
    """Parse the JSON verdict. On any failure → STILL_WORKING with score=0.0
    so the loop continues rather than terminating on bad parse."""
    stripped = out.strip()
    start = stripped.find("{")
    end = stripped.rfind("}") + 1
    if start < 0 or end <= start:
        return JudgeVerdict(
            done=False, reason="STILL_WORKING", score=0.0,
            next_action_hint=f"judge JSON parse failure: {stripped[:120]!r}",
        )
    try:
        obj = json.loads(stripped[start:end])
    except (json.JSONDecodeError, ValueError):
        return JudgeVerdict(
            done=False, reason="STILL_WORKING", score=0.0,
            next_action_hint=f"judge JSON parse failure: {stripped[:120]!r}",
        )
    if not isinstance(obj, dict):
        return JudgeVerdict(
            done=False, reason="STILL_WORKING", score=0.0,
            next_action_hint="judge JSON parse failure: not an object",
        )
    reason = str(obj.get("reason", "STILL_WORKING"))
    if reason not in VALID_REASONS:
        reason = "STILL_WORKING"
    try:
        score = float(obj.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(1.0, score))
    done = bool(obj.get("done", False)) and reason == "GOAL_MET"
    hint = str(obj.get("next_action_hint", ""))
    return JudgeVerdict(done=done, reason=reason, score=score, next_action_hint=hint)


async def judge(
    goal: str,
    workspace: str,
    state: JudgeState | None = None,
    *,
    timeout_s: int = 60,
    session_id: str = "",
) -> JudgeVerdict:
    """Score a goal-state pair via the evaluator role (Sonnet 4.6 per RA-1099).

    On `KillSwitchAbort` bubbling from the SDK chain — RAISE; never swallow.
    On any other SDK failure → STILL_WORKING verdict so the caller can decide
    whether to keep iterating or trip its own kill-switch.
    """
    prompt = _build_prompt(goal, state)
    model = select_model(JUDGE_ROLE)
    try:
        rc, out, _cost = await _run_claude_via_sdk(
            prompt=prompt,
            model=model,
            workspace=workspace,
            timeout=timeout_s,
            session_id=session_id,
            phase=f"{JUDGE_ROLE}.tao_judge",
        )
    except KillSwitchAbort:
        raise
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("tao_judge SDK failure: %s", exc)
        return JudgeVerdict(
            done=False, reason="STILL_WORKING", score=0.0,
            next_action_hint=f"judge SDK failure: {type(exc).__name__}",
        )
    if rc != 0 or not out.strip():
        return JudgeVerdict(
            done=False, reason="STILL_WORKING", score=0.0,
            next_action_hint=f"judge SDK rc={rc}",
        )
    return _parse_verdict(out)


__all__ = [
    "JUDGE_ROLE",
    "JudgeState",
    "JudgeVerdict",
    "VALID_REASONS",
    "judge",
]
