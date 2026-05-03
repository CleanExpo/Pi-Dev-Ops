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


# ── RA-1407: sessions table checkpointing ────────────────────────────────────

def _repo_name_from_url(repo_url: str) -> str:
    """Extract repo_name (e.g. 'CleanExpo/Pi-Dev-Ops') from a github URL."""
    if not repo_url:
        return "unknown"
    s = repo_url.rstrip("/").rstrip(".git")
    parts = s.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return s


def save_session_checkpoint(session) -> bool:
    """RA-1407 — Persist session checkpoint to Supabase `sessions` table.

    Fire-and-forget: any failure logs WARN and returns False. The build
    pipeline must NEVER block on observability writes (RA-1109 surface
    treatment compliance — but unlike a dashboard surface, this is the
    canonical persistence path. JSON local file remains the fallback).

    Uses the `_upsert` helper so repeated calls during a build update the
    same row (keyed by `id` PK). The full resume state lives in the
    `checkpoint` JSONB column added by the RA-1407 migration.

    Returns True on success, False on Supabase unavailable / error.
    """
    if session is None or not getattr(session, "id", ""):
        return False
    try:
        repo_url = getattr(session, "repo_url", "") or ""
        status = (getattr(session, "status", "") or "running").lower()
        terminal_states = {
            "complete", "done", "failed", "error",
            "killed", "interrupted", "blocked",
        }
        row: dict[str, Any] = {
            "id": session.id,
            "repo_url": repo_url,
            "repo_name": _repo_name_from_url(repo_url),
            "branch": getattr(session, "branch", "") or "",
            "status": status,
            "trigger": getattr(session, "trigger", "manual") or "manual",
            "started_at": _iso_or_now(getattr(session, "started_at", None)),
            "checkpoint": {
                "last_completed_phase": getattr(session, "last_completed_phase", "") or "",
                "retry_count":       int(getattr(session, "retry_count", 0) or 0),
                "evaluator_status":  getattr(session, "evaluator_status", "pending") or "pending",
                "evaluator_score":   getattr(session, "evaluator_score", None),
                "evaluator_model":   getattr(session, "evaluator_model", "") or "",
                "evaluator_consensus": getattr(session, "evaluator_consensus", "") or "",
                "linear_issue_id":   getattr(session, "linear_issue_id", None),
                "workspace":         getattr(session, "workspace", "") or "",
                "error":             getattr(session, "error", "") or "",
                "output_line_count": len(getattr(session, "output_lines", []) or []),
            },
        }
        if status in terminal_states:
            row["completed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return _upsert("sessions", row)
    except Exception as exc:
        log.warning("RA-1407 save_session_checkpoint failed (non-fatal): %s", exc)
        return False


def fetch_interrupted_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """RA-1407 — Return sessions in `status='interrupted'` for startup recovery.

    Used by the startup hook (RA-1407 PR 2) to auto-enqueue resume calls.
    Fail-soft: returns empty list if Supabase unavailable.
    """
    try:
        return _select(
            "sessions",
            f"status=eq.interrupted&order=started_at.desc&limit={int(limit)}",
        )
    except Exception as exc:
        log.warning("RA-1407 fetch_interrupted_sessions failed: %s", exc)
        return []


def _iso_or_now(ts: Any) -> str:
    """Best-effort ISO timestamp from a float epoch / str / None."""
    try:
        if isinstance(ts, (int, float)) and ts > 0:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")
        if isinstance(ts, str) and ts:
            return ts
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── RA-1439: cron_state — durable last_fired_at per trigger ──────────────────

def save_cron_last_fired(trigger_id: str, last_fired_at: float) -> bool:
    """RA-1439 — Persist a single trigger's last_fired_at to Supabase cron_state.

    Survives Railway redeploys. The committed `.harness/cron-triggers.json`
    otherwise resets last_fired_at on every container boot, defeating
    catch-up because the next deploy reverts again before save persists.

    Fire-and-forget: returns False on any failure but never raises.
    """
    if not trigger_id or last_fired_at is None or last_fired_at <= 0:
        return False
    try:
        ts = datetime.fromtimestamp(float(last_fired_at), tz=timezone.utc).isoformat(timespec="seconds")
        return _upsert("cron_state", {
            "trigger_id": trigger_id,
            "last_fired_at": ts,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    except Exception as exc:
        log.warning("RA-1439 save_cron_last_fired failed (non-fatal): %s", exc)
        return False


def load_cron_state() -> dict[str, float]:
    """RA-1439 — Return {trigger_id: last_fired_at_epoch_seconds} from Supabase.

    Used by `cron_store._load_triggers()` to overlay durable state onto the
    schedule defined in `.harness/cron-triggers.json`. Empty dict on
    Supabase outage — caller falls back to JSON's value (which may be
    frozen but at least lets the system keep running).
    """
    try:
        rows = _select("cron_state", "select=trigger_id,last_fired_at&limit=200")
        out: dict[str, float] = {}
        for r in rows:
            tid = r.get("trigger_id", "")
            ts_str = r.get("last_fired_at", "")
            if not tid or not ts_str:
                continue
            try:
                # Postgres returns ISO with offset; fromisoformat accepts
                # trailing Z on Python 3.11+, normalise just in case.
                ts_norm = ts_str.replace("Z", "+00:00")
                out[tid] = datetime.fromisoformat(ts_norm).timestamp()
            except Exception:
                continue
        return out
    except Exception as exc:
        log.warning("RA-1439 load_cron_state failed (non-fatal): %s", exc)
        return {}


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


# ── RA-1905: margot_conversations — durable Margot memory ────────────────────

def insert_margot_conversation(row: dict[str, Any]) -> bool:
    """RA-1905 — Insert a Margot turn into the durable margot_conversations
    table. Fire-and-forget: any failure logs WARN and returns False.

    JSONL on Railway disk is a hot cache; this table is the source of truth
    that survives redeploys.
    """
    return _insert("margot_conversations", row)


def select_margot_conversations(
    *,
    chat_id: str,
    limit: int = 10,
    tenant_id: str = "pi-ceo",
) -> list[dict[str, Any]]:
    """RA-1905 — Return up to `limit` most-recent Margot turns for `chat_id`,
    ordered by started_at desc. Returns [] when Supabase is unconfigured or
    on any error (caller falls back to JSONL cache).
    """
    if not chat_id:
        return []
    params = (
        f"tenant_id=eq.{tenant_id}"
        f"&chat_id=eq.{chat_id}"
        f"&order=started_at.desc"
        f"&limit={int(limit)}"
    )
    return _select("margot_conversations", params)


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
