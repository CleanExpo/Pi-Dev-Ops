"""Binary LLM-as-judge — Prove-It Gate slice 2 (RA-7014).

Doctrine (from the grill, Grills/08-prove-it-gate.md): the judge returns a
**binary PASS/FAIL**, never a 1-10 score. It routes through the estate's existing
model layer — provider_router role "evaluator" (mid tier = claude-sonnet-5) — so it
reuses the same routing/policy the live-session evaluator already uses; no new
model plumbing.

The judge may NOT gate a merge until it clears the <20% expert-disagreement
calibration bar (slice 3a). Until then it runs non-blocking / advisory.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_VERDICT_RE = re.compile(r"VERDICT:\s*(PASS|FAIL)", re.IGNORECASE)

_RUBRIC_PREAMBLE = """You are a strict binary evaluator. Judge the CANDIDATE against the RUBRIC.
Answer with a one-line verdict and nothing else, in exactly this form:
VERDICT: PASS
or
VERDICT: FAIL
PASS only if the candidate fully satisfies the rubric. When uncertain, answer FAIL."""


@dataclass(frozen=True)
class Verdict:
    passed: bool
    raw: str
    cost_usd: float = 0.0


def build_prompt(candidate: str, rubric: str) -> str:
    """The exact judge prompt — pure, unit-testable without any model call."""
    return (
        f"{_RUBRIC_PREAMBLE}\n\n"
        f"RUBRIC:\n{rubric}\n\n"
        f"CANDIDATE:\n{candidate}\n\n"
        f"VERDICT:"
    )


def parse_verdict(raw: str) -> bool:
    """Parse a model reply into a binary pass. Unparseable → FAIL (fail-closed)."""
    m = _VERDICT_RE.search(raw or "")
    return bool(m) and m.group(1).upper() == "PASS"


async def judge_binary(candidate: str, rubric: str, *, session_id: str = "prove-it") -> Verdict:
    """Run the binary judge via provider_router role 'evaluator' (claude-sonnet-5).

    Imported lazily so importing this module never pulls the server stack (keeps
    build_prompt/parse_verdict testable in a bare environment / keyless CI).
    """
    from app.server.provider_router import run_via_provider  # noqa: PLC0415

    prompt = build_prompt(candidate, rubric)
    rc, text, cost, error = await run_via_provider(
        prompt, role="evaluator", session_id=session_id, thinking="off"
    )
    if rc != 0 or error:
        # Fail-closed: an unreachable/erroring judge never silently passes.
        return Verdict(passed=False, raw=f"judge-error: {error or rc}", cost_usd=cost or 0.0)
    return Verdict(passed=parse_verdict(text), raw=text.strip(), cost_usd=cost or 0.0)
