"""
cron.py — Scheduled build triggers (GROUP F).

Stores cron triggers in .harness/cron-triggers.json.
Background loop checks every 60s and fires sessions when schedule matches.

Trigger schema:
  {
    "id": str,
    "repo_url": str,
    "brief": str,
    "model": str,
    "hour": int | null,            # UTC hour (0-23), null = any hour
    "minute": int,                 # UTC minute (0-59)
    "weekday": int | null,         # 0=Monday .. 6=Sunday; null = any day of week
    "day_of_month": int | null,    # 1-31; null = any day of month (RA-634)
    "month": int | list[int] | null,  # 1-12 or list e.g. [1,4,7,10]; null = any month (RA-634)
    "enabled": bool,
    "created_at": float,
    "last_fired_at": float | null
  }
"""
import asyncio
import json
import os
import time
import uuid

_TRIGGERS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", ".harness", "cron-triggers.json"
)


def _load() -> list[dict]:
    try:
        with open(_TRIGGERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def _save(triggers: list[dict]) -> None:
    os.makedirs(os.path.dirname(_TRIGGERS_FILE), exist_ok=True)
    tmp = _TRIGGERS_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(triggers, f, indent=2)
        os.replace(tmp, _TRIGGERS_FILE)
    except OSError:
        pass


def list_triggers() -> list[dict]:
    return _load()


def create_trigger(repo_url: str, brief: str, minute: int, hour: int | None = None, model: str = "sonnet") -> dict:
    trigger = {
        "id": uuid.uuid4().hex[:12],
        "repo_url": repo_url,
        "brief": brief,
        "model": model,
        "hour": hour,
        "minute": minute,
        "enabled": True,
        "created_at": time.time(),
        "last_fired_at": None,
    }
    triggers = _load()
    triggers.append(trigger)
    _save(triggers)
    return trigger


def delete_trigger(tid: str) -> bool:
    triggers = _load()
    before = len(triggers)
    triggers = [t for t in triggers if t.get("id") != tid]
    if len(triggers) == before:
        return False
    _save(triggers)
    return True


def _matches(
    trigger: dict,
    now_hour: int,
    now_minute: int,
    now_weekday: int | None = None,
    now_day: int | None = None,
    now_month: int | None = None,
) -> bool:
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
    # Each scan/monitor trigger has a repeat interval encoded in its id (every 6h for high, etc.)
    # Use a conservative 8h threshold — if it's been > 8h since last fire, run it.
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


async def _fire_script_trigger(trigger: dict, log) -> None:
    """Fire a script-based trigger (analyse_lessons, etc.) as a subprocess."""
    import asyncio as _asyncio
    script = trigger.get("script", "")
    if not script:
        log.warning("Script trigger id=%s has no 'script' field — skipped", trigger["id"])
        return
    log.info("Firing script trigger id=%s script=%s", trigger["id"], script)
    # Resolve relative paths against the repo root
    _repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
    cmd = ["python3"] + script.split() if not script.startswith("python") else script.split()
    proc = await _asyncio.create_subprocess_exec(
        *cmd,
        cwd=_repo_root,
        stdout=_asyncio.subprocess.PIPE,
        stderr=_asyncio.subprocess.PIPE,
    )
    stdout, stderr = await _asyncio.wait_for(proc.communicate(), timeout=300)
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
    import asyncio as _asyncio
    import json as _json
    from . import config

    log.info("Firing board_meeting trigger id=%s", trigger["id"])
    loop = _asyncio.get_event_loop()

    # run_full_board_meeting is synchronous — run it off the event loop
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

    # Telegram summary — truncate long text for readability
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
            "chat_id": chat_id,
            "text": summary_text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
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
    import asyncio as _asyncio
    import json as _json
    from . import config

    log.info("Firing scout trigger id=%s", trigger["id"])
    loop = _asyncio.get_event_loop()

    from .agents.scout import run_scout_cycle
    result: dict = await loop.run_in_executor(None, run_scout_cycle)

    findings  = result.get("findings", 0)
    created   = result.get("issues_created", [])
    sources   = result.get("sources", {})
    src_str   = ", ".join(f"{k}={v}" for k, v in sources.items())

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
            "chat_id": chat_id,
            "text": summary_text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
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
    elif trigger_type == "analyse_lessons":
        await _fire_script_trigger(trigger, log)
    elif trigger_type == "fallback_dryrun":              # RA-634: quarterly API key test
        await _fire_script_trigger(trigger, log)
    elif trigger_type == "board_meeting":
        await _fire_board_meeting_trigger(trigger, log)
    elif trigger_type == "scout":                              # RA-684
        await _fire_scout_trigger(trigger, log)
    else:
        await create_session(
            repo_url=trigger["repo_url"],
            brief=trigger.get("brief", ""),
            model=trigger.get("model", "sonnet"),
        )
        log.info("Fired build trigger id=%s repo=%s", trigger["id"], trigger.get("repo_url"))


async def _watchdog_check(triggers: list[dict], log) -> None:
    """
    12-hour watchdog. If no scan/monitor trigger has fired in the last 12h,
    create an Urgent Linear ticket to alert the team.
    """
    from . import config
    scan_triggers = [t for t in triggers if t.get("type") in ("scan", "monitor")]
    if not scan_triggers:
        return
    most_recent_fire = max(
        (t.get("last_fired_at") or 0) for t in scan_triggers
    )
    silence_h = (time.time() - most_recent_fire) / 3600
    if silence_h < 12:
        return
    log.warning("Watchdog: no scan/monitor has fired in %.1fh — raising alert", silence_h)
    if not config.LINEAR_API_KEY:
        return
    try:
        import urllib.request
        import json as _json
        _LINEAR_ENDPOINT = "https://api.linear.app/graphql"
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) { success issue { identifier } }
        }
        """
        variables = {
            "input": {
                "teamId": "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673",
                "projectId": "f45212be-3259-4bfb-89b1-54c122c939a7",
                "title": f"[WATCHDOG] Pi-SEO scheduler silent for {silence_h:.0f}h — no scans fired",
                "description": (
                    f"The Pi-SEO cron scheduler has not fired any scan or monitor trigger "
                    f"in the last {silence_h:.1f} hours.\n\n"
                    f"Most recent fire timestamp: {most_recent_fire}\n\n"
                    "**Investigate:** Railway container restart, cron-triggers.json state, "
                    "scanner exceptions in server logs."
                ),
                "priority": 1,  # Urgent
                "stateId": None,  # use default (Todo)
            }
        }
        payload = _json.dumps({"query": mutation, "variables": variables}).encode()
        req = urllib.request.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": config.LINEAR_API_KEY},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = _json.loads(resp.read())
        identifier = (result.get("data", {}).get("issueCreate", {}).get("issue") or {}).get("identifier", "?")
        log.info("Watchdog: created Linear ticket %s", identifier)
    except Exception as exc:
        log.error("Watchdog: failed to create Linear ticket: %s", exc)


# RA-635 — module-level dedup state for docs-stale watchdog.
# Tracks the time we last created a docs-stale Linear ticket.
# Prevents spamming on every 30-minute watchdog check.
_docs_stale_last_raised: float = 0.0
_DOCS_STALE_COOLDOWN_H = 24.0  # only raise once per 24 hours


async def _watchdog_zte_reality_check(log) -> None:
    """
    RA-608 — ZTE Reality-Check watchdog.

    Every 30 minutes, fetches the Linear board state. If the pipeline is stalled
    (In Progress = 0 AND Urgent/High Todo > 0) and has been so for ≥ 12 hours,
    two things happen:
      1. A REALITY CHECK warning block is written into leverage-audit.md at the
         top of the Changelog, making the stall visible to any ZTE score reader.
      2. A Telegram alert fires (if not already sent in the last 2h).

    When the stall clears (someone picks up an issue), the warning block is removed
    and a Telegram "pipeline healthy" message fires.

    State is persisted in .harness/zte-reality-status.json to survive restarts.
    """
    from . import config
    from pathlib import Path
    import json as _json

    _HARNESS = Path(__file__).parent.parent.parent / ".harness"
    _STATUS_FILE = _HARNESS / "zte-reality-status.json"
    _AUDIT_FILE = _HARNESS / "leverage-audit.md"
    _STALL_THRESHOLD_H = 12.0
    _ALERT_COOLDOWN_H = 2.0

    # ── 1. Load persisted state ───────────────────────────────────────────────
    status: dict = {}
    if _STATUS_FILE.exists():
        try:
            status = _json.loads(_STATUS_FILE.read_text())
        except Exception:
            pass

    stall_since: float | None = status.get("stall_since")
    last_alerted: float = status.get("last_alerted", 0.0)
    was_stalled: bool = status.get("stalled", False)

    # ── 2. Query Linear board ────────────────────────────────────────────────
    if not config.LINEAR_API_KEY:
        return

    _LINEAR_ENDPOINT = "https://api.linear.app/graphql"
    _PROJECT_ID = "f45212be-3259-4bfb-89b1-54c122c939a7"

    def _gql(query: str, variables: dict) -> dict:
        import urllib.request as _ureq
        payload = _json.dumps({"query": query, "variables": variables}).encode()
        req = _ureq.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": config.LINEAR_API_KEY},
        )
        with _ureq.urlopen(req, timeout=10) as resp:
            return _json.loads(resp.read()).get("data", {})

    try:
        data = _gql(
            """
            query BoardState($projectId: String!) {
              project(id: $projectId) {
                issues(first: 100) {
                  nodes { priority state { type name } }
                }
              }
            }
            """,
            {"projectId": _PROJECT_ID},
        )
        issues = (data.get("project") or {}).get("issues", {}).get("nodes", [])
    except Exception as exc:
        log.warning("ZTE reality check: Linear fetch failed: %s", exc)
        return

    in_progress = [i for i in issues if i.get("state", {}).get("type") == "started"]
    urgent_todo = [
        i for i in issues
        if i.get("state", {}).get("type") in ("unstarted", "backlog")
        and i.get("priority", 4) <= 2  # 1=Urgent, 2=High
    ]

    now = time.time()
    is_stalled = len(in_progress) == 0 and len(urgent_todo) > 0

    # ── 3. Update stall_since tracking ────────────────────────────────────────
    if is_stalled:
        if stall_since is None:
            stall_since = now
            log.info(
                "ZTE reality check: stall detected — %d urgent/high todo, 0 in-progress",
                len(urgent_todo),
            )
    else:
        stall_since = None

    stall_h = (now - stall_since) / 3600 if stall_since else 0.0
    stall_qualifies = is_stalled and stall_h >= _STALL_THRESHOLD_H

    # ── 4. Update leverage-audit.md ───────────────────────────────────────────
    _STALL_MARKER_START = "<!-- ZTE-REALITY-CHECK-START -->"
    _STALL_MARKER_END   = "<!-- ZTE-REALITY-CHECK-END -->"

    if _AUDIT_FILE.exists():
        audit_text = _AUDIT_FILE.read_text(encoding="utf-8")

        # Remove any existing reality-check block
        import re as _re
        audit_text = _re.sub(
            rf"{_re.escape(_STALL_MARKER_START)}.*?{_re.escape(_STALL_MARKER_END)}\n?",
            "",
            audit_text,
            flags=_re.DOTALL,
        )

        if stall_qualifies:
            stall_block = (
                f"{_STALL_MARKER_START}\n"
                f"## ⚠️ REALITY CHECK — PIPELINE STALLED ({stall_h:.0f}h)\n\n"
                f"> **Auto-detected by ZTE watchdog — {time.strftime('%Y-%m-%dT%H:%M UTC', time.gmtime())}**\n>\n"
                f"> In Progress: **0**  |  Urgent/High Todo: **{len(urgent_todo)}**\n>\n"
                f"> While scores above reflect *capability*, the pipeline is currently **not processing work**.\n"
                f"> A stall of ≥12h is a ZTE failure condition — the system is autonomous in theory only.\n"
                f"> Resolve: assign an In Progress issue or check autonomy poller (`TAO_AUTONOMY_ENABLED`).\n"
                f"{_STALL_MARKER_END}\n\n"
            )
            # Insert after the first heading
            audit_text = _re.sub(
                r"(# Pi Dev Ops — Leverage Audit\n)",
                r"\1" + stall_block,
                audit_text,
                count=1,
            )
            log.warning(
                "ZTE reality check: STALL block written to leverage-audit.md (%dh stall)",
                stall_h,
            )
        else:
            log.info("ZTE reality check: pipeline healthy — no stall block")

        try:
            tmp = str(_AUDIT_FILE) + ".tmp"
            Path(tmp).write_text(audit_text, encoding="utf-8")
            Path(tmp).replace(_AUDIT_FILE)
        except Exception as exc:
            log.warning("ZTE reality check: could not write leverage-audit.md: %s", exc)

    # ── 5. Telegram alert ─────────────────────────────────────────────────────
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_ALERT_CHAT_ID
    if token and chat_id:
        alert_due = (now - last_alerted) >= _ALERT_COOLDOWN_H * 3600

        if stall_qualifies and alert_due:
            tickets_list = "\n".join(
                f"  • priority={i['priority']} state={i['state']['name']}"
                for i in urgent_todo[:5]
            )
            text = (
                f"⚠️ *ZTE REALITY CHECK — Pipeline Stalled {stall_h:.0f}h*\n\n"
                f"In Progress: *0*  |  Urgent/High Todo: *{len(urgent_todo)}*\n\n"
                f"Top waiting items:\n{tickets_list or '  (none details available)'}\n\n"
                f"_The system is autonomous in theory only while work sits unprocessed._\n"
                f"Check: `TAO_AUTONOMY_ENABLED` env var and Railway logs."
            )
            import urllib.request as _ureq2
            payload = _json.dumps(
                {"chat_id": chat_id, "text": text, "parse_mode": "Markdown",
                 "disable_web_page_preview": True}
            ).encode()
            req = _ureq2.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=payload, method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                with _ureq2.urlopen(req, timeout=10) as resp:
                    _json.loads(resp.read())
                log.warning("ZTE reality check: stall Telegram alert sent")
                last_alerted = now
            except Exception as exc:
                log.warning("ZTE reality check: Telegram alert failed: %s", exc)

        elif was_stalled and not is_stalled and alert_due:
            text = (
                "✅ *ZTE REALITY CHECK — Pipeline Healthy*\n\n"
                f"In Progress: *{len(in_progress)}*  |  Urgent/High Todo: *{len(urgent_todo)}*\n\n"
                "_Stall cleared. Autonomous pipeline is processing work again._"
            )
            import urllib.request as _ureq3
            payload = _json.dumps(
                {"chat_id": chat_id, "text": text, "parse_mode": "Markdown",
                 "disable_web_page_preview": True}
            ).encode()
            req = _ureq3.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=payload, method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                with _ureq3.urlopen(req, timeout=10) as resp:
                    _json.loads(resp.read())
                log.info("ZTE reality check: stall cleared — Telegram alert sent")
                last_alerted = now
            except Exception as exc:
                log.warning("ZTE reality check: Telegram clear alert failed: %s", exc)

    # ── 6. Persist state ──────────────────────────────────────────────────────
    new_status = {
        "stalled":      is_stalled,
        "stall_since":  stall_since,
        "in_progress":  len(in_progress),
        "urgent_todo":  len(urgent_todo),
        "stall_h":      round(stall_h, 2),
        "last_alerted": last_alerted,
        "checked_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        tmp = str(_STATUS_FILE) + ".tmp"
        Path(tmp).write_text(_json.dumps(new_status, indent=2), encoding="utf-8")
        Path(tmp).replace(_STATUS_FILE)
    except Exception as exc:
        log.warning("ZTE reality check: could not write status file: %s", exc)


async def _watchdog_escalations(log) -> None:
    """
    RA-633 — On-call escalation watchdog.

    Every 30 minutes, fetch critical Telegram alerts that are:
      - sent > 30 minutes ago
      - not yet acknowledged
      - not yet escalated

    For each one, send a second louder Telegram page tagged [ESCALATION] and
    mark the row as escalated so it doesn't fire again.
    """
    from . import config
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_ALERT_CHAT_ID:
        return

    try:
        from .supabase_log import fetch_unacknowledged_alerts, mark_alert_escalated
    except Exception as exc:
        log.warning("Escalation watchdog: supabase_log import failed: %s", exc)
        return

    try:
        unacked = fetch_unacknowledged_alerts(max_age_minutes=30)
    except Exception as exc:
        log.warning("Escalation watchdog: fetch_unacknowledged_alerts failed: %s", exc)
        return

    if not unacked:
        return

    log.warning("Escalation watchdog: %d unacknowledged alert(s) — escalating", len(unacked))

    import urllib.request as _ureq
    import json as _json

    for alert in unacked:
        alert_key  = alert.get("alert_key", "?")
        title      = alert.get("issue_title", "Unknown issue")
        project    = alert.get("project_id", "?")
        ticket     = alert.get("linear_ticket", "")
        sent_at    = alert.get("telegram_sent_at", "?")

        text = (
            f"🚨 *[ESCALATION]* Pi-CEO alert unacknowledged\n\n"
            f"*{title}*\n"
            f"Project: `{project}`\n"
            f"First alert: {sent_at}\n"
            f"Linear: {ticket}\n\n"
            f"_Reply /ack\\_alert {alert_key} to silence_"
        )
        payload = _json.dumps({
            "chat_id": config.TELEGRAM_ALERT_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode()
        req = _ureq.Request(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with _ureq.urlopen(req, timeout=10) as resp:
                result = _json.loads(resp.read())
            if result.get("ok"):
                log.info("Escalation sent for alert_key=%s", alert_key)
                mark_alert_escalated(alert_key)
            else:
                log.warning("Escalation Telegram returned ok=false for %s: %s", alert_key, result)
        except Exception as exc:
            log.warning("Escalation Telegram send failed for %s: %s", alert_key, exc)


async def _watchdog_docs_staleness(log) -> None:
    """
    RA-635 — 48h Anthropic docs staleness watchdog.

    Checks if the newest dated snapshot in .harness/anthropic-docs/ is >48h old
    (or missing entirely). Creates a Medium Linear ticket with label [DOCS-STALE]
    if stale. Deduplicates via module-level timestamp — at most one ticket per 24h.
    """
    global _docs_stale_last_raised
    from . import config
    from pathlib import Path

    _HARNESS = Path(__file__).parent.parent.parent / ".harness"
    _DOCS_ROOT = _HARNESS / "anthropic-docs"
    _STALE_THRESHOLD_H = 48.0

    # Cooldown: don't raise again within 24 hours
    if _docs_stale_last_raised and (time.time() - _docs_stale_last_raised) < _DOCS_STALE_COOLDOWN_H * 3600:
        return

    # Find the most recent dated snapshot directory (YYYY-MM-DD pattern)
    stale_h: float | None = None
    if not _DOCS_ROOT.exists():
        stale_h = float("inf")  # never fetched
    else:
        dated_dirs = sorted(
            [d for d in _DOCS_ROOT.iterdir() if d.is_dir() and d.name[:4].isdigit()],
            reverse=True,
        )
        if not dated_dirs:
            stale_h = float("inf")
        else:
            newest = dated_dirs[0]
            # Use directory mtime as proxy for freshness
            dir_mtime = newest.stat().st_mtime
            stale_h = (time.time() - dir_mtime) / 3600

    if stale_h is None or stale_h < _STALE_THRESHOLD_H:
        return

    age_desc = "never fetched" if stale_h == float("inf") else f"{stale_h:.0f}h old"
    log.warning("Docs-stale watchdog: .harness/anthropic-docs/ is %s (threshold: %.0fh)", age_desc, _STALE_THRESHOLD_H)

    if not config.LINEAR_API_KEY:
        _docs_stale_last_raised = time.time()
        return

    try:
        import urllib.request
        import json as _json
        _LINEAR_ENDPOINT = "https://api.linear.app/graphql"
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) { success issue { identifier } }
        }
        """
        variables = {
            "input": {
                "teamId": "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673",
                "projectId": "f45212be-3259-4bfb-89b1-54c122c939a7",
                "title": f"[WATCHDOG][DOCS-STALE] Anthropic docs snapshot is {age_desc} — intel refresh not running?",
                "description": (
                    f"The `.harness/anthropic-docs/` snapshot is **{age_desc}** "
                    f"(threshold: {_STALE_THRESHOLD_H:.0f}h).\n\n"
                    "This means the weekly `intel_refresh` cron trigger "
                    "(`intel-refresh-monday` in `.harness/cron-triggers.json`) "
                    "has not run recently.\n\n"
                    "**Investigate:**\n"
                    "1. Check Railway logs for `intel_refresh id=intel-refresh-monday` lines\n"
                    "2. Verify `intel-refresh-monday` trigger is enabled in `.harness/cron-triggers.json`\n"
                    "3. Check `anthropic_intel_refresh.py` for fetch errors (docs.claude.com reachable?)\n\n"
                    "**Related:** RA-635 (Risk Register R-08)"
                ),
                "priority": 3,  # Medium
                "stateId": None,  # default Todo
            }
        }
        payload = _json.dumps({"query": mutation, "variables": variables}).encode()
        req = urllib.request.Request(
            _LINEAR_ENDPOINT, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": config.LINEAR_API_KEY},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = _json.loads(resp.read())
        identifier = (result.get("data", {}).get("issueCreate", {}).get("issue") or {}).get("identifier", "?")
        log.info("Docs-stale watchdog: created Linear ticket %s", identifier)
        _docs_stale_last_raised = time.time()
    except Exception as exc:
        log.error("Docs-stale watchdog: failed to create Linear ticket: %s", exc)


async def cron_loop():
    """Background asyncio task. Checks triggers every 60s."""
    import logging
    import datetime
    _log = logging.getLogger("pi-ceo.cron")
    _log.info("Trigger loop started.")

    # --- Startup catch-up: fire overdue scan/monitor triggers immediately ---
    await asyncio.sleep(10)  # brief delay so server is fully ready
    try:
        triggers = _load()
        fired = False
        for trigger in triggers:
            if _should_catch_up(trigger):
                _log.info("Catch-up: trigger %s is overdue — firing now", trigger["id"])
                try:
                    await _fire_trigger(trigger, _log)
                    trigger["last_fired_at"] = time.time()
                    fired = True
                except Exception as exc:
                    _log.error("Catch-up: trigger %s failed: %s", trigger["id"], exc)
        if fired:
            _save(triggers)
    except Exception as exc:
        _log.error("Catch-up startup error: %s", exc)

    # --- Main loop ---
    _watchdog_interval = 0
    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.datetime.utcnow()
            triggers = _load()
            fired = False
            for trigger in triggers:
                if _matches(trigger, now.hour, now.minute, now.weekday(), now.day, now.month):
                    try:
                        await _fire_trigger(trigger, _log)
                        trigger["last_fired_at"] = time.time()
                        fired = True
                    except RuntimeError as exc:
                        _log.warning("Trigger skipped id=%s reason=%s", trigger["id"], exc)
            if fired:
                _save(triggers)

            # Watchdog checks every 30 minutes
            _watchdog_interval += 1
            if _watchdog_interval >= 30:
                _watchdog_interval = 0
                await _watchdog_check(triggers, _log)
                await _watchdog_docs_staleness(_log)      # RA-635
                await _watchdog_escalations(_log)          # RA-633
                await _watchdog_zte_reality_check(_log)    # RA-608

        except Exception as exc:
            _log.error("Loop error: %s", exc)
