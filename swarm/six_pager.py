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
import re
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


def _first_client_section(repo_root: Path) -> str | None:
    """Top-of-page banner for any first-client business with active state.

    Scans CFO + CMO + CTO + CS ledgers for rows whose business_id is in
    the first-client list (default: ccw-crm). If found, renders a
    one-glance summary with the highest-priority signals — first-response
    time, NPS, runway band, recent CS alerts.

    Returns None when no first-client has data in any ledger (suppresses
    the banner — no point taking up section 0 if there's nothing to say).
    """
    try:
        from . import client_priority  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None

    first_clients = client_priority.list_first_clients()
    if not first_clients:
        return None

    # Pull last per-business rows from all four senior-bot ledgers.
    cfo_rows = {r.get("business_id"): r
                for r in _load_last_per_business(
                    ".harness/swarm/cfo_state.jsonl", repo_root=repo_root)}
    cmo_rows = {r.get("business_id"): r
                for r in _load_last_per_business(
                    ".harness/swarm/cmo_state.jsonl", repo_root=repo_root)}
    cto_rows = {r.get("business_id"): r
                for r in _load_last_per_business(
                    ".harness/swarm/cto_state.jsonl", repo_root=repo_root)}
    cs_rows = {r.get("business_id"): r
               for r in _load_last_per_business(
                   ".harness/swarm/cs_state.jsonl", repo_root=repo_root)}

    have_data = False
    blocks: list[str] = []
    for bid in first_clients:
        rows = {
            "cfo": cfo_rows.get(bid),
            "cmo": cmo_rows.get(bid),
            "cto": cto_rows.get(bid),
            "cs": cs_rows.get(bid),
        }
        if not any(rows.values()):
            continue
        have_data = True
        block = [f"⭐ FIRST CLIENT — {bid}"]
        cs_row = rows["cs"]
        if cs_row:
            fr = cs_row.get("avg_first_response_minutes")
            nps = cs_row.get("nps")
            grr = cs_row.get("grr_pct")
            threats = cs_row.get("open_enterprise_churn_threats", 0)
            sla_alert = client_priority.first_client_first_response_alert(bid)
            sla_critical = (
                client_priority.first_client_first_response_critical(bid)
            )
            sla_state = "✅ within SLA"
            if fr is not None and fr > sla_critical:
                sla_state = f"🔴 SLA BREACH ({fr:.0f}m > {sla_critical:.0f}m)"
            elif fr is not None and fr > sla_alert:
                sla_state = f"🟡 watching ({fr:.0f}m > {sla_alert:.0f}m)"
            if nps is not None and grr is not None and fr is not None:
                block.append(
                    f"  CS: NPS {nps:.0f} | GRR {grr:.0%} | "
                    f"first-response {fr:.0f}m | {threats} churn-threats | "
                    f"{sla_state}"
                )
            else:
                block.append("  CS: partial data — see section 4.")
        cfo_row = rows["cfo"]
        if cfo_row:
            mrr = cfo_row.get("mrr")
            nrr = cfo_row.get("nrr")
            if mrr is not None and nrr is not None:
                block.append(f"  CFO: ${mrr:,.0f} MRR | NRR {nrr:.0%}")
        cto_row = rows["cto"]
        if cto_row:
            band = cto_row.get("dora_band")
            uptime = cto_row.get("uptime_pct")
            if band and uptime is not None:
                block.append(
                    f"  CTO: DORA {band} | uptime {uptime:.4%}"
                )
        cmo_row = rows["cmo"]
        if cmo_row:
            spend = cmo_row.get("total_spend_usd")
            ratio = cmo_row.get("ltv_cac_ratio")
            if spend is not None:
                ratio_str = (f"L:C {ratio:.2f}"
                             if ratio is not None else "L:C n/a")
                block.append(
                    f"  CMO: ${spend:,.0f} attributed spend | {ratio_str}"
                )
        blocks.append("\n".join(block))

    if not have_data:
        return None
    return "\n\n".join(blocks)


