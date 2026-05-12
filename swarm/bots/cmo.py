"""swarm/bots/cmo.py — RA-1860 (Wave 4 A2): CMO / Growth senior-agent bot.

Per-cycle job (mirrors swarm/bots/cfo.py shape):
  1. Pull RawMarketingMetrics from configured provider.
  2. Compute MarketingMetrics via swarm.cmo engine.
  3. Compare to prior snapshot → detect breaches.
  4. Audit-emit each snapshot + each breach.
  5. If a daily-fire window: assemble daily brief + post to draft_review.

Self-gates on TAO_SWARM_ENABLED + kill-switch like every other bot.

Wire into swarm/orchestrator.py main loop alongside chief_of_staff + cfo.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .. import cmo as _cmo

log = logging.getLogger("swarm.bots.cmo")

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DAILY_HOUR_UTC = 6


# ── Metrics provider plug-point ──────────────────────────────────────────────
MarketingProvider = Callable[[], list[_cmo.RawMarketingMetrics]]


def _default_marketing_provider() -> list[_cmo.RawMarketingMetrics]:
    """Production provider — routes through ``swarm.providers.select_marketing_provider``.

    Defaults to synthetic so the CMO daily brief is never empty; flip to real
    data with ``TAO_CMO_PROVIDER=ad_platforms`` once Google Ads / LinkedIn / etc.
    keys are populated. Per-business synthetic fallback inside the real
    provider keeps a partially-wired portfolio coherent.

    Never raises — any provider failure degrades to empty list and the bot
    self-skips that cycle.
    """
    try:
        from ..providers import select_marketing_provider
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "cmo: marketing provider import failed (%s) — empty list", exc
        )
        return []
    try:
        return select_marketing_provider()()
    except Exception as exc:  # noqa: BLE001 — never crash the cycle
        log.warning("cmo: marketing provider call failed (%s) — empty list", exc)
        return []


_provider: MarketingProvider = _default_marketing_provider


def set_marketing_provider(provider: MarketingProvider) -> None:
    """Override the marketing provider (used by tests + future ad-platform wire-up)."""
    global _provider
    _provider = provider


# ── State helpers ────────────────────────────────────────────────────────────


def _is_daily_fire_window(state: dict, now: datetime) -> bool:
    target_hour = int(os.environ.get(
        "TAO_CMO_DAILY_HOUR_UTC", DEFAULT_DAILY_HOUR_UTC))
    if now.hour != target_hour:
        return False
    last_fired = state.get("cmo_last_daily_fire")
    if last_fired:
        try:
            last_dt = datetime.fromisoformat(last_fired)
            if (now - last_dt).total_seconds() < 23 * 3600:
                return False
        except Exception:
            pass
    return True


def _gates_open() -> bool:
    if os.environ.get("TAO_SWARM_ENABLED", "0") != "1":
        log.debug("cmo: TAO_SWARM_ENABLED != 1 — skipping cycle")
        return False
    try:
        from .. import kill_switch
        if kill_switch.is_active():
            log.debug("cmo: kill-switch active — skipping cycle")
            return False
    except Exception:
        pass
    return True


def _is_test_mode() -> bool:
    return os.environ.get("TAO_DRAFT_REVIEW_TEST", "0") == "1"


# ── Cycle entry point ────────────────────────────────────────────────────────


def run_cycle(unacked_count: int, *, state: dict | None = None) -> dict:
    """One CMO cycle. Called by orchestrator."""
    state = state if state is not None else {}

    if not _is_test_mode() and not _gates_open():
        return {"status": "skipped", "reason": "gates_closed"}

    # ── RA-1868 — consume Board directives for CMO before metrics work.
    cmo_directives_acted = 0
    try:
        from .. import board_directive_consumer  # noqa: PLC0415
        new_directives = board_directive_consumer.consume_for(
            "CMO", state=state, repo_root=REPO_ROOT,
        )
        for d in new_directives:
            cmo_directives_acted += 1
            try:
                from .. import audit_emit
                audit_emit.row(
                    "board_directive_consumed", "CMO",
                    session_id=d.session_id,
                    action=d.action[:200],
                    deadline=d.deadline,
                )
            except Exception:
                pass
            log.info("cmo: board directive %s — %s",
                     d.session_id, d.action[:80])
    except Exception as exc:  # noqa: BLE001
        log.debug("cmo: directive consume suppressed (%s)", exc)

    raw_list = _provider()
    if not raw_list:
        return {"status": "skipped", "reason": "no_data"}

    snapshots: list[_cmo.MarketingMetrics] = []
    all_breaches: list[_cmo.MarketingBreach] = []

    for raw in raw_list:
        prev = _cmo.load_last_snapshot(raw.business_id, repo_root=REPO_ROOT)
        curr = _cmo.compute_metrics(raw)
        snapshots.append(curr)

        _cmo.append_snapshot(curr, repo_root=REPO_ROOT)

        try:
            from .. import audit_emit
            audit_emit.row(
                "cmo_metric_snapshot", "CMO",
                business_id=curr.business_id,
                mrr=curr.mrr,
                ltv_cac_ratio=curr.ltv_cac_ratio,
                blended_cpa_usd=curr.blended_cpa_usd,
                top_channel=curr.top_channel,
                top_channel_share=curr.top_channel_share,
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("cmo: audit_emit (snapshot) suppressed: %s", exc)

        breaches = _cmo.detect_breaches(curr, prev)
        for b in breaches:
            all_breaches.append(b)
            try:
                from .. import audit_emit
                audit_emit.row(
                    "cmo_alert", "CMO",
                    business_id=b.business_id,
                    metric=b.metric,
                    value=b.value,
                    threshold=b.threshold,
                    severity=b.severity,
                )
            except Exception as exc:
                log.debug("cmo: audit_emit (alert) suppressed: %s", exc)

    now = datetime.now(timezone.utc)
    fired_brief = False
    if _is_daily_fire_window(state, now):
        brief = _cmo.assemble_daily_brief(snapshots, all_breaches)
        try:
            from .. import draft_review
            draft = draft_review.post_draft(
                draft_text=brief,
                destination_chat_id=os.environ.get("REVIEW_CHAT_ID", "review"),
                drafted_by_role="CMO",
                originating_intent_id="cmo-daily-brief",
            )
            log.info("cmo daily brief posted: draft_id=%s", draft.get("draft_id"))
            state["cmo_last_daily_fire"] = now.isoformat()
            fired_brief = True
            try:
                from .. import audit_emit
                audit_emit.row(
                    "cmo_brief_emitted", "CMO",
                    draft_id=draft.get("draft_id"),
                    snapshot_count=len(snapshots),
                    breach_count=len(all_breaches),
                )
            except Exception:
                pass
        except Exception as exc:
            log.warning("cmo: daily brief post failed: %s", exc)

    return {
        "status": "ok",
        "snapshots": len(snapshots),
        "breaches": len(all_breaches),
        "brief_posted": fired_brief,
    }


# ── Ad-spend approval entry-point ───────────────────────────────────────────


def request_adspend_approval(
    *,
    amount_usd_per_day: float,
    channel: str,
    business_id: str,
    justification: str,
) -> _cmo.AdSpendDecision:
    """Public entry-point for any other bot to request ad-spend approval.

    Per Phill's founder directive 2026-05-13 (see Wiki/pathway-to-2b-2026-2028.md):
    Unite-Group does **no ad spend, ever**. Synthex produces all marketing
    in-house via free + owned distribution channels. When TAO_NO_AD_SPEND=1
    (default), every adspend request is blocked with a clear reason. The
    existing draft_review path is preserved for the case where the directive
    is ever reversed via TAO_NO_AD_SPEND=0.

    Auto-approves <= ceiling. Above ceiling → routes through draft_review HITL.
    """
    if os.environ.get("TAO_NO_AD_SPEND", "1") == "1":
        log.info(
            "cmo: ad-spend request blocked by founder directive — "
            "no ad spend, in-house Synthex only. Request was $%.2f/day on %s for %s",
            amount_usd_per_day, channel, business_id,
        )
        try:
            from .. import audit_emit
            audit_emit.row(
                "cmo_adspend_blocked_by_directive",
                "CMO",
                business_id=business_id,
                amount_usd_per_day=amount_usd_per_day,
                channel=channel,
                directive="founder_2026-05-13_no_ad_spend",
            )
        except Exception as exc:
            log.debug("cmo: audit_emit suppressed: %s", exc)
        return _cmo.AdSpendDecision(
            status="blocked",
            amount_usd_per_day=amount_usd_per_day,
            channel=channel,
            business_id=business_id,
            justification=(
                f"FOUNDER DIRECTIVE 2026-05-13: no ad spend. "
                f"Use Synthex in-house production for {channel}. "
                f"Original justification: {justification}"
            ),
            draft_id=None,
        )

    spend_ceiling = float(os.environ.get(
        "TAO_CMO_ADSPEND_CEILING",
        _cmo.AUTONOMOUS_ADSPEND_CEILING_USD_PER_DAY,
    ))

    post_draft = None
    try:
        from .. import draft_review
        post_draft = draft_review.post_draft
    except Exception as exc:
        log.debug("cmo: draft_review unavailable (%s) — only auto-approve open",
                  exc)

    decision = _cmo.approve_adspend(
        amount_usd_per_day=amount_usd_per_day,
        channel=channel,
        business_id=business_id,
        justification=justification,
        spend_ceiling=spend_ceiling,
        post_draft=post_draft,
        review_chat_id=os.environ.get("REVIEW_CHAT_ID"),
    )

    try:
        from .. import audit_emit
        audit_emit.row(
            "cmo_adspend_approved" if decision.status == "approved"
            else "cmo_adspend_blocked",
            "CMO",
            business_id=business_id,
            amount_usd_per_day=amount_usd_per_day,
            channel=channel,
            status=decision.status,
            draft_id=decision.draft_id,
        )
    except Exception as exc:
        log.debug("cmo: audit_emit (adspend) suppressed: %s", exc)

    return decision


__all__ = [
    "run_cycle",
    "request_adspend_approval",
    "set_marketing_provider",
]
