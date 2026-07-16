"""Judge calibration — Prove-It Gate slice 3a (RA-7014).

The judge may not gate a merge until it is *calibrated*: it must agree with an
expert-labelled set on ≥80% of cases (disagreement <20%, the grill bar), and be
stable run-to-run. This module computes those metrics from judge verdicts; it is
pure/deterministic given the verdicts, so the math is unit-tested without a model,
and a runner (run_calibration.py) supplies live verdicts when a model is reachable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The <20% disagreement bar from the grill (Grills/08-prove-it-gate.md, Q2).
MAX_DISAGREEMENT = 0.20


@dataclass(frozen=True)
class CalibrationCase:
    case_id: str
    expert_pass: bool          # the expert label
    judge_passes: list[bool]   # one entry per repeated judge run (variance signal)
    _errors: list[str] = field(default_factory=list)  # judge-error raws (runner use; ignored by math)


@dataclass(frozen=True)
class CalibrationReport:
    n_cases: int
    n_runs_each: int
    disagreement_rate: float   # fraction of cases where majority judge verdict != expert
    flip_rate: float           # fraction of cases whose judge verdict was not unanimous across runs
    disagreements: list[str]   # case_ids where majority != expert
    unstable: list[str]        # case_ids that flipped across runs

    @property
    def calibrated(self) -> bool:
        """Gate condition: agrees with experts AND is stable enough to trust."""
        return self.disagreement_rate < MAX_DISAGREEMENT and self.flip_rate < MAX_DISAGREEMENT


def _majority(votes: list[bool]) -> bool:
    return sum(votes) * 2 > len(votes)


def compute_calibration(cases: list[CalibrationCase]) -> CalibrationReport:
    if not cases:
        raise ValueError("calibration needs at least one case")
    runs = {len(c.judge_passes) for c in cases}
    if runs != {max(runs)}:
        raise ValueError(f"all cases must have the same run count, got {sorted(runs)}")
    n_runs = max(runs)
    if n_runs < 1:
        raise ValueError("each case needs at least one judge run")

    disagreements, unstable = [], []
    for c in cases:
        if _majority(c.judge_passes) != c.expert_pass:
            disagreements.append(c.case_id)
        if len(set(c.judge_passes)) > 1:  # not unanimous across runs
            unstable.append(c.case_id)

    n = len(cases)
    return CalibrationReport(
        n_cases=n,
        n_runs_each=n_runs,
        disagreement_rate=len(disagreements) / n,
        flip_rate=len(unstable) / n,
        disagreements=disagreements,
        unstable=unstable,
    )


def format_report(r: CalibrationReport) -> str:
    verdict = "CALIBRATED — may gate" if r.calibrated else "NOT CALIBRATED — stays advisory"
    lines = [
        f"Judge calibration: {verdict}",
        f"  cases={r.n_cases}  runs/case={r.n_runs_each}  bar=<{MAX_DISAGREEMENT:.0%}",
        f"  disagreement={r.disagreement_rate:.0%}  instability(flip)={r.flip_rate:.0%}",
    ]
    if r.disagreements:
        lines.append(f"  disagreements: {', '.join(r.disagreements)}")
    if r.unstable:
        lines.append(f"  unstable: {', '.join(r.unstable)}")
    return "\n".join(lines)
