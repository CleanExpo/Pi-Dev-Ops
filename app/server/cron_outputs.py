"""cron_outputs.py — re-run a scheduled job on boot when the file it produces is gone.

`last_fired_at` is durable (Supabase `cron_state`, RA-1439) but a job's OUTPUT is not:
`.harness/` sits on the container's disk, which every Railway deploy replaces. After a
deploy the scheduler therefore believes a daily job already ran while its result has
vanished. Seen live on 2026-09-29: `zte-v2-score-daily` completed at 03:00 UTC, the #826
deploy at 03:12 wiped `.harness/zte-v2-score.json`, and Mission Control's ZTE badge got
404 "no score computed yet" on every request until the next day's run.

A trigger may declare `"output": "<repo-relative path>"`. On boot it fires if that file
is missing, whatever `last_fired_at` says.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from .config_loader import REPO_ROOT
from .cron_triggers import _should_catch_up

log = logging.getLogger("pi-ceo.cron")


def output_missing(trigger: dict, root: Path = REPO_ROOT) -> bool:
    """True when an enabled trigger declares an output file that does not exist."""
    out = trigger.get("output")
    if not out or not trigger.get("enabled", True):
        return False
    rel = os.path.normpath(str(out))
    if os.path.isabs(rel) or rel == ".." or rel.startswith(".." + os.sep):
        log.warning("trigger %s: output %r is outside the repo — ignored", trigger.get("id"), out)
        return False
    if (root / rel).exists():
        return False
    log.info("trigger %s: output %s is missing — re-running on boot", trigger.get("id"), rel)
    return True


def should_fire_on_boot(trigger: dict) -> bool:
    """Startup catch-up: overdue by schedule (RA-2016), or its declared output is gone."""
    return _should_catch_up(trigger) or output_missing(trigger)
