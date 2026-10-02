"""tests/_ticket_sweeper_support.py — fake Linear + GitHub for the ticket-sweeper tests.

Nothing here touches the network: ``autonomy._gql``, the Linear write helpers
and ``ticket_sweeper_io.github_get`` are replaced, and every write is recorded.
"""
from __future__ import annotations

import copy
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import autonomy, ticket_sweeper, ticket_sweeper_io, ticket_sweeper_write  # noqa: E402

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
_PROJECT = [{"name": "pi-dev-ops", "project_id": "proj-RA", "repo_url": "x", "team_id": "team-RA"}]
PR = "https://github.com/CleanExpo/ATO/pull/35"


def _issue(ident, state="In Progress", *, stype="started", labels=(), pr=None, blocker=None, comments=()):
    return {
        "id": f"id-{ident}", "identifier": ident, "title": ident, "description": "",
        "updatedAt": "2026-09-01T00:00:00Z",
        "state": {"id": "s", "name": state, "type": stype},
        "labels": {"pageInfo": {"hasNextPage": False}, "nodes": [{"name": n} for n in labels]},
        "attachments": {"pageInfo": {"hasNextPage": False}, "nodes": [{"url": pr}] if pr else []},
        "inverseRelations": {"pageInfo": {"hasNextPage": False}, "nodes": [
            {"type": "blocks", "issue": {"identifier": blocker, "state": {"type": "started"}}},
        ] if blocker else []},
        "comments": {"pageInfo": {"hasNextPage": False}, "nodes": [
            {"body": b, "createdAt": f"2026-09-{10 + n:02d}T00:00:00Z"} for n, b in enumerate(comments)]},
    }


FAILED = "Pi CEO build **failed** after 12s.\n\nSession: `abc`"
GRANT = "**Failed-build sweep:** first failure — sent back to Ready for Pi-Dev once."
BLOCK = "**Failed-build sweep:** failed again after its one retry — blocked for a human."


def _fake_gql(state: dict):
    """A small Linear: bucket queries page over state[bucket]; SweeperIssue re-reads
    the live copy in state["db"], which the fake write helpers mutate."""
    def fake_gql(api_key, query, variables=None, **kw):
        if "SweeperIssue" in query:
            return {"issue": copy.deepcopy(state["db"].get(variables["id"]))}
        bucket = ("stale" if "SweeperStarted" in query else
                  "in_review" if "SweeperInReview" in query else "recent_todo")
        if bucket in state["fail"]:
            raise RuntimeError("Linear HTTP 500")
        if bucket in state["null_project"]:
            return {"project": None}
        pages = state["pages"].get(bucket) or [state[bucket]]
        idx = int((variables or {}).get("cursor") or 0)
        more = idx + 1 < len(pages)
        for i in pages[idx]:
            if i:
                state["db"].setdefault(i["id"], copy.deepcopy(i))
        return {"project": {"issues": {
            "pageInfo": {"hasNextPage": more, "endCursor": str(idx + 1) if more else None},
            "nodes": [copy.deepcopy(state["db"][i["id"]]) if i else i for i in pages[idx]]}}}
    return fake_gql


def _fake_writes(state: dict, monkeypatch) -> None:
    """Write helpers that record, and persist into state["db"] unless told not to."""
    def label(k, iid, team, name):
        state["writes"].append(("label", iid, name))
        state["on_label"](state["db"][iid])
        if state["label_ok"]:
            state["db"][iid]["labels"]["nodes"].append({"name": name})
        return True

    def comment(k, iid, body):
        state["writes"].append(("comment", iid))
        state["on_comment"](state["db"][iid])
        if state["comment_ok"]:
            state["db"][iid]["comments"]["nodes"].append({"body": body, "createdAt": "2026-09-30T00:00:00Z"})

    def transition(k, iid, name, team_id=None):
        state["writes"].append(("state", iid, name))
        if state["state_ok"]:
            state["db"][iid]["state"]["name"] = name

    monkeypatch.setattr(ticket_sweeper_write, "add_label", label)
    monkeypatch.setattr(autonomy, "comment_on_issue", comment)
    monkeypatch.setattr(autonomy, "transition_issue", transition)


def _fake_github(state: dict):
    def fake_github(path):
        for key, value in state["prs"].items():
            if path.startswith(key):
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected GitHub path {path}")
    return fake_github


@pytest.fixture
def world(monkeypatch, tmp_path):
    """Fake Linear + GitHub; records every write the sweeper makes."""
    state = {"stale": [], "in_review": [], "recent_todo": [], "fail": set(), "null_project": set(),
             "pages": {}, "prs": {}, "writes": [], "db": {}, "on_label": lambda issue: None,
             "on_comment": lambda issue: None,
             "label_ok": True, "comment_ok": True, "state_ok": True}
    monkeypatch.setenv("LINEAR_API_KEY", "lin_test")
    monkeypatch.delenv("TAO_TICKET_SWEEPER_WRITE", raising=False)
    monkeypatch.setattr(ticket_sweeper, "_STATE_FILE", tmp_path / "sweeper.json")
    monkeypatch.setattr(ticket_sweeper, "_unsaved_run_at", None)
    monkeypatch.setattr(autonomy, "_load_portfolio_projects", lambda: _PROJECT)
    monkeypatch.setattr(autonomy, "_gql", _fake_gql(state))
    monkeypatch.setattr(ticket_sweeper_io, "github_get", _fake_github(state))
    _fake_writes(state, monkeypatch)
    return state


def _pr(repo_num, *, red=False, reviewed=False, created="2026-09-13T00:00:00Z", open_=True, status="success"):
    base = f"/repos/CleanExpo/ATO/pulls/{repo_num}"
    return {
        base + "/reviews": [{"id": 1}] if reviewed else [],
        base: {"state": "open" if open_ else "closed", "merged": False,
               "created_at": created, "head": {"sha": f"sha{repo_num}"}},
        f"/repos/CleanExpo/ATO/commits/sha{repo_num}/check-runs": {"total_count": 1, "check_runs": [
            {"conclusion": "failure" if red else "success"}]},
        f"/repos/CleanExpo/ATO/commits/sha{repo_num}/status": {"state": status},
    }
