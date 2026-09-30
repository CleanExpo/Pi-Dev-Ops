"""tests/test_ticket_sweeper.py — nightly ticket-lifecycle sweeper (audit #17).

Linear (``autonomy._gql`` + the write helpers) and GitHub (``github_get``) are
mocked, so nothing here touches the network. Pins:
  * dry-run is the default: decisions are counted, no Linear write is made
  * stale started ticket, no PR, no blocker → comment + stale:14d + Todo
  * stale with a PR or an open blocker → labelled, never moved
  * In Review is surfaced, never moved; red or >3d-unreviewed PR → review:red-pr
  * a GitHub read failure is "unknown", never "green"
  * failed build: first failure → Ready once, second → Pi-Dev: Blocked + reason
  * a failed Linear fetch marks the run incomplete instead of reading as zero
  * counts persist to the state file and appear in the Mission Control snapshot
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import autonomy, cron_handler_registry, ticket_sweeper, ticket_sweeper_io  # noqa: E402

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
_PROJECT = [{"name": "pi-dev-ops", "project_id": "proj-RA", "repo_url": "x", "team_id": "team-RA"}]
PR = "https://github.com/CleanExpo/ATO/pull/35"


def _issue(ident, state="In Progress", *, stype="started", labels=(), pr=None, blocker=None, comments=()):
    return {
        "id": f"id-{ident}", "identifier": ident, "title": ident, "description": "",
        "updatedAt": "2026-09-01T00:00:00Z",
        "state": {"id": "s", "name": state, "type": stype},
        "labels": {"nodes": [{"name": n} for n in labels]},
        "attachments": {"nodes": [{"url": pr}] if pr else []},
        "inverseRelations": {"pageInfo": {"hasNextPage": False}, "nodes": [
            {"type": "blocks", "issue": {"identifier": blocker, "state": {"type": "started"}}},
        ] if blocker else []},
        "comments": {"pageInfo": {"hasNextPage": False}, "nodes": [
            {"body": b, "createdAt": f"2026-09-{10 + n:02d}T00:00:00Z"} for n, b in enumerate(comments)]},
    }


FAILED = "Pi CEO build **failed** after 12s.\n\nSession: `abc`"
GRANT = "**Failed-build sweep:** first failure — sent back to Ready for Pi-Dev once."
BLOCK = "**Failed-build sweep:** failed again after its one retry — blocked for a human."


@pytest.fixture
def world(monkeypatch, tmp_path):
    """Fake Linear + GitHub; records every write the sweeper makes."""
    state = {"stale": [], "in_review": [], "recent_todo": [], "fail": set(), "null_project": set(),
             "pages": {}, "prs": {}, "writes": [], "label_ok": True}
    monkeypatch.setenv("LINEAR_API_KEY", "lin_test")
    monkeypatch.delenv("TAO_TICKET_SWEEPER_WRITE", raising=False)
    monkeypatch.setattr(ticket_sweeper, "_STATE_FILE", tmp_path / "sweeper.json")
    monkeypatch.setattr(autonomy, "_load_portfolio_projects", lambda: _PROJECT)

    def fake_gql(api_key, query, variables=None, **kw):
        bucket = ("stale" if "SweeperStarted" in query else
                  "in_review" if "SweeperInReview" in query else "recent_todo")
        if bucket in state["fail"]:
            raise RuntimeError("Linear HTTP 500")
        if bucket in state["null_project"]:
            return {"project": None}
        pages = state["pages"].get(bucket) or [state[bucket]]
        idx = int((variables or {}).get("cursor") or 0)
        more = idx + 1 < len(pages)
        return {"project": {"issues": {
            "pageInfo": {"hasNextPage": more, "endCursor": str(idx + 1) if more else None},
            "nodes": [dict(i) for i in pages[idx]]}}}

    def fake_github(path):
        for key, value in state["prs"].items():
            if path.startswith(key):
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected GitHub path {path}")

    monkeypatch.setattr(autonomy, "_gql", fake_gql)
    monkeypatch.setattr(ticket_sweeper_io, "github_get", fake_github)
    monkeypatch.setattr(autonomy, "comment_on_issue",
                        lambda k, iid, body: state["writes"].append(("comment", iid)))
    monkeypatch.setattr(autonomy, "add_label_to_issue",
                        lambda k, iid, team, label: state["label_ok"] and not state["writes"].append(("label", iid, label)))
    monkeypatch.setattr(autonomy, "transition_issue",
                        lambda k, iid, name, team_id=None: state["writes"].append(("state", iid, name)))
    return state


def _pr(repo_num, *, red=False, reviewed=False, created="2026-09-13T00:00:00Z", open_=True, status="success"):
    base = f"/repos/CleanExpo/ATO/pulls/{repo_num}"
    return {
        base + "/reviews": [{"id": 1}] if reviewed else [],
        base: {"state": "open" if open_ else "closed", "merged": False,
               "created_at": created, "head": {"sha": f"sha{repo_num}"}},
        f"/repos/CleanExpo/ATO/commits/sha{repo_num}/check-runs": {"check_runs": [
            {"conclusion": "failure" if red else "success"}]},
        f"/repos/CleanExpo/ATO/commits/sha{repo_num}/status": {"state": status},
    }


def test_dry_run_is_default_and_makes_no_writes(world):
    world["stale"] = [_issue("UNI-1")]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.dry_run is True
    assert report.stale_to_todo == ["UNI-1"]
    assert world["writes"] == []


def test_stale_without_pr_or_blocker_moves_to_todo(world, monkeypatch):
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["stale"] = [_issue("UNI-1")]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.dry_run is False
    assert ("label", "id-UNI-1", "stale:14d") in world["writes"]
    assert ("comment", "id-UNI-1") in world["writes"]
    assert ("state", "id-UNI-1", "Todo") in world["writes"]


def test_stale_with_pr_or_blocker_is_labelled_not_moved(world, monkeypatch):
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["stale"] = [_issue("UNI-2", pr=PR), _issue("RA-7785", blocker="RA-7474"),
                      _issue("RA-9", state="Pi-Dev: Blocked"), _issue("RA-7148", state="In Review")]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert sorted(report.stale_labelled) == ["RA-7785", "RA-9", "UNI-2"]
    assert report.stale_to_todo == []
    assert not [w for w in world["writes"] if w[0] == "state"]
    assert not [w for w in world["writes"] if w[1] == "id-RA-7148"]  # In Review is not stale-swept


def test_in_review_red_or_unreviewed_pr_is_labelled_never_moved(world, monkeypatch):
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["in_review"] = [
        _issue("RA-7148", "In Review", pr=PR),
        _issue("RA-2", "In Review", pr="https://github.com/CleanExpo/ATO/pull/36"),
        _issue("RA-3", "In Review", pr="https://github.com/CleanExpo/ATO/pull/37"),
    ]
    world["prs"] = {**_pr(35, red=True, reviewed=True),
                    **_pr(36, reviewed=False, created="2026-09-21T00:00:00Z")}
    world["prs"]["/repos/CleanExpo/ATO/pulls/37"] = RuntimeError("GitHub 502")
    report = ticket_sweeper.run_sweep(now=NOW)
    assert sorted(report.review_red_pr) == ["RA-2", "RA-7148"]
    assert report.review_unknown == ["RA-3"]
    labelled = {w[1] for w in world["writes"] if w[0] == "label"}
    assert labelled == {"id-RA-7148", "id-RA-2"}
    assert not [w for w in world["writes"] if w[0] == "state"]


def test_green_reviewed_pr_is_not_flagged(world):
    world["in_review"] = [_issue("RA-5", "In Review", pr=PR)]
    world["prs"] = _pr(35, red=False, reviewed=True)
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.review_red_pr == [] and report.review_unknown == []


def test_failed_build_goes_to_ready_once_then_blocked(world, monkeypatch):
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["recent_todo"] = [
        _issue("RA-10", "Todo", stype="unstarted", comments=[FAILED]),
        _issue("RA-11", "Todo", stype="unstarted", comments=[FAILED, GRANT, "note", FAILED]),
        # Retry granted, no failure since: the retry is owed or in flight — never blocked early.
        _issue("RA-12", "Todo", stype="unstarted", comments=[FAILED, GRANT], labels=["pi-dev:failed-retry-used"]),
        _issue("RA-13", "Todo", stype="unstarted", comments=["just a todo"]),
        # A human moved it back after the block; no failure since → left alone.
        _issue("RA-14", "Todo", stype="unstarted", comments=[FAILED, GRANT, FAILED, BLOCK],
               labels=["pi-dev:failed-retry-used"]),
        # Two historical failures, never granted a retry → gets its one retry first.
        _issue("RA-15", "Todo", stype="unstarted", comments=[FAILED, FAILED]),
    ]
    report = ticket_sweeper.run_sweep(now=NOW)
    # Ready for Pi-Dev is also type "unstarted"; the bucket must select Todo by name.
    assert 'state: { name: { eq: "Todo" } }' in ticket_sweeper_io._RECENT_TODO_QUERY
    assert sorted(report.failed_to_ready) == ["RA-10", "RA-15"]
    assert report.failed_to_blocked == ["RA-11"]
    assert ("state", "id-RA-10", "Ready for Pi-Dev") in world["writes"]
    assert ("label", "id-RA-10", "pi-dev:failed-retry-used") in world["writes"]
    assert ("state", "id-RA-11", "Pi-Dev: Blocked") in world["writes"]
    assert ("label", "id-RA-11", "pi-dev:blocked-reason:build-failed") in world["writes"]
    assert not [w for w in world["writes"] if w[1] in ("id-RA-12", "id-RA-13", "id-RA-14")]


def test_truncated_comments_or_relations_fail_closed(world, monkeypatch):
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    todo = _issue("RA-20", "Todo", stype="unstarted", comments=[FAILED])
    todo["comments"]["pageInfo"]["hasNextPage"] = True
    stale = _issue("UNI-20")
    stale["inverseRelations"]["pageInfo"]["hasNextPage"] = True  # 51st relation could block
    world["recent_todo"], world["stale"] = [todo], [stale]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.failed_to_ready == [] and "comments_unread:RA-20" in report.errors
    assert report.stale_labelled == ["UNI-20"] and report.stale_to_todo == []
    assert not [w for w in world["writes"] if w[0] == "state"]
    assert report.complete is False


def test_malformed_issue_page_is_incomplete_not_zero(world, monkeypatch):
    monkeypatch.setattr(autonomy, "_gql", lambda *a, **k: {"project": {"issues": {}}})
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.complete is False and len(report.errors) == 3


def test_failed_fetch_marks_run_incomplete(world):
    world["fail"] = {"stale"}
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.complete is False
    assert any(e.startswith("fetch_failed:stale") for e in report.errors)


def test_no_api_key_records_error_and_fetches_nothing(world, monkeypatch):
    monkeypatch.delenv("LINEAR_API_KEY")
    monkeypatch.setattr(ticket_sweeper.config, "LINEAR_API_KEY", "", raising=False)
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.errors == ["no_linear_api_key"] and report.complete is False


def test_counts_persist_to_mission_control_snapshot(world):
    assert ticket_sweeper.status_snapshot()["last_run_at"] is None
    world["stale"] = [_issue("UNI-1"), _issue("UNI-2", pr=PR)]
    ticket_sweeper.run_sweep(now=NOW)
    snap = ticket_sweeper.status_snapshot()
    assert snap["last_run_at"] and snap["dry_run"] is True and snap["complete"] is True
    assert snap["counts"]["stale_to_todo"] == 1 and snap["counts"]["stale_labelled"] == 1


def test_failed_retry_label_write_blocks_the_move(world, monkeypatch):
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["label_ok"] = False
    world["recent_todo"] = [_issue("RA-10", "Todo", stype="unstarted", comments=[FAILED])]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert not [w for w in world["writes"] if w[0] == "state"]
    assert report.errors == ["label_failed:RA-10"] and report.complete is False


def test_red_commit_status_counts_as_red(world):
    world["in_review"] = [_issue("RA-5", "In Review", pr=PR)]
    world["prs"] = _pr(35, red=False, reviewed=True, status="failure")
    assert ticket_sweeper.run_sweep(now=NOW).review_red_pr == ["RA-5"]


def test_every_page_is_swept(world):
    world["pages"]["stale"] = [[_issue(f"UNI-{i}") for i in range(50)], [_issue("UNI-99")]]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert len(report.stale_to_todo) == 51 and report.complete is True


def test_too_many_pages_is_incomplete_not_short(world, monkeypatch):
    monkeypatch.setattr(ticket_sweeper_io, "_MAX_PAGES", 1)
    world["pages"]["stale"] = [[_issue("UNI-1")], [_issue("UNI-2")]]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.complete is False and any("OverflowError" in e for e in report.errors)


def test_missing_project_is_incomplete_not_zero(world):
    world["null_project"] = {"stale", "in_review", "recent_todo"}
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.complete is False and len(report.errors) == 3
    assert ticket_sweeper.status_snapshot()["complete"] is False


def test_committed_cron_row_fires_at_0330():
    import json
    from app.server import cron_triggers
    rows = json.loads((REPO_ROOT / "config" / "harness" / "cron-triggers.json").read_text())
    row = next(r for r in rows if r["id"] == "ticket-sweeper-nightly")
    assert cron_triggers._matches(row, 3, 30) and not cron_triggers._matches(row, 4, 30)


def test_cron_registry_knows_the_sweeper():
    assert cron_handler_registry.resolve_handler("ticket_sweeper") is ticket_sweeper._fire_ticket_sweeper_trigger
