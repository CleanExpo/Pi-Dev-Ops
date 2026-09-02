"""Fleet snapshot assembly for `GET /api/mesh/fleet` (RA-7392).

WHY THIS IS ITS OWN MODULE. `docs/runbooks/fleet-operations.md` names that
endpoint as the ONLY confirmation for action item 1 — "3 rows, all fresh within
~20 s" — and `mesh/bootstrap.sh` ends by pointing operators at it ("Confirm
from the fleet, not from this output"). Its previous inline parser turned a
failed Supabase read into `{"machines": [], ...}`, byte-identical to a fleet
nobody has joined yet, so an operator who had just bootstrapped three machines
would read zero rows and re-run the join.

Extracted rather than grown in place: `app/server/routes/mesh.py` is baselined
at 462 lines and the RA-7402 ratchet fails a baselined file that grows. Pulling
this out shrinks it, and the assembly is pure — it takes a `fetch` callable, so
it is testable with no HTTP and no Supabase.

TWO FAILURE SHAPES, and the second is the one the ticket missed:

  * A body that is not JSON at all (an HTML error page from a gateway) hit the
    old `except JSONDecodeError: return []` and became an empty list.
  * A PostgREST error is VALID JSON — an object like
    `{"message": "permission denied", "code": "42501"}`. It never reached that
    fallback, so the field came back as a **dict**. `mesh/runner.py` then does
    `[c for c in fleet["claims"] if c.get(...)]`; iterating a dict yields
    strings and `.get` on a string raises AttributeError. That one crashes the
    caller rather than merely misleading it.

Both now resolve to an empty list AND are reported, so "empty" and "broken"
stop being the same answer. The HTTP status is honoured too — `fleet()` used to
discard it with `_, body = _sb(...)`, so a 500 with a parseable body read as
success.
"""

from __future__ import annotations

import json
from typing import Any, Callable

# name -> PostgREST query. Order is the operator's reading order in the runbook.
SOURCES: tuple[tuple[str, str], ...] = (
    ("machines", "mesh_fleet?select=*&order=host"),
    ("agents", "mesh_agents?select=*&state=neq.idle&order=updated_at.desc"),
    ("ships", "mesh_ships?select=*&order=shipped_at.desc&limit=25"),
    ("claims", "mesh_work_claims?select=*&state=in.(claimed,working)&order=claimed_at.desc"),
)


def parse_rows(body: str) -> "tuple[list, str | None]":
    """`(rows, problem)`. `problem` is None only when the body was a JSON list.

    Returning the reason rather than a bare bool keeps the endpoint's `errors`
    entries actionable: "not-json" and "not-a-list" send an operator to very
    different places — a gateway in front of Supabase versus PostgREST refusing
    the query itself.
    """
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return [], "not-json"
    if not isinstance(data, list):
        return [], "not-a-list"
    return [row for row in data if isinstance(row, dict)], None


def snapshot(fetch: Callable[[str], "tuple[int, str]"]) -> dict[str, Any]:
    """Assemble the fleet snapshot from `fetch(path) -> (status, body)`.

    Always returns every list key as a LIST, whatever the source did, so no
    consumer can be handed a dict where it iterates rows.
    """
    out: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    for name, path in SOURCES:
        status, body = fetch(path)
        rows, problem = parse_rows(body)
        if status >= 300:
            errors.append({"source": name, "status": status, "reason": "http-error"})
        elif problem:
            errors.append({"source": name, "status": status, "reason": problem})
        out[name] = rows
    out["degraded"] = bool(errors)
    out["errors"] = errors
    return out


def read(fetch: Callable[[str], "tuple[int, str]"], path: str) -> "tuple[list, str | None]":
    """Rows for `path`, or `(…, reason)` when the read cannot be trusted.

    THE POINT OF THE SIGNATURE. This takes the FETCHER, not a body, so there is
    no way to reach rows without the status having been considered. The helper
    it replaces took a body alone (`_rows(body)`), which made
    `_, body = _sb("GET", …)` the natural call — and that idiom was written five
    separate times in `routes/mesh.py`, once destructively (RA-7405). A parser
    that never sees the status cannot report an HTTP failure, so every caller
    had to remember to check, and none did.

    `_sb` raises on a transport error but RETURNS on a non-2xx from PostgREST,
    which is the dangerous half: an expired service-role key answers 401 with a
    valid JSON error object on every read, so nothing raises and every list
    comes back empty. That case is `http-401` here rather than silence.
    """
    status, body = fetch(path)
    if status >= 300:
        return [], f"http-{status}"
    return parse_rows(body)
