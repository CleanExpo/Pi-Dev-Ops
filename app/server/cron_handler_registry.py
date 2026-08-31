"""cron_handler_registry.py — trigger type → fire-function lookup.

Extracted from ``cron_triggers.py``, which is over the 300-line ceiling and so
may not grow (CLAUDE.md § Conventions). The dispatcher there was an elif chain
that every new trigger type lengthened; as a table, adding a type is one row and
the file it lives in stays flat.

Every handler is resolved at FIRE time, never bound at import time. That keeps
optional handlers lazy — a broken `discovery` module must not stop scans from
firing — and it is what lets tests patch either the source module
(``pdc._fire_plan_discovery_trigger``) or the name as imported into
``cron_triggers`` (``cron_triggers._fire_script_trigger``) and have the patch
take effect.

    python3 -c "from app.server.cron_handler_registry import HANDLERS; print(len(HANDLERS))"
"""
from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Optional

# trigger type → (module holding the handler, handler attribute).
# ".cron_triggers" is where the in-module fire functions live; the rest are
# imported only when a trigger of that type actually fires.
HANDLERS: dict[str, tuple[str, str]] = {
    "scan": (".cron_triggers", "_fire_scan_trigger"),
    "monitor": (".cron_triggers", "_fire_monitor_trigger"),
    "intel_refresh": (".cron_triggers", "_fire_intel_refresh_trigger"),      # RA-587
    "analyse_lessons": (".cron_triggers", "_fire_script_trigger"),
    "fallback_dryrun": (".cron_triggers", "_fire_script_trigger"),
    "zte_v2_score": (".cron_triggers", "_fire_script_trigger"),
    "script": (".cron_triggers", "_fire_script_trigger"),
    "capability_loop": (".cron_triggers", "_fire_script_trigger"),
    "board_meeting": (".cron_triggers", "_fire_board_meeting_trigger"),
    "scout": (".cron_triggers", "_fire_scout_trigger"),                      # RA-684
    "feedback_loop": (".cron_triggers", "_fire_feedback_trigger"),           # RA-689
    "meta_curator": (".cron_triggers", "_fire_meta_curator_trigger"),        # RA-1839
    "portfolio_pulse": (".cron_triggers", "_fire_portfolio_pulse_trigger"),  # RA-1888
    "marketing_bridge": (".cron_triggers", "_fire_marketing_bridge_trigger"),  # UNI-2236
    "discovery": (".discovery", "_fire_discovery_trigger"),                  # RA-2026
    "discovery_archive": (".discovery_archive", "_fire_discovery_archive_trigger"),  # RA-2027
    "burndown": (".burndown", "_fire_burndown_trigger"),                     # RA-6670
    "plan_discovery": (".plan_discovery_cron", "_fire_plan_discovery_trigger"),
    "mesh_dispatch": (".cron_fire_mesh", "_fire_mesh_dispatch_trigger"),     # Nexus Mesh P2
}


def resolve_handler(trigger_type: str) -> Optional[Callable[..., Any]]:
    """Return the async fire function for a trigger type, or None if it has none.

    None means "this type has no handler entry" — the caller decides whether
    that is the `build` path or an error. It must never be read as "handler
    missing, skip quietly": an unknown type has to raise, or a typo'd trigger
    sits silently un-fired the way `plan-discovery-daily-0300` once did.
    """
    entry = HANDLERS.get(trigger_type)
    if entry is None:
        return None
    module_path, attr = entry
    return getattr(import_module(module_path, __package__), attr)