# ── Telegram chunking ───────────────────────────────────────────────────────

TELEGRAM_MESSAGE_LIMIT = 4096
# Reserve a few chars for the chunk header "[3/5]\n" so we don't push past
# the limit when the receiver re-prepends the marker.
TELEGRAM_CHUNK_BUDGET = TELEGRAM_MESSAGE_LIMIT - 32


def chunk_for_telegram(brief: str, *,
                        max_chars: int = TELEGRAM_CHUNK_BUDGET
                        ) -> list[str]:
    """Split a 6-pager into Telegram-safe chunks.

    Splits on section boundaries first (lines matching ``\\d+\\. `` at the
    start), then within an over-large section on paragraph boundaries
    (blank lines), then within an over-large paragraph on line boundaries.
    Hard-cuts mid-line only as a last resort — the caller can rely on
    every chunk being <= max_chars.

    A short message (≤ max_chars) returns as a single-element list. The
    caller decides whether to prepend "[i/N]" markers.
    """
    if len(brief) <= max_chars:
        return [brief]

    # Try section-boundary splitting first
    sections = _split_on_section_boundary(brief)
    chunks: list[str] = []
    current = ""
    for sec in sections:
        candidate = (current + ("\n\n" if current else "") + sec).strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        # `current` is what fits; flush it and start a new chunk with `sec`
        if current:
            chunks.append(current)
            current = ""
        if len(sec) <= max_chars:
            current = sec
        else:
            # The section itself is too big — recurse on paragraphs
            for para_chunk in _split_oversize(sec, max_chars=max_chars):
                if not current:
                    current = para_chunk
                elif len(current) + 2 + len(para_chunk) <= max_chars:
                    current = current + "\n\n" + para_chunk
                else:
                    chunks.append(current)
                    current = para_chunk
    if current:
        chunks.append(current)
    return chunks


_SECTION_BOUNDARY = re.compile(r"^(?=\d+\.\s+)", re.MULTILINE)


def _split_on_section_boundary(text: str) -> list[str]:
    """Split right before each `<digit>. ` line. Preserve order; drop empties."""
    parts = _SECTION_BOUNDARY.split(text)
    return [p.strip() for p in parts if p.strip()]


def _split_oversize(section: str, *, max_chars: int) -> list[str]:
    """Split an over-large section: paragraphs, then lines, then hard cut."""
    if len(section) <= max_chars:
        return [section]

    # Paragraph boundary first
    paragraphs = section.split("\n\n")
    out: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = (current + ("\n\n" if current else "") + para)
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            out.append(current)
            current = ""
        if len(para) <= max_chars:
            current = para
        else:
            # Line-boundary split inside one over-large paragraph
            for line_chunk in _split_by_line(para, max_chars=max_chars):
                if not current:
                    current = line_chunk
                elif len(current) + 1 + len(line_chunk) <= max_chars:
                    current = current + "\n" + line_chunk
                else:
                    out.append(current)
                    current = line_chunk
    if current:
        out.append(current)
    return out


def _split_by_line(paragraph: str, *, max_chars: int) -> list[str]:
    out: list[str] = []
    current = ""
    for line in paragraph.split("\n"):
        if len(line) > max_chars:
            # Hard cut a single over-long line
            if current:
                out.append(current)
                current = ""
            for i in range(0, len(line), max_chars):
                out.append(line[i:i + max_chars])
            continue
        candidate = (current + ("\n" if current else "") + line)
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                out.append(current)
            current = line
    if current:
        out.append(current)
    return out


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

    sections: list[str] = [f"📋 Pi-CEO daily 6-pager — {date_str}", ""]

    first_client = _first_client_section(rr)
    if first_client:
        sections.extend([first_client, ""])

    sections.extend([
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
    ])
    return "\n".join(sections)


__all__ = [
    "assemble_six_pager",
    "chunk_for_telegram",
    "TELEGRAM_MESSAGE_LIMIT",
    "TELEGRAM_CHUNK_BUDGET",
]
