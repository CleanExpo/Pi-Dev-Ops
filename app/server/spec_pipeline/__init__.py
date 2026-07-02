"""Machine spec pipeline orchestrator."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.server import supabase_log
from app.server.tao_planner import resolve_planner_loop_kwargs
from app.server.tao_loop import run_until_done

from . import persistence as persist
from .boardroom import boardroom_query
from .review_runner import run_review
from .ship_gate import (
    machine_ship_enabled,
    open_pr_and_merge,
    run_oracles,
    scan_diff_boundary,
    scan_proposal_boundary,
)
from .spm_runner import run_spm
from .storm_evidence import gather_evidence
from .liaison_loop import judge_with_liaison
from .proposal_validator import ProposalValidationError, validate_proposal_text

log = logging.getLogger("pi-ceo.spec_pipeline")

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPO = os.environ.get("GITHUB_REPO", "CleanExpo/Pi-Dev-Ops")


@dataclass
class PipelineResult:
    pipeline_id: str
    status: str
    reason: str = ""
    judge_score: int = 0
    boardroom_decision: str = ""
    pr_url: str = ""
    stages: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "status": self.status,
            "reason": self.reason,
            "judge_score": self.judge_score,
            "boardroom_decision": self.boardroom_decision,
            "pr_url": self.pr_url,
            "stages": self.stages,
        }


def _repo_context() -> str:
    parts: list[str] = []
    for name in ("CLAUDE.md", "AGENTS.md", "README.md"):
        p = REPO_ROOT / name
        if p.is_file():
            parts.append(f"--- {name} ---\n{p.read_text(encoding='utf-8')[:2000]}")
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=10, check=False,
        )
        parts.append(f"git status:\n{(proc.stdout or '')[:1500]}")
    except (subprocess.SubprocessError, OSError):
        pass
    return "\n\n".join(parts)


def _persist_meta(
    pipeline_id: str,
    *,
    status: str,
    proposal: str = "",
    reason: str = "",
    stages: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {
        "pipeline_id": pipeline_id,
        "status": status,
        "reason": reason,
        "stages": stages or [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if proposal:
        payload["proposal"] = proposal
    payload.update(extra)
    persist.write_json(pipeline_id, "meta.json", payload)


def _write_handoff(
    pipeline_id: str,
    *,
    status: str,
    proposal: str,
    reason: str,
    extra: dict[str, Any],
) -> None:
    lines = [
        "# Session Handoff — Machine Spec Pipeline",
        f"**Pipeline:** `{pipeline_id}`",
        f"**Status:** {status}",
        f"**Reason:** {reason}",
        "",
        "## Proposal",
        proposal,
        "",
        "## Artifacts",
        f"`.harness/spec-pipelines/{pipeline_id}/`",
        "",
        "## Pick up here",
        extra.get("pickup", "Review artifacts and re-run with fixes."),
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
    ]
    persist.write_text(pipeline_id, "08-handoff.md", "\n".join(lines))


def _log_machine_gate(pipeline_id: str, gate_checks: dict[str, bool], score: float) -> None:
    try:
        supabase_log.log_gate_check(
            pipeline_id=pipeline_id,
            session_id=None,
            gate_checks=gate_checks,
            review_score=score,
            shipped=gate_checks.get("shipped", False),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("gate_check log failed: %s", exc)


async def run_pipeline(
    proposal: str,
    *,
    trigger: Literal["cli", "linear", "mission_control"] = "cli",
    dry_run: bool = False,
    issue_id: str | None = None,
    pipeline_id: str | None = None,
) -> PipelineResult:
    """Run full machine spec pipeline."""
    pipeline_id = pipeline_id or persist.new_pipeline_id()
    stages: list[dict[str, Any]] = []
    persist.write_text(pipeline_id, "00-proposal.md", proposal + "\n")
    persist.write_json(pipeline_id, "meta.json", {
        "pipeline_id": pipeline_id,
        "proposal": proposal,
        "trigger": trigger,
        "issue_id": issue_id,
        "dry_run": dry_run,
        "status": "running",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    boundary = scan_proposal_boundary(proposal)
    if boundary.tier == "blocked":
        reason = f"boundary blocked: {boundary.blocked_paths}"
        stages.append({"stage": "boundary", "status": "blocked", "reason": reason})
        _write_handoff(pipeline_id, status="BLOCKED", proposal=proposal, reason=reason, extra={})
        _persist_meta(
            pipeline_id, status="blocked", proposal=proposal, reason=reason, stages=stages,
        )
        return PipelineResult(pipeline_id, "blocked", reason, stages=stages)

    try:
        proposal = validate_proposal_text(proposal)
    except ProposalValidationError as exc:
        reason = f"proposal validation: {exc}"
        stages.append({"stage": "proposal_validator", "status": "blocked", "reason": str(exc)})
        _write_handoff(pipeline_id, status="BLOCKED", proposal=proposal, reason=reason, extra={})
        _persist_meta(
            pipeline_id, status="blocked", proposal=proposal, reason=reason, stages=stages,
        )
        return PipelineResult(pipeline_id, "blocked", reason, stages=stages)

    evidence = await gather_evidence(proposal)
    persist.write_json(pipeline_id, "01-storm-evidence.json", {
        "rows": [e.to_dict() for e in evidence],
    })
    stages.append({"stage": "storm", "status": "ok", "count": len(evidence)})

    working_proposal, final_judge, _history, evidence = await judge_with_liaison(
        pipeline_id,
        proposal,
        evidence,
        repo_context=_repo_context(),
        stages=stages,
    )

    if final_judge.score < 100 or final_judge.has_open_evidence_gaps() or final_judge.honest_ceiling:
        reason = final_judge.ceiling_reason or f"judge score {final_judge.score}"
        _write_handoff(pipeline_id, status="BLOCKED", proposal=working_proposal, reason=reason, extra={})
        _persist_meta(
            pipeline_id,
            status="blocked",
            proposal=working_proposal,
            reason=reason,
            stages=stages,
            judge_score=final_judge.score,
        )
        return PipelineResult(
            pipeline_id, "blocked", reason,
            judge_score=final_judge.score, stages=stages,
        )

    spec = await run_spm(working_proposal, final_judge)
    persist.write_text(pipeline_id, "03-spm-spec.md", spec.markdown)
    stages.append({"stage": "spm", "status": "ok"})

    br_prompt = (
        f"Should we build this proposal?\n\n{working_proposal}\n\n"
        f"Judge score: {final_judge.score}\n\nSpec excerpt:\n{spec.markdown[:4000]}"
    )
    boardroom = await boardroom_query(
        prompt=br_prompt,
        system_prompt=(
            "You are a senior agency board. Australian English. "
            "Decide APPROVE_BUILD only if evidence is complete and scope is reversible."
        ),
    )
    persist.write_json(pipeline_id, "04-boardroom.json", boardroom.to_dict())
    stages.append({
        "stage": "boardroom",
        "status": "ok",
        "decision": boardroom.decision,
        "escalated": boardroom.escalated,
    })

    approved = (
        boardroom.decision == "APPROVE_BUILD"
        and (boardroom.min_pairwise_similarity >= 0.25 or boardroom.escalated)
    )
    _log_machine_gate(pipeline_id, {
        "spec_exists": True,
        "plan_exists": True,
        "build_complete": False,
        "tests_passed": False,
        "review_passed": False,
        "machine_judge_100": final_judge.score >= 100,
        "boardroom_approve": boardroom.decision == "APPROVE_BUILD",
    }, float(final_judge.score))

    if not approved:
        reason = f"boardroom {boardroom.decision}"
        _write_handoff(pipeline_id, status="BLOCKED", proposal=proposal, reason=reason, extra={})
        _persist_meta(
            pipeline_id,
            status="blocked",
            proposal=proposal,
            reason=reason,
            stages=stages,
            judge_score=final_judge.score,
            boardroom_decision=boardroom.decision,
        )
        return PipelineResult(
            pipeline_id, "blocked", reason,
            judge_score=final_judge.score,
            boardroom_decision=boardroom.decision,
            stages=stages,
        )

    if dry_run or not machine_ship_enabled():
        reason = "dry_run" if dry_run else "TAO_MACHINE_SHIP_MODE off"
        _write_handoff(pipeline_id, status="DRY_COMPLETE", proposal=proposal, reason=reason, extra={
            "pickup": "Set TAO_MACHINE_SHIP_MODE=1 and re-run without --dry-run to build.",
        })
        _persist_meta(
            pipeline_id,
            status="dry_complete",
            proposal=proposal,
            reason=reason,
            stages=stages,
            judge_score=100,
            boardroom_decision=boardroom.decision,
        )
        return PipelineResult(
            pipeline_id, "dry_complete", reason,
            judge_score=100, boardroom_decision=boardroom.decision, stages=stages,
        )

    ws_root = os.environ.get("TAO_WORKSPACE", "/tmp/pi-ceo-workspaces")
    workspace = str(Path(ws_root) / pipeline_id)
    if Path(workspace).exists():
        shutil.rmtree(workspace)
    shutil.copytree(
        REPO_ROOT, workspace,
        ignore=shutil.ignore_patterns(".git", "node_modules", ".next", "__pycache__"),
    )
    subprocess.run(["git", "init"], cwd=workspace, check=False, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=False, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=False, capture_output=True)

    loop_result = await run_until_done(
        goal=spec.goal_command,
        workspace=workspace,
        max_iters=int(os.environ.get("TAO_MAX_ITERS", "25")),
        judge_every_n_iters=1,
        timeout_per_iter_s=600,
        **resolve_planner_loop_kwargs(),
    )
    persist.append_jsonl(pipeline_id, "05-build-loop.jsonl", {
        "done": loop_result.done,
        "reason": loop_result.reason,
        "iters": loop_result.iters,
        "cost_usd": loop_result.cost_usd,
    })
    stages.append({
        "stage": "build",
        "status": "ok" if loop_result.done else "incomplete",
        "reason": loop_result.reason,
    })

    diff_boundary = scan_diff_boundary(workspace)
    if diff_boundary.tier == "blocked":
        reason = f"diff boundary: {diff_boundary.blocked_paths}"
        _write_handoff(pipeline_id, status="BLOCKED", proposal=proposal, reason=reason, extra={})
        _persist_meta(
            pipeline_id, status="blocked", proposal=proposal, reason=reason,
            stages=stages, judge_score=100,
        )
        return PipelineResult(pipeline_id, "blocked", reason, judge_score=100, stages=stages)

    oracles = run_oracles(workspace)
    review = run_review(workspace, oracles=oracles)
    persist.write_json(pipeline_id, "06-review-packet.json", review.to_dict())
    stages.append({"stage": "review", "status": review.verdict})

    if review.verdict == "BLOCKED":
        reason = "; ".join(review.blockers)
        _write_handoff(pipeline_id, status="BLOCKED", proposal=proposal, reason=reason, extra={})
        _persist_meta(
            pipeline_id, status="blocked", proposal=proposal, reason=reason,
            stages=stages, judge_score=100,
        )
        return PipelineResult(pipeline_id, "blocked", reason, judge_score=100, stages=stages)

    branch = f"pidev/auto-{pipeline_id[:8]}"
    subprocess.run(["git", "checkout", "-b", branch], cwd=workspace, check=False)
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=False)
    subprocess.run(
        ["git", "commit", "-m", f"feat(spec-pipeline): {proposal[:72]}"],
        cwd=workspace, check=False,
    )
    remote = os.environ.get("GITHUB_REPO_URL", f"https://github.com/{DEFAULT_REPO}.git")
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        remote = remote.replace("https://", f"https://x-access-token:{token}@")
    subprocess.run(["git", "remote", "add", "origin", remote], cwd=workspace, check=False)
    subprocess.run(["git", "push", "-u", "origin", branch], cwd=workspace, check=False)

    ship = open_pr_and_merge(
        repo=DEFAULT_REPO,
        branch=branch,
        title=f"feat(spec-pipeline): {proposal[:80]}",
        body=f"Machine spec pipeline `{pipeline_id}`\n\nTrigger: {trigger}\nIssue: {issue_id or 'n/a'}",
    )
    persist.write_json(pipeline_id, "07-ship-result.json", ship)
    stages.append({"stage": "ship", "status": ship.get("status", "unknown")})

    _log_machine_gate(pipeline_id, {
        "spec_exists": True,
        "plan_exists": True,
        "build_complete": loop_result.done,
        "tests_passed": oracles.get("pytest_ok", False),
        "review_passed": review.verdict in ("PASS", "PASS_WITH_WARNINGS"),
        "shipped": ship.get("status") == "merged",
    }, float(final_judge.score))

    status = "complete" if ship.get("status") == "merged" else "ship_blocked"
    _write_handoff(pipeline_id, status=status.upper(), proposal=proposal,
                   reason=str(ship.get("status", "")), extra={
                       "pickup": ship.get("pr_url", ""),
                   })
    _persist_meta(
        pipeline_id,
        status=status,
        proposal=proposal,
        reason=str(ship.get("status", "")),
        stages=stages,
        pr_url=ship.get("pr_url", ""),
        judge_score=100,
        boardroom_decision=boardroom.decision,
    )
    return PipelineResult(
        pipeline_id, status,
        reason=str(ship.get("status", "")),
        judge_score=100,
        boardroom_decision=boardroom.decision,
        pr_url=ship.get("pr_url", ""),
        stages=stages,
    )


def run_pipeline_sync(**kwargs: Any) -> PipelineResult:
    return asyncio.run(run_pipeline(**kwargs))
