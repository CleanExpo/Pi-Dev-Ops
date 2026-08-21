"""
supabase_log.py — Minimal Supabase REST write/read helper (RA-651, RA-633).

Uses stdlib urllib only (no supabase-py dependency). Reads NEXT_PUBLIC_SUPABASE_URL
and SUPABASE_SERVICE_ROLE_KEY from env via config.py.

All writes are fire-and-forget: errors are logged at WARNING level but never raised.
The pipeline must never fail because of an observability write.

Tables written:
  gate_checks        — RA-651: every /ship phase gate evaluation
  alert_escalations  — RA-633: critical Telegram alerts + escalation state
  lessons_durable    — RA-7111: runtime lesson appends (write-through + boot hydration)
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
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


# ── Filter-value escaping (RA-7219) ───────────────────────────────────────────

def _q(value: Any) -> str:
    """Percent-encode a value for use inside a PostgREST filter.

    Every filter in this module is built by f-string interpolation. An
    unescaped `&` starts a NEW filter parameter and an unescaped `=` splits the
    operator, so a value containing either silently BROADENS the query instead
    of erroring — and a PATCH whose filter is broadened updates rows it was
    never meant to touch. `_patch` only checks the HTTP status, so that failure
    is invisible.

    Not an injection fix: every caller's value arrives on a signature-verified
    webhook or is generated internally. The sharp one is `alert_key`, whose own
    docstring calls it a "finding fingerprint" — arbitrary content by
    construction. safe="" so that `&`, `=` and `/` are all encoded; repo names
    like CleanExpo/Pi-Dev-Ops encode their slash, which PostgREST decodes back.
    """
    return urllib.parse.quote(str(value), safe="")


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
    linear_issue_id: str | None = None,
    repo_name: str | None = None,
    pr_number: int | None = None,
    head_branch: str | None = None,
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
    # RA-7216: the join key. `record_acceptance()` below is driven by a Linear
    # webhook, which knows only the issue id — without this column an acceptance
    # event has no gate_checks row to attach to, and first-pass acceptance,
    # trigger-to-accepted and review latency all stay unmeasurable.
    if linear_issue_id:
        row["linear_issue_id"] = linear_issue_id
    # RA-7216 gap 2: the ship-time half of the attribution keys. `record_merge()`
    # matches on (repo_name, pr_number) — pr_number alone is unique only within a
    # repo, and Pi-CEO ships to many. Written only when non-empty so a session
    # that opened no PR does not leave a row matchable by an empty key.
    if repo_name:
        row["repo_name"] = repo_name
    if pr_number:
        row["pr_number"] = int(pr_number)
    if head_branch:
        row["head_branch"] = head_branch
    _insert("gate_checks", row)
    log.info(
        "gate_check logged: pipeline=%s all_passed=%s score=%.1f confidence=%s "
        "scope_adhered=%s files=%s shipped=%s",
        pipeline_id, all(gate_checks.values()), review_score,
        f"{confidence:.0f}%" if confidence is not None else "n/a",
        scope_adhered, files_modified, shipped,
    )


# ── RA-7216: acceptance events ────────────────────────────────────────────────

def record_acceptance(
    *,
    linear_issue_id: str,
    state_name: str,
    state_type: str,
    occurred_at: str | None = None,
) -> bool:
    """RA-7216 — Stamp the terminal Linear outcome onto this issue's gate_checks row.

    Called from the Linear webhook when an issue reaches a terminal state. This
    is the only writer of `accepted_at`, and `accepted_at` is what makes
    first-pass acceptance, trigger-to-accepted-outcome and review latency
    measurable. Review latency is derived at read time as
    `accepted_at - push_timestamp` (the founder's chosen instrument, 14/08/2026)
    rather than stored, so there is one source of truth and no column to drift.

    `state_type` distinguishes an acceptance ("completed") from a rejection
    ("canceled"); both are recorded. Writing only acceptances would reproduce the
    defect this ticket exists to fix — a numerator with no denominator.

    Only rows whose `accepted_at` is still null are patched, so the FIRST
    terminal transition wins. That makes a retried webhook idempotent, and it
    keeps the metric honest when an issue is reopened and closed again: the
    reopen is rework, and it must not be able to overwrite the original outcome
    and disguise itself as a clean first pass.

    Fire-and-forget per module doctrine: returns False on any failure, never raises.
    """
    if not linear_issue_id or not state_type:
        return False
    patch: dict[str, Any] = {
        "accepted_at": occurred_at or datetime.now(timezone.utc).isoformat(),
        "accepted_state": state_name or "",
        "accepted_state_type": state_type,
    }
    ok = _patch(
        "gate_checks",
        f"linear_issue_id=eq.{_q(linear_issue_id)}&accepted_at=is.null",
        patch,
    )
    log.info(
        "RA-7216 acceptance recorded: issue=%s state=%s type=%s ok=%s",
        linear_issue_id, state_name, state_type, ok,
    )
    return ok


def record_merge(
    *,
    repo_name: str,
    pr_number: int,
    merge_sha: str,
    merged_at: str | None = None,
) -> bool:
    """RA-7216 gap 2 — stamp the merge identity onto this PR's gate_checks row.

    Called from the GitHub webhook when a pull request closes as merged. This is
    the second half of the attribution keys: `merge_sha` is the value a future
    revert detector matches against, and it does not exist at ship time because
    the PR is only opened then, not merged.

    Matches on (repo_name, pr_number). Both are required — `pr_number` is unique
    only within a repository, so matching on it alone would stamp a merge in one
    portfolio repo onto a gate_check row from another.

    Only rows whose `merge_sha` is still null are patched, so the first merge
    wins. A PR cannot merge twice, but a redelivered webhook can arrive twice,
    and GitHub redelivers freely — this makes the write idempotent rather than
    relying on that not happening.

    Fire-and-forget per module doctrine: returns False on any failure, never raises.
    """
    if not repo_name or not pr_number or not merge_sha:
        return False
    ok = _patch(
        "gate_checks",
        f"repo_name=eq.{_q(repo_name)}&pr_number=eq.{int(pr_number)}&merge_sha=is.null",
        {
            "merge_sha": merge_sha,
            "merged_at": merged_at or datetime.now(timezone.utc).isoformat(),
        },
    )
    log.info(
        "RA-7216 merge recorded: repo=%s pr=%s sha=%s ok=%s",
        repo_name, pr_number, merge_sha[:12], ok,
    )
    return ok


# ── RA-7216 gap 2: outcome events ─────────────────────────────────────────────

def find_gate_check_by_merge_sha(merge_sha: str) -> int | None:
    """Return the gate_checks.id whose merge_sha matches, or None.

    Prefix match: a revert commit body may name a short SHA (`This reverts
    commit a1b2c3d.`) while the stored merge_sha is full-length, so an equality
    match would miss. `like.<sha>*` resolves both. Returns None on no match —
    the caller records the event with a NULL gate_check_id rather than dropping
    it, per the §9 decision.
    """
    if not merge_sha:
        return None
    rows = _select("gate_checks", f"select=id&merge_sha=like.{_q(merge_sha)}*&limit=2")
    if len(rows) != 1:
        # 0 = unattributable. >1 = ambiguous prefix, which must NOT be guessed:
        # attributing a revert to the wrong session is worse than not attributing it.
        return None
    try:
        return int(rows[0]["id"])
    except (KeyError, TypeError, ValueError):
        return None


def find_accepted_gate_check(linear_issue_id: str) -> int | None:
    """Return the gate_checks.id for an issue that has ALREADY been accepted.

    This is Detector B's whole basis. The design proposed inferring a reopen
    from a PATCH that matched no rows; that conflates "already accepted" with
    "Pi-CEO never shipped this issue" — two different facts, and the metric
    would be wrong in a way nothing surfaces. An explicit lookup cannot make
    that mistake. Superseded in .spm/RA-7216-completion.md §8.
    """
    if not linear_issue_id:
        return None
    rows = _select(
        "gate_checks",
        f"select=id&linear_issue_id=eq.{_q(linear_issue_id)}"
        f"&accepted_at=not.is.null&limit=1",
    )
    try:
        return int(rows[0]["id"]) if rows else None
    except (KeyError, TypeError, ValueError):
        return None


def record_outcome_event(
    *,
    kind: str,
    repo_name: str,
    occurred_at: str,
    detected_by: str,
    gate_check_id: int | None = None,
    merge_sha: str | None = None,
    event_sha: str | None = None,
    raw_ref: str | None = None,
) -> bool:
    """RA-7216 gap 2 — append one post-merge outcome. Fire-and-forget.

    Append-only: nothing here updates an existing row. A duplicate delivery
    collides with `outcome_events_dedupe_idx` and the insert fails; that is the
    intended outcome and is not retried, so redelivery is idempotent without a
    read-modify-write.
    """
    if not kind or not repo_name or not occurred_at:
        return False
    row: dict[str, Any] = {
        "kind": kind,
        "repo_name": repo_name,
        "occurred_at": occurred_at,
        "detected_by": detected_by or "unknown",
    }
    if gate_check_id is not None:
        row["gate_check_id"] = int(gate_check_id)
    if merge_sha:
        row["merge_sha"] = merge_sha
    if event_sha:
        row["event_sha"] = event_sha
    if raw_ref:
        row["raw_ref"] = raw_ref
    ok = _insert("outcome_events", row)
    log.info(
        "RA-7216 outcome_event: kind=%s repo=%s attributed=%s sha=%s ok=%s",
        kind, repo_name, gate_check_id is not None,
        (event_sha or "")[:12], ok,
    )
    return ok


def is_recorded_revert(event_sha: str) -> bool:
    """True when this SHA is itself a previously-recorded revert.

    A revert of a revert re-lands the original change; counting it as a second
    rollback would double-penalise a recovery. Detector A uses this to classify
    such an event as `re_land`, which is excluded from C1's numerator.
    """
    if not event_sha:
        return False
    rows = _select(
        "outcome_events",
        f"select=id&kind=eq.revert&event_sha=like.{_q(event_sha)}*&limit=1",
    )
    return bool(rows)


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
        from .senior_harness_admission import api_projection  # noqa: PLC0415

        senior_harness = api_projection(session)
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
                "senior_harness_observation_status": senior_harness["status"],
                "senior_harness_admission_ref": senior_harness["admission_ref"],
                "senior_harness_reservation": copy.deepcopy(senior_harness["reservation"]),
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

    Survives Railway redeploys. The committed `config/harness/cron-triggers.json`
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
    schedule defined in `config/harness/cron-triggers.json`. Empty dict on
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
        f"alert_key=eq.{_q(alert_key)}",
        {
            "escalated":    True,
            "escalated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def mark_alert_acked(alert_key: str) -> None:
    """RA-633 — Mark an alert as acknowledged (called from Telegram /ack command)."""
    _patch(
        "alert_escalations",
        f"alert_key=eq.{_q(alert_key)}",
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


# ── RA-7014 slice 4: eval_candidates — online-eval capture queue ──────────────

def insert_eval_candidate(row: dict[str, Any]) -> bool:
    """Fire-and-forget insert of a redacted classifier call. Spec:
    docs/specs/spec-cap5-slice4-online-eval.md. Returns False when Supabase is
    unconfigured or the insert fails — caller falls back to the local JSONL."""
    return _insert("eval_candidates", row)


def select_eval_candidates(status: str = "pending", limit: int = 50) -> list[dict[str, Any]]:
    """Fetch capture-queue rows for the founder promotion CLI."""
    return _select("eval_candidates", f"status=eq.{_q(status)}&order=captured_at.asc&limit={int(limit)}")


def update_eval_candidate_status(candidate_id: int, status: str) -> bool:
    """Mark a candidate promoted/rejected after founder review."""
    return _patch("eval_candidates", f"id=eq.{int(candidate_id)}", {"status": status})


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
        f"tenant_id=eq.{_q(tenant_id)}"
        f"&chat_id=eq.{_q(chat_id)}"
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


# ── RA-7111: lessons_durable — cross-deploy lesson persistence ────────────────

def save_lesson(entry: dict[str, Any]) -> bool:
    """RA-7111 — Write-through one runtime lesson append to lessons_durable.

    Idempotent: the primary key is the sha256 of the canonical JSON line, and
    _upsert's merge-duplicates resolves PK conflicts, so a retried write lands on
    itself. Fire-and-forget per module doctrine — the local append has already
    succeeded before this is called, so a failure here costs durability of one
    row, never availability.
    """
    line = json.dumps(entry, sort_keys=True)
    row_hash = hashlib.sha256(line.encode("utf-8")).hexdigest()
    return _upsert("lessons_durable", {"hash": row_hash, "line": entry})


def fetch_lessons_since(iso_watermark: str) -> list[dict[str, Any]]:
    """RA-7111 — Rows at-or-after the watermark, oldest first, for boot hydration.

    gte, not gt (review of 58e28fc4): a strict cursor permanently dropped rows sharing
    the watermark timestamp that became visible after it was persisted. Boundary rows
    are therefore re-fetched on every boot and the hydrator's content-hash
    reconciliation skips the ones already in the file — no omission, no duplication.

    Returns [{"line": {...}, "created_at": "..."}]. Empty list on any failure
    (including unset Supabase env) — hydration is best-effort by design.
    """
    return _select(
        "lessons_durable",
        f"select=line,created_at&created_at=gte.{iso_watermark}&order=created_at.asc",
    )
