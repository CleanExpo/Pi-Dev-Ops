"""
app/server/routes/swarm.py — RA-1839: dashboard kill-switch endpoints.

Three endpoints:
  POST /api/swarm/kill     — engage kill-switch (requires 2-of-N + 2FA)
  POST /api/swarm/resume   — disengage kill-switch (single approver + 2FA)
  GET  /api/swarm/status   — current state + panic count

All three sit behind require_auth + require_rate_limit (consistent with
the existing webhook / session routes).

TOTP secrets per approver are configured via env:
  KILL_SWITCH_APPROVERS=alice,bob,carol            # comma-sep allowlist
  KILL_SWITCH_TOTP_alice=JBSWY3DPEHPK3PXP          # base32 secret per user
  KILL_SWITCH_TOTP_bob=...
  ...

If `pyotp` is not installed, the endpoints return 503 with a clear
remediation message. This lets the rest of the API ship without a hard
runtime dependency.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import require_auth, require_rate_limit

log = logging.getLogger("pi-ceo.swarm")
router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _approver_allowlist() -> list[str]:
    raw = os.environ.get("KILL_SWITCH_APPROVERS", "")
    return [u.strip() for u in raw.split(",") if u.strip()]


def _totp_secret(user: str) -> str | None:
    return os.environ.get(f"KILL_SWITCH_TOTP_{user}", "").strip() or None


def _verify_totp(user: str, code: str) -> tuple[bool, str]:
    """Return (ok, message). Drift window: ±1 (30s either side)."""
    if user not in _approver_allowlist():
        return False, f"user {user!r} not in KILL_SWITCH_APPROVERS allowlist"
    secret = _totp_secret(user)
    if not secret:
        return False, f"no KILL_SWITCH_TOTP_{user} env var configured"
    try:
        import pyotp  # type: ignore
    except ImportError:
        return False, "pyotp not installed; pip install pyotp"
    try:
        ok = pyotp.TOTP(secret).verify(str(code), valid_window=1)
        return (ok, "ok" if ok else "TOTP code invalid (check authenticator app)")
    except Exception as exc:
        return False, f"TOTP verification error: {exc!r}"


# ── Request models ───────────────────────────────────────────────────────────


class KillRequest(BaseModel):
    approver1_user: str = Field(..., description="First approver username (in allowlist)")
    approver1_totp: str = Field(..., min_length=6, max_length=8, description="TOTP code")
    approver2_user: str = Field(..., description="Second approver username (in allowlist, must differ)")
    approver2_totp: str = Field(..., min_length=6, max_length=8, description="TOTP code")
    reason: str = Field("", description="Reason — appended to audit log")


class ResumeRequest(BaseModel):
    approver_user: str = Field(..., description="Single approver username")
    approver_totp: str = Field(..., min_length=6, max_length=8, description="TOTP code")
    reason: str = Field("", description="Reason")
    confirmed: bool = Field(False, description="Required when escalation lock is active")


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/api/swarm/status",
           dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def swarm_status() -> dict:
    """Return kill-switch state. Read-only."""
    try:
        from swarm import kill_switch
    except Exception as exc:
        raise HTTPException(503, f"swarm module unreachable: {exc!r}")
    return {
        "swarm_enabled_env": os.environ.get("TAO_SWARM_ENABLED", "0") == "1",
        "kill_switch_active": kill_switch.is_active(),
        "escalation_lock_active": kill_switch.is_locked(),
        "panic_count_last_hour": kill_switch.panic_count_last_hour(),
        "approver_allowlist": _approver_allowlist(),
        "approver_totp_configured": [
            u for u in _approver_allowlist() if _totp_secret(u)
        ],
    }


@router.post("/api/swarm/kill",
            dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def swarm_kill(req: KillRequest) -> dict:
    """Engage kill-switch via 2-of-N + 2FA from the dashboard."""
    try:
        from swarm import kill_switch
    except Exception as exc:
        raise HTTPException(503, f"swarm module unreachable: {exc!r}")

    if req.approver1_user == req.approver2_user:
        raise HTTPException(400, "approver1 and approver2 must be different users")

    ok1, msg1 = _verify_totp(req.approver1_user, req.approver1_totp)
    ok2, msg2 = _verify_totp(req.approver2_user, req.approver2_totp)

    if not (ok1 and ok2):
        log.warning("kill-switch dashboard rejection: %s=%s, %s=%s",
                   req.approver1_user, msg1, req.approver2_user, msg2)
        raise HTTPException(401, {
            "error": "TOTP validation failed",
            "approver1": msg1,
            "approver2": msg2,
        })

    record = kill_switch.trigger(
        "dashboard_2fa",
        reason=req.reason,
        approvers=[req.approver1_user, req.approver2_user],
    )
    log.warning("kill-switch ENGAGED via dashboard 2FA by %s + %s",
               req.approver1_user, req.approver2_user)
    return {
        "status": "engaged" if record.get("action") == "engaged" else record.get("action"),
        "approvers": [req.approver1_user, req.approver2_user],
        "loop_guard_locked": record.get("loop_guard_locked", False),
        "ts": record.get("ts"),
    }


@router.post("/api/swarm/resume",
            dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def swarm_resume(req: ResumeRequest) -> dict:
    """Disengage kill-switch (single approver + 2FA).

    If escalation lock is active, also requires `confirmed=True` AND a
    non-empty reason.
    """
    try:
        from swarm import kill_switch
    except Exception as exc:
        raise HTTPException(503, f"swarm module unreachable: {exc!r}")

    ok, msg = _verify_totp(req.approver_user, req.approver_totp)
    if not ok:
        log.warning("kill-switch resume rejection: %s=%s", req.approver_user, msg)
        raise HTTPException(401, {"error": "TOTP validation failed", "detail": msg})

    record = kill_switch.resume(
        "dashboard",
        reason=req.reason,
        confirmed=req.confirmed,
    )
    if "error" in record:
        raise HTTPException(409, record)
    log.info("kill-switch RESUMED via dashboard by %s", req.approver_user)
    return {
        "status": record.get("action"),
        "approver": req.approver_user,
        "had_escalation_lock": record.get("had_escalation_lock", False),
        "ts": record.get("ts"),
    }


# ── RA-1839 — Curator proposals (read-only) ─────────────────────────────────


@router.get("/api/swarm/curator/proposals",
           dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def curator_proposals(
    status: str | None = None,
    limit: int = 50,
) -> dict:
    """Return Curator proposal records. Read-only.

    Optional `status` filter: pending | accepted | rejected_dedup |
    rejected_cooloff | rejected_rate | expired | queued_dry_run.
    `limit` caps newest-first (default 50, max 200).
    """
    try:
        from swarm import meta_curator
    except Exception as exc:
        raise HTTPException(503, f"meta_curator unreachable: {exc!r}")

    cap = max(1, min(int(limit or 50), 200))
    rows = meta_curator.list_proposals(status=status)
    rows.sort(key=lambda r: r.get("ts", ""), reverse=True)

    # Strip the proposed_skill_content field from list view — it's the full
    # SKILL.md body, large + only useful when reviewing one proposal.
    summary_rows = [
        {k: v for k, v in r.items() if k != "proposed_skill_content"}
        for r in rows[:cap]
    ]

    by_status: dict[str, int] = {}
    for r in rows:
        s = r.get("status") or "unknown"
        by_status[s] = by_status.get(s, 0) + 1

    return {
        "total": len(rows),
        "returned": len(summary_rows),
        "by_status": by_status,
        "proposals": summary_rows,
    }
