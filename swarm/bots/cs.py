"""swarm/bots/cs.py — RA-1862 (Wave 4 A4): CS-tier1 senior-agent bot.

Same shape as cfo / cmo / cto. Refund > $100 routes through draft_review;
NPS / FCR / GRR breaches surface in daily brief + alerts.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .. import cs as _cs

log = logging.getLogger("swarm.bots.cs")

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DAILY_HOUR_UTC = 6


CsProvider = Callable[[], list[_cs.RawCsMetrics]]


def _default_cs_provider() -> list[_cs.RawCsMetrics]:
    """Production provider — routes through ``swarm.providers.select_cs_provider``.

    Defaults to synthetic; flip with ``TAO_CS_PROVIDER=zendesk`` once a
    helpdesk connector is wired (follow-up).
    """
    try:
        from ..providers import select_cs_provider
    except Exception as exc:  # noqa: BLE001
        log.warning("cs: provider import failed (%s) — empty list", exc)
        return []
    try:
        return select_cs_provider()()
    except Exception as exc:  # noqa: BLE001
        log.warning("cs: provider call failed (%s) — empty list", exc)
        return []


_provider: CsProvider = _default_cs_provider


def set_cs_provider(provider: CsProvider) -> None:
    global _provider
    _provider = provider


def _is_daily_fire_window(state: dict, now: datetime) -> bool:
    target_hour = int(os.environ.get(
        "TAO_CS_DAILY_HOUR_UTC", DEFAULT_DAILY_HOUR_UTC))
    if now.hour != target_hour:
        return False
    last_fired = state.get("cs_last_daily_fire")
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
        return False
    try:
        from .. import kill_switch
        if kill_switch.is_active():
            return False
    except Exception:
        pass
    return True


def _is_test_mode() -> bool:
    return os.environ.get("TAO_DRAFT_REVIEW_TEST", "0") == "1"


def run_cycle(unacked_count: int, *, state: dict | None = None) -> dict:
    state = state if state is not None else {}

    if not _is_test_mode() and not _gates_open():
        return {"status": "skipped", "reason": "gates_closed"}

    raw_list = _provider()
    if not raw_list:
        return {"status": "skipped", "reason": "no_data"}

    snapshots: list[_cs.CsMetrics] = []
    all_breaches: list[_cs.CsBreach] = []

    for raw in raw_list:
        prev = _cs.load_last_snapshot(raw.business_id, repo_root=REPO_ROOT)
        curr = _cs.compute_metrics(raw)
        snapshots.append(curr)
        _cs.append_snapshot(curr, repo_root=REPO_ROOT)

        try:
            from .. import audit_emit
            audit_emit.row(
                "cs_metric_snapshot", "CS",
                business_id=curr.business_id,
                nps=curr.nps, fcr_pct=curr.fcr_pct,
                grr_pct=curr.grr_pct,
                avg_first_response_minutes=curr.avg_first_response_minutes,
                open_enterprise_churn_threats=curr.open_enterprise_churn_threats,
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("cs: audit_emit (snapshot) suppressed: %s", exc)

        breaches = _cs.detect_breaches(curr, prev)
        for b in breaches:
            all_breaches.append(b)
            try:
                from .. import audit_emit
                audit_emit.row(
                    "cs_alert", "CS",
                    business_id=b.business_id, metric=b.metric,
                    value=b.value, threshold=b.threshold,
                    severity=b.severity,
                )
            except Exception as exc:
                log.debug("cs: audit_emit (alert) suppressed: %s", exc)

    now = datetime.now(timezone.utc)
    fired_brief = False
    if _is_daily_fire_window(state, now):
        brief = _cs.assemble_daily_brief(snapshots, all_breaches)
        try:
            from .. import draft_review
            draft = draft_review.post_draft(
                draft_text=brief,
                destination_chat_id=os.environ.get("REVIEW_CHAT_ID", "review"),
                drafted_by_role="CS",
                originating_intent_id="cs-daily-brief",
            )
            log.info("cs daily brief posted: draft_id=%s", draft.get("draft_id"))
            state["cs_last_daily_fire"] = now.isoformat()
            fired_brief = True
            try:
                from .. import audit_emit
                audit_emit.row(
                    "cs_brief_emitted", "CS",
                    draft_id=draft.get("draft_id"),
                    snapshot_count=len(snapshots),
                    breach_count=len(all_breaches),
                )
            except Exception:
                pass
        except Exception as exc:
            log.warning("cs: daily brief post failed: %s", exc)

    return {
        "status": "ok",
        "snapshots": len(snapshots),
        "breaches": len(all_breaches),
        "brief_posted": fired_brief,
    }


def request_refund_approval(
    *,
    amount_usd: float,
    customer_id: str,
    business_id: str,
    justification: str,
) -> _cs.RefundDecision:
    """Public entry-point — refunds <= $100 auto-approve, above route HITL."""
    refund_ceiling = float(os.environ.get(
        "TAO_CS_REFUND_CEILING", _cs.AUTONOMOUS_REFUND_CEILING_USD))

    post_draft = None
    try:
        from .. import draft_review
        post_draft = draft_review.post_draft
    except Exception as exc:
        log.debug("cs: draft_review unavailable (%s)", exc)

    decision = _cs.approve_refund(
        amount_usd=amount_usd, customer_id=customer_id,
        business_id=business_id, justification=justification,
        refund_ceiling=refund_ceiling,
        post_draft=post_draft,
        review_chat_id=os.environ.get("REVIEW_CHAT_ID"),
    )

    try:
        from .. import audit_emit
        audit_emit.row(
            "cs_refund_approved" if decision.status == "approved"
            else "cs_refund_blocked",
            "CS",
            business_id=business_id, customer_id=customer_id,
            amount_usd=amount_usd,
            status=decision.status, draft_id=decision.draft_id,
        )
    except Exception as exc:
        log.debug("cs: audit_emit (refund) suppressed: %s", exc)

    return decision


__all__ = [
    "run_cycle",
    "request_refund_approval",
    "set_cs_provider",
]
