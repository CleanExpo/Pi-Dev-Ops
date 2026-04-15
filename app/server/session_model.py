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


# ── Output helper ──────────────────────────────────────────────────────────────

def em(session: BuildSession, t: str, d: str) -> None:
    """Append a structured log line to session.output_lines."""
    session.output_lines.append({"type": t, "text": d, "ts": time.time()})
