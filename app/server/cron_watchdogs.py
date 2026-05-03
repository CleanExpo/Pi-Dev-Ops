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

# RA-1742 — Vercel deploy-failure watchdog. The 2026-04-27 outage left
# both restoreassist + restoreassist-sandbox stuck on Prisma P3009 for
# 6 days / 11 h respectively while every prod deploy errored. /health
# stayed green (it polls the DB, not the deploy state). This watchdog
# polls the Vercel API for the most-recent prod deployment per project
# in `.harness/projects.json` and alerts when the latest is `ERROR` and
# >2 h old. Cooldown: 6 h to avoid storming during a multi-day outage.
_vercel_deploy_failure_last_raised: float = 0.0
_VERCEL_DEPLOY_FAILURE_THRESHOLD_H = 2.0
_VERCEL_DEPLOY_FAILURE_COOLDOWN_H = 6.0

# RA-1908 — Linear API auth watchdog. On 2026-05-03 the local Hermes
# `LINEAR_API_KEY` returned "Not authenticated" twice (errors.log 03:38
# + 06:00). Cron jobs (board-meeting, intel refresh, scout queue) lost
# Linear capability silently. This watchdog probes Linear daily with a
# no-op `viewer { id email }` query and fires a Telegram alert when
# auth fails. Skips Linear ticket creation deliberately — Linear is
# the broken component. 24h cooldown so a slow rotation doesn't spam.
_linear_auth_last_raised: float = 0.0
_LINEAR_AUTH_COOLDOWN_H = 24.0


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


