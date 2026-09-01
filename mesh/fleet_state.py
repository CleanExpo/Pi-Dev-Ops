"""Fleet reads for the runner, where UNKNOWN is not the same as EMPTY (RA-7392).

`GET /api/mesh/fleet` used to render a failed Supabase read as
`{"machines": [], "agents": [], "ships": [], "claims": []}` — byte-identical to
a fleet nobody has joined. `mesh/runner.py` consumed that directly, so an
outage reached the runner as two specific false facts:

  * `my_claims()` -> `[]`, so `get_work()` concluded it held nothing and went on
    to SELF-CLAIM another ticket while its real claims were merely invisible.
  * `active_agent_count()` -> `0`, so `0 < MAX_PARALLEL` was true and the loop
    took its immediate-reclaim path (a 3 s floor) instead of the 30 s poll
    sleep. That branch is the queue-drain accelerator, not a spawn gate —
    `tests/test_mesh_runner_idle_autoclaim.py` pins both halves of it — so the
    effect was to claim MORE work, FASTER, precisely while the fleet could not
    be read. The two reads are separate API calls, so the second can fail after
    the first succeeded; that is the case the `is not None` guard covers.

Both now return None, meaning "could not read", which the caller must handle
explicitly. Returning None rather than 0 or [] is the whole point: a falsy
value would keep flowing through `if claims:` and `count < MAX_PARALLEL` and
reproduce the bug with extra steps.

Split out of runner.py rather than added to it: that file was at 297 lines
against the repo's 300-line convention, and these helpers are pure given an
`api` callable, so they are testable without a runner loop or a server. The
`sys.path` sibling import in runner.py follows the pattern it already uses for
`repo_guard`.
"""

from __future__ import annotations

from typing import Callable

Api = Callable[..., dict]


def _readable(api: Api) -> "dict | None":
    """The fleet snapshot, or None when it cannot be trusted.

    Two independent signals, because the read can fail at two layers:
    `_api` renders any HTTP or transport error as `{"error": ...}`, and the
    server sets `degraded` when one of its four Supabase sources failed even
    though the request itself returned 200.
    """
    fleet = api("GET", "/api/mesh/fleet")
    if not isinstance(fleet, dict):
        return None
    if fleet.get("error") or fleet.get("degraded"):
        return None
    return fleet


def _rows(fleet: dict, key: str) -> list:
    """Row dicts under `key`. Tolerates a non-list, which the endpoint used to
    return verbatim when PostgREST answered with a JSON error object."""
    value = fleet.get(key)
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def my_claims(api: Api, host: str) -> "list[dict] | None":
    """Open claims for `host`, or None when the fleet could not be read."""
    fleet = _readable(api)
    if fleet is None:
        return None
    return [c for c in _rows(fleet, "claims")
            if c.get("machine") == host and c.get("state") == "claimed"]


def active_agent_count(api: Api, host: str) -> "int | None":
    """Non-idle agents on `host`, or None when the fleet could not be read."""
    fleet = _readable(api)
    if fleet is None:
        return None
    return sum(1 for a in _rows(fleet, "agents") if a.get("machine") == host)
