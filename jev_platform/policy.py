"""Shadow-mode decision policy (docs/plans/jev-platform/PLAN.md, rev 4 governs).

Pure functions, no network. Slice 1 never recommends "allow": the best a
recommendation can be is `escalate`, because no class claim can be verified yet.
"""
from __future__ import annotations

import math

POLICY_VERSION = "jev-shadow-1"
ABSTAIN_LOW, ABSTAIN_HIGH = 0.40, 0.60
FAIL_BELOW = 0.10
USABLE_STATE = "provisional"
RULE_COUNT = 538

PASS, FAIL, UNCERTAIN = "pass", "fail", "uncertain"
REFUSE, ESCALATE = "refuse", "escalate"


def valid_noul(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value) and 0.0 <= value <= 1.0


def classify_rule(noul, threshold: float | None, state: str, response_valid: bool) -> tuple[str, str]:
    """(result, reason) for one rule. pass/fail only on a valid response and a provisional rule."""
    if not response_valid:
        return UNCERTAIN, "signal_unavailable"
    if state != USABLE_STATE or threshold is None:
        return UNCERTAIN, state
    if not valid_noul(noul):
        return UNCERTAIN, "signal_unavailable"
    if noul < FAIL_BELOW:
        return FAIL, "below_fail_floor"
    if ABSTAIN_LOW <= noul <= ABSTAIN_HIGH:
        return UNCERTAIN, "abstain_band"
    if noul >= threshold:
        return PASS, "at_or_above_threshold"
    return UNCERTAIN, "below_threshold"


def selection_problems(rule_ids: list[str], known: set[str]) -> list[str]:
    if not rule_ids:
        return ["empty_selection"]
    problems = [f"unknown_rule:{r}" for r in rule_ids if r not in known]
    if len(set(rule_ids)) != len(rule_ids):
        problems.append("duplicate_rule_ids")
    return problems


def class_reason(claimed) -> str:
    if claimed in (0, 1, 2) and not isinstance(claimed, bool):
        return "class_unverified"
    return "founder_class"


def recommend(findings: list[dict], claimed_class, problems: list[str]) -> dict:
    """Combine per-rule findings into a shadow recommendation. Never 'allow'."""
    reasons = list(problems) + [class_reason(claimed_class)]
    failing = [f["rule"] for f in findings if f["result"] == FAIL]
    reasons += [f"uncertain:{f['rule']}:{f['reason']}" for f in findings if f["result"] == UNCERTAIN]
    verdict = REFUSE if failing and not problems else ESCALATE
    return {
        "mode": "shadow",
        "policy_version": POLICY_VERSION,
        "verdict": verdict,
        "refused_by": failing,
        "reasons": reasons,
        "class": f"{claimed_class} (claimed, unverified)",
        "evaluated": len(findings),
        "unevaluated": RULE_COUNT - len(findings),
    }


def overall_rating(artifact: str, judgment_available: bool, evaluated: int) -> dict:
    """Four evidence components; overall is the minimum, never rounded up."""
    order = ["FAIL", "A", "AA", "AAA"]
    parts = {
        "artifact": artifact,
        "judgment": "A" if judgment_available else "FAIL",
        "classification": "FAIL",
        "coverage": "FAIL" if evaluated < RULE_COUNT else "A",
    }
    parts["overall"] = min(parts.values(), key=order.index)
    return parts
