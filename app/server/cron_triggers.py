"""
cron_triggers.py — Schedule matching, core fire functions, and dispatcher (GROUP F).

Contains:
    _matches()                      — cron schedule matching with debounce
    _should_catch_up()              — startup catch-up check for overdue triggers
    _fire_scan_trigger()            — Pi-SEO scanner
    _fire_monitor_trigger()         — Pi-SEO monitor agent
    _fire_intel_refresh_trigger()   — Anthropic intel refresh (RA-587)
    _fire_script_trigger()          — generic script subprocess
    _fire_trigger()                 — type-based dispatcher

Agent fire functions with Telegram summaries live in cron_fire_agents.py.
"""
import asyncio
import os
import time

from .cron_fire_agents import (
    _fire_board_meeting_trigger,
    _fire_feedback_trigger,
    _fire_meta_curator_trigger,
    _fire_scout_trigger,
)


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
    # Optional weekday gate (0=Monday per Python convention, matches cron spec)
    wd = trigger.get("weekday")
    if wd is not None and now_weekday is not None and wd != now_weekday:
        return False
    # Optional day-of-month gate (RA-634: quarterly triggers)
    dom = trigger.get("day_of_month")
    if dom is not None and now_day is not None and dom != now_day:
        return False
    # Optional month gate: int or list[int] (RA-634: [1, 4, 7, 10] = quarterly)
    months = trigger.get("month")
    if months is not None and now_month is not None:
        if isinstance(months, list):
            if now_month not in months:
                return False
        elif now_month != months:
            return False
    # Debounce: don't fire twice in the same minute.
    # Use abs() to guard against bogus future last_fired_at values.
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


async def _fire_portfolio_pulse_trigger(trigger: dict, log) -> None:
    """Fire the Portfolio Pulse — RA-1888 (daily) or RA-2006 (weekly recap).

    Calls swarm.portfolio_pulse.run_all_projects() which builds one
    markdown briefing per project under .harness/portfolio-pulse/.
    Sibling tickets (RA-1889..1893) plug section providers + delivery.
    Failure of any single project does NOT raise — the whole batch
    completes and the log surfaces per-project errors.

    Trigger fields:
      * ``projects`` (list[str], optional) — override DEFAULT_PROJECTS
      * ``lookback_hours`` (int, optional, default 24) — RA-2006: pass 168
        on the Friday weekly trigger so section providers query 7 days
        instead of 24h. The window flows through `lookback_window()` so
        every provider sees the same value without per-provider plumbing.
      * ``recap_label`` (str, optional) — used by Telegram delivery
        (RA-1893) for distinct framing. Defaults to "Daily" / "Weekly"
        based on lookback_hours.
    """
    log.info("Firing portfolio_pulse id=%s", trigger["id"])
    try:
        from swarm import portfolio_pulse as _pp  # noqa: PLC0415
        from swarm.portfolio_pulse import run_all_projects  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.error("portfolio_pulse import failed: %s", exc)
        return

    # Import sibling section providers so they self-register before run.
    # Each is fail-soft: missing dep / module-level raise → placeholder
    # foundation provider stays in place for that section.
    for _mod in ("portfolio_pulse_linear",):
        try:
            __import__(f"swarm.{_mod}")
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "portfolio_pulse: section provider swarm.%s failed to load: %s",
                _mod, exc,
            )

    projects = trigger.get("projects")  # optional override; None → DEFAULT_PROJECTS
    lookback_hours = int(trigger.get("lookback_hours") or 24)
    if lookback_hours <= 0:
        lookback_hours = 24

    # Run sync function in a worker thread — keeps the cron loop async-clean.
    # The lookback_window context manager scopes the override to this run
    # so the daily trigger isn't accidentally widened.
    def _run() -> list:
        with _pp.lookback_window(lookback_hours):
            return run_all_projects(projects=projects)

    results = await asyncio.to_thread(_run)
    ok = sum(1 for r in results if not r.error)
    err = sum(1 for r in results if r.error)
    log.info(
        "portfolio_pulse id=%s complete: %d ok, %d errored, lookback=%dh",
        trigger["id"], ok, err, lookback_hours,
    )

    # RA-2006 — optional Telegram delivery. Opt-in via `deliver_telegram: true`
    # in the trigger config so the existing daily file-only cron isn't
    # silently changed. The Friday weekly trigger sets this to true.
    if trigger.get("deliver_telegram"):
        try:
            from swarm import portfolio_pulse_telegram as _ppt  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            log.warning("portfolio_pulse: telegram delivery import failed: %s", exc)
            return

        # Compose a Telegram digest by stitching the cross-portfolio
        # synthesis (if available) + a one-line-per-project summary table.
        is_weekly = lookback_hours >= 168
        recap_label = (
            trigger.get("recap_label")
            or ("🗓 Pi-CEO Weekly Recap" if is_weekly else "📊 Pi-CEO Daily Pulse")
        )
        from datetime import datetime as _dt, timezone as _tz  # noqa: PLC0415
        today = _dt.now(_tz.utc).strftime("%a %d %b %Y")
        synthesis = getattr(results, "cross_portfolio_synthesis", "") or ""
        per_project_lines = []
        for r in results:
            tag = "✅" if not r.error else "⚠️"
            per_project_lines.append(f"- {tag} `{r.project_id}`")
        per_project_block = "\n".join(per_project_lines) or "_(no projects)_"
        digest_md = (
            f"# {recap_label} — {today}\n\n"
            + (synthesis + "\n\n" if synthesis else "")
            + "## Per-project status\n"
            + per_project_block
            + "\n\n"
            + (
                "_Full markdown briefings live under "
                "`.harness/portfolio-pulse/<project>/<date>.md`._"
            )
        )

        try:
            delivery = await asyncio.to_thread(
                _ppt.deliver_to_telegram, digest_md,
                voice=bool(trigger.get("voice", False)),
            )
            log.info(
                "portfolio_pulse id=%s telegram delivery: sent=%s chunks=%d errors=%d",
                trigger["id"], delivery.get("sent"),
                delivery.get("chunks", 0), len(delivery.get("errors") or []),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("portfolio_pulse: telegram delivery raised: %s", exc)


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
    elif trigger_type == "meta_curator":                       # RA-1839
        await _fire_meta_curator_trigger(trigger, log)
    elif trigger_type == "portfolio_pulse":                    # RA-1888
        await _fire_portfolio_pulse_trigger(trigger, log)
    else:
        await create_session(
            repo_url=trigger["repo_url"],
            brief=trigger.get("brief", ""),
            model=trigger.get("model", "sonnet"),
        )
        log.info("Fired build trigger id=%s repo=%s", trigger["id"], trigger.get("repo_url"))
