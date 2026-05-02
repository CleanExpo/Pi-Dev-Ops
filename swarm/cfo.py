"""
swarm/cfo.py — RA-1850 (Wave 4.1): CFO senior-agent engine.

Computes burn multiple, NRR, CAC payback, gross margin, runway, model-spend
ratio from a pluggable ``metrics_provider`` callable. Pure-Python; deterministic;
no I/O at module scope. Stripe/Xero wire-up lives in the bot (``swarm/bots/cfo.py``)
or in tests as a synthetic provider — the engine doesn't care.

Public API:
  compute_metrics(raw)             -> Metrics
  detect_breaches(curr, prev)      -> list[Breach]
  assemble_daily_brief(snapshots, breaches) -> str
  approve_spend(amount_usd, ...)   -> SpendDecision  # gates dual-key
  snapshot_to_dict(metrics)        -> dict           # for jsonl persistence

Defaults (overridable via env or constructor of bot wrapper):
  AUTONOMOUS_SPEND_CEILING = 1000.0  # USD
  ALERT_BURN_MULTIPLE      = 1.5
  ALERT_NRR_B2B            = 1.10
  ALERT_NRR_PROSUMER       = 0.90
  ALERT_GROSS_MARGIN       = 0.75
  ALERT_RUNWAY_MONTHS      = 12
  ALERT_MODEL_SPEND_RATIO  = 0.07

Audit events emitted (see audit_emit allowlist):
  cfo_metric_snapshot, cfo_alert, cfo_invoice_approved, cfo_spend_blocked
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

log = logging.getLogger("swarm.cfo")

# ── Defaults (constants — bot wrapper may override via env) ──────────────────
AUTONOMOUS_SPEND_CEILING = 1000.0
ALERT_BURN_MULTIPLE = 1.5
ALERT_NRR_B2B = 1.10
ALERT_NRR_PROSUMER = 0.90
ALERT_GROSS_MARGIN = 0.75
ALERT_RUNWAY_MONTHS = 12.0
ALERT_MODEL_SPEND_RATIO = 0.07
ALERT_CAC_PAYBACK_MONTHS = 18.0

CFO_STATE_FILE_REL = ".harness/swarm/cfo_state.jsonl"


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class RawMetrics:
    """Raw figures from Stripe + Xero, one snapshot per business per cycle."""
    business_id: str
    mrr: float                       # current monthly recurring revenue, USD
    starting_mrr: float              # MRR at start of measurement window
    expansion_mrr: float             # upgrades + cross-sell in window
    contraction_mrr: float           # downgrades in window
    churn_mrr: float                 # cancellations in window
    new_mrr: float                   # new customer revenue in window
    cogs: float                      # cost of goods sold for the window
    revenue: float                   # total revenue for the window
    cash_on_hand: float              # USD
    monthly_burn: float              # avg monthly cash burn
    cac_paid: float                  # marketing+sales spend in window
    customers_acquired: int          # new customers in window
    inference_cost: float            # AI/LLM API spend in window
    business_type: Literal["b2b", "prosumer"] = "b2b"


@dataclass
class Metrics:
    """Computed metrics for one business at one point in time."""
    ts: str
    business_id: str
    business_type: str
    mrr: float
    net_new_arr: float
    net_burn: float
    burn_multiple: float | None       # None when net_new_arr == 0
    nrr: float
    gross_margin: float
    cac_payback_months: float | None  # None when no acquisitions
    runway_months: float | None       # None when burn == 0
    model_spend_ratio: float


@dataclass
class Breach:
    """A breach of an alert threshold for one metric."""
    business_id: str
    metric: str
    value: float
    threshold: float
    severity: Literal["info", "warning", "critical"]
    note: str = ""


@dataclass
class SpendDecision:
    """Outcome of a spend-approval request."""
    status: Literal["approved", "pending", "blocked"]
    amount_usd: float
    vendor: str
    business_id: str
    justification: str
    draft_id: str | None = None  # populated when routed through draft_review


# ── Pure-Python computation ──────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_div(num: float, den: float) -> float | None:
    if den == 0:
        return None
    return num / den


def compute_metrics(raw: RawMetrics) -> Metrics:
    """Compute canonical SaaS metrics from raw figures.

    Burn multiple = Net Burn / Net New ARR (annualised from MRR delta).
    NRR = (start_MRR + expansion - contraction - churn) / start_MRR.
    Gross margin = (revenue - COGS) / revenue.
    Runway = cash_on_hand / monthly_burn (when burn > 0).
    CAC payback = CAC / (ARPU * GM) in months.
    Model spend ratio = inference_cost / MRR.
    """
    # Net new ARR for the window — convert MRR delta → annualised ARR.
    net_new_mrr = raw.new_mrr + raw.expansion_mrr - raw.contraction_mrr - raw.churn_mrr
    net_new_arr = net_new_mrr * 12.0

    nrr_value = (
        (raw.starting_mrr + raw.expansion_mrr
         - raw.contraction_mrr - raw.churn_mrr)
        / raw.starting_mrr
        if raw.starting_mrr > 0 else 1.0
    )

    gm = _safe_div(raw.revenue - raw.cogs, raw.revenue) or 0.0

    runway = _safe_div(raw.cash_on_hand, raw.monthly_burn)

    arpu = _safe_div(raw.mrr, max(raw.customers_acquired, 1))
    cac_payback = None
    if raw.customers_acquired > 0 and arpu and gm > 0:
        cac_per_customer = raw.cac_paid / raw.customers_acquired
        cac_payback = cac_per_customer / (arpu * gm) if (arpu * gm) > 0 else None

    burn_multiple = _safe_div(raw.monthly_burn * 12.0, net_new_arr) \
        if net_new_arr > 0 else None

    model_spend_ratio = _safe_div(raw.inference_cost, raw.mrr) or 0.0

    return Metrics(
        ts=_now_iso(),
        business_id=raw.business_id,
        business_type=raw.business_type,
        mrr=round(raw.mrr, 2),
        net_new_arr=round(net_new_arr, 2),
        net_burn=round(raw.monthly_burn, 2),
        burn_multiple=round(burn_multiple, 3) if burn_multiple is not None else None,
        nrr=round(nrr_value, 4),
        gross_margin=round(gm, 4),
        cac_payback_months=round(cac_payback, 2) if cac_payback is not None else None,
        runway_months=round(runway, 2) if runway is not None else None,
        model_spend_ratio=round(model_spend_ratio, 4),
    )


# ── Breach detection ─────────────────────────────────────────────────────────


def detect_breaches(curr: Metrics, prev: Metrics | None = None) -> list[Breach]:
    """Compare current snapshot to thresholds (and optionally prior snapshot).

    Severity:
      * critical = breach is acute (runway <12mo, GM <75%)
      * warning  = breach is sustained (set in caller after 2-cycle lookback)
      * info     = breach exists but not yet acted on
    """
    out: list[Breach] = []

    if curr.burn_multiple is not None and curr.burn_multiple > ALERT_BURN_MULTIPLE:
        out.append(Breach(
            business_id=curr.business_id, metric="burn_multiple",
            value=curr.burn_multiple, threshold=ALERT_BURN_MULTIPLE,
            severity="warning",
            note=f"Burn multiple {curr.burn_multiple}x > {ALERT_BURN_MULTIPLE}x — "
                 f"every $1 of new ARR costs {curr.burn_multiple} of cash.",
        ))

    nrr_threshold = (ALERT_NRR_B2B if curr.business_type == "b2b"
                     else ALERT_NRR_PROSUMER)
    if curr.nrr < nrr_threshold:
        out.append(Breach(
            business_id=curr.business_id, metric="nrr",
            value=curr.nrr, threshold=nrr_threshold,
            severity="warning",
            note=f"NRR {curr.nrr:.1%} < {nrr_threshold:.0%} — "
                 f"churn + contraction outpacing expansion.",
        ))

    if curr.gross_margin < ALERT_GROSS_MARGIN:
        out.append(Breach(
            business_id=curr.business_id, metric="gross_margin",
            value=curr.gross_margin, threshold=ALERT_GROSS_MARGIN,
            severity="critical",
            note=f"GM {curr.gross_margin:.1%} < {ALERT_GROSS_MARGIN:.0%} — "
                 f"COGS unsustainable at scale.",
        ))

    if curr.runway_months is not None and curr.runway_months < ALERT_RUNWAY_MONTHS:
        out.append(Breach(
            business_id=curr.business_id, metric="runway_months",
            value=curr.runway_months, threshold=ALERT_RUNWAY_MONTHS,
            severity="critical",
            note=f"Runway {curr.runway_months}mo < {ALERT_RUNWAY_MONTHS}mo — "
                 f"raise / cut path required.",
        ))

    if curr.model_spend_ratio > ALERT_MODEL_SPEND_RATIO:
        out.append(Breach(
            business_id=curr.business_id, metric="model_spend_ratio",
            value=curr.model_spend_ratio, threshold=ALERT_MODEL_SPEND_RATIO,
            severity="warning",
            note=f"Inference {curr.model_spend_ratio:.1%} > "
                 f"{ALERT_MODEL_SPEND_RATIO:.0%} of MRR — caching needed.",
        ))

    if (curr.cac_payback_months is not None
            and curr.cac_payback_months > ALERT_CAC_PAYBACK_MONTHS):
        out.append(Breach(
            business_id=curr.business_id, metric="cac_payback_months",
            value=curr.cac_payback_months, threshold=ALERT_CAC_PAYBACK_MONTHS,
            severity="warning",
            note=f"CAC payback {curr.cac_payback_months}mo > "
                 f"{ALERT_CAC_PAYBACK_MONTHS}mo — channel mix off.",
        ))

    # Cycle-over-cycle deltas (if prior snapshot available)
    if prev is not None and prev.business_id == curr.business_id:
        if (prev.runway_months is not None and curr.runway_months is not None
                and curr.runway_months < prev.runway_months - 1):
            out.append(Breach(
                business_id=curr.business_id, metric="runway_drop",
                value=curr.runway_months, threshold=prev.runway_months,
                severity="info",
                note=f"Runway dropped {prev.runway_months}mo → "
                     f"{curr.runway_months}mo since prior cycle.",
            ))

    return out


# ── Daily brief assembly ─────────────────────────────────────────────────────


def assemble_daily_brief(
    snapshots: list[Metrics],
    breaches: list[Breach],
    *,
    pending_spend_count: int = 0,
    date_str: str | None = None,
) -> str:
    """Compose a 1-page financial brief for the daily 6-pager."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    total_mrr = sum(s.mrr for s in snapshots)
    runways = [s.runway_months for s in snapshots if s.runway_months is not None]
    portfolio_runway_str = (f"{min(runways):.1f}m (worst-case)"
                             if runways else "n/a")

    burns = [s.burn_multiple for s in snapshots if s.burn_multiple is not None]
    portfolio_bm_str = (f"{sum(burns) / len(burns):.2f}x"
                        if burns else "n/a (no net new ARR)")

    n_alerts = len(breaches)
    n_critical = sum(1 for b in breaches if b.severity == "critical")

    lines = [
        f"💰 CFO daily — {date_str}",
        "",
        f"Portfolio runway: {portfolio_runway_str} | "
        f"Total MRR: ${total_mrr:,.0f} | "
        f"Avg burn multiple: {portfolio_bm_str}",
        f"{n_alerts} alert{'s' if n_alerts != 1 else ''} "
        f"({n_critical} critical) overnight",
        "",
    ]

    if breaches:
        lines.append("🚨 Alerts:")
        # Sort: critical first, then warning, then info
        sev_order = {"critical": 0, "warning": 1, "info": 2}
        for b in sorted(breaches, key=lambda x: sev_order.get(x.severity, 9)):
            icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(
                b.severity, "•")
            lines.append(f"{icon} [{b.business_id}] {b.metric}: {b.note}")
        lines.append("")

    if snapshots:
        lines.append("Per-business:")
        for s in sorted(snapshots, key=lambda x: -x.mrr):
            nrr_str = f"NRR {s.nrr:.1%}"
            gm_str = f"GM {s.gross_margin:.1%}"
            runway_str = (f"runway {s.runway_months:.1f}m"
                          if s.runway_months is not None else "runway n/a")
            lines.append(f"- {s.business_id}: ${s.mrr:,.0f} MRR | "
                         f"{nrr_str} | {gm_str} | {runway_str}")
        lines.append("")

    if pending_spend_count > 0:
        lines.append(
            f"📥 {pending_spend_count} spend approval"
            f"{'s' if pending_spend_count != 1 else ''} queued (>${AUTONOMOUS_SPEND_CEILING:.0f})"
        )

    return "\n".join(lines)


