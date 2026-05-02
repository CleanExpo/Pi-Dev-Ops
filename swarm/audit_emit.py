"""
swarm/audit_emit.py — RA-1839: Centralised, schema-enforced audit boundary.

Single emit point for every audit row produced by:
  * draft_review (draft_posted, draft_reaction, draft_expired)
  * flow_engine (flow_start, step_start, step_complete, step_error, flow_end)
  * intent_router → CoS (cos_intent_classified, cos_routed)
  * meta-curator (curator_proposal, curator_accepted, curator_rejected)
  * kill-switch (kill_switch_triggered, kill_switch_resumed)
  * pii_redactor (pii_redacted)

Schema is enforced at the boundary — unknown types raise ValueError,
not silently dropped. Migration plan in skills/audit-emit/SKILL.md
allows incremental adoption (per-module rewrite).

Optional Langfuse sink: when LANGFUSE_HOST + LANGFUSE_PUBLIC_KEY +
LANGFUSE_SECRET_KEY are set, every row is also POSTed to Langfuse
on a thread-pool. Local jsonl write is the source of truth.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.audit_emit")

# Whitelist of types — keep tight. Adding a new type requires a code change
# (intentional: prevents silently-dropping new producers from showing up
# without anyone noticing the schema isn't covering them).
_VALID_TYPES: set[str] = {
    # draft_review
    "draft_posted", "draft_reaction", "draft_expired",
    "draft_pii_aborted", "draft_send_pii_aborted",
    # flow_engine
    "flow_start", "flow_end",
    "step_start", "step_complete", "step_error",
    # CoS / intent_router
    "cos_intent_classified", "cos_routed",
    # meta-curator
    "curator_proposal", "curator_accepted", "curator_rejected",
    # kill-switch
    "kill_switch_triggered", "kill_switch_resumed",
    # pii redactor
    "pii_redacted",
    # CFO (RA-1850, Wave 4.1)
    "cfo_metric_snapshot", "cfo_alert",
    "cfo_invoice_approved", "cfo_spend_blocked",
    "cfo_brief_emitted",
}

# Fields we never redact (safe-by-construction)
_NEVER_REDACT = {"ts", "type", "actor_role", "session_id", "flow_id",
                "step_id", "draft_id", "level"}

MAX_ROW_BYTES = 64 * 1024


def _config():
    from . import config as _cfg
    return _cfg


def _audit_file() -> Path:
    cfg = _config()
    cfg.SWARM_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return cfg.SWARM_LOG_DIR / "swarm.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _maybe_redact(fields: dict[str, Any]) -> dict[str, Any]:
    """Redact long string fields before write. Caller can opt out per-field."""
    no_redact = set(fields.pop("__no_redact", []))
    out: dict[str, Any] = {}
    redactor = None
    for k, v in fields.items():
        if k in _NEVER_REDACT or k in no_redact:
            out[k] = v
            continue
        if isinstance(v, str) and len(v) > 32:
            if redactor is None:
                try:
                    from . import pii_redactor as _r
                    redactor = _r
                except Exception:
                    redactor = False  # mark "import failed; skip silently"
            if redactor:
                try:
                    res = redactor.redact(v, context="audit_emit",
                                         strictness="standard")
                    out[k] = res.redacted_payload
                    continue
                except Exception as exc:
                    log.debug("redact-on-emit failed for %s: %s", k, exc)
        out[k] = v
    return out


def _truncate(row: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(row, ensure_ascii=False)
    if len(raw.encode("utf-8")) <= MAX_ROW_BYTES:
        return row
    # Truncate the largest string field
    largest_key, largest_len = None, 0
    for k, v in row.items():
        if isinstance(v, str) and len(v) > largest_len:
            largest_key, largest_len = k, len(v)
    if largest_key is None:
        return row  # nothing to do
    over_by = len(raw.encode("utf-8")) - MAX_ROW_BYTES
    cut_to = max(64, len(row[largest_key]) - over_by - 200)
    row[largest_key] = row[largest_key][:cut_to] + " ...[truncated]"
    row["truncated_at"] = cut_to
    row["truncated_field"] = largest_key
    return row


def _langfuse_post(row: dict[str, Any]) -> None:
    """Fire-and-forget POST to Langfuse. Never raises."""
    host = os.environ.get("LANGFUSE_HOST")
    pub = os.environ.get("LANGFUSE_PUBLIC_KEY")
    sec = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (host and pub and sec):
        return
    if os.environ.get("TAO_SWARM_ENABLED", "0") != "1":
        # Suppress Langfuse on halted swarm — local write is the source of truth
        return
    try:
        import base64
        creds = base64.b64encode(f"{pub}:{sec}".encode()).decode()
        payload = json.dumps({
            "events": [{"type": row["type"], "metadata": row}]
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{host.rstrip('/')}/api/public/ingestion",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Basic {creds}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception as exc:
        log.warning("langfuse post failed: %s", exc)


def row(
    type: str,
    actor_role: str,
    *,
    session_id: str | None = None,
    flow_id: str | None = None,
    step_id: str | None = None,
    draft_id: str | None = None,
    **fields: Any,
) -> None:
    """Emit one audit row. Synchronous local write; async Langfuse mirror.

    Raises ValueError on unknown `type` — unknown types must be added
    to _VALID_TYPES intentionally; this prevents silent schema drift.
    """
    if type not in _VALID_TYPES:
        raise ValueError(
            f"unknown audit type: {type!r}. "
            f"Add to _VALID_TYPES if intentional."
        )

    rec: dict[str, Any] = {
        "ts": _now_iso(),
        "type": type,
        "actor_role": actor_role,
    }
    for k, v in (("session_id", session_id), ("flow_id", flow_id),
                 ("step_id", step_id), ("draft_id", draft_id)):
        if v is not None:
            rec[k] = v
    if fields:
        rec["fields"] = _maybe_redact(dict(fields))

    rec = _truncate(rec)

    # Synchronous local write (atomic-append)
    with _audit_file().open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Async Langfuse mirror (fire-and-forget thread)
    threading.Thread(target=_langfuse_post, args=(rec,), daemon=True).start()


__all__ = ["row"]
