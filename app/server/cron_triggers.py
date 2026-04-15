"""
cron_triggers.py — Trigger fire-functions, schedule matching, and dispatcher (GROUP F).

Contains:
    _matches()                       — cron schedule matching with debounce
    _should_catch_up()               — startup catch-up check for overdue triggers
    _fire_scan_trigger()             — Pi-SEO scanner
    _fire_monitor_trigger()          — Pi-SEO monitor agent
    _fire_intel_refresh_trigger()    — Anthropic intel refresh (RA-587)
    _fire_script_trigger()           — generic script subprocess
    _fire_board_meeting_trigger()    — full board meeting
    _fire_scout_trigger()            — Scout Agent (RA-684)
    _fire_feedback_trigger()         — outcome feedback loop (RA-689)
    _fire_trigger()                  — type-based dispatcher
"""
import asyncio
import os
import time


def _matches(
    trigger: dict,
    now_hour: int,
    now_minute: int,
    now_weekday: int | None = None,
    now_day: int | None = None,
    now_month: int | None = None,
) -> bool:
    """Return True if trigger schedule matches the given time components."""
    if not trigger.get("enabled", True):
        return False
    if trigger.get("minute") != now_minute:
        return False
    h = trigger.get("hour")
    if h is not None and h != now_hour:
        return False
    wd = trigger.get("weekday")
    if wd is not None and now_weekday is not None and wd != now_weekday:
        return False
    dom = trigger.get("day_of_month")
    if dom is not None and now_day is not None and dom != now_day:
        return False
    months = trigger.get("month")
    if months is not None and now_month is not None:
        if isinstance(months, list):
            if now_month not in months:
                return False
        elif now_month != months:
            return False
    # Debounce: don't fire twice in the same minute.
    last = trigger.get("last_fired_at")
    if last and abs(time.time() - last) < 90:
        return False
    return True


def _should_catch_up(trigger: dict) -> bool:
    """
    Return True if this scan/monitor trigger is overdue and should fire immediately
    on startup. Criteria: enabled, has a scheduled hour, and hasn't fired in >8h
    (or has never fired). Build triggers are excluded — they fire on demand only.
    """
    if not trigger.get("enabled", True):
        return False
    if trigger.get("type", "build") not in ("scan", "monitor", "intel_refresh", "analyse_lessons"):
        return False
    last = trigger.get("last_fired_at")
    if last is None:
        return True
    hours_since = abs(time.time() - last) / 3600
    return hours_since > 8


async def _fire_scan_trigger(trigger: dict, log) -> None:
    """Fire a Pi-SEO scan trigger directly via the scanner module."""
    from . import config  # RA-586 gate
    if not config.PI_SEO_ACTIVE:
        log.info(
            "Scan trigger id=%s skipped — PI_SEO_ACTIVE=0 (set PI_SEO_ACTIVE=1 in Railway to enable)",
            trigger["id"],
        )
        return
    from .scanner import ProjectScanner
    from .triage import TriageEngine
    priority = trigger.get("priority_filter")
    scan_types = trigger.get("scan_types") or None
    scanner = ProjectScanner()
    engine = TriageEngine()
    log.info("Firing scan trigger id=%s priority=%s types=%s", trigger["id"], priority, scan_types)
    all_results = await scanner.scan_all(priority=priority, scan_types=scan_types)
    created = engine.triage_all(all_results)
    total = sum(len(v) for v in created.values())
    log.info("Scan trigger id=%s complete: %d tickets created", trigger["id"], total)


