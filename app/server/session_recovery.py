"""
session_recovery.py — rebuild a live BuildSession from a Supabase checkpoint row.

Split out of `session_model.py`, which is at the 300-line ceiling
(`.github/scripts/file_length_lint.py`). This is the read side of
`session_lease.checkpoint_payload()`: that function decides what a resume needs,
this one puts it back on a `BuildSession`.

The interesting decision is `resume_target()` — what a checkpoint's `workspace`
means on a machine that did not write it.
"""
from __future__ import annotations

import logging

from .session_model import BuildSession

_log = logging.getLogger("pi-ceo.session_recovery")

# The phase immediately BEFORE "sandbox" in session_phases._PHASE_ORDER. Resuming
# from it makes `_phase_sandbox` run, and that phase already knows how to
# re-clone a workspace directory that is not there.
# Re-derive: grep -n "_PHASE_ORDER = " app/server/session_phases.py
PRE_SANDBOX_PHASE = "claude_check"


def resume_target(checkpoint: dict, last_phase: str) -> tuple[str, str]:
    """Return `(workspace, resume_from)` for a checkpoint recovered on THIS machine.

    `checkpoint["workspace"]` is an absolute path on whichever machine wrote it.
    If that was a different machine the directory does not exist here — and
    neither does any of the work the generator left in it, so resuming at
    `last_phase` would evaluate and push a freshly cloned tree with none of the
    changes in it. Blanking the path alone is not enough: `_should_skip` skips
    `sandbox` — the phase that re-clones a missing workspace — whenever
    `resume_from` is at or past it, so the resume is also wound back to just
    before that phase. Plan and generate then re-run against the new clone,
    which is the only way their output can exist on this disk at all.

    Same host → the directory is real; both values pass through unchanged.
    """
    workspace = checkpoint.get("workspace", "") or ""
    origin_host = checkpoint.get("host", "") or ""
    from . import session_lease  # noqa: PLC0415

    here = session_lease.local_host()
    if origin_host and origin_host != here:
        _log.info(
            "startup recovery: checkpoint written by host %r, resuming on %r — "
            "discarding workspace %r and re-cloning from %s",
            origin_host, here, workspace, PRE_SANDBOX_PHASE,
        )
        return "", PRE_SANDBOX_PHASE
    return workspace, last_phase


def session_from_checkpoint(sid: str, row: dict, checkpoint: dict) -> BuildSession:
    """Rebuild a BuildSession from a `sessions` row plus its checkpoint JSONB.

    Every field `session_lease.checkpoint_payload()` persists is read back here.
    The writer used to drop about fifteen of them, so a "resumed" session came
    back with no plan, no repo context, no scope contract and no findings, then
    re-derived all of it from scratch and called that a resume.

    `budget` is deliberately not restored: it is a live BudgetTracker object,
    and `session_phases._phase_plan` constructs a fresh one. The checkpoint
    keeps its numbers for forensics, not for rehydration.
    """
    workspace, _ = resume_target(checkpoint, checkpoint.get("last_completed_phase", ""))
    return BuildSession(
        id=sid,
        repo_url=row.get("repo_url", ""),
        workspace=workspace,
        started_at=0.0,
        status="building",  # run_build will advance from last_completed_phase
        error=checkpoint.get("error"),
        last_completed_phase=checkpoint.get("last_completed_phase", ""),
        retry_count=int(checkpoint.get("retry_count", 0) or 0),
        evaluator_status=checkpoint.get("evaluator_status", "pending"),
        evaluator_score=checkpoint.get("evaluator_score"),
        evaluator_model=checkpoint.get("evaluator_model", ""),
        evaluator_consensus=checkpoint.get("evaluator_consensus", ""),
        linear_issue_id=checkpoint.get("linear_issue_id"),
        plan=checkpoint.get("plan", "") or "",
        repo_context=checkpoint.get("repo_context") or {},
        evaluator_findings=checkpoint.get("evaluator_findings") or [],
        scope=checkpoint.get("scope"),
        modified_files=checkpoint.get("modified_files") or [],
        budget_params=checkpoint.get("budget_params"),
        phase_metrics=checkpoint.get("phase_metrics") or {},
        plan_discovery_meta=checkpoint.get("plan_discovery_meta"),
        parent_session_id=checkpoint.get("parent_session_id"),
        complexity_tier=checkpoint.get("complexity_tier", "") or "",
        shared_workspace=checkpoint.get("shared_workspace", "") or "",
    )
