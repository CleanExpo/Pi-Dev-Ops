"""budget_tracker.py — RA-1909 phase-1 LLM cost tracking.

Records per-call LLM cost data to a local JSONL file
(`.harness/llm-cost.jsonl`) and best-effort to Supabase via supabase_log.

Phase-1 scope: visibility only. No ceiling enforcement at call sites yet.
The check_ceiling helper exists so callers / future enforcement work has a
deterministic API to call.

All public functions are defensive — file/network errors are swallowed.
record_cost MUST never raise; it is called from inside hot LLM dispatch
paths and a budget-tracker bug must never break an LLM call.

Storage:
  JSONL row schema:
    {
      "ts": "<utc-iso>",
      "tenant_id": "<str>",
      "provider": "<str>",
      "role": "<str>",
      "model": "<str>",
      "cost_usd": <float>,
      "tokens_in": <int>,
      "tokens_out": <int>
    }

  JSONL location: repo_root / ".harness/llm-cost.jsonl"
  Override via env BUDGET_TRACKER_LOG_PATH (absolute path).

  Supabase mirror: table `llm_costs` (created in
  supabase/migrations/<date>_llm_costs.sql).
"""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.budget_tracker")

DEFAULT_DAILY_LIMIT_USD = 20.00


def _log_path() -> Path:
    """Resolve the JSONL log path. Override via BUDGET_TRACKER_LOG_PATH env."""
    override = os.environ.get("BUDGET_TRACKER_LOG_PATH", "").strip()
    if override:
        return Path(override)
    # Default: repo_root / .harness / llm-cost.jsonl
    repo_root = Path(__file__).resolve().parents[1]
    return repo_root / ".harness" / "llm-cost.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_iso(day_iso: str | None = None) -> str:
    """Return YYYY-MM-DD in UTC for filtering today's rows."""
    if day_iso:
        return day_iso[:10]
    return datetime.now(timezone.utc).date().isoformat()


def record_cost(
    *,
    provider: str,
    role: str,
    model: str,
    cost_usd: float,
    tokens_in: int,
    tokens_out: int,
    tenant_id: str = "pi-ceo",
) -> None:
    """Record one LLM cost event.

    Writes a JSONL row to the local log AND best-effort to Supabase.
    Both writes are guarded — any exception is swallowed and logged at
    DEBUG level. This function MUST NOT raise.
    """
    try:
        ts = _utc_now_iso()
        row: dict[str, Any] = {
            "ts": ts,
            "tenant_id": str(tenant_id or "pi-ceo"),
            "provider": str(provider or "unknown"),
            "role": str(role or ""),
            "model": str(model or ""),
            "cost_usd": float(cost_usd or 0.0),
            "tokens_in": int(tokens_in or 0),
            "tokens_out": int(tokens_out or 0),
        }
    except Exception as exc:  # noqa: BLE001
        log.debug("budget_tracker: row build failed (non-fatal): %s", exc)
        return

    # Local JSONL — best effort
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.debug("budget_tracker: jsonl write failed (non-fatal): %s", exc)

    # Supabase mirror — best effort, must not break record_cost
    try:
        from app.server.supabase_log import _insert  # noqa: PLC0415
        _insert("llm_costs", row)
    except Exception as exc:  # noqa: BLE001
        log.debug("budget_tracker: supabase mirror failed (non-fatal): %s", exc)


def _iter_rows() -> list[dict[str, Any]]:
    """Read all rows from the JSONL log. Returns [] on any error."""
    path = _log_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception as exc:  # noqa: BLE001
        log.debug("budget_tracker: jsonl read failed (non-fatal): %s", exc)
        return []
    return rows


def _rows_for_day(
    day_iso: str | None = None,
    tenant_id: str = "pi-ceo",
) -> list[dict[str, Any]]:
    target = _today_iso(day_iso)
    out: list[dict[str, Any]] = []
    for r in _iter_rows():
        ts = str(r.get("ts", ""))
        if not ts.startswith(target):
            continue
        if tenant_id and str(r.get("tenant_id", "")) != tenant_id:
            continue
        out.append(r)
    return out


def daily_total_usd(
    *,
    day_iso: str | None = None,
    tenant_id: str = "pi-ceo",
) -> float:
    """Sum cost_usd for the given UTC day (default: today)."""
    try:
        rows = _rows_for_day(day_iso=day_iso, tenant_id=tenant_id)
        total = 0.0
        for r in rows:
            try:
                total += float(r.get("cost_usd", 0.0) or 0.0)
            except Exception:
                continue
        return round(total, 6)
    except Exception as exc:  # noqa: BLE001
        log.debug("budget_tracker: daily_total_usd failed: %s", exc)
        return 0.0


def by_provider_24h(
    *,
    tenant_id: str = "pi-ceo",
) -> dict[str, float]:
    """Aggregate today's spend by provider."""
    try:
        rows = _rows_for_day(tenant_id=tenant_id)
        out: dict[str, float] = defaultdict(float)
        for r in rows:
            prov = str(r.get("provider", "unknown") or "unknown")
            try:
                out[prov] += float(r.get("cost_usd", 0.0) or 0.0)
            except Exception:
                continue
        return {k: round(v, 6) for k, v in out.items()}
    except Exception as exc:  # noqa: BLE001
        log.debug("budget_tracker: by_provider_24h failed: %s", exc)
        return {}


def by_role_24h(
    *,
    tenant_id: str = "pi-ceo",
) -> dict[str, float]:
    """Aggregate today's spend by role."""
    try:
        rows = _rows_for_day(tenant_id=tenant_id)
        out: dict[str, float] = defaultdict(float)
        for r in rows:
            role = str(r.get("role", "") or "")
            try:
                out[role] += float(r.get("cost_usd", 0.0) or 0.0)
            except Exception:
                continue
        return {k: round(v, 6) for k, v in out.items()}
    except Exception as exc:  # noqa: BLE001
        log.debug("budget_tracker: by_role_24h failed: %s", exc)
        return {}


def check_ceiling(
    *,
    limit_usd: float | None = None,
    tenant_id: str = "pi-ceo",
) -> tuple[bool, float]:
    """Check today's spend vs the daily ceiling.

    Returns (over_limit, current_total_usd).

    Limit resolution:
      1. ``limit_usd`` arg if provided.
      2. ``DAILY_SPEND_LIMIT_USD`` env (float).
      3. ``DEFAULT_DAILY_LIMIT_USD`` (20.00).
    """
    try:
        if limit_usd is None:
            raw = os.environ.get("DAILY_SPEND_LIMIT_USD", "").strip()
            try:
                limit = float(raw) if raw else DEFAULT_DAILY_LIMIT_USD
            except Exception:
                limit = DEFAULT_DAILY_LIMIT_USD
        else:
            limit = float(limit_usd)
        total = daily_total_usd(tenant_id=tenant_id)
        return (total >= limit, total)
    except Exception as exc:  # noqa: BLE001
        log.debug("budget_tracker: check_ceiling failed: %s", exc)
        return (False, 0.0)


__all__ = [
    "record_cost",
    "daily_total_usd",
    "by_provider_24h",
    "by_role_24h",
    "check_ceiling",
    "DEFAULT_DAILY_LIMIT_USD",
]
