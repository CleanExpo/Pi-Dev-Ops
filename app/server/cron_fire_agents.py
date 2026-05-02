"""
cron_fire_agents.py — Agent-style fire functions with Telegram summaries (GROUP F).

Contains:
    _fire_board_meeting_trigger()   — full board meeting + Telegram summary
    _fire_scout_trigger()           — Scout Agent + Telegram summary (RA-684)
    _fire_feedback_trigger()        — outcome feedback loop + Telegram summary (RA-689)
    _fire_meta_curator_trigger()    — meta-curator scan + propose (RA-1839)
"""
import asyncio


async def _fire_meta_curator_trigger(trigger: dict, log) -> None:
    """RA-1839 — Run meta-curator scan for the configured source, post HITL drafts.

    Trigger fields:
      * ``source`` (str): "lessons" | "prs" | "both" (default "both")
      * Other standard schedule fields (hour, minute, weekday, ...)

    Output is a curator_proposal audit row per cluster + draft posted to
    REVIEW_CHAT_ID via draft_review. No Telegram summary here — every
    draft already lands in the review chat individually.
    """
    log.info("Firing meta_curator trigger id=%s source=%s",
             trigger.get("id"), trigger.get("source", "both"))

    source = (trigger.get("source") or "both").lower()
    loop = asyncio.get_event_loop()

    def _run() -> dict:
        # Import inside the executor — keeps the swarm package optional
        # at module load time and lets the cron module fail gracefully
        # if Pi-Dev-Ops is checked out without `swarm/`.
        from swarm import meta_curator
        if source == "lessons":
            clusters = meta_curator.scan_lessons()
        elif source == "prs":
            clusters = meta_curator.scan_pr_diffs(since_days=1)
        else:
            clusters = (meta_curator.scan_lessons() +
                        meta_curator.scan_pr_diffs(since_days=1))
        results = [meta_curator.propose_from_cluster(c) for c in clusters]
        return {"clusters": len(clusters), "results": results}

    try:
        out = await loop.run_in_executor(None, _run)
        proposed = sum(1 for r in out["results"] if r.get("status") == "pending")
        log.info(
            "meta_curator id=%s clusters=%d proposed=%d",
            trigger.get("id"), out["clusters"], proposed,
        )
    except Exception as exc:  # noqa: BLE001 — never raise from cron path
        log.warning("meta_curator trigger id=%s failed: %s",
                    trigger.get("id"), exc)


async def _fire_board_meeting_trigger(trigger: dict, log) -> None:
    """Fire the full board meeting (all 6 phases) in a thread executor, then Telegram summary."""
    import json as _json
    from . import config

    log.info("Firing board_meeting trigger id=%s", trigger["id"])
    loop = asyncio.get_event_loop()

    from .agents.board_meeting import run_full_board_meeting
    result: dict = await loop.run_in_executor(None, run_full_board_meeting)

    swot     = result.get("swot") or {}
    recs     = result.get("sprint_recommendations") or {}
    gap      = result.get("gap_audit") or {}
    status   = result.get("status") or {}
    duration = result.get("duration_s", 0)

    critical_n = len(gap.get("critical", []))
    high_n     = len(gap.get("high", []))
    zte_v2     = status.get("zte_v2") or {}
    zte_str    = (
        f"ZTE v2: *{zte_v2['total']}/{zte_v2['max']}* ({zte_v2['band']})"
        if zte_v2 else
        f"ZTE v1: *{status.get('zte_score', '?')}*"
    )

    def _short(text: str, n: int = 400) -> str:
        return (text[:n] + "…") if len(text) > n else text

    summary_text = (
        "🏛 *Pi-CEO Weekly Board Meeting — Complete*\n\n"
        + zte_str + "\n"
        + f"Duration: {duration:.0f}s\n\n"
        + "*SWOT Summary*\n"
        + _short(swot.get("summary", swot.get("analysis", "—")), 300) + "\n\n"
        + "*Sprint Recommendations*\n"
        + _short(recs.get("summary", recs.get("recommendations", "—")), 300) + "\n\n"
        + f"*Gap Audit:* {critical_n} critical, {high_n} high findings"
        + (" → Linear tickets created" if not gap.get("dry_run") else " (dry-run)")
    )

    token   = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_ALERT_CHAT_ID
    if token and chat_id:
        import urllib.request as _ureq
        payload = _json.dumps({
            "chat_id": chat_id, "text": summary_text,
            "parse_mode": "Markdown", "disable_web_page_preview": True,
        }).encode()
        req = _ureq.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with _ureq.urlopen(req, timeout=10):
                pass
            log.info("Board meeting Telegram summary sent")
        except Exception as exc:
            log.warning("Board meeting Telegram send failed: %s", exc)

    log.info("Board meeting trigger id=%s complete in %.1fs", trigger["id"], duration)


