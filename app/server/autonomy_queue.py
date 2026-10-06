"""Autonomy poller queue read and the claim outcomes that must not loop (W1b).

Extracted from autonomy.py, which sits on its file-length baseline:

- ``TODO_ISSUES_QUERY`` / ``issue_pages``: the queue read, paginated. The old
  read took ``first: 10`` with no ``pageInfo``, so an eleventh Ready ticket in a
  project was invisible forever.
- ``block_repeat_claims``: a ticket refused as ``repeat-claim`` is labelled
  ``pi-dev:blocked-reason:repeat-claim`` and parked, instead of being picked up
  again (RA-7785 was started 14 times in a day).
- ``fail_start``: a session that fails to start goes to the team's Blocked
  state, never back to Ready, and its fleet claim is released.
- ``token_cap_refusal``: a per-ticket cumulative token cap. Every session's
  checkpoint row in Supabase already stores ``budget.used`` and
  ``linear_issue_id``; summing them per ticket survives restarts and retries,
  which the per-session BudgetTracker (rebuilt fresh on every start) does not.

Autonomy helpers are looked up on the autonomy module at call time, so tests
that patch ``autonomy.transition_issue`` etc. reach these paths too.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from typing import Any

from app.server.autonomy_eligibility import (
    GUARD_FIELDS, MESH_STATES, REPEAT_CLAIM_LABEL, IncompleteRead, page_of,
)

log = logging.getLogger("pi-ceo.autonomy")

PAGE_SIZE = 10  # three 50-node guard connections per issue; 25 exceeded Linear's 10,000 (RA-7910)
MAX_PAGES = 50  # 500 Ready tickets across the portfolio; a runaway cursor cannot spin forever
TOKEN_CAP_LABEL = "pi-dev:blocked-reason:token-cap"
START_FAILED_LABEL = "pi-dev:blocked-reason:start-failed"
SESSION_FAILED_LABEL = "pi-dev:blocked-reason:session-failed"
# A session row whose checkpoint carries no budget.used is charged one default
# session budget: unknown spend is counted, never read as zero.
_UNKNOWN_SESSION_SPEND = 100_000
_DEFAULT_TICKET_TOKEN_CAP = 300_000  # three default session budgets

# RA-7931: ONE read across every portfolio project and both autonomy labels. The
# old read ran per project x per label (15 x 2 = 30+ requests every poll, ~360+/h
# of the fleet key's 2,500/h). Every filter key is an AND of field comparators —
# no top-level ``or``, which Linear silently ignored in RA-7910 (it matched every
# issue). ``project.id.in`` and ``labels.name.in`` were verified live to filter.
TODO_ISSUES_QUERY = """
query AutonomyQueueIssues($projectIds: [ID!]!, $statusName: String!, $labelNames: [String!]!, $after: String) {
    issues(filter: {
        project: { id: { in: $projectIds } }
        state: { name: { eq: $statusName } }
        labels: { name: { in: $labelNames } }
    }, first: %d, after: $after, orderBy: updatedAt) {
        pageInfo { hasNextPage endCursor }
        nodes {
            id
            identifier
            title
            description
            priority
            url
            estimate
            state { id name type }
            labels { nodes { name } }
            %s
        }
    }
}
""" % (PAGE_SIZE, GUARD_FIELDS)


def issue_pages(gql: Callable[..., dict], api_key: str, variables: dict) -> Iterator[dict]:
    """Yield every issue node of the portfolio queue read, following ``pageInfo``."""
    after = None
    for _ in range(MAX_PAGES):
        data = gql(api_key, TODO_ISSUES_QUERY, {**variables, "after": after})
        nodes, more, after = page_of(data.get("issues"))
        yield from nodes
        if not more:
            return
        if not after:
            raise IncompleteRead("Linear said more pages but gave no cursor")
    # An incomplete read is refused, never served as the whole queue.
    raise IncompleteRead(f"Linear queue read exceeded {MAX_PAGES} pages")


def _autonomy():
    from app.server import autonomy  # noqa: PLC0415 — autonomy imports this module
    return autonomy


def _park(api_key: str, issue_id: str, team_id: str, label: str, comment: str) -> str:
    """Label, move to the team's Blocked state, comment. Returns the state used.

    Teams without a Blocked state fall back to Todo, which the mesh lane reads;
    there the label is the only thing keeping the ticket unclaimable. So when the
    label cannot be attached the ticket is NOT moved into a claimable state: it
    stays where it is, and the comment says so.
    """
    a = _autonomy()
    target = a._recovery_state_for(team_id)
    if not a.add_label_to_issue(api_key, issue_id, team_id, label) and target in MESH_STATES:
        a.comment_on_issue(api_key, issue_id, f"{comment}\n\n(Label `{label}` could not be "
                           f"attached, so the ticket was not moved to `{target}`.)")
        return "unchanged"
    a.transition_issue(api_key, issue_id, target, team_id=team_id)
    a.comment_on_issue(api_key, issue_id, comment)
    return target


def block_repeat_claims(api_key: str, issues: list[dict]) -> None:
    """Park every ticket refused as ``repeat-claim`` so no poll picks it up again."""
    a = _autonomy()
    for issue in issues:
        ident = issue.get("identifier", "?")
        try:
            target = _park(
                api_key, issue["id"], issue.get("_team_id", a._TEAM_ID), REPEAT_CLAIM_LABEL,
                "⛔ Pi-CEO refused a third autonomous start inside 24h. Two sessions "
                "already started on this ticket without finishing it. A human should "
                "find why, remove the `pi-dev:blocked-reason:repeat-claim` label, then "
                "move it back to `Ready for Pi-Dev`.",
            )
            a._log_event({"action": "repeat_claim_blocked", "ticket": ident, "target_state": target})
        except Exception as exc:  # noqa: BLE001 — one ticket must not stop the rest
            log.warning("Autonomy: could not park repeat-claim %s: %s", ident, exc)


def fail_start(api_key: str, issue_id: str, identifier: str, team_id: str,
               exc: BaseException) -> None:
    """A session failed to start: Blocked (never Ready), claim released."""
    from app.server import session_lease  # noqa: PLC0415

    a = _autonomy()
    log.warning("Autonomy: session start failed for %s: %s", identifier, exc)
    a._log_event({"action": "session_error", "ticket": identifier, "error": str(exc)})
    try:
        _park(api_key, issue_id, team_id, START_FAILED_LABEL,
              f"⚠️ Pi-CEO session start failed — parked, not re-queued.\nError: `{exc}`")
    except Exception as park_exc:  # noqa: BLE001
        log.warning("Autonomy: could not park %s after start failure: %s", identifier, park_exc)
    session_lease.release_linear_ticket(identifier, "failed")


def ticket_token_cap() -> int:
    raw = os.environ.get("TAO_TICKET_TOKEN_CAP", "").strip()
    try:
        return int(raw) if raw else _DEFAULT_TICKET_TOKEN_CAP
    except ValueError:
        return _DEFAULT_TICKET_TOKEN_CAP


def tokens_spent(linear_issue_id: str) -> int | None:
    """Tokens every recorded session has spent on this ticket; None when unknowable.

    None when Supabase is not configured or the read fails: with no ledger the
    cap cannot be checked, so the caller refuses (TAO_TICKET_TOKEN_CAP=0 runs
    without a cap). A row without ``budget.used`` counts as one default session
    budget, never as zero.
    """
    from app.server import supabase_log  # noqa: PLC0415

    if not all(supabase_log._cfg()):
        return None
    status, rows = supabase_log._request(
        "GET",
        "sessions?select=used:checkpoint->budget->used"
        f"&checkpoint->>linear_issue_id=eq.{supabase_log._q(linear_issue_id)}",
        None, "",
    )
    if not supabase_log._ok(status) or not isinstance(rows, list):
        return None
    return sum(
        int(r["used"]) if isinstance(r.get("used"), (int, float)) else _UNKNOWN_SESSION_SPEND
        for r in rows if isinstance(r, dict)
    )


def within_token_cap(issue_id: str) -> bool:
    """The cap check every executor shares: False when over the cap or unknowable."""
    cap = ticket_token_cap()
    if cap <= 0:
        return True
    spent = tokens_spent(issue_id)
    return spent is not None and spent < cap


def token_cap_refusal(config: Any, issue_id: str, identifier: str, team_id: str) -> bool:
    """True when this ticket must not start: over its cap, or its spend is unreadable.

    Takes the poller's config, not the key, so the key is read only to park a ticket.
    """
    cap = ticket_token_cap()
    if cap <= 0:
        return False
    spent = tokens_spent(issue_id)
    if spent is None:
        log.warning("Autonomy: %s skipped — token ledger unreadable, cap cannot be checked", identifier)
        return True
    if spent < cap:
        return False
    a = _autonomy()
    try:
        _park(config.LINEAR_API_KEY, issue_id, team_id, TOKEN_CAP_LABEL,
              f"⛔ Pi-CEO token cap reached: {spent:,} tokens spent across sessions "
              f"(cap {cap:,}, TAO_TICKET_TOKEN_CAP). Not starting another session.")
    except Exception as exc:  # noqa: BLE001
        log.warning("Autonomy: could not park %s at token cap: %s", identifier, exc)
    a._log_event({"action": "token_cap_refused", "ticket": identifier, "spent": spent, "cap": cap})
    return True


_PENDING_REPEAT_CLAIMS: list[dict] = []


def drain_repeat_claims() -> list[dict]:
    """Repeat-claim refusals seen by the last queue read(s), each once, then cleared."""
    seen: dict[str, dict] = {i.get("id") or "": i for i in _PENDING_REPEAT_CLAIMS}
    _PENDING_REPEAT_CLAIMS.clear()
    return [i for k, i in seen.items() if k]


def claimable_or_refused(issues: list[dict], refused: list | None, **kwargs: Any) -> list[dict]:
    """Split issues into claimable ones (returned) and repeat-claim refusals.

    Refusals go to ``refused``, or when that is None to the pending list the
    poller drains — so ``fetch_todo_issues`` keeps its one-argument signature.
    """
    from app.server.autonomy_eligibility import (  # noqa: PLC0415
        claim_refusal, filter_claimable_issues, issue_project_id,
    )

    target = _PENDING_REPEAT_CLAIMS if refused is None else refused
    target.extend(
        i for i in issues
        if claim_refusal(i) == "repeat-claim"
        and issue_project_id(i) in kwargs["registered_project_ids"]
    )
    return filter_claimable_issues(issues, **kwargs)


_TERMINAL_CLAIM_STATE = {"complete": "done", "failed": "failed"}


_CLAIMED: dict[str, str] = {}  # Linear UUID -> identifier, for claims this process took


def remember_claim(issue_id: str, identifier: str) -> None:
    """Record which ticket a won claim belongs to, so release needs no Linear read."""
    _CLAIMED[issue_id] = identifier


def release_session_claim(session: Any) -> None:
    """On any terminal status: mark a failed ticket unclaimable, then free its claim.

    A failed session moves its ticket to Todo (session_linear), which the mesh
    lane reads. So a failed ticket is labelled ``pi-dev:blocked-reason:session-failed``
    first, while the fleet claim still locks it; if the label cannot be attached
    (Linear down included) the claim is kept, so nobody re-claims an unlabelled
    failure. Any other terminal status releases from the identity recorded at
    claim time, so a Linear outage cannot strand the claim.
    """
    issue_id = getattr(session, "linear_issue_id", None)
    status = str(getattr(session, "status", ""))
    if not issue_id or (status != "failed" and not getattr(session, "autonomy_triggered", False)):
        return
    from app.server import config, session_lease  # noqa: PLC0415

    a = _autonomy()
    ident = _CLAIMED.get(issue_id)
    if status == "failed":
        try:
            data = a._gql(config.LINEAR_API_KEY,
                          "query($id: String!) { issue(id: $id) { identifier team { id } } }", {"id": issue_id})
            issue = data.get("issue") or {}
            ident = ident or issue.get("identifier")
            labelled = a.add_label_to_issue(config.LINEAR_API_KEY, issue_id,
                                            (issue.get("team") or {}).get("id") or a._TEAM_ID, SESSION_FAILED_LABEL)
        except Exception as exc:  # noqa: BLE001 — terminal bookkeeping never raises
            log.warning("Autonomy: could not label failed %s: %s", issue_id, exc)
            labelled = False
        if not labelled:
            log.warning("Autonomy: %s failed and could not be labelled; claim kept", ident or issue_id)
            return
    if ident and getattr(session, "autonomy_triggered", False):
        if session_lease.release_linear_ticket(ident, _TERMINAL_CLAIM_STATE.get(status, "released")):
            _CLAIMED.pop(issue_id, None)
