"""swarm/cmo.py — RA-1860 (Wave 4 A2): CMO / Growth senior-agent engine.

Daily marketing visibility across the 11 Unite-Group businesses. Computes
LTV:CAC, blended CPA, channel concentration (Herfindahl-Hirschman), and
attribution-decay flag from a pluggable ``marketing_provider`` callable.
Pure-Python; deterministic; no I/O at module scope.

Public API:
  compute_metrics(raw)            -> MarketingMetrics
  detect_breaches(curr, prev)     -> list[MarketingBreach]
  assemble_daily_brief(snapshots, breaches) -> str
  approve_adspend(...)            -> AdSpendDecision   # gates dual-key
  snapshot_to_dict(metrics)       -> dict
  append_snapshot / load_last_snapshot

Thresholds (overridable via env in bot wrapper):
  AUTONOMOUS_ADSPEND_CEILING_USD_PER_DAY = 5000.0
  ALERT_LTV_CAC_RATIO       = 3.0
  ALERT_CHANNEL_TOP_SHARE   = 0.70
  CRITICAL_CHANNEL_TOP_SHARE = 0.85
  ALERT_BLENDED_CPA_USD     = 250.0   # over $250 CAC blended → flag
  ALERT_ATTR_DECAY_THRESHOLD = 0.30   # >30% loss vs cohort baseline → flag

Audit events emitted (whitelisted in audit_emit._VALID_TYPES):
  cmo_metric_snapshot, cmo_alert,
  cmo_adspend_approved, cmo_adspend_blocked, cmo_brief_emitted
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

log = logging.getLogger("swarm.cmo")

# ── Defaults ─────────────────────────────────────────────────────────────────
AUTONOMOUS_ADSPEND_CEILING_USD_PER_DAY = 5000.0
ALERT_LTV_CAC_RATIO = 3.0
ALERT_CHANNEL_TOP_SHARE = 0.70
CRITICAL_CHANNEL_TOP_SHARE = 0.85
ALERT_BLENDED_CPA_USD = 250.0
ALERT_ATTR_DECAY_THRESHOLD = 0.30

CMO_STATE_FILE_REL = ".harness/swarm/cmo_state.jsonl"


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class ChannelSpend:
    """Per-channel spend + acquisition for one window."""
    channel: str           # e.g. "google-ads", "linkedin", "seo", "referral"
    spend_usd: float
    customers_acquired: int


@dataclass
class RawMarketingMetrics:
    """Raw figures from ad platforms + product analytics, one per business."""
    business_id: str
    mrr: float
    avg_ltv_months: float                # avg customer lifetime in months
    total_marketing_spend_usd: float     # window spend across all channels
    total_customers_acquired: int        # window
    arpu_monthly: float                  # avg revenue per user per month
    gross_margin: float                  # 0..1
    channel_breakdown: list[ChannelSpend] = field(default_factory=list)
    attr_signal_count: int = 0           # number of channels with valid attribution
    attr_baseline_count: int = 0         # cohort baseline pre-iOS 14.5 etc


@dataclass
class MarketingMetrics:
    """Computed marketing metrics for one business at one snapshot."""
    ts: str
    business_id: str
    mrr: float
    blended_cpa_usd: float | None        # spend / acquisitions
    ltv_usd: float                       # avg_ltv_months * arpu_monthly * gross_margin
    ltv_cac_ratio: float | None
    channel_concentration_hhi: float     # 0..1 (1 = monoculture)
    top_channel: str | None
    top_channel_share: float             # 0..1
    attr_decay: float                    # 0..1; 0 = healthy, 1 = no signal
    total_spend_usd: float


@dataclass
class MarketingBreach:
    business_id: str
    metric: str
    value: float
    threshold: float
    severity: Literal["info", "warning", "critical"]
    note: str = ""


@dataclass
class AdSpendDecision:
    status: Literal["approved", "pending", "blocked"]
    amount_usd_per_day: float
    channel: str
    business_id: str
    justification: str
    draft_id: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_div(num: float, den: float) -> float | None:
    if den == 0:
        return None
    return num / den


# ── Pure-Python computation ──────────────────────────────────────────────────


def compute_metrics(raw: RawMarketingMetrics) -> MarketingMetrics:
    """Compute canonical marketing metrics from raw figures.

    Blended CPA = total_marketing_spend / total_customers_acquired
    LTV         = avg_ltv_months * arpu_monthly * gross_margin
    LTV:CAC     = LTV / blended_CPA
    HHI         = sum(channel_share^2)  — 0..1, higher = more concentrated
    attr_decay  = 1 - (signal_count / baseline_count); clamped to [0, 1]
    """
    blended_cpa = _safe_div(raw.total_marketing_spend_usd,
                            max(raw.total_customers_acquired, 0))
    ltv = raw.avg_ltv_months * raw.arpu_monthly * max(raw.gross_margin, 0.0)
    ltv_cac = _safe_div(ltv, blended_cpa) if blended_cpa else None

    total_spend = sum(c.spend_usd for c in raw.channel_breakdown)
    if total_spend > 0 and raw.channel_breakdown:
        shares = [c.spend_usd / total_spend for c in raw.channel_breakdown]
        hhi = sum(s * s for s in shares)
        # Top channel
        top_idx = max(range(len(raw.channel_breakdown)),
                      key=lambda i: raw.channel_breakdown[i].spend_usd)
        top_channel = raw.channel_breakdown[top_idx].channel
        top_share = shares[top_idx]
    else:
        hhi = 0.0
        top_channel = None
        top_share = 0.0

    if raw.attr_baseline_count > 0:
        attr_decay = max(
            0.0,
            min(1.0, 1.0 - (raw.attr_signal_count / raw.attr_baseline_count)),
        )
    else:
        attr_decay = 0.0

    return MarketingMetrics(
        ts=_now_iso(),
        business_id=raw.business_id,
        mrr=round(raw.mrr, 2),
        blended_cpa_usd=round(blended_cpa, 2) if blended_cpa is not None else None,
        ltv_usd=round(ltv, 2),
        ltv_cac_ratio=round(ltv_cac, 3) if ltv_cac is not None else None,
        channel_concentration_hhi=round(hhi, 4),
        top_channel=top_channel,
        top_channel_share=round(top_share, 4),
        attr_decay=round(attr_decay, 4),
        total_spend_usd=round(raw.total_marketing_spend_usd, 2),
    )


# ── Breach detection ─────────────────────────────────────────────────────────


def detect_breaches(curr: MarketingMetrics,
                    prev: MarketingMetrics | None = None) -> list[MarketingBreach]:
    """Compare current snapshot to thresholds (and optionally prior)."""
    out: list[MarketingBreach] = []

    if curr.ltv_cac_ratio is not None and curr.ltv_cac_ratio < ALERT_LTV_CAC_RATIO:
        out.append(MarketingBreach(
            business_id=curr.business_id, metric="ltv_cac_ratio",
            value=curr.ltv_cac_ratio, threshold=ALERT_LTV_CAC_RATIO,
            severity="warning",
            note=f"LTV:CAC {curr.ltv_cac_ratio:.2f} < {ALERT_LTV_CAC_RATIO} — "
                 f"channel mix or pricing under review.",
        ))

    if curr.top_channel_share > CRITICAL_CHANNEL_TOP_SHARE:
        out.append(MarketingBreach(
            business_id=curr.business_id, metric="channel_concentration",
            value=curr.top_channel_share, threshold=CRITICAL_CHANNEL_TOP_SHARE,
            severity="critical",
            note=f"{curr.top_channel} {curr.top_channel_share:.0%} of spend — "
                 f"single-platform risk.",
        ))
    elif curr.top_channel_share > ALERT_CHANNEL_TOP_SHARE:
        out.append(MarketingBreach(
            business_id=curr.business_id, metric="channel_concentration",
            value=curr.top_channel_share, threshold=ALERT_CHANNEL_TOP_SHARE,
            severity="warning",
            note=f"{curr.top_channel} {curr.top_channel_share:.0%} of spend — "
                 f"diversify before TOS change.",
        ))

    if (curr.blended_cpa_usd is not None
            and curr.blended_cpa_usd > ALERT_BLENDED_CPA_USD):
        out.append(MarketingBreach(
            business_id=curr.business_id, metric="blended_cpa",
            value=curr.blended_cpa_usd, threshold=ALERT_BLENDED_CPA_USD,
            severity="warning",
            note=f"CPA ${curr.blended_cpa_usd:.0f} > ${ALERT_BLENDED_CPA_USD:.0f} — "
                 f"channel ROI investigation.",
        ))

    if curr.attr_decay > ALERT_ATTR_DECAY_THRESHOLD:
        out.append(MarketingBreach(
            business_id=curr.business_id, metric="attribution_decay",
            value=curr.attr_decay, threshold=ALERT_ATTR_DECAY_THRESHOLD,
            severity="info",
            note=f"Attribution decay {curr.attr_decay:.0%} — "
                 f"last-click data unreliable, switch to MMM.",
        ))

    # Cycle-over-cycle drop
    if prev is not None and prev.business_id == curr.business_id:
        if (prev.ltv_cac_ratio is not None and curr.ltv_cac_ratio is not None
                and curr.ltv_cac_ratio < prev.ltv_cac_ratio - 0.5):
            out.append(MarketingBreach(
                business_id=curr.business_id, metric="ltv_cac_drop",
                value=curr.ltv_cac_ratio, threshold=prev.ltv_cac_ratio,
                severity="info",
                note=f"LTV:CAC {prev.ltv_cac_ratio:.2f} → "
                     f"{curr.ltv_cac_ratio:.2f} cycle-over-cycle.",
            ))

    return out


# ── Daily brief assembly ─────────────────────────────────────────────────────


def assemble_daily_brief(
    snapshots: list[MarketingMetrics],
    breaches: list[MarketingBreach],
    *,
    pending_adspend_count: int = 0,
    date_str: str | None = None,
) -> str:
    """Compose a 1-page CMO snippet for the daily 6-pager."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    total_spend = sum(s.total_spend_usd for s in snapshots)
    ratios = [s.ltv_cac_ratio for s in snapshots if s.ltv_cac_ratio is not None]
    portfolio_ratio_str = (f"{sum(ratios) / len(ratios):.2f}x"
                           if ratios else "n/a")
    n_alerts = len(breaches)
    n_critical = sum(1 for b in breaches if b.severity == "critical")

    lines = [
        f"📈 CMO daily — {date_str}",
        "",
        f"Portfolio LTV:CAC: {portfolio_ratio_str} | "
        f"Total spend: ${total_spend:,.0f} | "
        f"{n_alerts} alert{'s' if n_alerts != 1 else ''} ({n_critical} critical)",
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
        for s in sorted(snapshots, key=lambda x: -x.total_spend_usd):
            ratio_str = (f"L:C {s.ltv_cac_ratio:.2f}"
                         if s.ltv_cac_ratio is not None else "L:C n/a")
            cpa_str = (f"CPA ${s.blended_cpa_usd:.0f}"
                       if s.blended_cpa_usd is not None else "CPA n/a")
            top = (f"{s.top_channel} {s.top_channel_share:.0%}"
                   if s.top_channel else "no channels")
            lines.append(
                f"- {s.business_id}: ${s.total_spend_usd:,.0f} spend | "
                f"{ratio_str} | {cpa_str} | top: {top}"
            )
        lines.append("")

    if pending_adspend_count > 0:
        lines.append(
            f"📥 {pending_adspend_count} ad-spend approval"
            f"{'s' if pending_adspend_count != 1 else ''} queued "
            f"(>${AUTONOMOUS_ADSPEND_CEILING_USD_PER_DAY:.0f}/day)"
        )

    return "\n".join(lines)


# ── Ad-spend approval gate ───────────────────────────────────────────────────


def approve_adspend(
    *,
    amount_usd_per_day: float,
    channel: str,
    business_id: str,
    justification: str,
    spend_ceiling: float = AUTONOMOUS_ADSPEND_CEILING_USD_PER_DAY,
    post_draft: Callable[..., dict[str, Any]] | None = None,
    review_chat_id: str | None = None,
) -> AdSpendDecision:
    """Gate an ad-spend request through the dual-key threshold (default $5k/day).

    <= ceiling   → auto-approve
    >  ceiling + post_draft → route through draft_review (HITL), status=pending
    >  ceiling + no draft   → block (status=blocked)
    """
    if amount_usd_per_day <= spend_ceiling:
        log.info("CMO auto-approved $%.2f/day on %s for %s",
                 amount_usd_per_day, channel, business_id)
        return AdSpendDecision(
            status="approved", amount_usd_per_day=amount_usd_per_day,
            channel=channel, business_id=business_id,
            justification=justification,
        )
    if post_draft is None:
        log.warning(
            "CMO ad-spend $%.2f/day on %s for %s blocked — no draft_review",
            amount_usd_per_day, channel, business_id,
        )
        return AdSpendDecision(
            status="blocked", amount_usd_per_day=amount_usd_per_day,
            channel=channel, business_id=business_id,
            justification=justification,
        )
    draft_text = (
        f"📈 Ad-spend approval — ${amount_usd_per_day:,.2f}/day on "
        f"{channel} ({business_id})\n"
        f"\nJustification: {justification}\n"
        f"\nReact 👍 to approve · ❌ to reject · ⏳ to defer"
    )
    out = post_draft(
        draft_text=draft_text,
        destination_chat_id=str(review_chat_id or "review"),
        drafted_by_role="CMO",
        originating_intent_id=f"cmo-adspend-{business_id}",
    )
    return AdSpendDecision(
        status="pending", amount_usd_per_day=amount_usd_per_day,
        channel=channel, business_id=business_id,
        justification=justification,
        draft_id=out.get("draft_id"),
    )


# ── Persistence helpers ──────────────────────────────────────────────────────


def snapshot_to_dict(metrics: MarketingMetrics) -> dict[str, Any]:
    return asdict(metrics)


def append_snapshot(metrics: MarketingMetrics, *, repo_root: Path) -> None:
    p = repo_root / CMO_STATE_FILE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot_to_dict(metrics), ensure_ascii=False) + "\n")


def load_last_snapshot(business_id: str, *,
                        repo_root: Path) -> MarketingMetrics | None:
    p = repo_root / CMO_STATE_FILE_REL
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
        return MarketingMetrics(**last_row)
    except Exception as exc:
        log.debug("cmo: skipping malformed prior snapshot (%s)", exc)
        return None


__all__ = [
    "ChannelSpend", "RawMarketingMetrics", "MarketingMetrics",
    "MarketingBreach", "AdSpendDecision",
    "compute_metrics", "detect_breaches", "assemble_daily_brief",
    "approve_adspend", "snapshot_to_dict",
    "append_snapshot", "load_last_snapshot",
    "AUTONOMOUS_ADSPEND_CEILING_USD_PER_DAY",
    "ALERT_LTV_CAC_RATIO", "ALERT_CHANNEL_TOP_SHARE",
    "CRITICAL_CHANNEL_TOP_SHARE", "ALERT_BLENDED_CPA_USD",
    "ALERT_ATTR_DECAY_THRESHOLD",
]
