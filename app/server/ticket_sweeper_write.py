"""ticket_sweeper_write.py — verified Linear writes for the ticket sweeper.

Called only behind ``TAO_TICKET_SWEEPER_WRITE=1``. The shared autonomy write
helpers do not check GraphQL ``success``, so no write here is trusted until a
re-read of the issue shows it.
"""
from __future__ import annotations

from collections import Counter
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
    kind: str = ""  # which guard re-validates an unfinished move on the next sweep
    seen_updated_at: str = ""  # the ticket's updatedAt once our label + comment were on


def _comment_count(issue: dict, body: str) -> int | None:
    nodes = io.complete_nodes(issue, "comments")
    return None if nodes is None else sum(1 for c in nodes if c.get("body") == body)


def only_our_changes(fresh: dict, after: dict, w: Write) -> bool:
    """True when the only differences between the two reads are the sweeper's own
    label and comment — no human comment, label, state, title or text change."""
    fb, ab = io.ordered_bodies(fresh), io.ordered_bodies(after)
    fl, al = io.label_names(fresh), io.label_names(after)
    if fb is None or ab is None or fl is None or al is None:
        return False
    return (Counter(ab) == Counter(fb) + Counter([w.comment] if w.comment else [])
            and al == fl | {w.label.lower()}
            and all(after.get(k) == fresh.get(k) for k in ("title", "description"))
            and io.state_is(after, (fresh.get("state") or {}).get("name") or ""))


def _move(api_key: str, iid: str, team: str, state: str) -> str | None:
    try:
        autonomy.transition_issue(api_key, iid, state, team_id=team)
    except autonomy.LinearRateLimitError:
        raise
    except Exception:  # noqa: BLE001 — reported as move_failed and retried next sweep
        return "move_failed"
    return None if io.state_is(io.fetch_issue(api_key, iid), state) else "state_unconfirmed"


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
        if not only_our_changes(fresh, after, w) or (w.move_guard is not None and not w.move_guard(after)):
            return "drift"  # someone else touched it while we wrote — do not move it
        w.seen_updated_at = after.get("updatedAt") or ""
        return _move(api_key, iid, team, w.state)
    return None


def resume_move(api_key: str, p: dict, guard: Callable[[dict], bool] | None) -> str | None:
    """Finish a move a previous sweep wrote the label and comment for but could
    not complete. Only when nothing at all happened since (updatedAt unchanged
    from the read after our label + comment, same state, our comment newest,
    our label on) AND the ticket still qualifies under its kind's guard.
    Otherwise it is dropped as 'drift'."""
    cur = io.fetch_issue(api_key, p["id"])
    bodies = io.ordered_bodies(cur)
    if (guard is None or bodies is None or not bodies or bodies[-1] != p["comment"]
            or not p.get("seen_updated_at") or cur.get("updatedAt") != p["seen_updated_at"]
            or not io.state_is(cur, p["from_state"]) or p["label"].lower() not in (io.label_names(cur) or set())
            or not guard(cur)):
        return "drift"
    return _move(api_key, p["id"], p["team"], p["to_state"])


def apply(api_key: str, issue: dict, report, w: Write) -> bool:
    """One verified write for the sweep; problems and unfinished moves go on ``report``.
    True only when every write was confirmed on Linear (or, in a dry run, would be made),
    so a ticket is counted as swept only after its write stuck."""
    if report.dry_run:
        return True
    try:
        problem = write_verified(api_key, issue["id"], issue.get("_team_id") or autonomy._TEAM_ID, w)
    except autonomy.LinearRateLimitError:
        raise
    except Exception as exc:  # noqa: BLE001 — one ticket never aborts the sweep
        problem = f"write_failed:{type(exc).__name__}"
    if problem:
        report.errors.append(f"{problem}:{issue.get('identifier')}")
    if problem in ("move_failed", "state_unconfirmed"):
        report.pending_moves.append({
            "id": issue["id"], "identifier": issue.get("identifier"), "label": w.label, "comment": w.comment,
            "team": issue.get("_team_id") or autonomy._TEAM_ID, "to_state": w.state, "kind": w.kind,
            "from_state": (issue.get("state") or {}).get("name") or "", "seen_updated_at": w.seen_updated_at})
    return problem is None


def resume_pending(api_key: str, report, guards: dict[str, Callable[[dict], bool]]) -> None:
    """Retry the unfinished moves carried on ``report.pending_moves``. Each one
    stays on the list until it is finished or proven obsolete, so a crashed or
    dry run never loses the record."""
    if report.dry_run:
        return
    todo, report.pending_moves[:] = list(report.pending_moves), []
    for i, p in enumerate(todo):
        try:
            problem = resume_move(api_key, p, guards.get(p.get("kind", "")))
        except autonomy.LinearRateLimitError:
            report.pending_moves.extend(todo[i:])  # this one and the rest wait for the next sweep
            raise
        except Exception as exc:  # noqa: BLE001
            problem = f"write_failed:{type(exc).__name__}"
        if problem and problem != "drift":
            report.errors.append(f"resume_{problem}:{p.get('identifier')}")
            report.pending_moves.append(p)
