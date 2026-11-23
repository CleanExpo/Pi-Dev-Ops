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

import urllib.parse
from typing import Callable

Api = Callable[..., dict]


def _readable(api: Api, failed: Callable[[object], object] = lambda response: None) -> "dict | None":
    """The fleet snapshot, or None when it cannot be trusted.

    Two independent signals, because the read can fail at two layers:
    `_api` renders any HTTP or transport error as `{"error": ...}`, and the
    server sets `degraded` when one of its four Supabase sources failed even
    though the request itself returned 200. A snapshot without its `claims` and `agents`
    lists (`{}`, or an error object where rows belong) carries no claim evidence either.
    `failed` is shown the response it refused.
    """
    fleet = api("GET", "/api/mesh/fleet")
    if (not isinstance(fleet, dict) or fleet.get("error") or fleet.get("degraded")
            or not all(isinstance(fleet.get(key), list) for key in ("claims", "agents"))):
        failed(fleet)
        return None
    return fleet


def _rows(fleet: dict, key: str) -> list:
    """Row dicts under `key`. Tolerates a non-list, which the endpoint used to
    return verbatim when PostgREST answered with a JSON error object."""
    value = fleet.get(key)
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def my_claims(api: Api, host: str,
              failed: Callable[[object], object] = lambda response: None) -> "list[dict] | None":
    """Open claims for `host`, or None when the fleet could not be read."""
    fleet = _readable(api, failed)
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


# A 4xx the server chose to send is a refusal; 404 is Railway's "Application not found"
# edge page during an outage, and 408/429 are the server too busy to answer.
_NOT_A_REFUSAL = ("HTTP 404", "HTTP 408", "HTTP 429")


def _failure(response: object) -> str:
    """Rejected when the server refused the call, unavailable when it was not reached."""
    error = str(response.get("error") or "") if isinstance(response, dict) else ""
    refused = error.startswith("HTTP 4") and not error.startswith(_NOT_A_REFUSAL)
    return "rejected" if refused else "unavailable"


def next_work(api: Api, host: str, report: Callable[[str], object] = lambda outcome: None,
              contact: Callable[[], object] = lambda: None) -> list[dict]:
    """Use assigned work first, otherwise atomically self-claim a mesh:auto ticket.

    A dispatcher-assigned claim carries no brief: `mesh_work_claims` has no text
    columns (mesh/schema/0001_nexus_mesh.sql). `with_brief` fetches it from the server,
    which reads the ticket from Linear for the node holding the claim; a claim it cannot
    brief is failed with a named code and never reaches an agent.

    `report` hears one outcome per poll — unavailable, rejected, empty, assigned or
    refused — because the first four used to return [] alike, so an outage read as an
    empty queue. `refused` means claims were assigned but none could be briefed; no
    self-claim is attempted in that poll.
    `contact` hears each call the server answered successfully, even when a later one fails.
    """
    claims = my_claims(api, host, lambda response: report(_failure(response)))
    if claims is None:
        return []          # fleet unreadable: hold, never self-claim on a guess
    contact()
    if claims:
        ready = [c for c in (with_brief(api, host, claim) for claim in claims) if c]
        report("assigned" if ready else "refused")
        return ready
    response = api("POST", "/api/mesh/claim/self", {"host": host})
    if not isinstance(response, dict) or response.get("error"):
        report(_failure(response))
        return []
    claimed = response.get("claimed", False)  # absent is no answer; null is "nothing to claim"
    if not (claimed is None or (isinstance(claimed, dict) and isinstance(claimed.get("linear_id"), str)
                                and claimed["linear_id"])):
        report("unavailable")
        return []
    contact()
    report("assigned" if claimed else "empty")
    return [claimed] if claimed else []


def _has_brief(claim: dict) -> bool:
    return bool(str(claim.get("title") or "").strip() or str(claim.get("description") or "").strip())


def _brief_problem(response: object, linear_id: str) -> str:
    """The refusal code for a brief response, or "" when it is usable."""
    if not isinstance(response, dict) or (response.get("error") and _failure(response) == "unavailable"):
        return "brief_unreadable"
    if response.get("error") or response.get("linear_id") != linear_id:
        return "brief_refused"
    if not _well_formed(response):
        return "brief_unreadable"
    return "" if _has_brief(response) else "brief_empty"


def _well_formed(brief: dict) -> bool:
    """The full contract: a known lane and an explicit repo (None = no repo needed).

    A brief without its lane could build an idea:plan ticket (plan_lane.lane_of
    defaults to build), and one without its repo key could build in the default repo.
    """
    text_ok = all(isinstance(brief.get(k) or "", str) for k in ("title", "description"))
    return (text_ok and brief.get("lane") in ("build", "plan") and "repo" in brief
            and (brief["repo"] is None or isinstance(brief["repo"], str)))


def with_brief(api: Api, host: str, claim: dict) -> "dict | None":
    """`claim` with its ticket's brief, lane and repo, or None after refusing it.

    A self-claim already carries its brief and is returned as it is. A refusal fails
    the claim on the server with a closed-set code, which ends the claim and returns
    the ticket to the pool, rather than leaving it locked under a claim nobody works.
    A claim naming no ticket cannot be briefed or ended by ticket id; it is dropped.
    """
    linear_id = claim.get("linear_id")
    if not isinstance(linear_id, str) or not linear_id:
        return None
    if _has_brief(claim):
        return claim
    q = urllib.parse.urlencode({"linear_id": linear_id, "host": host, "claim_id": claim.get("id") or ""})
    response = api("GET", f"/api/mesh/claim/brief?{q}")
    if code := _brief_problem(response, linear_id):
        api("POST", "/api/mesh/claim/update", {"linear_id": linear_id, "state": "failed", "host": host,
                                               "claim_id": claim.get("id"), "error_code": code})
        return None
    brief = {k: response.get(k) for k in ("title", "description", "lane", "repo")}
    return {**claim, **{k: v for k, v in brief.items() if v is not None}}