async def _fire_monitor_trigger(trigger: dict, log) -> None:
    """Fire a Pi-SEO monitor trigger via the monitor agent."""
    from . import config  # RA-586 gate
    if not config.PI_SEO_ACTIVE:
        log.info(
            "Monitor trigger id=%s skipped — PI_SEO_ACTIVE=0 (set PI_SEO_ACTIVE=1 in Railway to enable)",
            trigger["id"],
        )
        return
    from .agents.pi_seo_monitor import run_monitor_cycle
    project_id = trigger.get("project_id") or None
    use_agent = trigger.get("use_agent", False)
    log.info("Firing monitor trigger id=%s project=%s use_agent=%s", trigger["id"], project_id, use_agent)
    digest = run_monitor_cycle(project_id=project_id, use_agent=use_agent, dry_run=False)
    log.info(
        "Monitor trigger id=%s complete: health=%d alerts=%d",
        trigger["id"], digest.portfolio_health, len(digest.alerts),
    )


async def _fire_intel_refresh_trigger(trigger: dict, log) -> None:
    """RA-587 — Fire the Anthropic intel refresh loop directly (no subprocess)."""
    from .agents.anthropic_intel_refresh import refresh_anthropic_intel
    log.info("Firing intel_refresh trigger id=%s", trigger["id"])
    result = await refresh_anthropic_intel(dry_run=False)
    fetched = len(result.get("fetched_urls", []))
    brief = result.get("brief_path")
    errors = result.get("errors", [])
    if errors:
        log.warning("intel_refresh: %d fetch errors: %s", len(errors), errors)
    log.info(
        "intel_refresh id=%s complete: fetched=%d brief=%s",
        trigger["id"], fetched, brief or "none (no delta)",
    )
    # RA-837 — consolidate anthropic docs into a single digest file
    import subprocess as _subprocess
    _repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
    _consolidate_result = _subprocess.run(
        ["python", "scripts/consolidate_anthropic_docs.py"],
        capture_output=True, text=True, timeout=30,
        cwd=_repo_root,
    )
    if _consolidate_result.returncode != 0:
        log.warning("consolidate_anthropic_docs failed: %s", _consolidate_result.stderr[:200])
    else:
        log.info("Anthropic docs consolidated: %s", _consolidate_result.stdout.strip()[:100])


async def _fire_script_trigger(trigger: dict, log) -> None:
    """Fire a script-based trigger (analyse_lessons, etc.) as a subprocess."""
    script = trigger.get("script", "")
    if not script:
        log.warning("Script trigger id=%s has no 'script' field — skipped", trigger["id"])
        return
    log.info("Firing script trigger id=%s script=%s", trigger["id"], script)
    _repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
    cmd = ["python3"] + script.split() if not script.startswith("python") else script.split()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=_repo_root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    if proc.returncode != 0:
        log.error(
            "Script trigger id=%s exited %d: %s",
            trigger["id"], proc.returncode,
            stderr.decode("utf-8", errors="replace")[:500],
        )
    else:
        log.info("Script trigger id=%s complete (rc=0)", trigger["id"])


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


async def _fire_trigger(trigger: dict, log) -> None:
    """Dispatch a single trigger by type. Raises on failure."""
    from .sessions import create_session
    trigger_type = trigger.get("type", "build")
    if trigger_type == "scan":
        await _fire_scan_trigger(trigger, log)
    elif trigger_type == "monitor":
        await _fire_monitor_trigger(trigger, log)
    elif trigger_type == "intel_refresh":                      # RA-587
        await _fire_intel_refresh_trigger(trigger, log)
    elif trigger_type in ("analyse_lessons", "fallback_dryrun", "zte_v2_score"):
        await _fire_script_trigger(trigger, log)
    elif trigger_type == "board_meeting":
        await _fire_board_meeting_trigger(trigger, log)
    elif trigger_type == "scout":                              # RA-684
        await _fire_scout_trigger(trigger, log)
    elif trigger_type == "feedback_loop":                      # RA-689
        await _fire_feedback_trigger(trigger, log)
    else:
        await create_session(
            repo_url=trigger["repo_url"],
            brief=trigger.get("brief", ""),
            model=trigger.get("model", "sonnet"),
        )
        log.info("Fired build trigger id=%s repo=%s", trigger["id"], trigger.get("repo_url"))
