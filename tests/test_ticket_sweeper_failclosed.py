"""tests/test_ticket_sweeper_failclosed.py — ticket sweeper (audit #17): fail closed.

Every partial read, malformed payload or failed write must leave the run
marked incomplete and the ticket untouched — never a clean zero on the tile.
"""
from __future__ import annotations

from _ticket_sweeper_support import FAILED, GRANT, NOW, PR, _issue, _pr, world  # noqa: F401 — fixture
from app.server import autonomy, ticket_sweeper, ticket_sweeper_io, ticket_sweeper_write


def test_truncated_comments_or_relations_fail_closed(world, monkeypatch):  # noqa: F811
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


def test_malformed_nodes_fail_closed(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    stale = _issue("UNI-30")
    del stale["inverseRelations"]["nodes"]
    todo = _issue("RA-30", "Todo", stype="unstarted", comments=[FAILED])
    del todo["comments"]["nodes"]
    world["stale"], world["recent_todo"] = [stale], [todo]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.stale_labelled == ["UNI-30"] and report.stale_to_todo == []
    assert "comments_unread:RA-30" in report.errors and report.complete is False
    assert not [w for w in world["writes"] if w[0] == "state"]


def test_null_issue_node_rejects_the_bucket(world):  # noqa: F811
    world["in_review"] = [None]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.complete is False and any(e.startswith("fetch_failed:in_review") for e in report.errors)


def test_label_write_reporting_success_but_not_persisted_blocks_the_move(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    monkeypatch.setattr(ticket_sweeper_write, "add_label", lambda *a: True)  # says ok, writes nothing
    world["recent_todo"] = [_issue("RA-31", "Todo", stype="unstarted", comments=[FAILED])]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert not [w for w in world["writes"] if w[0] in ("state", "comment")]
    assert report.errors == ["label_unconfirmed:RA-31"]


def test_sweep_crash_persists_incomplete(world, monkeypatch):  # noqa: F811
    def boom(*a, **k):
        raise AttributeError("boom")
    monkeypatch.setattr(ticket_sweeper_io, "fetch_buckets", boom)
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.errors == ["sweep_crashed:AttributeError"]
    assert ticket_sweeper.status_snapshot()["complete"] is False


def test_red_check_run_on_second_page_counts(world):  # noqa: F811
    world["in_review"] = [_issue("RA-32", "In Review", pr=PR)]
    prs = _pr(35, reviewed=True)
    runs = "/repos/CleanExpo/ATO/commits/sha35/check-runs"
    del prs[runs]
    world["prs"] = {
        runs + "?per_page=100&page=2": {"total_count": 101, "check_runs": [{"conclusion": "failure"}]},
        runs + "?per_page=100&page=1": {"total_count": 101, "check_runs": [{"conclusion": "success"}] * 100},
        **prs,
    }
    assert ticket_sweeper.run_sweep(now=NOW).review_red_pr == ["RA-32"]


def test_open_pr_without_head_sha_is_unknown(world):  # noqa: F811
    world["in_review"] = [_issue("RA-33", "In Review", pr=PR)]
    prs = _pr(35, reviewed=True)
    prs["/repos/CleanExpo/ATO/pulls/35"]["head"] = {}
    world["prs"] = prs
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.review_unknown == ["RA-33"] and report.review_red_pr == []


def test_malformed_issue_page_is_incomplete_not_zero(world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(autonomy, "_gql", lambda *a, **k: {"project": {"issues": {}}})
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.complete is False and len(report.errors) == 3


def test_failed_fetch_marks_run_incomplete(world):  # noqa: F811
    world["fail"] = {"stale"}
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.complete is False
    assert any(e.startswith("fetch_failed:stale") for e in report.errors)


def test_no_api_key_records_error_and_fetches_nothing(world, monkeypatch):  # noqa: F811
    monkeypatch.delenv("LINEAR_API_KEY")
    monkeypatch.setattr(ticket_sweeper.config, "LINEAR_API_KEY", "", raising=False)
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.errors == ["no_linear_api_key"] and report.complete is False


def test_failed_retry_label_write_blocks_the_move(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["label_ok"] = False
    world["recent_todo"] = [_issue("RA-10", "Todo", stype="unstarted", comments=[FAILED])]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert not [w for w in world["writes"] if w[0] == "state"]
    assert report.errors == ["label_unconfirmed:RA-10"] and report.complete is False


def test_too_many_pages_is_incomplete_not_short(world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ticket_sweeper_io, "_MAX_PAGES", 1)
    world["pages"]["stale"] = [[_issue("UNI-1")], [_issue("UNI-2")]]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.complete is False and any("OverflowError" in e for e in report.errors)


def test_missing_project_is_incomplete_not_zero(world):  # noqa: F811
    world["null_project"] = {"stale", "in_review", "recent_todo"}
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.complete is False and len(report.errors) == 3
    assert ticket_sweeper.status_snapshot()["complete"] is False


def test_ticket_moved_to_in_review_mid_write_is_not_moved(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["stale"] = [_issue("RA-40")]
    world["on_label"] = lambda issue: issue["state"].update(name="In Review")
    report = ticket_sweeper.run_sweep(now=NOW)
    assert not [w for w in world["writes"] if w[0] == "state"]
    assert "drift:RA-40" in report.errors and report.complete is False


def test_lost_grant_comment_blocks_the_move(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["comment_ok"] = False
    world["recent_todo"] = [_issue("RA-41", "Todo", stype="unstarted", comments=[FAILED])]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert not [w for w in world["writes"] if w[0] == "state"]
    assert report.errors == ["comment_unconfirmed:RA-41"]


def test_unpersisted_transition_is_an_error(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["state_ok"] = False
    world["recent_todo"] = [_issue("RA-42", "Todo", stype="unstarted", comments=[FAILED])]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.errors == ["state_unconfirmed:RA-42"] and report.complete is False


def test_empty_project_registry_is_incomplete(world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(autonomy, "_load_portfolio_projects", lambda: [])
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.errors == ["no_portfolio_projects"] and report.complete is False


def test_truncated_attachments_or_labels_fail_closed(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    stale = _issue("RA-43")
    stale["attachments"]["pageInfo"]["hasNextPage"] = True  # a PR could be attachment 101
    todo = _issue("RA-44", "Todo", stype="unstarted", comments=[FAILED])
    todo["labels"]["pageInfo"]["hasNextPage"] = True  # the retry label could be label 101
    review = _issue("RA-45", "In Review")
    review["attachments"]["pageInfo"]["hasNextPage"] = True
    world["stale"], world["recent_todo"], world["in_review"] = [stale], [todo], [review]
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.stale_labelled == ["RA-43"] and report.stale_to_todo == []
    assert "comments_unread:RA-44" in report.errors and report.failed_to_ready == []
    assert report.review_unknown == ["RA-45"]
    assert not [w for w in world["writes"] if w[0] == "state"]


def test_retry_label_removed_mid_block_is_not_moved(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["recent_todo"] = [_issue("RA-50", "Todo", stype="unstarted", comments=[FAILED, GRANT, FAILED],
                                   labels=["pi-dev:failed-retry-used"])]
    world["on_comment"] = lambda issue: issue["labels"]["nodes"].remove({"name": "pi-dev:failed-retry-used"})
    report = ticket_sweeper.run_sweep(now=NOW)  # a human revoked the retry while we were writing
    assert not [w for w in world["writes"] if w[0] == "state"]
    assert report.errors == ["drift:RA-50"] and report.complete is False


def test_label_write_that_drops_an_existing_label_is_an_error(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["recent_todo"] = [_issue("RA-51", "Todo", stype="unstarted", comments=[FAILED], labels=["keep-me"])]
    world["on_label"] = lambda issue: issue["labels"]["nodes"].clear()  # a replace-style write
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.errors == ["label_unconfirmed:RA-51"]
    assert not [w for w in world["writes"] if w[0] in ("comment", "state")]


def test_add_label_adds_one_label_and_checks_success(monkeypatch):
    sent = []
    monkeypatch.setattr(autonomy, "_resolve_or_create_label", lambda k, team, name: "lbl-1")

    def fake_gql(api_key, query, variables=None, **kw):
        sent.append((query, variables))
        return {"issueAddLabel": {"success": ok}}
    monkeypatch.setattr(autonomy, "_gql", fake_gql)
    ok = True
    assert ticket_sweeper_write.add_label("k", "iss-1", "team", "stale:14d") is True
    ok = False
    assert ticket_sweeper_write.add_label("k", "iss-1", "team", "stale:14d") is False
    assert all("issueAddLabel" in q and "labelIds" not in q for q, _ in sent)
    assert sent[0][1] == {"id": "iss-1", "labelId": "lbl-1"}


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


def test_human_comment_during_the_sweep_stops_the_move(world, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TAO_TICKET_SWEEPER_WRITE", "1")
    world["stale"] = [_issue("RA-62")]
    world["on_comment"] = lambda issue: issue["comments"]["nodes"].append(
        {"body": "still on it", "createdAt": "2026-09-30T01:00:00Z"})
    report = ticket_sweeper.run_sweep(now=NOW)
    assert report.errors == ["drift:RA-62"]
    assert not [w for w in world["writes"] if w[0] == "state"]


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

