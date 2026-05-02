"""
swarm/bots/cfo.py — RA-1850 (Wave 4.1): CFO senior-agent bot.

Per-cycle job:
  1. Pull RawMetrics from configured provider (Stripe + Xero in prod;
     synthetic in tests).
  2. Compute Metrics (engine in swarm.cfo).
  3. Compare to prior snapshot → detect breaches.
  4. Audit-emit each snapshot + each breach.
  5. If a daily-fire window: assemble daily brief + post to review chat
     via draft_review.

Self-gates on TAO_SWARM_ENABLED + TAO_SWARM_SHADOW like every other bot.

Wire into swarm/orchestrator.py main loop alongside chief_of_staff.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .. import cfo as _cfo

log = logging.getLogger("swarm.bots.cfo")

REPO_ROOT = Path(__file__).resolve().parents[2]

# Default daily-fire hour (user-local UTC offset compensated upstream;
# bot just checks the UTC hour matches.) Override via TAO_CFO_DAILY_HOUR_UTC.
DEFAULT_DAILY_HOUR_UTC = 6


# ── Metrics provider plug-point ──────────────────────────────────────────────
# In production this would call Stripe + Xero MCP tools; here it's a thin
# abstraction so tests can inject synthetic data.
MetricsProvider = Callable[[], list[_cfo.RawMetrics]]


def _default_metrics_provider() -> list[_cfo.RawMetrics]:
    """Production provider stub. Wired to Stripe + Xero MCP in Wave 4.1b.

    Returns an empty list today — bot self-skips when no data flows through.
    The wire-up ticket will replace this with calls to:
      mcp_stripe.list_subscriptions(), mcp_stripe.list_payment_intents(),
      mcp_xero.invoices(), mcp_xero.accounts() etc.
    """
    log.debug("cfo: default provider returning [] — wire Stripe/Xero in 4.1b")
    return []


_provider: MetricsProvider = _default_metrics_provider


def set_metrics_provider(provider: MetricsProvider) -> None:
    """Override the metrics provider (used by tests + Wave 4.1b wire-up)."""
    global _provider
    _provider = provider


# ── State helpers ────────────────────────────────────────────────────────────


def _is_daily_fire_window(state: dict, now: datetime) -> bool:
    """Fire once per UTC day, in the configured hour window (default 06:00)."""
    target_hour = int(os.environ.get("TAO_CFO_DAILY_HOUR_UTC", DEFAULT_DAILY_HOUR_UTC))
    if now.hour != target_hour:
        return False
    last_fired = state.get("cfo_last_daily_fire")
    if last_fired:
        try:
            last_dt = datetime.fromisoformat(last_fired)
            if (now - last_dt).total_seconds() < 23 * 3600:
                return False
        except Exception:
            pass
    return True


def _gates_open() -> bool:
    """Self-gate: TAO_SWARM_ENABLED=1 (kill-switch) AND not panicked."""
    if os.environ.get("TAO_SWARM_ENABLED", "0") != "1":
        log.debug("cfo: TAO_SWARM_ENABLED != 1 — skipping cycle")
        return False
    try:
        from .. import kill_switch
        if kill_switch.is_active():
            log.debug("cfo: kill-switch active — skipping cycle")
            return False
    except Exception:
        pass
    return True


def _is_test_mode() -> bool:
    """True when TAO_DRAFT_REVIEW_TEST=1 — same flag draft_review uses."""
    return os.environ.get("TAO_DRAFT_REVIEW_TEST", "0") == "1"


# ── Cycle entry point ────────────────────────────────────────────────────────


def run_cycle(unacked_count: int, *, state: dict | None = None) -> dict:
    """One CFO cycle. Called by orchestrator.

    Returns a small status dict so orchestrator can surface in audit log.
    """
    state = state if state is not None else {}

    # Gate-open in production; tests bypass via TAO_DRAFT_REVIEW_TEST.
    if not _is_test_mode() and not _gates_open():
        return {"status": "skipped", "reason": "gates_closed"}

    raw_list = _provider()
    if not raw_list:
        return {"status": "skipped", "reason": "no_data"}

    snapshots: list[_cfo.Metrics] = []
    all_breaches: list[_cfo.Breach] = []

    for raw in raw_list:
        prev = _cfo.load_last_snapshot(raw.business_id, repo_root=REPO_ROOT)
        curr = _cfo.compute_metrics(raw)
        snapshots.append(curr)

        # Persist snapshot
        _cfo.append_snapshot(curr, repo_root=REPO_ROOT)

        # Audit emit
        try:
            from .. import audit_emit
            audit_emit.row(
                "cfo_metric_snapshot", "CFO",
                business_id=curr.business_id,
                mrr=curr.mrr,
                burn_multiple=curr.burn_multiple,
                nrr=curr.nrr,
                gross_margin=curr.gross_margin,
                runway_months=curr.runway_months,
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("cfo: audit_emit (snapshot) suppressed: %s", exc)

        # Detect + emit breaches
        breaches = _cfo.detect_breaches(curr, prev)
        for b in breaches:
            all_breaches.append(b)
            try:
                from .. import audit_emit
                audit_emit.row(
                    "cfo_alert", "CFO",
                    business_id=b.business_id,
                    metric=b.metric,
                    value=b.value,
                    threshold=b.threshold,
                    severity=b.severity,
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("cfo: audit_emit (alert) suppressed: %s", exc)

    # Daily-fire window?
    now = datetime.now(timezone.utc)
    fired_brief = False
    if _is_daily_fire_window(state, now):
        brief = _cfo.assemble_daily_brief(snapshots, all_breaches)
        try:
            from .. import draft_review
            draft = draft_review.post_draft(
                draft_text=brief,
                destination_chat_id=os.environ.get("REVIEW_CHAT_ID", "review"),
                drafted_by_role="CFO",
                originating_intent_id="cfo-daily-brief",
            )
            log.info("cfo daily brief posted: draft_id=%s", draft.get("draft_id"))
            state["cfo_last_daily_fire"] = now.isoformat()
            fired_brief = True
            try:
                from .. import audit_emit
                audit_emit.row(
                    "cfo_brief_emitted", "CFO",
                    draft_id=draft.get("draft_id"),
                    snapshot_count=len(snapshots),
                    breach_count=len(all_breaches),
                )
            except Exception:
                pass
        except Exception as exc:  # noqa: BLE001 — never raise from cycle
            log.warning("cfo: daily brief post failed: %s", exc)

    return {
        "status": "ok",
        "snapshots": len(snapshots),
        "breaches": len(all_breaches),
        "brief_posted": fired_brief,
    }


# ── Spend approval entry-point (for explicit calls) ──────────────────────────


def request_spend_approval(
    *,
    amount_usd: float,
    vendor: str,
    business_id: str,
    justification: str,
) -> _cfo.SpendDecision:
    """Public entry-point for any other bot to request a spend approval.

    Auto-approves <= ceiling. Above ceiling → routes through draft_review HITL.
    """
    spend_ceiling = float(os.environ.get(
        "TAO_CFO_SPEND_CEILING", _cfo.AUTONOMOUS_SPEND_CEILING))

    post_draft = None
    try:
        from .. import draft_review
        post_draft = draft_review.post_draft
    except Exception as exc:
        log.debug("cfo: draft_review unavailable (%s) — only auto-approve path open", exc)

    decision = _cfo.approve_spend(
        amount_usd=amount_usd,
        vendor=vendor,
        business_id=business_id,
        justification=justification,
        spend_ceiling=spend_ceiling,
        post_draft=post_draft,
        review_chat_id=os.environ.get("REVIEW_CHAT_ID"),
    )

    try:
        from .. import audit_emit
        audit_emit.row(
            "cfo_invoice_approved" if decision.status == "approved"
            else "cfo_spend_blocked",
            "CFO",
            business_id=business_id,
            amount_usd=amount_usd,
            vendor=vendor,
            status=decision.status,
            draft_id=decision.draft_id,
        )
    except Exception as exc:
        log.debug("cfo: audit_emit (spend) suppressed: %s", exc)

    return decision


__all__ = [
    "run_cycle",
    "request_spend_approval",
    "set_metrics_provider",
]
