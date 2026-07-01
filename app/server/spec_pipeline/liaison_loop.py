"""Judge ↔ CEO-board ↔ SPM liaison loop until score 100 or honest ceiling."""
from __future__ import annotations

import logging
import os
from typing import Any

from . import persistence as persist
from .ceo_board_liaison import run_ceo_board_liaison
from .prebuild_judge import EvidenceRow, JudgeReport, iterate_to_100
from .proposal_validator import ProposalValidationError, validate_proposal_text
from .spm_runner import extract_refined_proposal, run_spm_gap_resolution

log = logging.getLogger("pi-ceo.spec_pipeline.liaison_loop")


def merge_evidence(
    base: list[EvidenceRow],
    *extra: list[EvidenceRow],
) -> list[EvidenceRow]:
    """Merge evidence rows; later rows override same claim text."""
    by_claim: dict[str, EvidenceRow] = {e.claim: e for e in base if e.claim}
    for batch in extra:
        for row in batch:
            if row.claim:
                by_claim[row.claim] = row
    return list(by_claim.values())


async def judge_with_liaison(
    pipeline_id: str,
    proposal: str,
    evidence: list[EvidenceRow],
    *,
    repo_context: str,
    stages: list[dict[str, Any]],
) -> tuple[str, JudgeReport, list[JudgeReport], list[EvidenceRow]]:
    """
    Run judge; on gaps invoke ceo-board + SPM; re-judge until 100 or ceiling.

    Returns (working_proposal, final_judge, judge_history, merged_evidence).
    """
    max_liaison = int(os.environ.get("TAO_SPEC_LIAISON_ROUNDS", "3"))
    judge_iters = int(os.environ.get("TAO_SPEC_JUDGE_ITERS", "5"))
    working_proposal = proposal
    merged_evidence = list(evidence)
    judge_history: list[JudgeReport] = []
    final_judge: JudgeReport | None = None

    for liaison_round in range(max_liaison + 1):
        final_judge, round_history = await iterate_to_100(
            working_proposal,
            evidence=merged_evidence,
            repo_context=repo_context,
            max_iters=judge_iters,
        )
        offset = len(judge_history)
        for i, rep in enumerate(round_history, 1):
            persist.write_json(
                pipeline_id,
                f"02-judge-iter-{offset + i}.json",
                rep.to_dict(),
            )
        judge_history.extend(round_history)

        if (
            final_judge.score >= 100
            and not final_judge.has_open_evidence_gaps()
            and not final_judge.honest_ceiling
        ):
            final_judge.decision = "APPROVE_BUILD"
            stages.append({
                "stage": "judge",
                "status": "ok",
                "score": final_judge.score,
                "liaison_rounds": liaison_round,
            })
            return working_proposal, final_judge, judge_history, merged_evidence

        if liaison_round >= max_liaison:
            stages.append({
                "stage": "judge",
                "status": "ceiling",
                "score": final_judge.score,
                "liaison_rounds": liaison_round,
            })
            return working_proposal, final_judge, judge_history, merged_evidence

        liaison = await run_ceo_board_liaison(
            working_proposal,
            final_judge,
            evidence=merged_evidence,
            repo_context=repo_context,
            round_n=liaison_round + 1,
        )
        persist.write_json(
            pipeline_id,
            f"02b-ceo-board-liaison-{liaison_round + 1}.json",
            liaison.to_dict(),
        )
        persist.write_text(
            pipeline_id,
            f"02b-ceo-board-memo-{liaison_round + 1}.md",
            liaison.memo,
        )
        stages.append({
            "stage": "ceo_board_liaison",
            "round": liaison_round + 1,
            "decision": liaison.decision,
            "proceed": liaison.proceed,
        })

        if not liaison.proceed or liaison.decision == "REJECT":
            final_judge.honest_ceiling = True
            final_judge.ceiling_reason = (
                final_judge.ceiling_reason
                or f"ceo-board REJECT at liaison round {liaison_round + 1}"
            )
            stages.append({"stage": "judge", "status": "rejected", "score": final_judge.score})
            return working_proposal, final_judge, judge_history, merged_evidence

        spm_packet = await run_spm_gap_resolution(
            working_proposal,
            final_judge,
            board_memo=liaison.memo,
            gap_resolutions=[g.to_dict() for g in liaison.gap_resolutions],
        )
        persist.write_text(
            pipeline_id,
            f"02c-spm-gap-resolution-{liaison_round + 1}.md",
            spm_packet.markdown,
        )
        stages.append({"stage": "spm_gap_resolution", "round": liaison_round + 1, "status": "ok"})

        next_proposal = extract_refined_proposal(
            spm_packet, liaison.refined_proposal,
        )
        try:
            working_proposal = validate_proposal_text(next_proposal)
        except ProposalValidationError as exc:
            log.warning(
                "liaison round %d: SPM proposal rejected (%s); using liaison refinement",
                liaison_round + 1, exc,
            )
            working_proposal = liaison.refined_proposal
        merged_evidence = merge_evidence(
            merged_evidence,
            liaison.new_evidence,
        )
        persist.write_text(pipeline_id, "00-proposal.md", working_proposal + "\n")

    assert final_judge is not None
    return working_proposal, final_judge, judge_history, merged_evidence
