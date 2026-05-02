"""swarm/cto.py — RA-1861 (Wave 4 A3): CTO senior-agent engine.

Daily platform-health visibility. Computes the DORA quartet (deploy
frequency, lead time, MTTR, change-failure rate) plus p99 latency and
uptime from a pluggable ``platform_provider`` callable. Pure-Python;
deterministic; no I/O at module scope.

Public API:
  compute_metrics(raw)            -> PlatformMetrics
  detect_breaches(curr, prev)     -> list[PlatformBreach]
  assemble_daily_brief(snapshots, breaches) -> str
  approve_pr_merge(...)           -> PrMergeDecision   # gates dual-key on prod
  snapshot_to_dict(metrics)       -> dict
  append_snapshot / load_last_snapshot

Thresholds (overridable via env in bot wrapper):
  ALERT_DEPLOY_FREQ_PER_WEEK  = 2.0
  ALERT_LEAD_TIME_HOURS       = 24.0
  ALERT_MTTR_HOURS            = 4.0
  CRITICAL_MTTR_HOURS         = 24.0
  ALERT_CHANGE_FAILURE_RATE   = 0.15
  CRITICAL_CHANGE_FAILURE_RATE = 0.30
  ALERT_P99_LATENCY_MS        = 1000.0
  ALERT_UPTIME_PCT            = 0.995
  CRITICAL_UPTIME_PCT         = 0.99
  ALERT_COST_PER_REQ_USD      = 0.0050

Audit events emitted (whitelisted in audit_emit._VALID_TYPES):
  cto_metric_snapshot, cto_alert,
  cto_pr_merge_approved, cto_pr_merge_blocked, cto_brief_emitted
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

log = logging.getLogger("swarm.cto")

# ── Defaults ─────────────────────────────────────────────────────────────────
ALERT_DEPLOY_FREQ_PER_WEEK = 2.0
ALERT_LEAD_TIME_HOURS = 24.0
ALERT_MTTR_HOURS = 4.0
CRITICAL_MTTR_HOURS = 24.0
ALERT_CHANGE_FAILURE_RATE = 0.15
CRITICAL_CHANGE_FAILURE_RATE = 0.30
ALERT_P99_LATENCY_MS = 1000.0
ALERT_UPTIME_PCT = 0.995
CRITICAL_UPTIME_PCT = 0.99
ALERT_COST_PER_REQ_USD = 0.0050

CTO_STATE_FILE_REL = ".harness/swarm/cto_state.jsonl"


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class RawPlatformMetrics:
    """Raw platform figures, one snapshot per repo per cycle."""
    business_id: str                  # e.g. "pi-dev-ops", "restoreassist"
    deploys_last_week: int
    lead_time_hours_p50: float        # commit → production p50
    mttr_hours: float                 # mean time to recover from incidents
    change_failure_count: int         # in window
    change_total_count: int
    p99_latency_ms: float
    uptime_pct: float                 # 0..1
    cost_per_request_usd: float
    is_production_branch: bool = True  # informs approve_pr_merge default


@dataclass
class PlatformMetrics:
    """Computed DORA-style metrics for one repo at one point in time."""
    ts: str
    business_id: str
    deploy_freq_per_week: float
    lead_time_hours_p50: float
    mttr_hours: float
    change_failure_rate: float        # 0..1
    p99_latency_ms: float
    uptime_pct: float
    cost_per_request_usd: float
    dora_band: Literal["elite", "high", "medium", "low"]


@dataclass
class PlatformBreach:
    business_id: str
    metric: str
    value: float
    threshold: float
    severity: Literal["info", "warning", "critical"]
    note: str = ""


@dataclass
class PrMergeDecision:
    status: Literal["approved", "pending", "blocked"]
    repo: str
    pr_number: int | None
    target_branch: str
    title: str
    is_production: bool
    draft_id: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_div(num: float, den: float) -> float:
    if den == 0:
        return 0.0
    return num / den


def _classify_dora(deploy_freq: float, lead_h: float, mttr_h: float,
                    cfr: float) -> Literal["elite", "high", "medium", "low"]:
    """Google DORA bands (simplified to bot use)."""
    if deploy_freq >= 7 and lead_h <= 1 and mttr_h <= 1 and cfr <= 0.15:
        return "elite"
    if deploy_freq >= 1 and lead_h <= 24 and mttr_h <= 24 and cfr <= 0.15:
        return "high"
    if deploy_freq >= 0.25 and lead_h <= 24 * 7 and mttr_h <= 24 and cfr <= 0.30:
        return "medium"
    return "low"


# ── Pure-Python computation ──────────────────────────────────────────────────


def compute_metrics(raw: RawPlatformMetrics) -> PlatformMetrics:
    """Compute canonical DORA + ops metrics from raw figures.

    deploy_freq_per_week     = raw.deploys_last_week
    change_failure_rate      = change_failure_count / change_total_count
    """
    cfr = _safe_div(raw.change_failure_count, max(raw.change_total_count, 0))
    band = _classify_dora(
        deploy_freq=float(raw.deploys_last_week),
        lead_h=raw.lead_time_hours_p50,
        mttr_h=raw.mttr_hours,
        cfr=cfr,
    )
    return PlatformMetrics(
        ts=_now_iso(),
        business_id=raw.business_id,
        deploy_freq_per_week=float(raw.deploys_last_week),
        lead_time_hours_p50=round(raw.lead_time_hours_p50, 2),
        mttr_hours=round(raw.mttr_hours, 2),
        change_failure_rate=round(cfr, 4),
        p99_latency_ms=round(raw.p99_latency_ms, 1),
        uptime_pct=round(raw.uptime_pct, 5),
        cost_per_request_usd=round(raw.cost_per_request_usd, 6),
        dora_band=band,
    )


# ── Breach detection ─────────────────────────────────────────────────────────


def detect_breaches(curr: PlatformMetrics,
                    prev: PlatformMetrics | None = None) -> list[PlatformBreach]:
    """Compare current snapshot to thresholds (and optionally prior)."""
    out: list[PlatformBreach] = []

    if curr.deploy_freq_per_week < ALERT_DEPLOY_FREQ_PER_WEEK:
        out.append(PlatformBreach(
            business_id=curr.business_id, metric="deploy_freq_per_week",
            value=curr.deploy_freq_per_week,
            threshold=ALERT_DEPLOY_FREQ_PER_WEEK,
            severity="warning",
            note=f"{curr.deploy_freq_per_week:.1f}/wk < "
                 f"{ALERT_DEPLOY_FREQ_PER_WEEK:.0f}/wk — "
                 f"shipping cadence stalling.",
        ))
    if curr.lead_time_hours_p50 > ALERT_LEAD_TIME_HOURS:
        out.append(PlatformBreach(
            business_id=curr.business_id, metric="lead_time_hours_p50",
            value=curr.lead_time_hours_p50, threshold=ALERT_LEAD_TIME_HOURS,
            severity="warning",
            note=f"Lead time {curr.lead_time_hours_p50:.1f}h > "
                 f"{ALERT_LEAD_TIME_HOURS:.0f}h — bottleneck investigation.",
        ))
    if curr.mttr_hours > CRITICAL_MTTR_HOURS:
        out.append(PlatformBreach(
            business_id=curr.business_id, metric="mttr_hours",
            value=curr.mttr_hours, threshold=CRITICAL_MTTR_HOURS,
            severity="critical",
            note=f"MTTR {curr.mttr_hours:.1f}h > "
                 f"{CRITICAL_MTTR_HOURS:.0f}h — incident-response broken.",
        ))
    elif curr.mttr_hours > ALERT_MTTR_HOURS:
        out.append(PlatformBreach(
            business_id=curr.business_id, metric="mttr_hours",
            value=curr.mttr_hours, threshold=ALERT_MTTR_HOURS,
            severity="warning",
            note=f"MTTR {curr.mttr_hours:.1f}h > {ALERT_MTTR_HOURS:.0f}h — "
                 f"slow recovery.",
        ))
    if curr.change_failure_rate > CRITICAL_CHANGE_FAILURE_RATE:
        out.append(PlatformBreach(
            business_id=curr.business_id, metric="change_failure_rate",
            value=curr.change_failure_rate,
            threshold=CRITICAL_CHANGE_FAILURE_RATE,
            severity="critical",
            note=f"CFR {curr.change_failure_rate:.0%} > "
                 f"{CRITICAL_CHANGE_FAILURE_RATE:.0%} — "
                 f"halt ship until root cause found.",
        ))
    elif curr.change_failure_rate > ALERT_CHANGE_FAILURE_RATE:
        out.append(PlatformBreach(
            business_id=curr.business_id, metric="change_failure_rate",
            value=curr.change_failure_rate,
            threshold=ALERT_CHANGE_FAILURE_RATE,
            severity="warning",
            note=f"CFR {curr.change_failure_rate:.0%} > "
                 f"{ALERT_CHANGE_FAILURE_RATE:.0%} — "
                 f"test gate review.",
        ))
    if curr.p99_latency_ms > ALERT_P99_LATENCY_MS:
        out.append(PlatformBreach(
            business_id=curr.business_id, metric="p99_latency_ms",
            value=curr.p99_latency_ms, threshold=ALERT_P99_LATENCY_MS,
            severity="warning",
            note=f"p99 {curr.p99_latency_ms:.0f}ms > "
                 f"{ALERT_P99_LATENCY_MS:.0f}ms — perf regression.",
        ))
    if curr.uptime_pct < CRITICAL_UPTIME_PCT:
        out.append(PlatformBreach(
            business_id=curr.business_id, metric="uptime_pct",
            value=curr.uptime_pct, threshold=CRITICAL_UPTIME_PCT,
            severity="critical",
            note=f"Uptime {curr.uptime_pct:.4%} < "
                 f"{CRITICAL_UPTIME_PCT:.2%} — SLA breach.",
        ))
    elif curr.uptime_pct < ALERT_UPTIME_PCT:
        out.append(PlatformBreach(
            business_id=curr.business_id, metric="uptime_pct",
            value=curr.uptime_pct, threshold=ALERT_UPTIME_PCT,
            severity="warning",
            note=f"Uptime {curr.uptime_pct:.4%} < "
                 f"{ALERT_UPTIME_PCT:.2%} — investigate flakes.",
        ))
    if curr.cost_per_request_usd > ALERT_COST_PER_REQ_USD:
        out.append(PlatformBreach(
            business_id=curr.business_id, metric="cost_per_request_usd",
            value=curr.cost_per_request_usd,
            threshold=ALERT_COST_PER_REQ_USD,
            severity="info",
            note=f"Cost ${curr.cost_per_request_usd:.4f}/req > "
                 f"${ALERT_COST_PER_REQ_USD:.4f}/req — caching audit.",
        ))

    if prev is not None and prev.business_id == curr.business_id:
        if curr.dora_band != prev.dora_band:
            sev = ("critical" if curr.dora_band == "low"
                   else "info")
            out.append(PlatformBreach(
                business_id=curr.business_id, metric="dora_band",
                value=0.0, threshold=0.0,
                severity=sev,
                note=f"DORA band {prev.dora_band} → {curr.dora_band}.",
            ))

    return out


# ── Daily brief ──────────────────────────────────────────────────────────────


def assemble_daily_brief(
    snapshots: list[PlatformMetrics],
    breaches: list[PlatformBreach],
    *,
    pending_pr_count: int = 0,
    date_str: str | None = None,
) -> str:
    """Compose a 1-page CTO snippet for the daily 6-pager."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    n_alerts = len(breaches)
    n_critical = sum(1 for b in breaches if b.severity == "critical")
    avg_uptime = (sum(s.uptime_pct for s in snapshots) / len(snapshots)
                  if snapshots else 0.0)
    band_counts: dict[str, int] = {}
    for s in snapshots:
        band_counts[s.dora_band] = band_counts.get(s.dora_band, 0) + 1
    band_str = " · ".join(
        f"{k}:{v}" for k, v in sorted(band_counts.items(),
                                        key=lambda kv: ("elite high medium low"
                                                         .index(kv[0])))
    ) or "n/a"

    lines = [
        f"⚙️ CTO daily — {date_str}",
        "",
        f"DORA distribution: {band_str} | "
        f"Avg uptime: {avg_uptime:.4%} | "
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
        lines.append("Per-repo:")
        band_rank = {"elite": 0, "high": 1, "medium": 2, "low": 3}
        for s in sorted(snapshots, key=lambda x: band_rank[x.dora_band]):
            lines.append(
                f"- {s.business_id}: {s.dora_band} | "
                f"deploys {s.deploy_freq_per_week:.1f}/wk | "
                f"lead {s.lead_time_hours_p50:.1f}h | "
                f"MTTR {s.mttr_hours:.1f}h | "
                f"CFR {s.change_failure_rate:.0%} | "
                f"p99 {s.p99_latency_ms:.0f}ms | "
                f"uptime {s.uptime_pct:.4%}"
            )
        lines.append("")

    if pending_pr_count > 0:
        lines.append(
            f"📥 {pending_pr_count} production PR merge"
            f"{'s' if pending_pr_count != 1 else ''} queued in review chat"
        )

    return "\n".join(lines)


# ── PR-merge approval gate ───────────────────────────────────────────────────


def approve_pr_merge(
    *,
    repo: str,
    pr_number: int | None,
    target_branch: str,
    title: str,
    is_production: bool,
    post_draft: Callable[..., dict[str, Any]] | None = None,
    review_chat_id: str | None = None,
) -> PrMergeDecision:
    """Gate a PR-merge request through the production dual-key threshold.

    is_production=False → auto-approve (feature branches, dev infra)
    is_production=True + post_draft supplied → route through draft_review (HITL)
    is_production=True + no draft → block
    """
    if not is_production:
        log.info("CTO auto-approved PR merge: %s#%s → %s",
                 repo, pr_number, target_branch)
        return PrMergeDecision(
            status="approved", repo=repo, pr_number=pr_number,
            target_branch=target_branch, title=title,
            is_production=False,
        )

    if post_draft is None:
        log.warning("CTO blocked PR merge to production %s#%s — no draft_review",
                    repo, pr_number)
        return PrMergeDecision(
            status="blocked", repo=repo, pr_number=pr_number,
            target_branch=target_branch, title=title,
            is_production=True,
        )

    draft_text = (
        f"⚙️ PR merge to production — {repo}#{pr_number} → {target_branch}\n"
        f"Title: {title}\n"
        f"\nReact 👍 to merge · ❌ to reject · ⏳ to defer"
    )
    out = post_draft(
        draft_text=draft_text,
        destination_chat_id=str(review_chat_id or "review"),
        drafted_by_role="CTO",
        originating_intent_id=f"cto-pr-{repo}-{pr_number}",
    )
    return PrMergeDecision(
        status="pending", repo=repo, pr_number=pr_number,
        target_branch=target_branch, title=title,
        is_production=True,
        draft_id=out.get("draft_id"),
    )


# ── Persistence ──────────────────────────────────────────────────────────────


def snapshot_to_dict(metrics: PlatformMetrics) -> dict[str, Any]:
    return asdict(metrics)


def append_snapshot(metrics: PlatformMetrics, *, repo_root: Path) -> None:
    p = repo_root / CTO_STATE_FILE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot_to_dict(metrics), ensure_ascii=False) + "\n")


def load_last_snapshot(business_id: str, *,
                        repo_root: Path) -> PlatformMetrics | None:
    p = repo_root / CTO_STATE_FILE_REL
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
        return PlatformMetrics(**last_row)
    except Exception as exc:
        log.debug("cto: skipping malformed prior snapshot (%s)", exc)
        return None


__all__ = [
    "RawPlatformMetrics", "PlatformMetrics", "PlatformBreach",
    "PrMergeDecision",
    "compute_metrics", "detect_breaches", "assemble_daily_brief",
    "approve_pr_merge", "snapshot_to_dict",
    "append_snapshot", "load_last_snapshot",
    "ALERT_DEPLOY_FREQ_PER_WEEK", "ALERT_LEAD_TIME_HOURS",
    "ALERT_MTTR_HOURS", "CRITICAL_MTTR_HOURS",
    "ALERT_CHANGE_FAILURE_RATE", "CRITICAL_CHANGE_FAILURE_RATE",
    "ALERT_P99_LATENCY_MS",
    "ALERT_UPTIME_PCT", "CRITICAL_UPTIME_PCT",
    "ALERT_COST_PER_REQ_USD",
]
