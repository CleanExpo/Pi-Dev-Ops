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
    "hour": int | null,       # UTC hour (0-23), null = any hour
    "minute": int,            # UTC minute (0-59)
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


def _matches(trigger: dict, now_hour: int, now_minute: int) -> bool:
    if not trigger.get("enabled", True):
        return False
    if trigger.get("minute") != now_minute:
        return False
    h = trigger.get("hour")
    if h is not None and h != now_hour:
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
    if trigger.get("type", "build") not in ("scan", "monitor"):
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
    from .agents.pi_seo_monitor import run_monitor_cycle
    project_id = trigger.get("project_id") or None
    use_agent = trigger.get("use_agent", False)
    log.info("Firing monitor trigger id=%s project=%s use_agent=%s", trigger["id"], project_id, use_agent)
    digest = run_monitor_cycle(project_id=project_id, use_agent=use_agent, dry_run=False)
    log.info(
        "Monitor trigger id=%s complete: health=%d alerts=%d",
        trigger["id"], digest.portfolio_health, len(digest.alerts),
    )


async def _fire_trigger(trigger: dict, log) -> None:
    """Dispatch a single trigger by type. Raises on failure."""
    from .sessions import create_session
    trigger_type = trigger.get("type", "build")
    if trigger_type == "scan":
        await _fire_scan_trigger(trigger, log)
    elif trigger_type == "monitor":
        await _fire_monitor_trigger(trigger, log)
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
                if _matches(trigger, now.hour, now.minute):
                    try:
                        await _fire_trigger(trigger, _log)
                        trigger["last_fired_at"] = time.time()
                        fired = True
                    except RuntimeError as exc:
                        _log.warning("Trigger skipped id=%s reason=%s", trigger["id"], exc)
            if fired:
                _save(triggers)

            # Watchdog check every 30 minutes
            _watchdog_interval += 1
            if _watchdog_interval >= 30:
                _watchdog_interval = 0
                await _watchdog_check(triggers, _log)

        except Exception as exc:
            _log.error("Loop error: %s", exc)
