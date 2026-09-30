"""tests/test_ticket_sweeper.py — nightly ticket-lifecycle sweeper (audit #17): behaviour.

Linear and GitHub are faked in ``_ticket_sweeper_support`` — no network. Pins:
  * dry-run is the default: decisions are counted, no Linear write is made
  * stale started ticket, no PR, no blocker → comment + stale:14d + Todo
  * stale with a PR or an open blocker → labelled, never moved
  * In Review is surfaced, never moved; red or >3d-unreviewed PR → review:red-pr
  * failed build: first failure → Ready once, a failure after the retry → Blocked
  * counts persist to the state file and appear in the Mission Control snapshot
Fail-closed cases (partial reads, malformed payloads, failed writes) live in
``test_ticket_sweeper_failclosed.py``.
"""
from __future__ import annotations

from _ticket_sweeper_support import (  # noqa: F401 — `world` is a pytest fixture
    BLOCK, FAILED, GRANT, NOW, PR, REPO_ROOT, _issue, _pr, world,
)
from app.server import cron_handler_registry, ticket_sweeper, ticket_sweeper_io


def test_dry_run_is_default_and_makes_no_writes(world):  # noqa: F811
    world["stale"] = [_issue("UNI-1")]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.dry_run is True
    assert report.stale_to_todo == ["UNI-1"]
    assert world["writes"] == []


def test_stale_without_pr_or_blocker_moves_to_todo(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["stale"] = [_issue("UNI-1")]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.dry_run is False
    assert ("label", "id-UNI-1", "stale:14d") in world["writes"]
    assert ("comment", "id-UNI-1") in world["writes"]
    assert ("state", "id-UNI-1", "Todo") in world["writes"]


def test_stale_with_pr_or_blocker_is_labelled_not_moved(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["stale"] = [_issue("UNI-2", pr=PR), _issue("RA-7785", blocker="RA-7474"),
                      _issue("RA-9", state="Pi-Dev: Blocked"), _issue("RA-7148", state="In Review")]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert sorted(report.stale_labelled) == ["RA-7785", "RA-9", "UNI-2"]
    assert report.stale_to_todo == []
    assert not [w for w in world["writes"] if w[0] == "state"]
    assert not [w for w in world["writes"] if w[1] == "id-RA-7148"]  # In Review is not stale-swept


def test_in_review_red_or_unreviewed_pr_is_labelled_never_moved(world, monkeypatch):  # noqa: F811
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


def test_green_reviewed_pr_is_not_flagged(world):  # noqa: F811
    world["in_review"] = [_issue("RA-5", "In Review", pr=PR)]
    world["prs"] = _pr(35, red=False, reviewed=True)
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.review_red_pr == [] and report.review_unknown == []


def test_failed_build_goes_to_ready_once_then_blocked(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["recent_todo"] = [
        _issue("RA-10", "Todo", stype="unstarted", comments=[FAILED]),
        _issue("RA-11", "Todo", stype="unstarted", comments=[FAILED, GRANT, "note", FAILED],
               labels=["pi-dev:failed-retry-used"]),
        # Grant comment but the retry label was removed by a human → another retry, not a block.
        _issue("RA-16", "Todo", stype="unstarted", comments=[FAILED, GRANT, FAILED]),
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
    assert sorted(report.failed_to_ready) == ["RA-10", "RA-15", "RA-16"]
    assert report.failed_to_blocked == ["RA-11"]
    assert ("state", "id-RA-10", "Ready for Pi-Dev") in world["writes"]
    assert ("label", "id-RA-10", "pi-dev:failed-retry-used") in world["writes"]
    assert ("state", "id-RA-11", "Pi-Dev: Blocked") in world["writes"]
    assert ("label", "id-RA-11", "pi-dev:blocked-reason:build-failed") in world["writes"]
    assert not [w for w in world["writes"] if w[1] in ("id-RA-12", "id-RA-13", "id-RA-14")]


def test_counts_persist_to_mission_control_snapshot(world):  # noqa: F811
    assert ticket_sweeper.status_snapshot()["last_run_at"] is None
    world["stale"] = [_issue("UNI-1"), _issue("UNI-2", pr=PR)]
    ticket_sweeper.run_sweep(now=NOW)
    snap = ticket_sweeper.status_snapshot()
    assert snap["last_run_at"] and snap["dry_run"] is True and snap["complete"] is True
    assert snap["counts"]["stale_to_todo"] == 1 and snap["counts"]["stale_labelled"] == 1


def test_red_commit_status_counts_as_red(world):  # noqa: F811
    world["in_review"] = [_issue("RA-5", "In Review", pr=PR)]
    world["prs"] = _pr(35, red=False, reviewed=True, status="failure")
    assert ticket_sweeper.run_sweep(now=NOW).review_red_pr == ["RA-5"]


def test_every_page_is_swept(world):  # noqa: F811
    world["pages"]["stale"] = [[_issue(f"UNI-{i}") for i in range(50)], [_issue("UNI-99")]]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert len(report.stale_to_todo) == 51 and report.complete is True


def test_committed_cron_row_fires_at_0330():
    import json
    from app.server import cron_triggers
    rows = json.loads((REPO_ROOT / "config" / "harness" / "cron-triggers.json").read_text())
    row = next(r for r in rows if r["id"] == "ticket-sweeper-nightly")
    assert cron_triggers._matches(row, 3, 30) and not cron_triggers._matches(row, 4, 30)


def test_cron_registry_knows_the_sweeper():
    assert cron_handler_registry.resolve_handler("ticket_sweeper") is ticket_sweeper._fire_ticket_sweeper_trigger
