"""app/server/tao_boomerang.py — RA-1994 (Wave 2 / 5).

Token-efficient one-shot dispatch with summary-only return. Port of
pi-boomerang. Composes on `_run_claude_via_sdk`. The pattern: caller
hands one or more questions; each question is dispatched in parallel
with a "respond ONLY with a brief summary, no preamble, no
reasoning" preamble so the SDK's output is just the answer text.
The wrapper aggregates results and returns a list[BoomerangResult].

Why this exists:
  Many research / lookup calls need a single fact, but vanilla SDK
  invocations return the model's reasoning trace, tool-use blocks,
  and conversational pleasantries — all of which the caller throws
  away. Wrapping with a summary-only preamble and stripping pre/post
  matter at parse time saves tokens at scale (typical ~3-8x reduction
  in returned-payload size for short factual queries).

Public API:

    from app.server.tao_boomerang import boomerang, dispatch_one

    # Single dispatch
    result = await dispatch_one(
        question="What's the latest stable Python version?",
        timeout_s=120,
    )
    # result.summary; result.cost_usd; result.error

    # Parallel dispatch — same shape, list-of-questions in
    results = await boomerang(
        questions=["q1", "q2", "q3"],
        timeout_s=120,
    )

Composition:
  * Worker model: Sonnet via `select_model("generator")` per RA-1099.
  * Kill-switch: inherits from `_run_claude_via_sdk`'s SDK-level
    timeout. Caller wanting deeper bounds wraps the coroutine in
    `asyncio.wait_for` or runs inside `tao_loop`.
  * Cost: per-dispatch cost reported via the SDK metric and surfaced
    on `BoomerangResult.cost_usd`.

Out of scope:
  * Streaming partial results — boomerang is one-shot summary by
    design. Callers wanting iterative output should use `tao_loop`.
  * Web search / external tools — caller controls the question; the
    SDK has its standard tool surface available, but the prompt
    explicitly discourages tool use beyond what's necessary.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Sequence

from .model_policy import select_model
from .session_sdk import _run_claude_via_sdk

log = logging.getLogger("pi-ceo.tao_boomerang")

# Default per-question timeout. Single fact queries usually return in
# < 30s; 120s gives headroom for the SDK warm-up and an occasional
# multi-step lookup without inviting runaway cost.
DEFAULT_TIMEOUT_S: int = 120

# Preamble that constrains the worker to summary-only output. Kept
# explicit and short — long preambles eat the token savings we're
# chasing here.
SUMMARY_PREAMBLE: str = (
    "Respond with ONLY the answer to the question below. No preamble, "
    "no chain-of-thought, no quoted sources, no markdown formatting "
    "unless the answer itself requires it. If the answer is unknown or "
    "requires more context than provided, reply exactly with: "
    "'UNKNOWN: <one-line reason>'.\n\nQuestion:\n"
)


@dataclass
class BoomerangResult:
    """One question's outcome."""

    question: str
    summary: str = ""
    cost_usd: float = 0.0
    elapsed_s: float = 0.0
    error: str | None = None
    rc: int = 0

    @property
    def is_unknown(self) -> bool:
        """True when the worker explicitly returned an UNKNOWN sentinel."""
        return self.summary.startswith("UNKNOWN:")


@dataclass
class BoomerangBatch:
    """Aggregate result for a parallel boomerang() call."""

    results: list[BoomerangResult] = field(default_factory=list)

    @property
    def total_cost_usd(self) -> float:
        return round(sum(r.cost_usd for r in self.results), 4)

    @property
    def all_succeeded(self) -> bool:
        return all(r.error is None for r in self.results)


# ── Internals ────────────────────────────────────────────────────────────────


def _build_prompt(question: str) -> str:
    """Wrap a bare question with the summary-only preamble. Idempotent —
    if the preamble is already present we don't double-add."""
    q = question.strip()
    if q.startswith(SUMMARY_PREAMBLE.strip().split("\n", 1)[0][:30]):
        return q
    return f"{SUMMARY_PREAMBLE}{q}\n"


