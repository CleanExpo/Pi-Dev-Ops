"""Judge: bounded development at 85, promotion at 95, pursuing an earned 100."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .llm import complete, parse_json_object
from .proposal_validator import enrich_proposal_for_judge

log = logging.getLogger("pi-ceo.spec_pipeline.prebuild_judge")

APPROVAL_FLOOR = 95
DEVELOPMENT_FLOOR = 85
QUALITY_TARGET = 100
ApprovalStage = Literal["development", "promotion"]


def validate_stage(stage: object) -> ApprovalStage:
    """Reject an unknown stage before callers perform any side effects."""
    if type(stage) is not str or stage not in ("development", "promotion"):
        raise ValueError("stage must be development or promotion")
    return "development" if stage == "development" else "promotion"


def approval_floor(stage: ApprovalStage = "promotion") -> int:
    return DEVELOPMENT_FLOOR if validate_stage(stage) == "development" else APPROVAL_FLOOR


NONBLOCKING_CATEGORIES = frozenset({
    "clear_problem", "reuse_existing", "ux_clarity", "testability",
})

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

    def is_supported(self) -> bool:
        return (
            isinstance(self.claim, str) and bool(self.claim.strip())
            and self.status == "SUPPORTED"
            and all(isinstance(value, str) for value in (
                self.source_url, self.source_title, self.perspective,
            ))
        )


@dataclass
class NonBlockingGap:
    name: str
    owner: str
    closure_action: str
    required_evidence: str
    category: str

    def is_valid(self) -> bool:
        return (
            all(isinstance(value, str) and bool(value.strip()) for value in (
                self.name, self.owner, self.closure_action, self.required_evidence,
                self.category,
            ))
            and self.category in NONBLOCKING_CATEGORIES
        )

    def to_dict(self) -> dict[str, str]:
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
    nonblocking_gaps: list[NonBlockingGap] = field(default_factory=list)

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
            "nonblocking_gaps": [g.to_dict() for g in self.nonblocking_gaps],
        }

    def has_open_evidence_gaps(self) -> bool:
        return (
            not isinstance(self.evidence, list) or not self.evidence
            or any(not isinstance(e, EvidenceRow) or not e.is_supported()
                   for e in self.evidence)
        )


def _is_quality_approved(report: JudgeReport, minimum: int) -> bool:
    """Both stages retain the same evidence and mandatory blockers."""
    if (
        type(report.score) is not int
        or not minimum <= report.score <= QUALITY_TARGET
        or report.honest_ceiling is not False
        or not isinstance(report.gaps, list) or report.gaps
        or report.has_open_evidence_gaps()
        or not isinstance(report.nonblocking_gaps, list)
    ):
        return False
    if report.score == QUALITY_TARGET:
        return not report.nonblocking_gaps
    return bool(report.nonblocking_gaps) and all(
        isinstance(gap, NonBlockingGap) and gap.is_valid()
        for gap in report.nonblocking_gaps
    )


def is_build_approved(report: JudgeReport) -> bool:
    """Ordinary build/promotion eligibility remains at 95, never at 85."""
    return _is_quality_approved(report, APPROVAL_FLOOR)


def is_development_approved(report: JudgeReport) -> bool:
    """Eligibility for a bounded preparation packet, not an automated builder."""
    return _is_quality_approved(report, DEVELOPMENT_FLOOR)


def is_stage_approved(report: JudgeReport, stage: ApprovalStage = "promotion") -> bool:
    if type(stage) is not str or stage not in ("development", "promotion"):
        return False
    return is_development_approved(report) if stage == "development" else is_build_approved(report)


def _stage_decision(stage: ApprovalStage) -> str:
    return "APPROVE_EXPERIMENT" if stage == "development" else "APPROVE_BUILD"


def _decision_for_score(score: int) -> str:
    """Numeric classification only; build authorization uses is_build_approved."""
    if score < 70:
        return "REJECT"
    if score < DEVELOPMENT_FLOOR:
        return "REDUCE_SCOPE"
    if score < APPROVAL_FLOOR:
        return "APPROVE_EXPERIMENT"
    return "APPROVE_BUILD"


def _build_prompt(
    proposal: str,
    evidence: list[EvidenceRow],
    repo_context: str,
    iteration: int,
    stage: ApprovalStage = "promotion",
) -> str:
    stage = validate_stage(stage)
    proposal = enrich_proposal_for_judge(proposal)
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
        '"gaps":["..."],"nonblocking_gaps":[{"name":"","owner":"",'
        '"closure_action":"","required_evidence":"","category":""}],'
        '"honest_ceiling":<bool>,"ceiling_reason":""}\n\n'
        "Nonblocking records require exactly those five nonblank string fields. "
        f"Requested stage {stage}; stage floor {approval_floor(stage)}. "
        f"Promotion floor {APPROVAL_FLOOR}; development floor {DEVELOPMENT_FLOOR}; quality target {QUALITY_TARGET}. "
        "Development approves only bounded reversible preparation/local work with separate authority; "
        "it never approves automated SDK implementation, push, merge, deployment or live activation. "
        "Require nonempty evidence, valid nonblank claims and every row SUPPORTED. "
        "Every legacy gaps item is blocking. At 85–99 explain deductions with at least one "
        f"complete nonblocking record; permitted categories: {', '.join(sorted(NONBLOCKING_CATEGORIES))}. "
        "Unknown/malformed or security, privacy, billing/spend, workspace trust, authority, "
        "isolation, rollback, irreversibility or must_fix gaps block at every score. "
        "Required evidence describes closure work; planned tests are never passed evidence. "
        "Score 100 ONLY with supported nonempty evidence and no blocking/nonblocking gaps. "
        "Never inflate. Set honest_ceiling true only for an explicit substantive ceiling, "
        "not merely because an iteration bound was reached; it blocks approval."
    )


def _parse_report(proposal: str, data: dict[str, Any], iteration: int,
                  stage: ApprovalStage = "promotion") -> JudgeReport:
    stage = validate_stage(stage)
    gaps: list[str] = []
    if not isinstance(data, dict):
        data = {}
        gaps.append("invalid judge report object")
    if set(data) - frozenset(JudgeReport.__dataclass_fields__):
        gaps.append("unknown judge report fields")
    raw_score = data.get("score", 0)
    if type(raw_score) is int and 0 <= raw_score <= QUALITY_TARGET:
        score = raw_score
    else:
        score = 0
        gaps.append("invalid score")
    raw_gaps = data.get("gaps", [])
    if not isinstance(raw_gaps, list):
        gaps.append("invalid blocking gaps collection")
    else:
        for gap in raw_gaps:
            if isinstance(gap, str) and gap.strip():
                gaps.append(gap)
            else:
                gaps.append("invalid blocking gap record")
    evidence = []
    raw_evidence = data.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        gaps.append("missing or malformed evidence collection")
        raw_evidence = []
    evidence_fields = frozenset(EvidenceRow.__dataclass_fields__)
    for row in raw_evidence:
        if (
            not isinstance(row, dict) or set(row) - evidence_fields
            or not isinstance(row.get("claim"), str) or not row["claim"].strip()
            or not isinstance(row.get("status"), str)
            or row["status"].upper() not in EVIDENCE_STATUSES
            or any(not isinstance(value, str) for value in row.values())
        ):
            gaps.append("invalid evidence row")
            continue
        evidence.append(EvidenceRow(
            claim=row["claim"], source_url=row.get("source_url", ""),
            source_title=row.get("source_title", ""),
            perspective=row.get("perspective", ""), status=row["status"].upper(),
        ))
    nonblocking_gaps = []
    raw_nonblocking = data.get("nonblocking_gaps", [])
    if not isinstance(raw_nonblocking, list):
        gaps.append("invalid nonblocking gaps collection")
    else:
        fields = frozenset(NonBlockingGap.__dataclass_fields__)
        for row in raw_nonblocking:
            if not isinstance(row, dict) or set(row) != fields:
                gaps.append("invalid nonblocking gap fields")
                continue
            gap = NonBlockingGap(**row)
            if not gap.is_valid():
                gaps.append("invalid or mandatory nonblocking gap classification")
                continue
            nonblocking_gaps.append(gap)
    category_scores = {}
    raw_categories = data.get("category_scores", {})
    if not isinstance(raw_categories, dict):
        raw_categories = {}
        gaps.append("invalid category scores")
    for category, maximum in CATEGORIES:
        value = raw_categories.get(category, 0)
        if type(value) is not int or not 0 <= value <= maximum:
            value = 0
            gaps.append("invalid category score")
        category_scores[category] = value
    honest_ceiling = data.get("honest_ceiling", False)
    if type(honest_ceiling) is not bool:
        honest_ceiling = True
        gaps.append("invalid honest ceiling")
    report = JudgeReport(
        proposal=proposal,
        score=score,
        decision=_decision_for_score(score),
        category_scores=category_scores,
        evidence=evidence,
        gaps=gaps,
        iteration=iteration,
        honest_ceiling=honest_ceiling,
        ceiling_reason=str(data.get("ceiling_reason", "")),
        nonblocking_gaps=nonblocking_gaps,
    )
    if report.score == QUALITY_TARGET and not is_build_approved(report):
        report.score = QUALITY_TARGET - 1
        report.gaps.append("score capped: claimed 100 has unresolved or invalid requirements")
    if is_stage_approved(report, stage):
        report.decision = _stage_decision(stage)
    elif report.score >= approval_floor(stage):
        report.decision = "NOT_APPROVED"
    return report


async def score_proposal(
    proposal: str,
    *,
    evidence: list[EvidenceRow],
    repo_context: str,
    iteration: int = 1,
    stage: ApprovalStage = "promotion",
) -> JudgeReport:
    stage = validate_stage(stage)
    text, _ = await complete(
        prompt=_build_prompt(proposal, evidence, repo_context, iteration, stage),
        role="prebuild_judge",
        max_tokens=3000,
    )
    return _parse_report(proposal, parse_json_object(text), iteration, stage)


async def iterate_to_100(
    proposal: str,
    *,
    evidence: list[EvidenceRow],
    repo_context: str,
    max_iters: int = 5,
    stage: ApprovalStage = "promotion",
) -> tuple[JudgeReport, list[JudgeReport]]:
    """Promotion pursues 100; development stops at its first qualified packet."""
    stage = validate_stage(stage)
    if max_iters < 1:
        raise ValueError("max_iters must be at least 1")
    history: list[JudgeReport] = []
    current_evidence = list(evidence)
    for i in range(1, max_iters + 1):
        report = await score_proposal(
            proposal,
            evidence=current_evidence,
            repo_context=repo_context,
            iteration=i,
            **({"stage": stage} if stage == "development" else {}),
        )
        if report.score >= approval_floor(stage) and not is_stage_approved(report, stage):
            report.decision = "NOT_APPROVED"
        history.append(report)
        if report.honest_ceiling:
            return report, history
        approved = is_stage_approved(report, stage)
        if stage == "development" and approved:
            report.decision = "APPROVE_EXPERIMENT"
            return report, history
        if report.score == QUALITY_TARGET and approved:
            report.decision = "APPROVE_BUILD"
            return report, history
        if i == max_iters and approved:
            report.decision = "APPROVE_BUILD"
            return report, history
        if i == max_iters:
            if report.score >= approval_floor(stage):
                report.decision = "NOT_APPROVED"
            report.honest_ceiling = True
            report.ceiling_reason = report.ceiling_reason or (
                f"max_iters={max_iters} reached at score {report.score}"
            )
            return report, history
        current_evidence = report.evidence or current_evidence
    return history[-1], history
