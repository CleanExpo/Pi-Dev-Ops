"""CEO-board liaison — machine adapter resolving judge gaps without human HITL."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .llm import complete, try_parse_json_object
from .prebuild_judge import EvidenceRow, JudgeReport
from .proposal_validator import ProposalValidationError, validate_proposal_text

log = logging.getLogger("pi-ceo.spec_pipeline.ceo_board_liaison")


@dataclass
class GapResolution:
    gap: str
    resolution: str
    owner: str = "board"

    def to_dict(self) -> dict[str, str]:
        return {"gap": self.gap, "resolution": self.resolution, "owner": self.owner}


@dataclass
class BoardLiaisonResult:
    memo: str
    decision: str
    proceed: bool
    refined_proposal: str
    gap_resolutions: list[GapResolution] = field(default_factory=list)
    new_evidence: list[EvidenceRow] = field(default_factory=list)
    research_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memo": self.memo,
            "decision": self.decision,
            "proceed": self.proceed,
            "refined_proposal": self.refined_proposal,
            "gap_resolutions": [g.to_dict() for g in self.gap_resolutions],
            "new_evidence": [e.to_dict() for e in self.new_evidence],
            "research_gaps": self.research_gaps,
        }


def _parse_evidence_rows(rows: list[Any]) -> list[EvidenceRow]:
    out: list[EvidenceRow] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        st = str(row.get("status", "SUPPORTED")).upper()
        if st not in ("SUPPORTED", "PARTIAL", "UNSUPPORTED", "CONFLICTING", "NOT CHECKED"):
            st = "SUPPORTED"
        out.append(EvidenceRow(
            claim=str(row.get("claim", "")),
            source_url=str(row.get("source_url", "")),
            source_title=str(row.get("source_title", "")),
            perspective=str(row.get("perspective", "ceo-board")),
            status=st,
        ))
    return out


async def run_ceo_board_liaison(
    proposal: str,
    judge_report: JudgeReport,
    *,
    evidence: list[EvidenceRow],
    repo_context: str,
    round_n: int = 1,
) -> BoardLiaisonResult:
    """Condensed ceo-board deliberation focused on judge gaps (Stages 2–6 machine form)."""
    gap_lines = "\n".join(f"- {g}" for g in judge_report.gaps) or "(none listed)"
    open_rows = [
        e for e in judge_report.evidence
        if e.status in ("UNSUPPORTED", "NOT CHECKED", "PARTIAL")
    ]
    open_lines = "\n".join(
        f"- [{e.status}] {e.claim} ({e.source_title})" for e in open_rows
    ) or "(none)"
    ev_lines = "\n".join(
        f"- [{e.status}] {e.claim} | {e.source_title}" for e in evidence[:30]
    )

    prompt = (
        "You are the CEO convening a machine board liaison to resolve pre-build judge gaps.\n"
        "Follow ceo-board discipline: frame the question, debate fault lines, constraint check, "
        "then emit a decision memo — NO human in the loop.\n\n"
        f"Round: {round_n}\n\n"
        f"Original proposal:\n{proposal}\n\n"
        f"Judge score: {judge_report.score}/100 decision={judge_report.decision}\n"
        f"Judge gaps:\n{gap_lines}\n\n"
        f"Open evidence rows:\n{open_lines}\n\n"
        f"STORM evidence sample:\n{ev_lines}\n\n"
        f"Repo context:\n{repo_context[:4000]}\n\n"
        "Tasks:\n"
        "1. CEO FRAMES — sharpen the core question from judge gaps.\n"
        "2. CONSTRAINT CHECK — Architect + Revenue flag fatal blockers only.\n"
        "3. THE MEMO — decision, rationale, next actions to unblock judge to 100.\n"
        "4. Refine proposal text if REDUCE_SCOPE; set proceed=false only on REJECT.\n"
        "5. Resolve each judge gap with a concrete, testable answer grounded in repo context.\n"
        "6. Add new_evidence rows marking prior NOT CHECKED items SUPPORTED when justified.\n\n"
        "Output: markdown memo first, then a single JSON object (last line starts with {):\n"
        '{"decision":"APPROVE_BUILD|REDUCE_SCOPE|REJECT","proceed":<bool>,'
        '"refined_proposal":"<full updated proposal text>",'
        '"gap_resolutions":[{"gap":"...","resolution":"...","owner":"Architect|Revenue|CEO"}],'
        '"new_evidence":[{"claim":"","source_url":"","source_title":"","perspective":"ceo-board",'
        '"status":"SUPPORTED|PARTIAL"}],'
        '"research_gaps":["..."]}\n'
    )
    text, _ = await complete(
        prompt=prompt,
        role="ceo_board_liaison",
        max_tokens=5000,
    )
    memo = text
    data: dict[str, Any] = {}
    if "{" in text:
        memo, _, tail = text.rpartition("{")
        data = try_parse_json_object("{" + tail) or {}
    if not data:
        data = try_parse_json_object(text) or {}
    if not data:
        log.warning("ceo_board_liaison: JSON tail missing; using memo-only fallback")
        memo = text

    decision = str(data.get("decision", "REDUCE_SCOPE")).upper()
    if decision not in ("APPROVE_BUILD", "REDUCE_SCOPE", "REJECT"):
        decision = "REDUCE_SCOPE"
    proceed = bool(data.get("proceed", decision != "REJECT"))
    refined = str(data.get("refined_proposal") or proposal).strip() or proposal
    if data.get("refined_proposal"):
        try:
            refined = validate_proposal_text(refined)
        except ProposalValidationError as exc:
            log.warning(
                "ceo_board_liaison: refined proposal rejected (%s); keeping original",
                exc,
            )
            refined = proposal
    resolutions = [
        GapResolution(
            gap=str(item.get("gap", "")),
            resolution=str(item.get("resolution", "")),
            owner=str(item.get("owner", "board")),
        )
        for item in (data.get("gap_resolutions") or [])
        if isinstance(item, dict) and item.get("gap")
    ]
    return BoardLiaisonResult(
        memo=memo.strip(),
        decision=decision,
        proceed=proceed,
        refined_proposal=refined,
        gap_resolutions=resolutions,
        new_evidence=_parse_evidence_rows(data.get("new_evidence") or []),
        research_gaps=[str(g) for g in (data.get("research_gaps") or [])],
    )
