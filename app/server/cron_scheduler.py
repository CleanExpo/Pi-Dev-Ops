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
    _watchdog_board_meeting_silence,
    _watchdog_check,
    _watchdog_docs_staleness,
    _watchdog_escalations,
    _watchdog_notebooklm_health,
    _watchdog_vercel_deploy_failures,
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
    _pulse_interval = 0
    _last_digest_day = None
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
                        # Expected skip path (e.g., gated triggers raising RuntimeError)
                        _log.warning("Trigger skipped id=%s reason=%s", trigger["id"], exc)
                    except Exception as exc:
                        # RA-1484/RA-1493/RA-1497: previously only RuntimeError was caught,
                        # so any other exception (network, subprocess, monitor cycle, etc.)
                        # propagated to the outer handler — aborting the rest of this
                        # minute's triggers and, crucially, never updating last_fired_at.
                        # The watchdog then alerted forever. Now we isolate per-trigger
                        # failures and keep iterating. last_fired_at stays unchanged on
                        # failure (intentional) so operators can see the stale timestamp,
                        # but we still advance the loop so one broken trigger cannot
                        # starve the others.
                        _log.error(
                            "Trigger failed id=%s type=%s: %s",
                            trigger.get("id"), trigger.get("type"), exc,
                            exc_info=True,
                        )
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
                await _watchdog_board_meeting_silence(_log)    # RA-1472
                await _watchdog_vercel_deploy_failures(_log)   # RA-1742

            # Linear pulse every 15 min — mandatory single-pane-of-glass for
            # the founder, per explicit requirement (2026-04-19).
            _pulse_interval += 1
            if _pulse_interval >= 15:
                _pulse_interval = 0
                try:
                    from .linear_pulse import run_pulse

                    await asyncio.get_event_loop().run_in_executor(None, run_pulse)
                except Exception as exc:
                    _log.error("Linear pulse failed: %s", exc)

            # Daily digest push at 08:00 and 20:00 UTC (override with
            # PI_CEO_DIGEST_HOURS="6,14,22" if needed).
            import os as _os

            digest_hours_env = _os.environ.get("PI_CEO_DIGEST_HOURS", "8,20")
            digest_hours = {
                int(h) for h in digest_hours_env.split(",") if h.strip().isdigit()
            }
            today_key = (now.day, now.hour)
            if (
                now.hour in digest_hours
                and now.minute < 5
                and _last_digest_day != today_key
            ):
                _last_digest_day = today_key
                try:
                    from .digest import push_digest_to_telegram

                    await asyncio.get_event_loop().run_in_executor(
                        None, push_digest_to_telegram
                    )
                    _log.info("Daily digest pushed at %s UTC", now.isoformat())
                except Exception as exc:
                    _log.error("Daily digest push failed: %s", exc)

        except Exception as exc:
            _log.error("Loop error: %s", exc)
