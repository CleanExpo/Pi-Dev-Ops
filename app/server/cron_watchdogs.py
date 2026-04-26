"""
cron_watchdogs.py — Watchdog checks for the cron scheduler (GROUP F).

Contains:
    _watchdog_check()               — 12h scan/monitor silence alert
    _watchdog_escalations()         — on-call escalation watchdog (RA-633)
    _watchdog_docs_staleness()      — Anthropic docs 48h staleness check (RA-635)
    _watchdog_notebooklm_health()   — NotebookLM KB health probe + Telegram alert (RA-820)

The ZTE pipeline-stall watchdog (RA-608) lives in cron_watchdog_zte.py.
"""
import time

# RA-635 — module-level dedup state for docs-stale watchdog.
# Prevents spamming on every 30-minute watchdog check.
_docs_stale_last_raised: float = 0.0
_DOCS_STALE_COOLDOWN_H = 24.0  # only raise once per 24 hours

# RA-820 — module-level dedup state for NotebookLM health watchdog.
_notebooklm_health_last_ran: float = 0.0
_NOTEBOOKLM_HEALTH_INTERVAL_H = 6.0  # probe each KB at most once per 6 hours

# RA-1484/RA-1493/RA-1497 — dedup for the Pi-SEO scheduler-silent watchdog.
# Without this, each 30-min watchdog tick creates a new Linear ticket with the
# same root cause (3 duplicate tickets in one incident prompted this guard).
_scheduler_silent_last_raised: float = 0.0
_SCHEDULER_SILENT_COOLDOWN_H = 6.0

# RA-1472 — Board meeting silence watchdog. The pi-dev-ops-board-meeting
# Cowork task went silent 2026-04-14 → 2026-04-20 (24 missed cycles, 6 days)
# without alerting. The fix: every 30 min, check the newest file in
# .harness/board-meetings/. If older than 12 h, fire a Telegram alert +
# Linear ticket. Cooldown prevents storming if the gap persists.
_board_meeting_silent_last_raised: float = 0.0
_BOARD_MEETING_SILENT_THRESHOLD_H = 12.0
_BOARD_MEETING_SILENT_COOLDOWN_H = 12.0


def _board_meetings_dir():
    """Return the on-disk directory holding board-meeting markdown files.

    Pulled out so tests can monkeypatch this single function without having
    to reach into the watchdog body's `Path(__file__).parent.parent.parent...`
    chain.
    """
    from pathlib import Path
    return Path(__file__).parent.parent.parent / ".harness" / "board-meetings"


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
    # RA-1484 — dedup: don't spam duplicate tickets on every 30-min tick.
    global _scheduler_silent_last_raised
    hours_since_last = (time.time() - _scheduler_silent_last_raised) / 3600
    if _scheduler_silent_last_raised and hours_since_last < _SCHEDULER_SILENT_COOLDOWN_H:
        log.info(
            "Watchdog: Pi-SEO silence ticket suppressed (cooldown %.1fh < %.1fh)",
            hours_since_last, _SCHEDULER_SILENT_COOLDOWN_H,
        )
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
        _scheduler_silent_last_raised = time.time()
    except Exception as exc:
        log.error("Watchdog: failed to create Linear ticket: %s", exc)


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
            dir_mtime = newest.stat().st_mtime
            stale_h = (time.time() - dir_mtime) / 3600

    if stale_h is None or stale_h < _STALE_THRESHOLD_H:
        return

    age_desc = "never fetched" if stale_h == float("inf") else f"{stale_h:.0f}h old"
    log.warning(
        "Docs-stale watchdog: .harness/anthropic-docs/ is %s (threshold: %.0fh)",
        age_desc, _STALE_THRESHOLD_H,
    )

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


