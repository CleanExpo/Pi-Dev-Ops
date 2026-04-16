"""
sessions.py — Public API surface for Pi-CEO build sessions.

RA-890: This file is now a thin facade. All implementation has been extracted
into focused leaf modules:

  session_model.py     — BuildSession dataclass, in-memory store, helpers
  session_sdk.py       — Claude Agent SDK runner + metrics
  session_evaluator.py — Evaluator runners, parsers, confidence alerts
  session_linear.py    — Linear GraphQL two-way sync
  session_phases.py    — Build phase pipeline + run_build orchestrator

This file re-exports everything for backward compatibility with callers in
main.py, orchestrator.py, autonomy.py, and cron.py.  The only functions
defined here are create_session, kill_session, and cleanup_session — the
session lifecycle layer that ties the modules together.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from typing import Optional

from . import config
from . import persistence

# ── RA-890: Re-export data model ──────────────────────────────────────────────
# NOTE: kill_session is NOT re-exported — sessions.py owns the async version.
from .session_model import (  # noqa: F401
    BuildSession,
    _sessions,
    _SESSIONS_DIR,
    get_session,
    list_sessions,
    restore_sessions,
    em,
)

# ── RA-890: Re-export SDK helpers ─────────────────────────────────────────────
from .session_sdk import (  # noqa: F401
    _SDK_METRICS_DIR,
    _write_sdk_metric,
    _emit_sdk_canary_metric,
    _run_claude_via_sdk,
)

# ── RA-890: Re-export evaluator helpers ───────────────────────────────────────
from .session_evaluator import (  # noqa: F401
    _parse_evaluator_dimensions,
    _extract_eval_score,
    _extract_eval_confidence,
    _send_low_confidence_alert,
    _get_claude_md,
    _run_eval_with_cache,
    _run_parallel_eval_cached,
    _run_single_eval,
    _run_parallel_eval,
)

# ── RA-890: Re-export Linear sync helpers ─────────────────────────────────────
from .session_linear import (  # noqa: F401
    _update_linear_state,
    _post_linear_comment,
    _record_session_outcome,
    _sync_linear_on_completion,
)

# ── RA-890: Re-export phase pipeline ─────────────────────────────────────────
from .session_phases import (  # noqa: F401
    run_cmd,
    parse_event,
    run_build,
    _build_incident_context,
    _select_model,
    _HARNESS_CONFIG,
    _TAO_AVAILABLE,
    _PHASE_ORDER,
    _should_skip,
    _phase_clone,
    _phase_analyze,
    _phase_claude_check,
    _phase_sandbox,
    _phase_generate,
    _phase_evaluate,
    _phase_push,
)

_log = logging.getLogger("pi-ceo.sessions")


# ── Session lifecycle ─────────────────────────────────────────────────────────

async def create_session(
    repo_url,
    brief="",
    model="",
    evaluator_enabled=True,
    intent="",
    parent_session_id="",
    linear_issue_id: Optional[str] = None,
    budget_minutes: Optional[int] = None,
    scope: Optional[dict] = None,
    plan_discovery: bool = False,
    complexity_tier: str = "",
    autonomy_triggered: bool = False,
    shared_workspace: str = "",  # RA-1029: path to parent's cloned workspace for worktree reuse
):
    """Create and start a new build session.

    RA-677: when budget_minutes is provided, auto-tunes eval_threshold,
    max_retries, model, and generator timeout via budget.budget_to_params().
    Per-request budget_minutes overrides TAO_AUTONOMY_BUDGET global default.

    RA-676: when scope is provided ({type, primary_file?, max_files_modified?}),
    the evaluator enforces a file-count ceiling and fires a Telegram alert on
    violation.  Default max_files_modified = 5.

    RA-681: complexity_tier overrides automatic brief complexity detection.
    Values: 'basic' | 'detailed' | 'advanced'. Empty string = auto-detect.
    """
    _running = sum(
        1 for s in _sessions.values()
        if (isinstance(s, BuildSession) and s.status == "running")
        or (isinstance(s, dict) and s.get("status") == "running")
    )
    if _running >= config.MAX_CONCURRENT_SESSIONS:
        raise RuntimeError("Max sessions reached")
    resolved_model = _select_model("generator", model)
    # RA-677 — apply AUTONOMY_BUDGET if specified
    bp: Optional[dict] = None
    if budget_minutes and budget_minutes > 0:
        from .budget import budget_to_params, describe_budget  # noqa: PLC0415
        bp = budget_to_params(budget_minutes)
        resolved_model = bp["model"]
        _log.info("AUTONOMY_BUDGET applied: %s", describe_budget(bp))
    session = BuildSession(
        repo_url=repo_url,
        started_at=time.time(),
        evaluator_enabled=evaluator_enabled,
        parent_session_id=parent_session_id or None,
        linear_issue_id=linear_issue_id or None,
        budget_params=bp,
        scope=scope or None,
        plan_discovery=plan_discovery,
        complexity_tier=complexity_tier,
        autonomy_triggered=autonomy_triggered,
        shared_workspace=shared_workspace,  # RA-1029: worktree source path for worker sessions
    )
    if scope:
        _log.info(
            "Scope contract set: session=%s type=%s max_files=%s",
            session.id, scope.get("type", "?"), scope.get("max_files_modified", 5),
        )
    _sessions[session.id] = session
    persistence.save_session(session)
    asyncio.create_task(run_build(session, brief, resolved_model, intent=intent))
    return session


async def kill_session(sid):
    s = _sessions.get(sid)
    if not s or not s.process:
        return False
    try:
        s.process.terminate()
        await asyncio.sleep(2)
        if s.process.returncode is None:
            s.process.kill()
        s.status = "killed"
        persistence.save_session(s)
        em(s, "error", "Killed by user")
        return True
    except Exception:
        return False


def cleanup_session(sid):
    import subprocess as _subprocess  # noqa: PLC0415 — local import avoids top-level cycle risk
    s = _sessions.pop(sid, None)
    if s and s.workspace and os.path.exists(s.workspace):
        # RA-1029: deregister git worktree before removing the directory for worker sessions
        if s.shared_workspace and s.parent_session_id:
            _subprocess.run(
                ["git", "-C", s.shared_workspace, "worktree", "remove",
                 "--force", s.workspace],
                capture_output=True,
            )
        shutil.rmtree(s.workspace, ignore_errors=True)
    persistence.delete_session_file(sid)
