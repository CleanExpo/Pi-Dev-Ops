"""nexus_audit — append-only audit ledger for Nexus state-changing actions.

Generalises the pattern from `swarm/tmux_audit.py`: HMAC-keyed audit ids,
512-byte atomic-write cap, fail-closed on write failure. Adds workspace +
client correlation keys + an `approvals` foreign-key field so audit rows
can carry the approval id that gated the action.

Persisted to the `nexus_audit` table (schema in 20260601_nexus_v1.sql).
This module is pure-logic for ROW CONSTRUCTION + redaction; the actual
DB write is the caller's responsibility (via NexusAuditStore Protocol).

Per spec §7 — every state-changing Nexus action MUST write one row here.
Caller MUST refuse the action if `build_audit_row()` raises.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Iterable, Literal, Protocol

# Reuse tmux_audit's HMAC key infrastructure
from swarm.tmux_audit import (
    AUDIT_KEY_PATH,
    AuditRowTooLargeError,
    AuditUnwritableError,
)
from swarm.tmux_validator import redact_secrets

ATOMIC_WRITE_CAP_BYTES = 512

_TRUNCATABLE_FIELDS = ("args_redacted",)

PolicyLevel = Literal["auto", "approval", "escalation"]
AuditResult = Literal["ok", "denied", "error", "timeout"]


# ============================================================
# Public types
# ============================================================

@dataclass(frozen=True)
class NexusAuditRow:
    """One row destined for the `nexus_audit` table."""
    id: str
    ts_realtime: str
    ts_monotonic_ns: int
    actor: str
    action: str
    args_redacted: dict
    policy_level: PolicyLevel
    result: AuditResult
    workspace_id: str | None = None
    workspace_slug: str | None = None
    client_id: str | None = None
    approval_id: str | None = None
    error_code: str | None = None
    duration_ms: int | None = None
    outcomes_link: str | None = None


class NexusAuditStore(Protocol):
    """Persistence boundary. PR-NEXUS-5 wires the Supabase adapter."""
    def append(self, row: NexusAuditRow) -> str: ...


# ============================================================
# HMAC audit id
# ============================================================

def _load_audit_key() -> bytes:
    """Read the HMAC key set up by tmux_audit on first run, or create it.

    We share the same key file `~/.hermes/audit-key` across all audit
    surfaces so a single operator key rotation invalidates every ledger
    at once.
    """
    p = AUDIT_KEY_PATH
    if p.exists():
        st = p.stat()
        if (st.st_mode & 0o077) != 0:
            raise AuditUnwritableError(
                f"audit key {p} has insecure mode {oct(st.st_mode)}; expected 0o600"
            )
        return p.read_bytes()
    # First-run case: tmux_audit usually creates this. Generate ourselves.
    p.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    return key


def _hmac_id(prefix: str, ts: str, action: str, actor: str, key: bytes) -> str:
    canonical = json.dumps(
        {"ts": ts, "action": action, "actor": actor},
        sort_keys=True,
    ).encode("utf-8")
    digest = hmac.new(key, canonical, sha256).hexdigest()
    return f"{prefix}-{digest[:12]}"


# ============================================================
# Row construction + truncation
# ============================================================

def _serialise_args(args: dict) -> dict:
    """Apply secret redaction to every string value in args."""
    out: dict = {}
    for k, v in args.items():
        if isinstance(v, str):
            redacted, _counts = redact_secrets(v)
            out[k] = redacted
        elif isinstance(v, dict):
            out[k] = _serialise_args(v)
        elif isinstance(v, (list, tuple)):
            out[k] = [
                redact_secrets(item)[0] if isinstance(item, str) else item
                for item in v
            ]
        else:
            out[k] = v
    return out


def _truncate_row(row_dict: dict) -> dict:
    """If serialised row > 512B, truncate truncatable fields in order."""
    out = dict(row_dict)
    for field_name in _TRUNCATABLE_FIELDS:
        if len(json.dumps(out, separators=(",", ":"))) + 1 <= ATOMIC_WRITE_CAP_BYTES:
            return out
        if field_name not in out or not out[field_name]:
            continue
        if isinstance(out[field_name], dict):
            out[field_name] = {"_truncated": True, "_n_keys": len(out[field_name])}
        elif isinstance(out[field_name], str):
            out[field_name] = out[field_name][:50] + "[…truncated]"
    if len(json.dumps(out, separators=(",", ":"))) + 1 > ATOMIC_WRITE_CAP_BYTES:
        raise AuditRowTooLargeError(
            f"row {len(json.dumps(out))} > {ATOMIC_WRITE_CAP_BYTES} after truncation"
        )
    return out


# ============================================================
# Public API — build_audit_row
# ============================================================

def build_audit_row(
    *,
    actor: str,
    action: str,
    args: dict,
    policy_level: PolicyLevel,
    result: AuditResult,
    workspace_id: str | None = None,
    workspace_slug: str | None = None,
    client_id: str | None = None,
    approval_id: str | None = None,
    error_code: str | None = None,
    duration_ms: int | None = None,
    outcomes_link: str | None = None,
    now: datetime | None = None,
) -> NexusAuditRow:
    """Construct a fully-populated audit row.

    Raises:
        AuditUnwritableError  — HMAC key missing or insecure
        AuditRowTooLargeError — row exceeds 512B even after truncation

    The caller MUST persist via NexusAuditStore.append() — this function
    does NOT touch storage. Callers that fail to persist should refuse
    the state-changing action they were about to take.
    """
    now = now or datetime.now(timezone.utc)
    ts_realtime = now.isoformat().replace("+00:00", "Z")
    ts_monotonic_ns = time.monotonic_ns()

    try:
        key = _load_audit_key()
    except (OSError, AuditUnwritableError) as exc:
        raise AuditUnwritableError(f"audit key unavailable: {exc}") from exc

    audit_id = _hmac_id("nex", ts_realtime, action, actor, key)

    args_redacted = _serialise_args(args)

    raw = {
        "id": audit_id,
        "ts_realtime": ts_realtime,
        "ts_monotonic_ns": ts_monotonic_ns,
        "actor": actor,
        "action": action,
        "args_redacted": args_redacted,
        "policy_level": policy_level,
        "result": result,
        "workspace_id": workspace_id,
        "workspace_slug": workspace_slug,
        "client_id": client_id,
        "approval_id": approval_id,
        "error_code": error_code,
        "duration_ms": duration_ms,
        "outcomes_link": outcomes_link,
    }
    truncated = _truncate_row(raw)

    return NexusAuditRow(
        id=truncated["id"],
        ts_realtime=truncated["ts_realtime"],
        ts_monotonic_ns=truncated["ts_monotonic_ns"],
        actor=truncated["actor"],
        action=truncated["action"],
        args_redacted=truncated["args_redacted"],
        policy_level=truncated["policy_level"],
        result=truncated["result"],
        workspace_id=truncated["workspace_id"],
        workspace_slug=truncated["workspace_slug"],
        client_id=truncated["client_id"],
        approval_id=truncated["approval_id"],
        error_code=truncated["error_code"],
        duration_ms=truncated["duration_ms"],
        outcomes_link=truncated["outcomes_link"],
    )
