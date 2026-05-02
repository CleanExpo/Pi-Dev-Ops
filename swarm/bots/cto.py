"""swarm/bots/cto.py — RA-1861 (Wave 4 A3): CTO senior-agent bot.

Same shape as cfo / cmo bots: per-cycle pull RawPlatformMetrics →
compute → detect breaches → audit-emit → daily brief on the fire window.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .. import cto as _cto

log = logging.getLogger("swarm.bots.cto")

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DAILY_HOUR_UTC = 6


PlatformProvider = Callable[[], list[_cto.RawPlatformMetrics]]


def _default_platform_provider() -> list[_cto.RawPlatformMetrics]:
    """Production provider — routes through ``swarm.providers.select_platform_provider``.

    Defaults to synthetic so the daily brief is never empty; flip to real
    data with ``TAO_CTO_PROVIDER=github_actions`` once GitHub Actions /
    Vercel observability connectors are wired (follow-up).

    Never raises — any provider failure degrades to empty list and the bot
    self-skips that cycle.
    """
    try:
        from ..providers import select_platform_provider
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "cto: platform provider import failed (%s) — empty list", exc
        )
        return []
    try:
        return select_platform_provider()()
    except Exception as exc:  # noqa: BLE001
        log.warning("cto: platform provider call failed (%s) — empty list", exc)
        return []


_provider: PlatformProvider = _default_platform_provider


def set_platform_provider(provider: PlatformProvider) -> None:
    """Override the platform provider (used by tests)."""
    global _provider
    _provider = provider


def _is_daily_fire_window(state: dict, now: datetime) -> bool:
    target_hour = int(os.environ.get(
        "TAO_CTO_DAILY_HOUR_UTC", DEFAULT_DAILY_HOUR_UTC))
    if now.hour != target_hour:
        return False
    last_fired = state.get("cto_last_daily_fire")
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

    # ── RA-1868 — consume Board directives for CTO before metrics work.
    cto_directives_acted = 0
    try:
        from .. import board_directive_consumer  # noqa: PLC0415
        new_directives = board_directive_consumer.consume_for(
            "CTO", state=state, repo_root=REPO_ROOT,
        )
        for d in new_directives:
            cto_directives_acted += 1
            try:
                from .. import audit_emit
                audit_emit.row(
                    "board_directive_consumed", "CTO",
                    session_id=d.session_id,
                    action=d.action[:200],
                    deadline=d.deadline,
                )
            except Exception:
                pass
            log.info("cto: board directive %s — %s",
                     d.session_id, d.action[:80])
    except Exception as exc:  # noqa: BLE001
        log.debug("cto: directive consume suppressed (%s)", exc)

    raw_list = _provider()
    if not raw_list:
        return {"status": "skipped", "reason": "no_data"}

    snapshots: list[_cto.PlatformMetrics] = []
    all_breaches: list[_cto.PlatformBreach] = []

    for raw in raw_list:
        prev = _cto.load_last_snapshot(raw.business_id, repo_root=REPO_ROOT)
        curr = _cto.compute_metrics(raw)
        snapshots.append(curr)
        _cto.append_snapshot(curr, repo_root=REPO_ROOT)

        try:
            from .. import audit_emit
            audit_emit.row(
                "cto_metric_snapshot", "CTO",
                business_id=curr.business_id,
                deploy_freq_per_week=curr.deploy_freq_per_week,
                lead_time_hours_p50=curr.lead_time_hours_p50,
                mttr_hours=curr.mttr_hours,
                change_failure_rate=curr.change_failure_rate,
                p99_latency_ms=curr.p99_latency_ms,
                uptime_pct=curr.uptime_pct,
                dora_band=curr.dora_band,
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("cto: audit_emit (snapshot) suppressed: %s", exc)

        breaches = _cto.detect_breaches(curr, prev)
        for b in breaches:
            all_breaches.append(b)
            try:
                from .. import audit_emit
                audit_emit.row(
                    "cto_alert", "CTO",
                    business_id=b.business_id, metric=b.metric,
                    value=b.value, threshold=b.threshold,
                    severity=b.severity,
                )
            except Exception as exc:
                log.debug("cto: audit_emit (alert) suppressed: %s", exc)

    now = datetime.now(timezone.utc)
    fired_brief = False
    if _is_daily_fire_window(state, now):
        brief = _cto.assemble_daily_brief(snapshots, all_breaches)
        try:
            from .. import draft_review
            draft = draft_review.post_draft(
                draft_text=brief,
                destination_chat_id=os.environ.get("REVIEW_CHAT_ID", "review"),
                drafted_by_role="CTO",
                originating_intent_id="cto-daily-brief",
            )
            log.info("cto daily brief posted: draft_id=%s", draft.get("draft_id"))
            state["cto_last_daily_fire"] = now.isoformat()
            fired_brief = True
            try:
                from .. import audit_emit
                audit_emit.row(
                    "cto_brief_emitted", "CTO",
                    draft_id=draft.get("draft_id"),
                    snapshot_count=len(snapshots),
                    breach_count=len(all_breaches),
                )
            except Exception:
                pass
        except Exception as exc:
            log.warning("cto: daily brief post failed: %s", exc)

    return {
        "status": "ok",
        "snapshots": len(snapshots),
        "breaches": len(all_breaches),
        "brief_posted": fired_brief,
    }


def request_pr_merge_approval(
    *,
    repo: str,
    pr_number: int | None,
    target_branch: str,
    title: str,
    is_production: bool,
) -> _cto.PrMergeDecision:
    """Public entry-point: any bot/agent requesting a production PR merge.

    Auto-approves when is_production=False; routes production merges
    through draft_review (HITL).
    """
    post_draft = None
    try:
        from .. import draft_review
        post_draft = draft_review.post_draft
    except Exception as exc:
        log.debug("cto: draft_review unavailable (%s)", exc)

    decision = _cto.approve_pr_merge(
        repo=repo, pr_number=pr_number,
        target_branch=target_branch, title=title,
        is_production=is_production,
        post_draft=post_draft,
        review_chat_id=os.environ.get("REVIEW_CHAT_ID"),
    )

    try:
        from .. import audit_emit
        audit_emit.row(
            "cto_pr_merge_approved" if decision.status == "approved"
            else "cto_pr_merge_blocked",
            "CTO",
            repo=repo, pr_number=pr_number,
            target_branch=target_branch,
            is_production=is_production,
            status=decision.status, draft_id=decision.draft_id,
        )
    except Exception as exc:
        log.debug("cto: audit_emit (pr) suppressed: %s", exc)

    return decision


__all__ = [
    "run_cycle",
    "request_pr_merge_approval",
    "set_platform_provider",
]