# ── Spend approval gate ──────────────────────────────────────────────────────


def approve_spend(
    *,
    amount_usd: float,
    vendor: str,
    business_id: str,
    justification: str,
    spend_ceiling: float = AUTONOMOUS_SPEND_CEILING,
    post_draft: Callable[..., dict[str, Any]] | None = None,
    review_chat_id: str | None = None,
) -> SpendDecision:
    """Gate a spend request through the dual-key threshold.

    If amount_usd <= ceiling → auto-approve, return status='approved'.
    If amount_usd > ceiling and post_draft callable supplied → route through
    draft_review (HITL gate), return status='pending' with draft_id.
    If amount_usd > ceiling and post_draft is None → return status='blocked'.
    """
    if amount_usd <= spend_ceiling:
        log.info("CFO auto-approved $%.2f to %s for %s",
                 amount_usd, vendor, business_id)
        return SpendDecision(
            status="approved",
            amount_usd=amount_usd, vendor=vendor,
            business_id=business_id, justification=justification,
        )

    if post_draft is None:
        log.warning(
            "CFO spend $%.2f > ceiling $%.2f for %s — no draft_review provider, blocking",
            amount_usd, spend_ceiling, vendor,
        )
        return SpendDecision(
            status="blocked",
            amount_usd=amount_usd, vendor=vendor,
            business_id=business_id, justification=justification,
        )

    draft_text = (
        f"🧾 Spend approval — ${amount_usd:,.2f} to {vendor} ({business_id})\n"
        f"\nJustification: {justification}\n"
        f"\nReact 👍 to approve · ❌ to reject · ⏳ to defer"
    )
    out = post_draft(
        draft_text=draft_text,
        destination_chat_id=str(review_chat_id or "review"),
        drafted_by_role="CFO",
        originating_intent_id=f"cfo-spend-{business_id}",
    )
    return SpendDecision(
        status="pending",
        amount_usd=amount_usd, vendor=vendor,
        business_id=business_id, justification=justification,
        draft_id=out.get("draft_id"),
    )


