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

from app.server.autonomy_eligibility import GUARD_FIELDS, REPEAT_CLAIM_LABEL

log = logging.getLogger("pi-ceo.autonomy")

PAGE_SIZE = 50
MAX_PAGES = 20  # 1,000 tickets per project/label; a runaway cursor cannot spin forever
TOKEN_CAP_LABEL = "pi-dev:blocked-reason:token-cap"
START_FAILED_LABEL = "pi-dev:blocked-reason:start-failed"
_DEFAULT_TICKET_TOKEN_CAP = 300_000  # three default session budgets

TODO_ISSUES_QUERY = """
query AutonomyQueueIssues($projectId: String!, $statusName: String!, $autonomyLabel: String!, $after: String) {
    project(id: $projectId) {
        issues(filter: {
            state: { name: { eq: $statusName } }
            labels: { name: { eq: $autonomyLabel } }
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
}
""" % (PAGE_SIZE, GUARD_FIELDS)


def issue_pages(gql: Callable[..., dict], api_key: str, variables: dict) -> Iterator[dict]:
    """Yield every issue node of one project/label read, following ``pageInfo``."""
    after = None
    for _ in range(MAX_PAGES):
        data = gql(api_key, TODO_ISSUES_QUERY, {**variables, "after": after})
        issues = (data.get("project") or {}).get("issues") or {}
        yield from issues.get("nodes") or []
        page = issues.get("pageInfo") or {}
        after = page.get("endCursor")
        if not page.get("hasNextPage") or not after:
            return
    log.warning("Autonomy: queue read stopped at %d pages for %s", MAX_PAGES, variables)


def _autonomy():
    from app.server import autonomy  # noqa: PLC0415 — autonomy imports this module
    return autonomy


def _park(api_key: str, issue_id: str, team_id: str, label: str, comment: str) -> str:
    """Label, move to the team's Blocked state, comment. Returns the state used."""
    a = _autonomy()
    target = a._recovery_state_for(team_id)
    a.add_label_to_issue(api_key, issue_id, team_id, label)
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
    """Tokens every recorded session has spent on this ticket; None when unreadable.

    0 when Supabase is not configured: there is no shared ledger to read, the
    same stance ``session_lease.claim_linear_ticket`` takes.
    """
    from app.server import supabase_log  # noqa: PLC0415

    if not all(supabase_log._cfg()):
        return 0
    status, rows = supabase_log._request(
        "GET",
        "sessions?select=used:checkpoint->budget->used"
        f"&checkpoint->>linear_issue_id=eq.{supabase_log._q(linear_issue_id)}",
        None, "",
    )
    if not supabase_log._ok(status) or not isinstance(rows, list):
        return None
    return sum(int(r.get("used") or 0) for r in rows if isinstance(r, dict))


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


def release_session_claim(session: Any) -> None:
    """Release the fleet claim an autonomy session holds, on any terminal status.

    The claim row is keyed by identifier (RA-123); a session knows only the
    Linear UUID, so the identifier is read back from Linear. Best-effort: a
    miss leaves the row for the reaper, exactly as before this existed.
    """
    issue_id = getattr(session, "linear_issue_id", None)
    if not issue_id or not getattr(session, "autonomy_triggered", False):
        return
    from app.server import config, session_lease  # noqa: PLC0415

    try:
        data = _autonomy()._gql(config.LINEAR_API_KEY, "query($id: String!) { issue(id: $id) { identifier } }",
                                {"id": issue_id})
        ident = (data.get("issue") or {}).get("identifier")
    except Exception as exc:  # noqa: BLE001 — terminal bookkeeping never raises
        log.warning("Autonomy: claim release lookup failed for %s: %s", issue_id, exc)
        return
    state = _TERMINAL_CLAIM_STATE.get(str(getattr(session, "status", "")), "released")
    if ident:
        session_lease.release_linear_ticket(ident, state)
