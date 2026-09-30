"""ticket_sweeper_write.py — verified Linear writes for the ticket sweeper.

Called only behind ``TAO_TICKET_SWEEPER_WRITE=1``. The shared autonomy write
helpers do not check GraphQL ``success``, so no write here is trusted until a
re-read of the issue shows it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import autonomy
from . import ticket_sweeper_io as io

# issueAddLabel adds ONE label. autonomy.add_label_to_issue instead rewrites the
# whole labelIds set from a first-page read, which drops labels past 50.
_ADD_LABEL = """
mutation SweeperAddLabel($id: String!, $labelId: String!) {
    issueAddLabel(id: $id, labelId: $labelId) { success }
}
"""


def add_label(api_key: str, iid: str, team: str, name: str) -> bool:
    label_id = autonomy._resolve_or_create_label(api_key, team, name)
    if not label_id:
        return False
    data = autonomy._gql(api_key, _ADD_LABEL, {"id": iid, "labelId": label_id})
    return bool((data.get("issueAddLabel") or {}).get("success"))


@dataclass
class Write:
    label: str
    comment: str | None = None
    state: str | None = None
    recheck: Callable[[dict], bool] | None = None  # does the FRESH issue still qualify?
    move_guard: Callable[[dict], bool] | None = None  # checked again just before the move


def _comment_count(issue: dict, body: str) -> int | None:
    nodes = io.complete_nodes(issue, "comments")
    return None if nodes is None else sum(1 for c in nodes if c.get("body") == body)


def write_verified(api_key: str, iid: str, team: str, w: Write) -> str | None:
    """Re-read, then each write followed by a re-read that proves it stuck.
    Returns a problem name, or None. Order is label → comment → move, so a
    ticket is never moved without both durable retry markers on Linear."""
    fresh = io.fetch_issue(api_key, iid)
    if w.recheck is not None and not w.recheck(fresh):
        return "drift"
    if io.label_names(fresh) is None:
        return "labels_unread"
    if w.label.lower() not in io.label_names(fresh):
        add_label(api_key, iid, team, w.label)
        relabelled = io.label_names(io.fetch_issue(api_key, iid)) or set()
        if w.label.lower() not in relabelled or not io.label_names(fresh) <= relabelled:
            return "label_unconfirmed"  # missing, or an existing label was lost
    if w.comment:
        autonomy.comment_on_issue(api_key, iid, w.comment)
    after = io.fetch_issue(api_key, iid)
    before_n, after_n = (_comment_count(fresh, w.comment), _comment_count(after, w.comment)) if w.comment else (0, 1)
    if before_n is None or after_n is None or after_n <= before_n:
        return "comment_unconfirmed"
    if w.state:
        if not io.state_is(after, (fresh.get("state") or {}).get("name") or "") or (
                w.move_guard is not None and not w.move_guard(after)):
            return "drift"  # changed under us (e.g. moved to In Review) — do not move it
        autonomy.transition_issue(api_key, iid, w.state, team_id=team)
        if not io.state_is(io.fetch_issue(api_key, iid), w.state):
            return "state_unconfirmed"
    return None