def _strip_summary_artifacts(text: str) -> str:
    """Trim noise the worker sometimes adds despite the preamble.

    Strips:
      * leading/trailing whitespace
      * common preamble phrases ("Sure, ", "Here is the answer:", etc.)
      * trailing "Let me know if you need anything else." footers
      * markdown fences when the entire answer is wrapped in a code block

    Keep this conservative — over-aggressive stripping mangles answers
    that legitimately use those markers. The single-line invariant we
    enforce is that we don't introduce content the model didn't write.
    """
    s = text.strip()
    # Strip leading "Sure, ", "Here is...", "The answer is..." prefixes
    leading_strips = (
        "sure, ", "sure! ", "sure: ", "here is the answer: ",
        "here is the answer:", "here's the answer: ", "here's the answer:",
        "the answer is: ", "the answer is:",
    )
    lower = s.lower()
    for p in leading_strips:
        if lower.startswith(p):
            s = s[len(p):].lstrip()
            lower = s.lower()
            break
    # If the WHOLE response is wrapped in a triple-backtick block, unwrap
    if s.startswith("```") and s.endswith("```") and s.count("```") == 2:
        inner = s[3:-3].strip()
        # Drop optional language hint on the first line
        if "\n" in inner:
            first, rest = inner.split("\n", 1)
            if first.strip() and " " not in first.strip():
                inner = rest
        s = inner.strip()
    # Strip trailing "Let me know if..." footers
    trailing_drop_lines = (
        "let me know if you need anything else.",
        "let me know if you have any questions.",
        "feel free to ask if you need more info.",
        "hope this helps!",
    )
    for line in s.splitlines()[::-1]:
        if line.strip().lower() in trailing_drop_lines:
            s = s.rsplit(line, 1)[0].rstrip()
        else:
            break
    return s.strip()


# ── Public API ───────────────────────────────────────────────────────────────


async def dispatch_one(
    question: str,
    *,
    workspace: str | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    session_id: str = "",
) -> BoomerangResult:
    """Dispatch one question. Returns BoomerangResult; never raises.

    Args:
        question: the bare question text.
        workspace: optional working directory for the SDK call. When
            None, falls through to the SDK's default.
        timeout_s: per-call cap; the SDK enforces.
        session_id: traceability tag passed to the SDK metrics.

    The summary string has summary-stripping artifacts removed — see
    `_strip_summary_artifacts`. Errors land on `result.error` (e.g.
    `"timeout"`, `"sdk_unavailable"`); callers MUST check before
    consuming `result.summary`.
    """
    import time
    t0 = time.monotonic()
    model = select_model("generator")
    prompt = _build_prompt(question)
    try:
        rc, text, cost = await asyncio.wait_for(
            _run_claude_via_sdk(
                prompt=prompt,
                model=model,
                workspace=workspace or "",
                timeout=timeout_s,
                session_id=session_id,
                phase="generator.boomerang",
                thinking="disabled",  # cost-control — no extended thinking
            ),
            timeout=timeout_s + 5,
        )
    except asyncio.TimeoutError:
        return BoomerangResult(
            question=question, error="timeout",
            elapsed_s=round(time.monotonic() - t0, 2),
        )
    except Exception as exc:  # noqa: BLE001
        # Defensive: SDK errors should be returned as data so caller
        # can decide whether to retry. Never bubble to the caller.
        log.warning("boomerang dispatch_one failed: %s", exc)
        return BoomerangResult(
            question=question, error=f"sdk_error: {exc}",
            elapsed_s=round(time.monotonic() - t0, 2),
        )
    summary = _strip_summary_artifacts(text or "")
    elapsed = round(time.monotonic() - t0, 2)
    return BoomerangResult(
        question=question, summary=summary,
        cost_usd=round(float(cost or 0.0), 4),
        elapsed_s=elapsed, rc=rc,
        error=None if rc == 0 else f"rc={rc}",
    )


async def boomerang(
    questions: Sequence[str],
    *,
    workspace: str | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    session_id: str = "",
    max_parallel: int = 5,
) -> BoomerangBatch:
    """Dispatch multiple questions in parallel, return a BoomerangBatch.

    `max_parallel` caps the asyncio fan-out so a long question list
    doesn't overrun the SDK rate limit. Default 5 is a conservative
    bound matching `MAX_CONCURRENT_SESSIONS`-class limits elsewhere.
    """
    if not questions:
        return BoomerangBatch()
    sem = asyncio.Semaphore(max(1, int(max_parallel)))

    async def _one(q: str) -> BoomerangResult:
        async with sem:
            return await dispatch_one(
                q, workspace=workspace, timeout_s=timeout_s,
                session_id=session_id,
            )

    results = await asyncio.gather(*(_one(q) for q in questions))
    return BoomerangBatch(results=list(results))


__all__ = [
    "BoomerangBatch",
    "BoomerangResult",
    "DEFAULT_TIMEOUT_S",
    "SUMMARY_PREAMBLE",
    "boomerang",
    "dispatch_one",
]
