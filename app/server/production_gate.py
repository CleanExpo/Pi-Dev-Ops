"""One owner for: may this deploy cause production side effects?

Railway PR preview deploys copy production variables, so they share production
Supabase, Linear and the Telegram bot. Any startup task that writes to one of those
(the cron loop, the Linear autonomy poller, the Telegram intake loop, the swarm
orchestrator, the Nexus scheduler, Supabase session recovery) must start through
`run_if_production_allowed`, never through its own copy of the environment check.

Allowed: local dev, CI and tests (no Railway variables) and the Railway production
environment. Not allowed: every other Railway environment, unless
TAO_CRON_ALLOW_NON_PRODUCTION=1 (the override name predates this module and stays).

The rule itself is cron_scheduler.cron_scheduler_allowed, which already gated cron_loop.
This module reuses it rather than copying it, so there is still exactly one owner of the
environment check. (cron_scheduler.py is a frozen path; the rule stays where it is.)
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from . import cron_scheduler

OVERRIDE_ENV = "TAO_CRON_ALLOW_NON_PRODUCTION"


def railway_environment_name() -> str:
    """Railway environment name, or "" when this process is not on Railway."""
    return cron_scheduler.railway_cron_environment()


def production_side_effects_allowed() -> bool:
    """True for local dev and the production Railway environment, or with the override."""
    return cron_scheduler.cron_scheduler_allowed()


def run_if_production_allowed(name: str, start: Callable[[], object], log: logging.Logger) -> bool:
    """Call `start` only where production side effects are allowed; log one warning otherwise."""
    if not production_side_effects_allowed():
        log.warning(
            "%s not started — Railway environment %r is not production. Preview deploys "
            "share production Supabase, Linear and Telegram. Set %s=1 to override.",
            name,
            railway_environment_name(),
            OVERRIDE_ENV,
        )
        return False
    start()
    return True
