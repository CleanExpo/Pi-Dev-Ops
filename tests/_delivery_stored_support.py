"""tests/_delivery_stored_support.py — planted state-file entries for the RA-8100 delivery tests.

``stored`` and ``summary_of`` build what a real tick writes, field for field, so a planted state is one
the store could have written. The fields are written out here by hand and never read from the schema;
``tests/test_delivery_state_schema.py`` compares them with a real tick's output.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone

PIDEV = "CleanExpo/Pi-Dev-Ops"

_PLACED = {"project_id": "", "repo": PIDEV, "ref": "", "stage": "building", "reason": None, "owner": None,
           "since": None, "age_source": None, "counted": None, "prs": [], "pr_head_sha": None,
           "reviewed_head_sha": None, "authorised_head_sha": None, "merge_sha": None, "deployed_sha": None,
           "verified_sha": None, "tests_passed": False, "acceptance_passed": False, "live_source_provable": True,
           "approval_identity_unverified": False}
_STORED = {  # every field a real tick writes for each kind, written out here by hand (never read from the schema)
    "mission": {"kind": "mission", **_PLACED},
    "orphan_pr": {"kind": "orphan_pr", **_PLACED},
    "repo": {"kind": "repo", "repo": PIDEV, "ref": PIDEV, "stage": "repo", "live_source": "none",
             "live_unconfirmed": None, "merged_unverifiable": 0, "counted": None},
    "alert": {"code": "", "severity": "info", "next_owner": "", "message": "", "ref": "",
              "repo": PIDEV, "since": None, "age_source": None, "url": None, "count": 1},
}


def stored(entry: dict, at: float = 1.0, *, alert: bool = False) -> dict:
    """A planted entry as a real tick writes it: every field of its kind (``entry`` overrides), first_seen
    and last_seen, and for a classified record its ``refreshed_at``. No kind given means a mission."""
    kind = "alert" if alert else entry.get("kind", "mission")
    seen = {"first_seen": at, "last_seen": at, **({} if kind in ("alert", "repo") else {"refreshed_at": at})}
    return {**copy.deepcopy(_STORED[kind]), **seen, **_named(kind, entry.get("id")), **entry}


def _named(kind: str, rid: object) -> dict:
    """The fields a real record derives from its id, so a planted record names itself as a real one does."""
    if not isinstance(rid, str) or kind == "alert":
        return {}
    if kind == "mission":
        return {"ref": rid}
    if kind == "repo":
        return {"repo": rid.removeprefix("repo:"), "ref": rid.removeprefix("repo:")}
    repo, _, number = rid.removeprefix("pr:").rpartition("#")
    if not number.isdigit():
        return {}
    return {"repo": repo, "ref": f"{repo}#{number}", "prs": [{"repo": repo, "number": int(number), "state": "open"}]}


def tick_summary(at: float, complete: bool, **over: object) -> dict:
    """The summary a tick at ``at`` hands the store: its own time, and a reason whenever it is not complete."""
    return summary_of(tick_at=datetime.fromtimestamp(at, timezone.utc).isoformat(), complete=complete, **over)


def planted(missions: dict | None = None, alerts: dict | None = None, at: float = 1.0, **summary: object) -> dict:
    """A whole state as an earlier tick at ``at`` left it: a tick has run, so there is a summary, and it
    says why it was not complete (``summary`` overrides). Nothing is stored where no tick has run."""
    made = tick_summary(at, **{"complete": False, **summary})
    return {"version": 1, "missions": missions or {}, "alerts": alerts or {}, "last_tick": at, "summary": made,
            "checkpoint": {"last_complete": at if made["complete"] else None}}


def summary_of(**over: object) -> dict:
    """A whole stored summary as a real tick writes it (``over`` overrides), for planted states."""
    made = {"tick_at": "2026-11-15T12:00:00+00:00", "complete": False, "missions": 0, "by_severity": {}, "by_code": {},
            "founder_or_critical": [], "skipped_repos": [], "unqueryable_projects": [], "refs_outside_scope": 0,
            "bot_prs": 0, "closed_unmerged": 0, "started_without_pr": 0, "completed_without_pr": 0,
            "not_refreshed": 0, "not_refreshed_ids": [], "vercel_unreadable": 0, "incomplete": {},
            "budget_left": None, **over}
    if not made["complete"] and "incomplete" not in over and "error" not in over:
        made["incomplete"] = {"planted": "earlier_tick"}  # a tick is never incomplete without saying why
    return made
