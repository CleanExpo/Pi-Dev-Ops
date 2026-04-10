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
import asyncio, json, os, time, uuid
from . import config

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
    # Debounce: don't fire twice in the same minute
    last = trigger.get("last_fired_at")
    if last and (time.time() - last) < 90:
        return False
    return True


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


async def cron_loop():
    """Background asyncio task. Checks triggers every 60s."""
    import logging
    _log = logging.getLogger("pi-ceo.cron")
    # Deferred import to avoid circular dependency
    from .sessions import create_session
    _log.info("Trigger loop started.")
    while True:
        await asyncio.sleep(60)
        try:
            import datetime
            now = datetime.datetime.utcnow()
            triggers = _load()
            fired = False
            for trigger in triggers:
                if _matches(trigger, now.hour, now.minute):
                    trigger_type = trigger.get("type", "build")
                    try:
                        if trigger_type == "scan":
                            await _fire_scan_trigger(trigger, _log)
                        elif trigger_type == "monitor":
                            await _fire_monitor_trigger(trigger, _log)
                        else:
                            await create_session(
                                repo_url=trigger["repo_url"],
                                brief=trigger.get("brief", ""),
                                model=trigger.get("model", "sonnet"),
                            )
                            _log.info("Fired build trigger id=%s repo=%s", trigger["id"], trigger.get("repo_url"))
                        trigger["last_fired_at"] = time.time()
                        fired = True
                    except RuntimeError as e:
                        _log.warning("Trigger skipped id=%s reason=%s", trigger["id"], e)
            if fired:
                _save(triggers)
        except Exception as e:
            _log.error("Loop error: %s", e)
