"""Is Supabase actually reachable from this process?

Mission Control's action ledger told operators to "implement or repair
supabase_log.health_check". The symbol did not exist, so the instruction could
never be followed and the component sat permanently `not_observed`.

It lives here rather than in supabase_log.py because that module is already far
over the 300-line convention and the size gate refuses additions to it.
"""

from __future__ import annotations

from typing import Any

from .supabase_log import _cfg, _ok, _request

# The cheapest read that proves the whole path — config, auth, network, PostgREST.
_PROBE = "gate_checks?select=id&limit=1"


def health_check() -> dict[str, Any]:
    """Return {"ok", "observed", "detail"}.

    `ok` and `observed` are deliberately two questions, because collapsing them
    is exactly what lets an outage read as health:

      observed=False  the probe could not run — nothing is configured, or the
                      request never reached Supabase. UNPROVEN, never a pass.
      observed=True   Supabase answered; `ok` carries its verdict.

    Never returns, logs or echoes the service-role key.
    """
    url, key = _cfg()
    if not url or not key:
        return {
            "ok": False,
            "observed": False,
            "detail": "not configured — SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must both be set",
        }

    status, _body = _request("GET", _PROBE, None, "")
    if status == 0:
        return {
            "ok": False,
            "observed": False,
            "detail": "configured, but the request never reached Supabase (transport failure or timeout)",
        }
    if _ok(status):
        return {"ok": True, "observed": True, "detail": f"read-back succeeded (HTTP {status})"}
    return {
        "ok": False,
        "observed": True,
        "detail": f"Supabase answered HTTP {status} for a read on gate_checks",
    }
