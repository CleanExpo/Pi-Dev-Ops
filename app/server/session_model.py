"""
session_model.py — BuildSession dataclass, in-memory store, and persistence helpers.

Extracted from sessions.py (RA-890). This is the pure data layer — no async
build logic, no evaluator, no Linear sync. All other session modules depend on
this one; it has no dependencies on them (leaf node in the import graph).

Public API (re-exported by sessions.py for backward compatibility):
    BuildSession       — dataclass representing one build run
    _sessions          — in-memory dict[str, BuildSession]
    get_session()      — look up session by ID
    list_sessions()    — serialise all sessions to dicts for the API
    restore_sessions() — reload persisted sessions on startup
    kill_session()     — cancel a running session
    em()               — append a log line to session.output_lines
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import config
from . import persistence

_log = logging.getLogger("pi-ceo.session_model")

# ── Disk-backed session directory ─────────────────────────────────────────────
_SESSIONS_DIR = Path(config.DATA_DIR) / "sessions"
_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


# ── BuildSession ───────────────────────────────────────────────────────────────

@dataclass
class BuildSession:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    repo_url: str = ""
    workspace: str = ""
    process: Optional[asyncio.subprocess.Process] = None
    started_at: float = 0.0
    status: str = "created"
    output_lines: list = field(default_factory=list)
    error: Optional[str] = None
    evaluator_enabled: bool = True
    evaluator_status: str = "pending"
    evaluator_score: Optional[float] = None
    evaluator_confidence: Optional[float] = None   # RA-674: 0-100% self-reported certainty
    evaluator_model: str = ""                       # RA-553: which model(s) produced the score
    evaluator_consensus: str = ""                   # RA-553: per-model scores + delta description
    parent_session_id: Optional[str] = None         # RA-464: fan-out parallelism
    budget: Optional[object] = None                 # RA-465: BudgetTracker instance
    budget_params: Optional[dict] = None            # RA-677: AUTONOMY_BUDGET computed params
    scope: Optional[dict] = None                    # RA-676: session scope contract
    modified_files: list = field(default_factory=list)    # RA-676: git-tracked modified files
    scope_adhered: Optional[bool] = None            # RA-676: None=no scope, True/False=check result
    plan_discovery: bool = False                    # RA-679: plan variation discovery before generate
    plan_discovery_meta: Optional[dict] = None      # RA-679: {scores, winner, winner_score, duration_s}
    complexity_tier: str = ""                       # RA-681: brief tier (basic/detailed/advanced)
    last_completed_phase: str = ""                  # Phase tracking for resume (GROUP D/E)
    retry_count: int = 0                            # Evaluator retry count (GROUP C)
    linear_issue_id: Optional[str] = None           # Linear issue ID for two-way sync
    autonomy_triggered: bool = False                # RA-887: True when started by autonomy poller
    repo_context: dict = field(default_factory=dict)  # RA-1025: grounded repo scan result
    plan: str = ""                                  # RA-1026: structured implementation plan (written by _phase_plan)
    evaluator_findings: list = field(default_factory=list)  # RA-1027: structured JSON findings from persona review
    shared_workspace: str = ""                      # RA-1029: path to parent's cloned workspace (worktree source)
    phase_metrics: dict = field(default_factory=dict)  # RA-1032: per-phase {duration_s, cost_usd}


# ── In-memory session store ────────────────────────────────────────────────────

_sessions: dict[str, BuildSession] = {}


# ── Store helpers ──────────────────────────────────────────────────────────────

def get_session(sid: str) -> Optional[BuildSession]:
    """Return session by ID, or None if not found."""
    return _sessions.get(sid)


def list_sessions() -> list[dict]:
    """Serialise all sessions to JSON-safe dicts for the REST API."""
    return [
        {
            "id": s.id,
            "repo": s.repo_url,
            "status": s.status,
            "started": s.started_at,
            "lines": len(s.output_lines),
            "parent": s.parent_session_id,
            "last_phase": s.last_completed_phase,
            "evaluator_score": s.evaluator_score,
            "evaluator_confidence": s.evaluator_confidence,
            "evaluator_model": s.evaluator_model,
            "evaluator_consensus": s.evaluator_consensus,
            "retry_count": s.retry_count,
            "evaluator_status": s.evaluator_status,
            "budget_minutes": (s.budget_params or {}).get("budget_minutes"),
            "scope_adhered": s.scope_adhered,
            "files_modified": len(s.modified_files),
            "complexity_tier": s.complexity_tier,
        }
        for s in _sessions.values()
    ]


def restore_sessions() -> None:
    """Load persisted sessions from disk on server startup.

    Sessions that were mid-flight (cloning/building) are marked 'interrupted'
    so the client knows to retry rather than wait for a result that will never come.
    """
    count = 0
    for data in persistence.load_all_sessions():
        sid = data.get("id", "")
        if not sid or sid in _sessions:
            continue
        session = BuildSession(
            id=sid,
            repo_url=data.get("repo_url", ""),
            workspace=data.get("workspace", ""),
            started_at=data.get("started_at", 0.0),
            status=data.get("status", "unknown"),
            error=data.get("error"),
            last_completed_phase=data.get("last_completed_phase", ""),
            retry_count=data.get("retry_count", 0),
            linear_issue_id=data.get("linear_issue_id"),
        )
        # Mark anything that was in-flight as interrupted
        if session.status in ("created", "cloning", "building"):
            session.status = "interrupted"
            persistence.save_session(session)
        _sessions[sid] = session
        count += 1
    if count:
        _log.info("Restored %d session(s) from disk.", count)


# RA-1407 PR 2 — module-level counter for /health.sessions.recovered surfacing.
_recovered_from_supabase: int = 0


def recover_interrupted_sessions_from_supabase(max_concurrent: int = 0) -> int:
    """RA-1407 PR 2 — Cross-deploy recovery of `interrupted` sessions.

    Pulls rows where status='interrupted' from Supabase (PR 1's writer wrote
    them there). For each session not already in local `_sessions`,
    rehydrates a BuildSession from the row's `checkpoint` JSONB and
    schedules a resume via `run_build(session, resume_from=last_phase)`.

    Capped at `max_concurrent` (defaults to MAX_CONCURRENT_SESSIONS) so a
    deploy after a 50-session outage doesn't melt the new container.

    Returns the number of sessions actually scheduled for resume.

    Fail-soft: any Supabase or import error returns 0; the rest of startup
    proceeds normally. Local JSON restore (already done in restore_sessions)
    is the fallback when Supabase is unavailable.
    """
    global _recovered_from_supabase
    try:
        from . import config, persistence, supabase_log  # noqa: PLC0415
        from .session_phases import run_build  # noqa: PLC0415
    except Exception as exc:
        _log.warning("RA-1407 startup recovery: import failed — %s", exc)
        return 0

    cap = int(max_concurrent) if max_concurrent > 0 else getattr(config, "MAX_CONCURRENT_SESSIONS", 3)
    try:
        rows = supabase_log.fetch_interrupted_sessions(limit=cap * 2)
    except Exception as exc:
        _log.warning("RA-1407 startup recovery: supabase fetch failed — %s", exc)
        return 0

    if not rows:
        return 0

    scheduled = 0
    for row in rows:
        if scheduled >= cap:
            _log.info(
                "RA-1407 startup recovery: hit cap of %d concurrent resumes; %d more rows queued in Supabase",
                cap, len(rows) - scheduled,
            )
            break
        sid = row.get("id", "")
        if not sid or sid in _sessions:
            continue  # local JSON restore already handled it
        checkpoint = row.get("checkpoint") or {}
        last_phase = checkpoint.get("last_completed_phase", "")
        if not last_phase:
            _log.warning(
                "RA-1407 startup recovery: skipping %s — no last_completed_phase in checkpoint", sid,
            )
            continue
        try:
            session = BuildSession(
                id=sid,
                repo_url=row.get("repo_url", ""),
                workspace=checkpoint.get("workspace", ""),
                started_at=0.0,
                status="building",  # run_build will advance from last_completed_phase
                error=checkpoint.get("error"),
                last_completed_phase=last_phase,
                retry_count=int(checkpoint.get("retry_count", 0) or 0),
                evaluator_status=checkpoint.get("evaluator_status", "pending"),
                evaluator_score=checkpoint.get("evaluator_score"),
                evaluator_model=checkpoint.get("evaluator_model", ""),
                evaluator_consensus=checkpoint.get("evaluator_consensus", ""),
                linear_issue_id=checkpoint.get("linear_issue_id"),
            )
            _sessions[sid] = session
            persistence.save_session(session)
            asyncio.create_task(run_build(session, resume_from=last_phase))
            scheduled += 1
        except Exception as exc:
            _log.warning("RA-1407 startup recovery: failed to rehydrate %s — %s", sid, exc)
            continue

    if scheduled:
        _log.info(
            "RA-1407 startup recovery: scheduled %d session(s) for resume from Supabase checkpoint",
            scheduled,
        )
    _recovered_from_supabase = scheduled
    return scheduled


def get_recovered_count() -> int:
    """RA-1407 PR 2 — /health.sessions.recovered surface helper."""
    return _recovered_from_supabase


# ── Output helper ──────────────────────────────────────────────────────────────

def em(session: BuildSession, t: str, d: str) -> None:
    """Append a structured log line to session.output_lines."""
    session.output_lines.append({"type": t, "text": d, "ts": time.time()})