# ── Persistence helpers ──────────────────────────────────────────────────────


def snapshot_to_dict(metrics: Metrics) -> dict[str, Any]:
    """Serialise a Metrics dataclass for jsonl persistence."""
    return asdict(metrics)


def append_snapshot(metrics: Metrics, *, repo_root: Path) -> None:
    """Append one metric snapshot to the cfo_state jsonl ledger."""
    p = repo_root / CFO_STATE_FILE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot_to_dict(metrics), ensure_ascii=False) + "\n")


def load_last_snapshot(business_id: str, *, repo_root: Path) -> Metrics | None:
    """Read the most recent snapshot for one business from the jsonl ledger."""
    p = repo_root / CFO_STATE_FILE_REL
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
        return Metrics(**last_row)
    except Exception as exc:
        log.debug("cfo: skipping malformed prior snapshot (%s)", exc)
        return None


__all__ = [
    "RawMetrics", "Metrics", "Breach", "SpendDecision",
    "compute_metrics", "detect_breaches", "assemble_daily_brief",
    "approve_spend", "snapshot_to_dict",
    "append_snapshot", "load_last_snapshot",
    # Constants
    "AUTONOMOUS_SPEND_CEILING", "ALERT_BURN_MULTIPLE",
    "ALERT_NRR_B2B", "ALERT_NRR_PROSUMER",
    "ALERT_GROSS_MARGIN", "ALERT_RUNWAY_MONTHS",
    "ALERT_MODEL_SPEND_RATIO", "ALERT_CAC_PAYBACK_MONTHS",
]
