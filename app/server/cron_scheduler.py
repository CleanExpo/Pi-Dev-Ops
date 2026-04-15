"""
cron_scheduler.py — Schedule matching predicates and main async cron loop (GROUP F).

Contains:
    _matches()          — schedule matching predicate
    _should_catch_up()  — startup catch-up eligibility
    cron_loop()         — asyncio background task; checks triggers every 60s
"""
import asyncio
import datetime
import logging
import time

from .cron_store import _load_triggers, _save_triggers
from .cron_triggers import _fire_trigger, _matches, _should_catch_up
from .cron_watchdogs import (
    _watchdog_check,
    _watchdog_docs_staleness,
    _watchdog_escalations,
    _watchdog_notebooklm_health,
)
from .cron_watchdog_zte import _watchdog_zte_reality_check


async def cron_loop() -> None:
    """Background asyncio task. Checks triggers every 60s."""
    _log = logging.getLogger("pi-ceo.cron")
    _log.info("Trigger loop started.")

    # --- Startup catch-up: fire overdue scan/monitor triggers immediately ---
    await asyncio.sleep(10)  # brief delay so server is fully ready
    try:
        triggers = _load_triggers()
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
            _save_triggers(triggers)
    except Exception as exc:
        _log.error("Catch-up startup error: %s", exc)

    # --- Main loop ---
    _watchdog_interval = 0
    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.datetime.utcnow()
            triggers = _load_triggers()
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
                _save_triggers(triggers)

            # Watchdog checks every 30 minutes
            _watchdog_interval += 1
            if _watchdog_interval >= 30:
                _watchdog_interval = 0
                await _watchdog_check(triggers, _log)
                await _watchdog_docs_staleness(_log)          # RA-635
                await _watchdog_escalations(_log)              # RA-633
                await _watchdog_zte_reality_check(_log)        # RA-608
                await _watchdog_notebooklm_health(_log)        # RA-820

        except Exception as exc:
            _log.error("Loop error: %s", exc)
