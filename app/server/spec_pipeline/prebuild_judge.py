"""Pre-build judge — structured 0–100 scoring with iteration to honest 100."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from .llm import complete, parse_json_object

log = logging.getLogger("pi-ceo.spec_pipeline.prebuild_judge")

EVIDENCE_STATUSES = frozenset({
    "SUPPORTED", "PARTIAL", "UNSUPPORTED", "CONFLICTING", "NOT CHECKED",
})

CATEGORIES = (
    ("first_source_evidence", 25),
    ("clear_problem", 20),
    ("reuse_existing", 15),
    ("security_privacy", 15),
    ("ux_clarity", 10),
    ("testability", 10),
    ("cost_simplicity", 5),
)


@dataclass
class EvidenceRow:
    claim: str
    source_url: str = ""
    source_title: str = ""
    perspective: str = ""
    status: str = "NOT CHECKED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JudgeReport:
    proposal: str
    score: int
    decision: str
    category_scores: dict[str, int] = field(default_factory=dict)
    evidence: list[EvidenceRow] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    iteration: int = 1
    honest_ceiling: bool = False
    ceiling_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal": self.proposal,
            "score": self.score,
            "decision": self.decision,
            "category_scores": self.category_scores,
            "evidence": [e.to_dict() for e in self.evidence],
            "gaps": self.gaps,
            "iteration": self.iteration,
            "honest_ceiling": self.honest_ceiling,
            "ceiling_reason": self.ceiling_reason,
        }

    def has_open_evidence_gaps(self) -> bool:
        return any(
            e.status in ("UNSUPPORTED", "NOT CHECKED")
            for e in self.evidence
        )


def _decision_for_score(score: int) -> str:
    if score < 70:
        return "REJECT"
    if score < 85:
        return "REDUCE_SCOPE"
    if score < 100:
        return "APPROVE_EXPERIMENT"
    return "APPROVE_BUILD"


def _build_prompt(
    proposal: str,
    evidence: list[EvidenceRow],
    repo_context: str,
    iteration: int,
) -> str:
    ev_lines = "\n".join(
        f"- [{e.status}] {e.claim} | {e.source_title} {e.source_url}".strip()
        for e in evidence
    ) or "(none yet)"
    cats = "\n".join(f"  {k}: /{max_v}" for k, max_v in CATEGORIES)
    return (
        "You are the pre-build judge gate. Output JSON ONLY — first char '{', last '}'.\n\n"
        f"Proposal:\n{proposal}\n\n"
        f"Repo context (read-only):\n{repo_context[:6000]}\n\n"
        f"Evidence rows:\n{ev_lines}\n\n"
        f"Iteration: {iteration}\n\n"
        "Score categories (sum to 100):\n"
        f"{cats}\n\n"
        "Schema:\n"
        '{"score":<int 0-100>,"category_scores":{...},'
        '"evidence":[{"claim":"","source_url":"","source_title":"","perspective":"","status":"SUPPORTED|PARTIAL|UNSUPPORTED|CONFLICTING|NOT CHECKED"}],'
        '"gaps":["..."],"honest_ceiling":<bool>,"ceiling_reason":""}\n\n'
        "Rules: score 100 ONLY if every evidence row is SUPPORTED and gaps empty. "
        "Never inflate; set honest_ceiling true if 100 is unreachable."
    )


def _parse_report(proposal: str, data: dict[str, Any], iteration: int) -> JudgeReport:
    score = int(data.get("score", 0))
    score = max(0, min(100, score))
    evidence = []
    for row in data.get("evidence") or []:
        if not isinstance(row, dict):
            continue
        st = str(row.get("status", "NOT CHECKED")).upper()
        if st not in EVIDENCE_STATUSES:
            st = "NOT CHECKED"
        evidence.append(EvidenceRow(
            claim=str(row.get("claim", "")),
            source_url=str(row.get("source_url", "")),
            source_title=str(row.get("source_title", "")),
            perspective=str(row.get("perspective", "")),
            status=st,
        ))
    report = JudgeReport(
        proposal=proposal,
        score=score,
        decision=_decision_for_score(score),
        category_scores={k: int((data.get("category_scores") or {}).get(k, 0))
                         for k, _ in CATEGORIES},
        evidence=evidence,
        gaps=[str(g) for g in (data.get("gaps") or [])],
        iteration=iteration,
        honest_ceiling=bool(data.get("honest_ceiling")),
        ceiling_reason=str(data.get("ceiling_reason", "")),
    )
    if report.score == 100 and report.has_open_evidence_gaps():
        report.score = 99
        report.decision = _decision_for_score(report.score)
        report.gaps.append("score capped: open UNSUPPORTED/NOT CHECKED evidence")
    return report


async def score_proposal(
    proposal: str,
    *,
    evidence: list[EvidenceRow],
    repo_context: str,
    iteration: int = 1,
) -> JudgeReport:
    text, _ = await complete(
        prompt=_build_prompt(proposal, evidence, repo_context, iteration),
        role="prebuild_judge",
        max_tokens=3000,
    )
    return _parse_report(proposal, parse_json_object(text), iteration)


async def iterate_to_100(
    proposal: str,
    *,
    evidence: list[EvidenceRow],
    repo_context: str,
    max_iters: int = 5,
) -> tuple[JudgeReport, list[JudgeReport]]:
    """Iterate judge until score 100 or honest ceiling. Returns final + history."""
    history: list[JudgeReport] = []
    current_evidence = list(evidence)
    for i in range(1, max_iters + 1):
        report = await score_proposal(
            proposal,
            evidence=current_evidence,
            repo_context=repo_context,
            iteration=i,
        )
        history.append(report)
        if report.honest_ceiling:
            return report, history
        if report.score >= 100 and not report.has_open_evidence_gaps():
            report.decision = "APPROVE_BUILD"
            return report, history
        if i == max_iters and report.score < 100:
            report.honest_ceiling = True
            report.ceiling_reason = report.ceiling_reason or (
                f"max_iters={max_iters} reached at score {report.score}"
            )
            return report, history
        current_evidence = report.evidence or current_evidence
    return history[-1], history