async def _watchdog_notebooklm_health(log) -> None:
    """
    RA-820 — NotebookLM knowledge base health probe.

    Every 6 hours, runs one standard query against each active notebook in
    .harness/notebooklm-registry.json. Logs results to Supabase notebooklm_health.
    Sends a Telegram alert if any notebook fails or times out.
    """
    global _notebooklm_health_last_ran

    if _notebooklm_health_last_ran and (
        time.time() - _notebooklm_health_last_ran
    ) < _NOTEBOOKLM_HEALTH_INTERVAL_H * 3600:
        return

    import asyncio
    import hashlib
    import json as _json
    from pathlib import Path
    from . import config

    _REGISTRY = Path(__file__).parent.parent.parent / ".harness" / "notebooklm-registry.json"
    _HEALTH_QUERY = "What are the top 3 risks for this entity right now?"
    _QUERY_HASH = hashlib.md5(_HEALTH_QUERY.encode()).hexdigest()[:12]
    _TIMEOUT_S = 60

    if not _REGISTRY.exists():
        log.warning("NotebookLM health: registry not found at %s", _REGISTRY)
        return

    try:
        registry = _json.loads(_REGISTRY.read_text())
    except Exception as exc:
        log.warning("NotebookLM health: failed to load registry: %s", exc)
        return

    active = [nb for nb in registry.get("notebooks", []) if nb.get("status") == "active"]
    if not active:
        log.debug("NotebookLM health: no active notebooks in registry")
        _notebooklm_health_last_ran = time.time()
        return

    log.info("NotebookLM health: probing %d active notebook(s)", len(active))

    try:
        from .supabase_log import log_notebooklm_health
    except Exception as exc:
        log.warning("NotebookLM health: supabase_log import failed: %s", exc)
        return

    failures: list[str] = []

    for nb in active:
        nb_id = nb.get("id", "")
        nb_name = nb.get("entity", nb.get("name", nb_id))
        if not nb_id or nb_id == "TBD":
            continue

        t_start = time.time()
        status = "failed"
        error_msg: str | None = None

        try:
            proc = await asyncio.create_subprocess_exec(
                "nlm", "notebook", "query", nb_id, _HEALTH_QUERY,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT_S)
                elapsed_ms = int((time.time() - t_start) * 1000)
                if proc.returncode == 0:
                    status = "ok"
                    log.info("NotebookLM health: %s OK (%dms)", nb_name, elapsed_ms)
                else:
                    error_msg = stderr.decode(errors="replace").strip()[:500]
                    log.warning("NotebookLM health: %s FAILED rc=%d: %s", nb_name, proc.returncode, error_msg)
                    failures.append(nb_name)
            except asyncio.TimeoutError:
                proc.kill()
                elapsed_ms = _TIMEOUT_S * 1000
                status = "timeout"
                error_msg = f"nlm query timed out after {_TIMEOUT_S}s"
                log.warning("NotebookLM health: %s TIMEOUT after %ds", nb_name, _TIMEOUT_S)
                failures.append(nb_name)
        except Exception as exc:
            elapsed_ms = int((time.time() - t_start) * 1000)
            error_msg = str(exc)[:500]
            log.warning("NotebookLM health: %s subprocess error: %s", nb_name, exc)
            failures.append(nb_name)

        log_notebooklm_health(
            notebook_id=nb_id,
            notebook_name=nb_name,
            query_hash=_QUERY_HASH,
            status=status,
            error_message=error_msg,
            response_ms=elapsed_ms,
        )

    _notebooklm_health_last_ran = time.time()

    if not failures or not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_ALERT_CHAT_ID:
        return

    import urllib.request as _ureq
    names = ", ".join(failures)
    text = (
        f"⚠️ *[NotebookLM Health]* KB probe failed\n\n"
        f"Notebooks unreachable: `{names}`\n"
        f"Query: _{_HEALTH_QUERY}_\n\n"
        f"Check `nlm login` session and `.harness/notebooklm-registry.json`.\n"
        f"_RA-820_"
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
        with _ureq.urlopen(req, timeout=10):
            pass
        log.info("NotebookLM health: Telegram alert sent for %d failure(s)", len(failures))
    except Exception as exc:
        log.warning("NotebookLM health: Telegram send failed: %s", exc)


async def _watchdog_board_meeting_silence(log) -> None:
    """
    RA-1472 — Board-meeting silence watchdog.

    Cycles 28–51 (2026-04-14 → 2026-04-20, ~6 days, 24 missed 6-hour windows)
    went silent without alerting because the pi-dev-ops-board-meeting Cowork
    task lost its workspace mount and the failure was never surfaced.

    This watchdog runs alongside the others on the 30-minute tick. It checks
    the most recent board-meeting markdown file:
      - .harness/board-meetings/*.md  (current location)
    If the newest is older than 12 h (or none exist at all), it raises a
    Telegram alert + Linear ticket. Cooldown matches the threshold so we
    don't storm during a multi-day outage.
    """
    global _board_meeting_silent_last_raised
    from . import config

    if _board_meeting_silent_last_raised and (
        time.time() - _board_meeting_silent_last_raised
    ) < _BOARD_MEETING_SILENT_COOLDOWN_H * 3600:
        return

    meetings_dir = _board_meetings_dir()
    silence_h: float | None = None
    if not meetings_dir.exists():
        silence_h = float("inf")
    else:
        md_files = [p for p in meetings_dir.iterdir() if p.is_file() and p.suffix == ".md"]
        if not md_files:
            silence_h = float("inf")
        else:
            newest = max(md_files, key=lambda p: p.stat().st_mtime)
            silence_h = (time.time() - newest.stat().st_mtime) / 3600

    if silence_h is None or silence_h < _BOARD_MEETING_SILENT_THRESHOLD_H:
        return

    age_desc = "never written" if silence_h == float("inf") else f"{silence_h:.0f}h old"
    log.warning(
        "Board-meeting watchdog: newest .harness/board-meetings/*.md is %s "
        "(threshold %.0fh) — pi-dev-ops-board-meeting Cowork task may be silent",
        age_desc, _BOARD_MEETING_SILENT_THRESHOLD_H,
    )

    # Telegram first — fastest signal to the operator's phone.
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_ALERT_CHAT_ID:
        import urllib.request as _ureq
        import json as _json
        payload = _json.dumps({
            "chat_id": config.TELEGRAM_ALERT_CHAT_ID,
            "text": (
                "🚨 *Board-meeting automation silent*\n\n"
                f"Newest `.harness/board-meetings/*.md` is *{age_desc}* "
                f"(threshold: {_BOARD_MEETING_SILENT_THRESHOLD_H:.0f}h).\n\n"
                "Likely cause: pi-dev-ops-board-meeting Cowork task lost its "
                "workspace mount or was disabled.\n\n"
                "_RA-1472_"
            ),
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode()
        try:
            req = _ureq.Request(
                f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
                data=payload, method="POST",
                headers={"Content-Type": "application/json"},
            )
            with _ureq.urlopen(req, timeout=10):
                pass
            log.info("Board-meeting watchdog: Telegram alert sent")
        except Exception as exc:
            log.warning("Board-meeting watchdog: Telegram send failed: %s", exc)

    # Linear ticket — durable record + dedup via the cooldown.
    if config.LINEAR_API_KEY:
        try:
            import urllib.request as _ureq
            import json as _json
            mutation = """
            mutation CreateIssue($input: IssueCreateInput!) {
                issueCreate(input: $input) { success issue { identifier } }
            }
            """
            variables = {
                "input": {
                    "teamId": "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673",
                    "projectId": "f45212be-3259-4bfb-89b1-54c122c939a7",
                    "title": (
                        f"[WATCHDOG] Board-meeting silence: {age_desc} — "
                        "pi-dev-ops-board-meeting task not running?"
                    ),
                    "description": (
                        f"`.harness/board-meetings/` newest file is **{age_desc}** "
                        f"(threshold: {_BOARD_MEETING_SILENT_THRESHOLD_H:.0f}h).\n\n"
                        "**Likely causes** (per RA-1472 RCA):\n"
                        "1. Cowork scheduled task `pi-dev-ops-board-meeting` paused "
                        "or disabled.\n"
                        "2. Cowork session lost workspace mount; static path in task "
                        "prompt no longer matches the live `mnt/Pi Dev Ops/` folder.\n"
                        "3. Task ran in memory but couldn't persist the markdown "
                        "(workspace path mismatch).\n\n"
                        "**Action:** check Cowork scheduled tasks dashboard. Cooldown "
                        f"prevents re-raising for {_BOARD_MEETING_SILENT_COOLDOWN_H:.0f}h."
                    ),
                    "priority": 2,  # High
                    "stateId": None,
                }
            }
            payload = _json.dumps({"query": mutation, "variables": variables}).encode()
            req = _ureq.Request(
                "https://api.linear.app/graphql", data=payload, method="POST",
                headers={"Content-Type": "application/json", "Authorization": config.LINEAR_API_KEY},
            )
            with _ureq.urlopen(req, timeout=10) as resp:
                result = _json.loads(resp.read())
            identifier = (result.get("data", {}).get("issueCreate", {}).get("issue") or {}).get("identifier", "?")
            log.info("Board-meeting watchdog: created Linear ticket %s", identifier)
        except Exception as exc:
            log.error("Board-meeting watchdog: Linear ticket create failed: %s", exc)

    _board_meeting_silent_last_raised = time.time()
