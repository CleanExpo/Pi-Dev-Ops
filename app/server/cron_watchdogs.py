"""
cron_watchdogs.py — Watchdog checks for the cron scheduler (GROUP F).

Contains:
    _watchdog_check()           — 12h scan/monitor silence alert
    _watchdog_escalations()     — on-call escalation watchdog (RA-633)
    _watchdog_docs_staleness()  — Anthropic docs 48h staleness check (RA-635)

The ZTE pipeline-stall watchdog (RA-608) lives in cron_watchdog_zte.py.
"""
import time

# RA-635 — module-level dedup state for docs-stale watchdog.
# Prevents spamming on every 30-minute watchdog check.
_docs_stale_last_raised: float = 0.0
_DOCS_STALE_COOLDOWN_H = 24.0  # only raise once per 24 hours


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
