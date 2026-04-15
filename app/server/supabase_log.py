"""
supabase_log.py — Minimal Supabase REST write/read helper (RA-651, RA-633).

Uses stdlib urllib only (no supabase-py dependency). Reads NEXT_PUBLIC_SUPABASE_URL
and SUPABASE_SERVICE_ROLE_KEY from env via config.py.

All writes are fire-and-forget: errors are logged at WARNING level but never raised.
The pipeline must never fail because of an observability write.

Tables written:
  gate_checks        — RA-651: every /ship phase gate evaluation
  alert_escalations  — RA-633: critical Telegram alerts + escalation state
"""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger("pi-ceo.supabase_log")


# ── Config (lazy-loaded once) ─────────────────────────────────────────────────

_URL: str = ""
_KEY: str = ""


def _cfg() -> tuple[str, str]:
    global _URL, _KEY
    if not _URL:
        from . import config as _c
        _URL = _c.SUPABASE_URL
        _KEY = _c.SUPABASE_SERVICE_ROLE_KEY
    return _URL, _KEY


# ── Low-level REST helpers ─────────────────────────────────────────────────────

def _insert(table: str, row: dict[str, Any]) -> bool:
    url, key = _cfg()
    if not url or not key:
        log.debug("Supabase not configured — skipping insert into %s", table)
        return False
    payload = json.dumps(row).encode()
    req = urllib.request.Request(
        f"{url}/rest/v1/{table}",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Prefer": "return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
        return True
    except Exception as exc:
        log.warning("Supabase insert %s failed (non-fatal): %s", table, exc)
        return False


def _upsert(table: str, row: dict[str, Any]) -> bool:
    url, key = _cfg()
    if not url or not key:
        return False
    payload = json.dumps(row).encode()
    req = urllib.request.Request(
        f"{url}/rest/v1/{table}",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Prefer": "return=minimal,resolution=merge-duplicates",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
        return True
    except Exception as exc:
        log.warning("Supabase upsert %s failed (non-fatal): %s", table, exc)
        return False


def _patch(table: str, filter_param: str, patch: dict[str, Any]) -> bool:
    url, key = _cfg()
    if not url or not key:
        return False
    payload = json.dumps(patch).encode()
    req = urllib.request.Request(
        f"{url}/rest/v1/{table}?{filter_param}",
        data=payload,
        method="PATCH",
        headers={
            "Content-Type": "application/json",
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Prefer": "return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
        return True
    except Exception as exc:
        log.warning("Supabase patch %s failed (non-fatal): %s", table, exc)
        return False


def _select(table: str, params: str) -> list[dict[str, Any]]:
    url, key = _cfg()
    if not url or not key:
        return []
    req = urllib.request.Request(
        f"{url}/rest/v1/{table}?{params}",
        method="GET",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        log.warning("Supabase select %s failed: %s", table, exc)
        return []


# ── RA-651: gate_checks ───────────────────────────────────────────────────────

def log_gate_check(
    *,
    pipeline_id: str,
    session_id: str | None,
    gate_checks: dict[str, bool],
    review_score: float,
    shipped: bool,
    session_started_at: float | None = None,
    push_timestamp: float | None = None,
    confidence: float | None = None,
    scope_adhered: bool | None = None,
    files_modified: int | None = None,
    linear_state_after: str | None = None,
) -> None:
    """
    Write one gate_check row to Supabase after every /ship phase.
    Called from pipeline.run_ship_phase() — non-blocking, never raises.

    RA-672: session_started_at (unix epoch) and push_timestamp (unix epoch) are
    used by zte_v2_score.py to compute C3 (mean time to value).
    RA-674: confidence (0-100%) is the evaluator's self-reported certainty score.
    RA-676: scope_adhered (bool) and files_modified (int) track scope contract results.
    RA-672 C2: linear_state_after persists Linear issue state at push time to Supabase
    so C2 scoring survives Railway redeploys (session-outcomes.jsonl is ephemeral).
    """
    row: dict = {
        "pipeline_id":    pipeline_id,
        "session_id":     session_id,
        "spec_exists":    gate_checks.get("spec_exists", False),
        "plan_exists":    gate_checks.get("plan_exists", False),
        "build_complete": gate_checks.get("build_complete", False),
        "tests_passed":   gate_checks.get("tests_passed", False),
        "review_passed":  gate_checks.get("review_passed", False),
        "all_passed":     all(gate_checks.values()),
        "review_score":   review_score,
        "shipped":        shipped,
        "checked_at":     datetime.now(timezone.utc).isoformat(),
    }
    if session_started_at is not None:
        row["session_started_at"] = datetime.fromtimestamp(
            session_started_at, tz=timezone.utc
        ).isoformat()
    if push_timestamp is not None:
        row["push_timestamp"] = datetime.fromtimestamp(
            push_timestamp, tz=timezone.utc
        ).isoformat()
    if confidence is not None:
        row["confidence"] = confidence
    if scope_adhered is not None:
        row["scope_adhered"] = scope_adhered
    if files_modified is not None:
        row["files_modified"] = files_modified
    if linear_state_after is not None:
        row["linear_state_after"] = linear_state_after
    _insert("gate_checks", row)
    log.info(
        "gate_check logged: pipeline=%s all_passed=%s score=%.1f confidence=%s "
        "scope_adhered=%s files=%s shipped=%s",
        pipeline_id, all(gate_checks.values()), review_score,
        f"{confidence:.0f}%" if confidence is not None else "n/a",
        scope_adhered, files_modified, shipped,
    )


# ── RA-633: alert_escalations ─────────────────────────────────────────────────

def log_alert_escalation(
    *,
    alert_key: str,
    project_id: str,
    issue_title: str,
    severity: str = "critical",
    linear_ticket: str | None = None,
    telegram_sent: bool = False,
) -> None:
    """
    Upsert an alert_escalations row when a Telegram alert fires.
    alert_key is the finding fingerprint or Linear ticket identifier.
    Conflict on alert_key → merge (don't duplicate rows for the same finding).
    """
    now = datetime.now(timezone.utc).isoformat()
    _upsert("alert_escalations", {
        "alert_key":       alert_key,
        "project_id":      project_id,
        "issue_title":     issue_title,
        "severity":        severity,
        "linear_ticket":   linear_ticket,
        "telegram_sent":   telegram_sent,
        "telegram_sent_at": now if telegram_sent else None,
        "escalated":       False,
        "acked":           False,
        "created_at":      now,
    })


def fetch_unacknowledged_alerts(max_age_minutes: int = 30) -> list[dict[str, Any]]:
    """
    RA-633 — Return critical alerts that:
      - were sent via Telegram
      - have NOT been acknowledged
      - have NOT already been escalated
      - were sent more than `max_age_minutes` ago

    Called by the escalation watchdog in cron.py every 30 minutes.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)).isoformat()
    params = (
        f"telegram_sent=eq.true"
        f"&escalated=eq.false"
        f"&acked=eq.false"
        f"&telegram_sent_at=lt.{cutoff}"
        f"&limit=20"
        f"&order=telegram_sent_at.asc"
    )
    return _select("alert_escalations", params)


def mark_alert_escalated(alert_key: str) -> None:
    """RA-633 — Mark an alert as escalated after the second Telegram page fires."""
    _patch(
        "alert_escalations",
        f"alert_key=eq.{alert_key}",
        {
            "escalated":    True,
            "escalated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def mark_alert_acked(alert_key: str) -> None:
    """RA-633 — Mark an alert as acknowledged (called from Telegram /ack command)."""
    _patch(
        "alert_escalations",
        f"alert_key=eq.{alert_key}",
        {
            "acked":    True,
            "acked_at": datetime.now(timezone.utc).isoformat(),
        },
    )


# ── RA-820: notebooklm_health ─────────────────────────────────────────────────

def log_notebooklm_health(
    *,
    notebook_id: str,
    notebook_name: str,
    query_hash: str,
    status: str,
    error_message: str | None = None,
    response_ms: int | None = None,
) -> None:
    """
    RA-820 — Write one notebooklm_health row after each health probe.
    Called from _watchdog_notebooklm_health() in cron_watchdogs.py.
    Fire-and-forget — never raises.
    """
    _insert("notebooklm_health", {
        "notebook_id":   notebook_id,
        "notebook_name": notebook_name,
        "query_hash":    query_hash,
        "status":        status,
        "error_message": error_message,
        "response_ms":   response_ms,
        "checked_at":    datetime.now(timezone.utc).isoformat(),
    })
