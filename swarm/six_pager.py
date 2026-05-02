"""swarm/six_pager.py — RA-1863 (Wave 4 A5): Daily 6-pager assembler.

Stripe-style executive brief. Reads each senior-agent's prior-cycle
metrics from its jsonl ledger (cfo / cmo / cto / cs), pulls the most
recent Margot deep-async insight, and the current RA-1842 (iOS release)
status. Renders one composed brief that the founder can read in 10
minutes.

Used by:
* the orchestrator daily-fire window (06:00 UTC) — invoke
  ``assemble_six_pager()`` and post via ``draft_review.post_draft``
* the CoS bot when the founder asks "what's the picture?" via Telegram

Composes (does not call the SDK or any external API by itself):
* CFO snippet  — last cfo_state.jsonl rows + breach roll-up
* CMO snippet  — last cmo_state.jsonl rows + breach roll-up
* CTO snippet  — last cto_state.jsonl rows + breach roll-up
* CS snippet   — last cs_state.jsonl rows + breach roll-up
* Margot insight (latest from .harness/margot/insights.jsonl if present)
* RA-1842 status (latest from .harness/ra-1842-status.json if present)

Pure-ish: no network. Reads files only. Returns a string.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import cfo as _cfo
from . import cmo as _cmo
from . import cs as _cs
from . import cto as _cto

log = logging.getLogger("swarm.six_pager")

REPO_ROOT = Path(__file__).resolve().parents[1]

MARGOT_INSIGHTS_REL = ".harness/margot/insights.jsonl"
RA_1842_STATUS_REL = ".harness/ra-1842-status.json"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now_utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_last_per_business(jsonl_rel: str,
                             *,
                             repo_root: Path) -> list[dict[str, Any]]:
    """Read the per-business last row of a snapshot jsonl ledger."""
    p = repo_root / jsonl_rel
    if not p.exists():
        return []
    last_per_biz: dict[str, dict[str, Any]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        bid = row.get("business_id")
        if bid:
            last_per_biz[bid] = row
    return list(last_per_biz.values())


def _load_latest_margot_insight(repo_root: Path) -> dict[str, Any] | None:
    p = repo_root / MARGOT_INSIGHTS_REL
    if not p.exists():
        return None
    last_row: dict[str, Any] | None = None
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last_row = json.loads(line)
        except Exception:
            continue
    return last_row


def _load_ra_1842_status(repo_root: Path) -> dict[str, Any] | None:
    p = repo_root / RA_1842_STATUS_REL
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── Page-builder helpers ─────────────────────────────────────────────────────


def _cfo_section(repo_root: Path) -> str:
    rows = _load_last_per_business(_cfo.CFO_STATE_FILE_REL, repo_root=repo_root)
    if not rows:
        return "💰 CFO — no recent snapshots in cfo_state.jsonl."
    snaps: list[_cfo.Metrics] = []
    for r in rows:
        try:
            snaps.append(_cfo.Metrics(**r))
        except Exception:
            continue
    breaches: list[_cfo.Breach] = []
    for s in snaps:
        breaches.extend(_cfo.detect_breaches(s))
    return _cfo.assemble_daily_brief(snaps, breaches)


def _cmo_section(repo_root: Path) -> str:
    rows = _load_last_per_business(_cmo.CMO_STATE_FILE_REL, repo_root=repo_root)
    if not rows:
        return "📈 CMO — no recent snapshots in cmo_state.jsonl."
    snaps: list[_cmo.MarketingMetrics] = []
    for r in rows:
        try:
            snaps.append(_cmo.MarketingMetrics(**r))
        except Exception:
            continue
    breaches: list[_cmo.MarketingBreach] = []
    for s in snaps:
        breaches.extend(_cmo.detect_breaches(s))
    return _cmo.assemble_daily_brief(snaps, breaches)


def _cto_section(repo_root: Path) -> str:
    rows = _load_last_per_business(_cto.CTO_STATE_FILE_REL, repo_root=repo_root)
    if not rows:
        return "⚙️ CTO — no recent snapshots in cto_state.jsonl."
    snaps: list[_cto.PlatformMetrics] = []
    for r in rows:
        try:
            snaps.append(_cto.PlatformMetrics(**r))
        except Exception:
            continue
    breaches: list[_cto.PlatformBreach] = []
    for s in snaps:
        breaches.extend(_cto.detect_breaches(s))
    return _cto.assemble_daily_brief(snaps, breaches)


def _cs_section(repo_root: Path) -> str:
    rows = _load_last_per_business(_cs.CS_STATE_FILE_REL, repo_root=repo_root)
    if not rows:
        return "💬 CS — no recent snapshots in cs_state.jsonl."
    snaps: list[_cs.CsMetrics] = []
    for r in rows:
        try:
            snaps.append(_cs.CsMetrics(**r))
        except Exception:
            continue
    breaches: list[_cs.CsBreach] = []
    for s in snaps:
        breaches.extend(_cs.detect_breaches(s))
    return _cs.assemble_daily_brief(snaps, breaches)


def _margot_section(repo_root: Path) -> str:
    insight = _load_latest_margot_insight(repo_root)
    if not insight:
        return "🧠 Margot insight — no insight queued. Trigger via `/research`."
    summary = insight.get("summary") or insight.get("body") or "(no summary)"
    ts = insight.get("ts") or "n/a"
    topic = insight.get("topic") or "(no topic)"
    return (
        f"🧠 Margot insight — {topic}\n"
        f"({ts})\n"
        f"\n{summary[:1200]}"
        + ("…" if len(summary) > 1200 else "")
    )


def _ra_1842_section(repo_root: Path) -> str:
    status = _load_ra_1842_status(repo_root)
    if not status:
        return "📱 RA-1842 (iOS release) — no status file; check Linear ticket directly."
    state = status.get("state") or "unknown"
    note = status.get("note") or ""
    last_update = status.get("last_update") or "n/a"
    return (
        f"📱 RA-1842 (iOS release) — {state}\n"
        f"Last update: {last_update}\n"
        f"{note}"
    )


# ── Public API ──────────────────────────────────────────────────────────────


def assemble_six_pager(*, repo_root: Path | None = None,
                        date_str: str | None = None) -> str:
    """Compose the daily 6-pager.

    Reads from the existing senior-agent jsonl ledgers; does not invoke
    SDKs or external APIs. Each section degrades gracefully when its
    upstream ledger is missing.
    """
    rr = repo_root or REPO_ROOT
    date_str = date_str or _now_utc_date()

    sections = [
        f"📋 Pi-CEO daily 6-pager — {date_str}",
        "",
        "1. " + _cfo_section(rr),
        "",
        "2. " + _cmo_section(rr),
        "",
        "3. " + _cto_section(rr),
        "",
        "4. " + _cs_section(rr),
        "",
        "5. " + _margot_section(rr),
        "",
        "6. " + _ra_1842_section(rr),
        "",
        "—",
        "React 👍 to ack · ❌ to flag · ⏳ to defer per section.",
    ]
    return "\n".join(sections)


__all__ = ["assemble_six_pager"]
