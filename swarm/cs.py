"""swarm/cs.py — RA-1862 (Wave 4 A4): Customer Success tier-1 senior-agent engine.

Real-time inbound customer-support visibility. Computes NPS, First Contact
Resolution (FCR), and Gross Retention Rate (GRR) from a pluggable
``cs_provider`` callable. Pure-Python; deterministic; no I/O at module
scope.

Public API:
  compute_metrics(raw)            -> CsMetrics
  detect_breaches(curr, prev)     -> list[CsBreach]
  assemble_daily_brief(snapshots, breaches) -> str
  approve_refund(...)             -> RefundDecision   # gates dual-key >$100
  snapshot_to_dict / append_snapshot / load_last_snapshot

Thresholds (overridable via env in bot wrapper):
  AUTONOMOUS_REFUND_CEILING_USD   = 100.0
  ALERT_NPS                       = 30.0
  ALERT_FCR_PCT                   = 0.65
  ALERT_GRR_PCT                   = 0.90
  CRITICAL_GRR_PCT                = 0.85
  ALERT_FIRST_RESPONSE_MINUTES    = 60.0
  CRITICAL_FIRST_RESPONSE_MINUTES = 240.0

Audit events emitted (whitelisted in audit_emit._VALID_TYPES):
  cs_metric_snapshot, cs_alert,
  cs_refund_approved, cs_refund_blocked, cs_brief_emitted
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

log = logging.getLogger("swarm.cs")

# ── Defaults ─────────────────────────────────────────────────────────────────
AUTONOMOUS_REFUND_CEILING_USD = 100.0
ALERT_NPS = 30.0
ALERT_FCR_PCT = 0.65
ALERT_GRR_PCT = 0.90
CRITICAL_GRR_PCT = 0.85
ALERT_FIRST_RESPONSE_MINUTES = 60.0
CRITICAL_FIRST_RESPONSE_MINUTES = 240.0

CS_STATE_FILE_REL = ".harness/swarm/cs_state.jsonl"


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class RawCsMetrics:
    business_id: str
    nps_promoters: int
    nps_passives: int
    nps_detractors: int
    tickets_total: int
    tickets_resolved_first_contact: int
    customers_at_period_start: int
    customers_lost_in_period: int
    avg_first_response_minutes: float
    open_enterprise_churn_threats: int = 0


@dataclass
class CsMetrics:
    ts: str
    business_id: str
    nps: float                          # -100 .. +100
    fcr_pct: float                      # 0..1
    grr_pct: float                      # 0..1 (gross retention)
    avg_first_response_minutes: float
    open_enterprise_churn_threats: int


@dataclass
class CsBreach:
    business_id: str
    metric: str
    value: float
    threshold: float
    severity: Literal["info", "warning", "critical"]
    note: str = ""


@dataclass
class RefundDecision:
    status: Literal["approved", "pending", "blocked"]
    amount_usd: float
    customer_id: str
    business_id: str
    justification: str
    draft_id: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_div(num: float, den: float) -> float:
    if den == 0:
        return 0.0
    return num / den


# ── Pure-Python computation ──────────────────────────────────────────────────


def compute_metrics(raw: RawCsMetrics) -> CsMetrics:
    """Compute CS metrics from raw figures.

    NPS = (promoters / total) * 100 - (detractors / total) * 100
    FCR = tickets_resolved_first_contact / tickets_total
    GRR = (customers_at_start - customers_lost) / customers_at_start
          (capped at 1.0)
    """
    total_responses = (raw.nps_promoters + raw.nps_passives
                       + raw.nps_detractors)
    if total_responses > 0:
        nps = ((raw.nps_promoters / total_responses) * 100.0
               - (raw.nps_detractors / total_responses) * 100.0)
    else:
        nps = 0.0
    fcr = _safe_div(raw.tickets_resolved_first_contact,
                     max(raw.tickets_total, 0))
    if raw.customers_at_period_start > 0:
        grr = max(
            0.0,
            (raw.customers_at_period_start - raw.customers_lost_in_period)
            / raw.customers_at_period_start,
        )
    else:
        grr = 1.0
    return CsMetrics(
        ts=_now_iso(),
        business_id=raw.business_id,
        nps=round(nps, 2),
        fcr_pct=round(fcr, 4),
        grr_pct=round(min(grr, 1.0), 4),
        avg_first_response_minutes=round(raw.avg_first_response_minutes, 1),
        open_enterprise_churn_threats=raw.open_enterprise_churn_threats,
    )


# ── Breach detection ─────────────────────────────────────────────────────────


def detect_breaches(curr: CsMetrics,
                    prev: CsMetrics | None = None) -> list[CsBreach]:
    out: list[CsBreach] = []

    if curr.nps < ALERT_NPS:
        out.append(CsBreach(
            business_id=curr.business_id, metric="nps",
            value=curr.nps, threshold=ALERT_NPS,
            severity="warning",
            note=f"NPS {curr.nps:.0f} < {ALERT_NPS:.0f} — "
                 f"detractors outpacing promoters.",
        ))
    if curr.fcr_pct < ALERT_FCR_PCT:
        out.append(CsBreach(
            business_id=curr.business_id, metric="fcr_pct",
            value=curr.fcr_pct, threshold=ALERT_FCR_PCT,
            severity="warning",
            note=f"FCR {curr.fcr_pct:.0%} < {ALERT_FCR_PCT:.0%} — "
                 f"tier-1 docs / playbook gap.",
        ))
    if curr.grr_pct < CRITICAL_GRR_PCT:
        out.append(CsBreach(
            business_id=curr.business_id, metric="grr_pct",
            value=curr.grr_pct, threshold=CRITICAL_GRR_PCT,
            severity="critical",
            note=f"GRR {curr.grr_pct:.0%} < {CRITICAL_GRR_PCT:.0%} — "
                 f"churn investigation required.",
        ))
    elif curr.grr_pct < ALERT_GRR_PCT:
        out.append(CsBreach(
            business_id=curr.business_id, metric="grr_pct",
            value=curr.grr_pct, threshold=ALERT_GRR_PCT,
            severity="warning",
            note=f"GRR {curr.grr_pct:.0%} < {ALERT_GRR_PCT:.0%} — "
                 f"retention drift.",
        ))
    # Per-business SLA — first clients (e.g. CCW) get tighter thresholds
    # via swarm.client_priority. Standard portfolio uses module defaults.
    try:
        from . import client_priority as _cp  # noqa: PLC0415
        is_first = _cp.is_first_client(curr.business_id)
        alert_min = _cp.first_client_first_response_alert(curr.business_id)
        critical_min = _cp.first_client_first_response_critical(
            curr.business_id,
        )
    except Exception:  # noqa: BLE001
        is_first = False
        alert_min = ALERT_FIRST_RESPONSE_MINUTES
        critical_min = CRITICAL_FIRST_RESPONSE_MINUTES

    fc_tag = " [FIRST CLIENT]" if is_first else ""

    if curr.avg_first_response_minutes > critical_min:
        out.append(CsBreach(
            business_id=curr.business_id,
            metric="avg_first_response_minutes",
            value=curr.avg_first_response_minutes,
            threshold=critical_min,
            severity="critical",
            note=f"First response {curr.avg_first_response_minutes:.0f}m > "
                 f"{critical_min:.0f}m — SLA breach{fc_tag}.",
        ))
    elif curr.avg_first_response_minutes > alert_min:
        out.append(CsBreach(
            business_id=curr.business_id,
            metric="avg_first_response_minutes",
            value=curr.avg_first_response_minutes,
            threshold=alert_min,
            severity="warning",
            note=f"First response {curr.avg_first_response_minutes:.0f}m > "
                 f"{alert_min:.0f}m — staffing gap{fc_tag}.",
        ))
    if curr.open_enterprise_churn_threats > 0:
        out.append(CsBreach(
            business_id=curr.business_id,
            metric="open_enterprise_churn_threats",
            value=float(curr.open_enterprise_churn_threats),
            threshold=0.0,
            severity="critical" if curr.open_enterprise_churn_threats >= 3
                     else "warning",
            note=f"{curr.open_enterprise_churn_threats} enterprise churn "
                 f"threat(s) open — escalate to founder.",
        ))
    return out


# ── Daily brief ──────────────────────────────────────────────────────────────


def assemble_daily_brief(
    snapshots: list[CsMetrics],
    breaches: list[CsBreach],
    *,
    pending_refund_count: int = 0,
    date_str: str | None = None,
) -> str:
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    avg_nps = (sum(s.nps for s in snapshots) / len(snapshots)
               if snapshots else 0.0)
    avg_fcr = (sum(s.fcr_pct for s in snapshots) / len(snapshots)
               if snapshots else 0.0)
    avg_grr = (sum(s.grr_pct for s in snapshots) / len(snapshots)
               if snapshots else 1.0)
    n_alerts = len(breaches)
    n_critical = sum(1 for b in breaches if b.severity == "critical")
    open_threats = sum(s.open_enterprise_churn_threats for s in snapshots)

    lines = [
        f"💬 CS daily — {date_str}",
        "",
        f"Avg NPS: {avg_nps:.0f} | "
        f"Avg FCR: {avg_fcr:.0%} | "
        f"Avg GRR: {avg_grr:.0%} | "
        f"{n_alerts} alert{'s' if n_alerts != 1 else ''} ({n_critical} critical) | "
        f"{open_threats} enterprise threat{'s' if open_threats != 1 else ''}",
        "",
    ]

    if breaches:
        lines.append("🚨 Alerts:")
        sev_order = {"critical": 0, "warning": 1, "info": 2}
        for b in sorted(breaches, key=lambda x: sev_order.get(x.severity, 9)):
            icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(
                b.severity, "•")
            lines.append(f"{icon} [{b.business_id}] {b.metric}: {b.note}")
        lines.append("")

    if snapshots:
        lines.append("Per-business:")
        for s in sorted(snapshots, key=lambda x: x.nps):
            lines.append(
                f"- {s.business_id}: NPS {s.nps:.0f} | "
                f"FCR {s.fcr_pct:.0%} | GRR {s.grr_pct:.0%} | "
                f"first-response {s.avg_first_response_minutes:.0f}m"
            )
        lines.append("")

    if pending_refund_count > 0:
        lines.append(
            f"📥 {pending_refund_count} refund approval"
            f"{'s' if pending_refund_count != 1 else ''} queued "
            f"(>${AUTONOMOUS_REFUND_CEILING_USD:.0f})"
        )

    return "\n".join(lines)


# ── Refund approval gate ─────────────────────────────────────────────────────


def approve_refund(
    *,
    amount_usd: float,
    customer_id: str,
    business_id: str,
    justification: str,
    refund_ceiling: float = AUTONOMOUS_REFUND_CEILING_USD,
    post_draft: Callable[..., dict[str, Any]] | None = None,
    review_chat_id: str | None = None,
) -> RefundDecision:
    """Gate a refund through the dual-key threshold (default $100).

    <= ceiling → auto-approve
    >  ceiling + post_draft → route through draft_review (HITL)
    >  ceiling + no draft → block
    """
    if amount_usd <= refund_ceiling:
        log.info("CS auto-approved $%.2f refund for %s (%s)",
                 amount_usd, customer_id, business_id)
        return RefundDecision(
            status="approved", amount_usd=amount_usd,
            customer_id=customer_id, business_id=business_id,
            justification=justification,
        )
    if post_draft is None:
        log.warning(
            "CS refund $%.2f blocked — no draft_review (customer %s, biz %s)",
            amount_usd, customer_id, business_id,
        )
        return RefundDecision(
            status="blocked", amount_usd=amount_usd,
            customer_id=customer_id, business_id=business_id,
            justification=justification,
        )
    draft_text = (
        f"💬 Refund approval — ${amount_usd:,.2f} to {customer_id} "
        f"({business_id})\n"
        f"\nJustification: {justification}\n"
        f"\nReact 👍 to approve · ❌ to reject · ⏳ to defer"
    )
    out = post_draft(
        draft_text=draft_text,
        destination_chat_id=str(review_chat_id or "review"),
        drafted_by_role="CS",
        originating_intent_id=f"cs-refund-{business_id}-{customer_id}",
    )
    return RefundDecision(
        status="pending", amount_usd=amount_usd,
        customer_id=customer_id, business_id=business_id,
        justification=justification,
        draft_id=out.get("draft_id"),
    )


# ── Persistence ──────────────────────────────────────────────────────────────


def snapshot_to_dict(metrics: CsMetrics) -> dict[str, Any]:
    return asdict(metrics)


def append_snapshot(metrics: CsMetrics, *, repo_root: Path) -> None:
    p = repo_root / CS_STATE_FILE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot_to_dict(metrics), ensure_ascii=False) + "\n")


def load_last_snapshot(business_id: str, *,
                        repo_root: Path) -> CsMetrics | None:
    p = repo_root / CS_STATE_FILE_REL
    if not p.exists():
        return None
    last_row: dict[str, Any] | None = None
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("business_id") == business_id:
            last_row = row
    if last_row is None:
        return None
    try:
        return CsMetrics(**last_row)
    except Exception as exc:
        log.debug("cs: skipping malformed prior snapshot (%s)", exc)
        return None


__all__ = [
    "RawCsMetrics", "CsMetrics", "CsBreach", "RefundDecision",
    "compute_metrics", "detect_breaches", "assemble_daily_brief",
    "approve_refund", "snapshot_to_dict",
    "append_snapshot", "load_last_snapshot",
    "AUTONOMOUS_REFUND_CEILING_USD",
    "ALERT_NPS", "ALERT_FCR_PCT", "ALERT_GRR_PCT", "CRITICAL_GRR_PCT",
    "ALERT_FIRST_RESPONSE_MINUTES", "CRITICAL_FIRST_RESPONSE_MINUTES",
]