async def _watchdog_linear_auth(log) -> None:
    """
    RA-1908 — Linear API auth watchdog.

    Issues a no-op `viewer { id email }` GraphQL query against Linear.
    If the response carries an auth error (no_api_key, request_failed
    with 401, or "Not authenticated" body), fires a Telegram alert.
    Does NOT create a Linear ticket — Linear is the broken component.
    24h cooldown.
    """
    global _linear_auth_last_raised
    from . import config

    if _linear_auth_last_raised and (
        time.time() - _linear_auth_last_raised
    ) < _LINEAR_AUTH_COOLDOWN_H * 3600:
        return

    # Probe Linear via the existing helper. _gql() catches network errors
    # and returns a structured dict — never raises.
    try:
        from swarm.linear_tools import _gql  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.debug("Linear-auth watchdog: linear_tools import failed (%s)", exc)
        return

    res = _gql("query { viewer { id email } }")

    auth_failed = False
    reason = ""
    if "error" in res:
        err = (res.get("error") or "").lower()
        if err == "no_api_key":
            auth_failed = True
            reason = "no_api_key"
        elif err == "request_failed":
            # Only flag as auth failure when the exception mentions 401 /
            # authentication. Pure network errors (ConnectionReset, DNS,
            # timeout) trip request_failed too — treating those as
            # auth-failed would produce false alerts during network blips.
            exc_text = str(res.get("exception", ""))
            if (
                "401" in exc_text
                or "not authenticated" in exc_text.lower()
                or "unauthorized" in exc_text.lower()
            ):
                auth_failed = True
                reason = "http_401"
    elif "errors" in res:
        # Linear returns GraphQL-level errors as `errors: [...]`
        errs = res.get("errors") or []
        for e in errs:
            msg = (e.get("message") or "").lower()
            if "authent" in msg or "unauthor" in msg or "401" in msg:
                auth_failed = True
                reason = e.get("message", "")[:120]
                break
    elif res.get("data", {}).get("viewer") is None:
        # Empty data + no error = ambiguous; treat as healthy unless errors
        pass

    if not auth_failed:
        return

    log.warning(
        "Linear-auth watchdog: Linear MCP auth failed (reason=%s) — "
        "rotate LINEAR_API_KEY in ~/.hermes/.env + Railway env",
        reason,
    )

    # Telegram alert only — Linear is broken so we can't file a ticket there.
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_ALERT_CHAT_ID:
        import urllib.request as _ureq
        import json as _json
        payload = _json.dumps({
            "chat_id": config.TELEGRAM_ALERT_CHAT_ID,
            "text": (
                "🚨 *Linear API auth failed*\n\n"
                f"Reason: `{reason}`\n\n"
                "Action: regenerate `LINEAR_API_KEY` on linear.app, "
                "update `~/.hermes/.env` and Railway env, restart Hermes.\n\n"
                "Cron jobs depending on Linear (board-meeting, intel refresh, "
                "scout queue, autonomy poller) are degraded until rotated.\n\n"
                "_RA-1908_ — 24h cooldown active."
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
            log.info("Linear-auth watchdog: Telegram alert sent")
        except Exception as exc:  # noqa: BLE001
            log.warning("Linear-auth watchdog: Telegram send failed: %s", exc)

    _linear_auth_last_raised = time.time()


def _vercel_projects_to_monitor():
    """Return [{name, project_id, team_id}] for portfolio repos with
    Vercel deployments worth monitoring. Read from .harness/projects.json
    so the watchdog automatically picks up new repos as the portfolio grows.

    Pulled into a function so tests can monkeypatch this single seam.
    """
    from pathlib import Path
    import json as _json

    candidate = Path(__file__).parent.parent.parent / ".harness" / "projects.json"
    if not candidate.exists():
        return []
    try:
        registry = _json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for p in registry.get("projects", []):
        # Only repos that explicitly opt in via vercel_project_id get watched.
        # Avoids hitting Vercel API for repos that have no deploy presence
        # (e.g. internal docs / scripts repos).
        vp = p.get("vercel_project_id")
        if not vp:
            continue
        out.append({
            "name": p.get("id") or p.get("repo") or vp,
            "project_id": vp,
            "team_id": p.get("vercel_team_id"),
        })
    return out


async def _watchdog_vercel_deploy_failures(log) -> None:
    """
    RA-1742 — Vercel deploy-failure watchdog.

    Polls the Vercel API for the most-recent Production deployment per
    monitored project. When the latest is in `ERROR` state and was created
    > 2 h ago, fire a Telegram alert + Linear ticket. Cooldown 6 h.

    The 2026-04-27 RestoreAssist outage left both prod + sandbox stuck for
    days because Prisma's `migrate deploy` failed silently — the build's
    HTTP /health endpoint stayed green (DB was reachable, just schema
    drifted), so UptimeRobot kept passing while every deploy errored.
    This watchdog catches that shape: deploy=ERROR for >2h is the canary.

    Requires VERCEL_TOKEN in env. Soft-fails if missing.
    """
    global _vercel_deploy_failure_last_raised
    from . import config

    if _vercel_deploy_failure_last_raised and (
        time.time() - _vercel_deploy_failure_last_raised
    ) < _VERCEL_DEPLOY_FAILURE_COOLDOWN_H * 3600:
        return

    vercel_token = getattr(config, "VERCEL_TOKEN", "") or ""
    if not vercel_token:
        log.debug("Vercel watchdog: VERCEL_TOKEN not set — skipping")
        return

    projects = _vercel_projects_to_monitor()
    if not projects:
        log.debug("Vercel watchdog: no monitored projects in .harness/projects.json")
        return

    import urllib.request as _ureq
    import urllib.parse as _uparse
    import json as _json

    failures: list[dict] = []
    for project in projects:
        params: dict[str, str] = {
            "projectId": project["project_id"],
            "target": "production",
            "limit": "1",
        }
        if project.get("team_id"):
            params["teamId"] = project["team_id"]
        url = "https://api.vercel.com/v6/deployments?" + _uparse.urlencode(params)
        try:
            req = _ureq.Request(url, headers={"Authorization": f"Bearer {vercel_token}"})
            with _ureq.urlopen(req, timeout=10) as resp:
                body = _json.loads(resp.read())
        except Exception as exc:  # noqa: BLE001
            log.warning("Vercel watchdog: %s API fetch failed: %s", project["name"], exc)
            continue

        deployments = body.get("deployments") or []
        if not deployments:
            continue
        latest = deployments[0]
        # Vercel returns ms-epoch in `created`; state in `state` (READY|ERROR|...)
        state = (latest.get("state") or "").upper()
        if state != "ERROR":
            continue
        created_ms = latest.get("created") or 0
        age_h = (time.time() - created_ms / 1000.0) / 3600.0
        if age_h < _VERCEL_DEPLOY_FAILURE_THRESHOLD_H:
            continue
        failures.append({
            "name": project["name"],
            "deployment_id": latest.get("uid", "?"),
            "url": latest.get("url", "?"),
            "age_h": age_h,
            "commit_msg": (latest.get("meta") or {}).get("githubCommitMessage", "")[:120],
        })

    if not failures:
        return

    log.warning(
        "Vercel watchdog: %d project(s) have stale ERROR prod deploys",
        len(failures),
    )

    # Telegram first.
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_ALERT_CHAT_ID:
        lines = ["🚨 *Vercel prod deploys ERRORed*", ""]
        for f in failures:
            lines.append(
                f"• *{f['name']}* — {f['age_h']:.0f}h ago — "
                f"`{f['deployment_id'][:12]}` — {f['commit_msg']}"
            )
        lines.append("")
        lines.append("_RA-1742_")
        text = "\n".join(lines)
        payload = _json.dumps({
            "chat_id": config.TELEGRAM_ALERT_CHAT_ID,
            "text": text,
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
            log.info("Vercel watchdog: Telegram alert sent for %d project(s)", len(failures))
        except Exception as exc:  # noqa: BLE001
            log.warning("Vercel watchdog: Telegram send failed: %s", exc)

    # Linear ticket.
    if config.LINEAR_API_KEY:
        try:
            mutation = """
            mutation CreateIssue($input: IssueCreateInput!) {
                issueCreate(input: $input) { success issue { identifier } }
            }
            """
            failure_lines = "\n".join(
                f"- **{f['name']}** — {f['age_h']:.1f}h old — "
                f"deployment `{f['deployment_id']}` — {f['commit_msg']}"
                for f in failures
            )
            variables = {
                "input": {
                    "teamId": "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673",
                    "projectId": "f45212be-3259-4bfb-89b1-54c122c939a7",
                    "title": (
                        f"[WATCHDOG] {len(failures)} Vercel prod deploy(s) ERROR > "
                        f"{_VERCEL_DEPLOY_FAILURE_THRESHOLD_H:.0f}h"
                    ),
                    "description": (
                        f"The most-recent Production deployment(s) for the following "
                        f"project(s) are in `ERROR` state and older than "
                        f"{_VERCEL_DEPLOY_FAILURE_THRESHOLD_H:.0f}h:\n\n"
                        f"{failure_lines}\n\n"
                        "**Common causes** (per RA-1742 RCA):\n"
                        "1. Prisma migration P3009 — see `feedback_prisma_migration_recovery.md`\n"
                        "2. Build-time env var missing\n"
                        "3. TypeScript compile error introduced in a merged PR\n\n"
                        "**Action:** open Vercel deployments view, read the build log "
                        "tail, fix forward.\n\n"
                        f"Cooldown: this watchdog re-raises at most every "
                        f"{_VERCEL_DEPLOY_FAILURE_COOLDOWN_H:.0f}h."
                    ),
                    "priority": 1,  # Urgent — a stale prod deploy is real outage risk
                    "stateId": None,
                }
            }
            payload = _json.dumps({"query": mutation, "variables": variables}).encode()
            req = _ureq.Request(
                "https://api.linear.app/graphql", data=payload, method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": config.LINEAR_API_KEY,
                },
            )
            with _ureq.urlopen(req, timeout=10) as resp:
                result = _json.loads(resp.read())
            identifier = (
                (result.get("data", {}).get("issueCreate", {}).get("issue") or {})
                .get("identifier", "?")
            )
            log.info("Vercel watchdog: created Linear ticket %s", identifier)
        except Exception as exc:  # noqa: BLE001
            log.error("Vercel watchdog: Linear ticket create failed: %s", exc)

    _vercel_deploy_failure_last_raised = time.time()
