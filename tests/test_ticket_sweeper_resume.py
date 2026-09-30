"""tests/test_ticket_sweeper_resume.py — ticket sweeper (audit #17): durability.

An unfinished move is finished on a later sweep only while the ticket still
qualifies, is never lost by a run that stops early, and a run whose state
could not be saved never lets an older clean run show as current.
"""
from __future__ import annotations

from _ticket_sweeper_support import FAILED, GRANT, NOW, PR, _issue, world  # noqa: F401 — fixture
from app.server import ticket_sweeper


def test_unsaved_run_never_shows_the_older_clean_run(world, monkeypatch):  # noqa: F811
    ticket_sweeper.run_sweep(now=NOW)  # a complete, clean, saved run
    assert ticket_sweeper.status_snapshot()["complete"] is True

    def read_only(*a):
        raise OSError("read-only")
    monkeypatch.setattr(ticket_sweeper.os, "replace", read_only)
    world["fail"] = {"stale"}
    ticket_sweeper.run_sweep(now=NOW)
    snap = ticket_sweeper.status_snapshot()
    assert snap["complete"] is False and snap["errors"] == ["state_write_failed"] and snap["counts"] is None


def test_unfinished_move_is_resumed_next_sweep(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["recent_todo"] = [
        _issue("RA-60", "Todo", stype="unstarted", comments=[FAILED]),
        _issue("RA-61", "Todo", stype="unstarted", comments=[FAILED, GRANT, FAILED],
               labels=["pi-dev:failed-retry-used"]),
    ]
    world["state_ok"] = False
    first = ticket_sweeper.run_sweep(now=NOW)
    assert sorted(first.errors) == ["state_unconfirmed:RA-60", "state_unconfirmed:RA-61"]
    world["state_ok"] = True
    second = ticket_sweeper.run_sweep(now=NOW)
    assert second.errors == [] and second.complete is True
    assert world["db"]["id-RA-60"]["state"]["name"] == "Ready for Pi-Dev"
    assert world["db"]["id-RA-61"]["state"]["name"] == "Pi-Dev: Blocked"


def test_failed_save_survives_a_restart(world, monkeypatch):  # noqa: F811
    ticket_sweeper.run_sweep(now=NOW)
    monkeypatch.setattr(ticket_sweeper.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("ro")))
    world["fail"] = {"stale"}
    ticket_sweeper.run_sweep(now=NOW)
    monkeypatch.setattr(ticket_sweeper, "_unsaved_run_at", None)  # a fresh process
    snap = ticket_sweeper.status_snapshot()
    assert snap["complete"] is False and snap["counts"] is None


def test_an_old_saved_run_reads_as_stale(world):  # noqa: F811
    import json
    ticket_sweeper._STATE_FILE.write_text(json.dumps(
        {"finished_at": "2026-01-01T00:00:00+00:00", "complete": True, "dry_run": True, "errors": []}))
    snap = ticket_sweeper.status_snapshot()
    assert snap["complete"] is False and snap["errors"][0] == "stale_state"


def test_unfinished_move_is_dropped_when_someone_acted_since(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["recent_todo"] = [_issue("RA-63", "Todo", stype="unstarted", comments=[FAILED])]
    world["state_ok"] = False
    ticket_sweeper.run_sweep(now=NOW)
    world["state_ok"] = True
    world["db"]["id-RA-63"]["comments"]["nodes"].append({"body": "leave it", "createdAt": "2026-09-30T02:00:00Z"})
    ticket_sweeper.run_sweep(now=NOW)
    assert world["db"]["id-RA-63"]["state"]["name"] == "Todo"


def _leave_pending(w, monkeypatch, issue, bucket):
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    w[bucket] = [issue]
    w["state_ok"] = False
    assert ticket_sweeper.run_sweep(now=NOW).errors == [f"state_unconfirmed:{issue['identifier']}"]
    w["state_ok"], w[bucket] = True, []
    return w["db"][issue["id"]]


def test_pending_stale_move_dropped_when_a_pr_is_attached(world, monkeypatch):  # noqa: F811
    live = _leave_pending(world, monkeypatch, _issue("RA-70"), "stale")
    live["attachments"]["nodes"].append({"url": PR})
    ticket_sweeper.run_sweep(now=NOW)
    assert live["state"]["name"] == "In Progress"


def test_pending_block_dropped_when_retry_label_removed(world, monkeypatch):  # noqa: F811
    live = _leave_pending(world, monkeypatch, _issue(
        "RA-71", "Todo", stype="unstarted", comments=[FAILED, GRANT, FAILED],
        labels=["pi-dev:failed-retry-used"]), "recent_todo")
    live["labels"]["nodes"].remove({"name": "pi-dev:failed-retry-used"})
    ticket_sweeper.run_sweep(now=NOW)
    assert live["state"]["name"] == "Todo"


def test_pending_move_survives_a_run_that_stops_early(world, monkeypatch):  # noqa: F811
    live = _leave_pending(world, monkeypatch, _issue("RA-72", "Todo", stype="unstarted", comments=[FAILED]),
                          "recent_todo")
    monkeypatch.delenv("LINEAR_API_KEY")
    monkeypatch.setattr(ticket_sweeper.config, "LINEAR_API_KEY", "", raising=False)
    assert ticket_sweeper.run_sweep(now=NOW).errors == ["no_linear_api_key"]
    monkeypatch.setenv("LINEAR_API_KEY", "lin_test")
    ticket_sweeper.run_sweep(now=NOW)
    assert live["state"]["name"] == "Ready for Pi-Dev"


def test_failed_save_with_undeletable_old_file_still_reads_incomplete(world, monkeypatch):  # noqa: F811
    import pathlib
    ticket_sweeper.run_sweep(now=NOW)

    def refuse(*a, **k):
        raise OSError("ro")
    monkeypatch.setattr(ticket_sweeper.os, "replace", refuse)
    monkeypatch.setattr(pathlib.Path, "unlink", refuse)
    world["fail"] = {"stale"}
    ticket_sweeper.run_sweep(now=NOW)
    monkeypatch.setattr(ticket_sweeper, "_unsaved_run_at", None)  # a fresh process
    snap = ticket_sweeper.status_snapshot()
    assert snap["complete"] is False and snap["errors"] == ["state_write_failed"]