async def _fire_scout_trigger(trigger: dict, log) -> None:
    """RA-684 — Fire the Scout Agent (GitHub/ArXiv/HN intel) and send a Telegram summary."""
    import json as _json
    from . import config

    log.info("Firing scout trigger id=%s", trigger["id"])
    loop = asyncio.get_event_loop()

    from .agents.scout import run_scout_cycle
    result: dict = await loop.run_in_executor(None, run_scout_cycle)

    findings = result.get("findings", 0)
    created  = result.get("issues_created", [])
    src_str  = ", ".join(f"{k}={v}" for k, v in result.get("sources", {}).items())

    summary_text = (
        "🔍 *Pi-CEO Scout Agent — Complete*\n\n"
        f"New findings: *{findings}*\n"
        f"Sources: {src_str}\n"
        f"Linear issues created: *{len(created)}*"
        + (f"\n{chr(10).join(created[:10])}" if created else "")
    )

    token   = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_ALERT_CHAT_ID
    if token and chat_id:
        import urllib.request as _ureq
        payload = _json.dumps({
            "chat_id": chat_id, "text": summary_text,
            "parse_mode": "Markdown", "disable_web_page_preview": True,
        }).encode()
        req = _ureq.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with _ureq.urlopen(req, timeout=10):
                pass
            log.info("Scout Telegram summary sent")
        except Exception as exc:
            log.warning("Scout Telegram send failed: %s", exc)

    log.info("Scout trigger id=%s complete: findings=%d issues=%d", trigger["id"], findings, len(created))


async def _fire_feedback_trigger(trigger: dict, log) -> None:
    """RA-689 — Fire the outcome feedback loop and send a Telegram summary."""
    import json as _json
    from . import config

    log.info("Firing feedback trigger id=%s", trigger["id"])
    loop = asyncio.get_event_loop()

    from .agents.feedback_loop import run_feedback_cycle
    result: dict = await loop.run_in_executor(None, run_feedback_cycle)

    analysed     = result.get("features_analysed", 0)
    bvi          = result.get("bvi_contribution", {})
    stale_issues = result.get("stale_issues_created", [])
    patterns     = result.get("patterns", [])

    summary_text = (
        "🔄 *Pi-CEO Feedback Loop — Complete*\n\n"
        f"Features analysed: *{analysed}*\n"
        f"Positive outcomes: {bvi.get('features_with_positive_outcome', 0)}\n"
        f"Negative outcomes: {bvi.get('features_with_negative_outcome', 0)}\n"
        f"Stale (>30 days): {bvi.get('features_stale', 0)}\n"
        f"Pending signal: {bvi.get('features_pending_signal', 0)}\n"
        f"Stale review issues created: *{len(stale_issues)}*"
        + (f"\nPatterns: {', '.join(p['pattern'] for p in patterns[:3])}" if patterns else "")
    )

    token   = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_ALERT_CHAT_ID
    if token and chat_id:
        import urllib.request as _ureq
        payload = _json.dumps({
            "chat_id": chat_id, "text": summary_text,
            "parse_mode": "Markdown", "disable_web_page_preview": True,
        }).encode()
        req = _ureq.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with _ureq.urlopen(req, timeout=10):
                pass
            log.info("Feedback loop Telegram summary sent")
        except Exception as exc:
            log.warning("Feedback loop Telegram send failed: %s", exc)

    log.info("Feedback trigger id=%s complete: analysed=%d stale_issues=%d",
             trigger["id"], analysed, len(stale_issues))
