"""How component health results become one verdict.

Split out of health_full.py for H01-H04. Two callers - `/api/health/full` and
Mission Control's observability snapshot - each carried their own copy of this
policy, and the copies had already drifted: one counted a component degraded only
when it was `ok`, which stops being true the moment an unobserved component
honestly reports `ok: False`. One copy, one place.

The policy itself, which is the whole point of the H01-H04 fix:

    observed and not ok   ->  RED       503, a real alarm
    not observed          ->  DEGRADED  200, visible, never counted green
    observed and ok       ->  GREEN

A component that was never looked at is neither healthy nor broken. Reporting it
as healthy is the defect this module exists to prevent; reporting it as broken
would 503 the public endpoint every time Hermes is absent from the Railway host,
which is the legitimate reason the lie was introduced in the first place.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any


log = logging.getLogger("pi-ceo.health_aggregate")

_CHECK_TIMEOUT_S = 2.0


def is_observed(payload: dict[str, Any]) -> bool:
    """Did this check actually look at the thing it reports on?

    Railway and local development hosts may not run every companion process, so
    absence must not always mean 503. It must still be visible as degraded.
    """
    return payload.get("observed") is not False and payload.get("status") != "not_observed"


# health_full.py and mission_control.py both imported the private name.
_is_observed = is_observed


async def run_with_timeout(name: str, coro_fn) -> tuple[str, dict[str, Any]]:
    try:
        result = await asyncio.wait_for(coro_fn(), timeout=_CHECK_TIMEOUT_S)
        if not isinstance(result, dict):
            return name, {"ok": False, "error": "non_dict_result"}
        if "ok" not in result:
            result["ok"] = False
        return name, result
    except asyncio.TimeoutError:
        return name, {"ok": False, "error": "timeout"}
    except Exception as exc:
        return name, {"ok": False, "error": str(exc)[:120]}


def classify(components: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Split components into red and degraded, and decide the overall verdict.

    `all_ok` is "no OBSERVED component is red", not "every component is ok".
    Those differ exactly for a component nobody managed to check, which is the
    case H01-H04 is about.
    """
    degraded = sorted(n for n, p in components.items() if not is_observed(p))
    red = sorted(n for n, p in components.items() if is_observed(p) and not bool(p.get("ok")))
    all_ok = not red
    return {
        "ok": all_ok,
        "fully_observed": all_ok and not degraded,
        "red_components": red,
        "degraded_components": degraded,
    }
