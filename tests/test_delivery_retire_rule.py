"""RA-8100 B5f: a stored record or alert is retired only by a WHOLE read of its own subject.

The class test generates every way one subject's read can be not whole (a budget or clock cut at each
request, an HTTP error, a 404 or a malformed answer on each read, links not whole) for three subjects
that each hold a stored founder or critical alert. After that tick the alert must still be stored AND
still be on the tile, whatever ``complete`` says. The control rows read the subject whole with an
answer that no longer supports the alert: then, and only then, it is retired.
"""
from __future__ import annotations

import functools
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    compare_answer,
    HTTP404, NOW, PIDEV, SHA_A, SHA_B, ago, linear_page, merged_paths, merged_pull, open_pull, pr_paths, reg_entry,
    run, setup_tick, sweep_path, tick_issue,
)

from app.server import delivery_collect as collect
from app.server import delivery_reconcile as dr

OWN = "d" * 40
LATER = NOW + timedelta(minutes=10)


class HTTP500(Exception):
    code = 500


def _evidence_reads(number: int) -> list[str]:
    base = f"/repos/{PIDEV}"
    return [f"{base}/pulls/{number}", f"{base}/commits/{SHA_A}",
            f"{base}/commits/{SHA_A}/check-runs?per_page=100&page=1", f"{base}/commits/{SHA_A}/status",
            f"{base}/pulls/{number}/reviews?per_page=100&page=1"]


# Each world: the reads of its subject's second tick, in request order (the sweep is always first).
READS = {
    "done": [sweep_path(PIDEV), *_evidence_reads(7)],
    "merged": [sweep_path(PIDEV), f"/repos/{PIDEV}/pulls/4", f"/repos/{PIDEV}/commits/{SHA_B}",
               f"/repos/{PIDEV}/compare/{SHA_B}...{OWN}"],
    "orphan": [sweep_path(PIDEV), *_evidence_reads(9)],
}
SUBJECT = {"done": ("RA-1", "FALSE_DONE"), "merged": ("RA-4", "DEPLOY_UNVERIFIED_24H"),
           "orphan": (f"{PIDEV}#9", "UNOWNED_24H")}


def _state(st: SimpleNamespace) -> dict:
    return json.loads(Path(st.path).read_text(encoding="utf-8"))


def _shown(now, st: SimpleNamespace) -> set[tuple]:  # type: ignore[no-untyped-def]
    return {(i["ref"], i["code"]) for i in dr.status_snapshot(st.path, now)["items"]}


def _issues(world: str, links_whole: bool = True) -> list[dict]:
    if world == "done":
        return [tick_issue("RA-1", ((PIDEV, 7),), state="completed", completed=0.5, links_whole=links_whole)]
    if world == "merged":
        return [tick_issue("RA-4", ((PIDEV, 4),), links_whole=links_whole)]
    return [tick_issue("RA-77", ((PIDEV, 9),), links_whole=links_whole)]


def _world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, world: str) -> SimpleNamespace:
    """Tick 1 stores the subject's founder or critical alert; the fakes are then set for a whole tick 2."""
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    if world == "done":
        st.gh.update(pr_paths(PIDEV, 7))
        st.gh[sweep_path(PIDEV)] = [open_pull(7)]
    elif world == "merged":
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", OWN)
        st.gh.update(merged_paths(PIDEV, 4))
        st.gh[f"/repos/{PIDEV}/compare/{SHA_B}...{OWN}"] = compare_answer(SHA_B, OWN, "behind")
        st.gh[sweep_path(PIDEV)] = []
    else:
        st.gh.update(pr_paths(PIDEV, 9))
        st.gh[sweep_path(PIDEV)] = [{**open_pull(9), "created_at": ago(72)}]
    st.gql_pages.append(linear_page(_issues(world) if world != "orphan" else []))
    run(st)
    ref, code = SUBJECT[world]
    assert (ref, code) in _shown(NOW, st)  # positive control: the alert exists and is shown
    st.gql_pages.append(linear_page(_issues(world)))
    return st


def _break(monkeypatch: pytest.MonkeyPatch, st: SimpleNamespace, world: str, how: str, i: int | None) -> None:
    """Make read ``i`` of tick 2 not whole, the ``how`` way."""
    if how == "links":
        st.gql_pages[-1] = linear_page(_issues(world, links_whole=False))
        return
    path = READS[world][i]
    if how in ("http", "missing", "malformed"):
        st.gh[path] = {"http": HTTP500(), "missing": HTTP404(), "malformed": "garbage"}[how]
    elif how == "budget":
        monkeypatch.setitem(collect.BUDGETS, "github", i)
    else:  # clock: the read clock runs out after the Linear page and ``i`` GitHub reads
        base = len(st.gql) + len(st.github)
        limit = i + 1
        clock = lambda: 0.0 if len(st.gql) + len(st.github) - base < limit else 1000.0  # noqa: E731
        monkeypatch.setattr(collect, "Tick", functools.partial(collect.Tick, clock=clock))


def _rows() -> list:
    rows = []
    for world, reads in READS.items():
        for i in range(len(reads)):
            for how in ("budget", "clock", "http", "malformed"):
                rows.append(pytest.param(world, how, i, id=f"{world}-{how}-read{i}"))
        rows.append(pytest.param(world, "links", None, id=f"{world}-links_not_whole"))
    rows.append(pytest.param("done", "missing", 2, id="done-missing-head_commit_404"))
    rows.append(pytest.param("merged", "missing", 2, id="merged-missing-merge_commit_404"))
    return rows


@pytest.mark.parametrize("world,how,i", _rows())
def test_a_subject_not_read_whole_keeps_and_shows_its_stored_alert(monkeypatch: pytest.MonkeyPatch,
                                                                  tmp_path: Path, world: str, how: str,
                                                                  i: int | None) -> None:
    st = _world(monkeypatch, tmp_path, world)
    before = {k: a for k, a in _state(st)["alerts"].items() if a["severity"] in ("founder", "critical")}
    assert before
    _break(monkeypatch, st, world, how, i)
    out = run(st, LATER)
    rid = "RA-1" if world == "done" else "RA-4" if world == "merged" else f"pr:{PIDEV}#9"
    assert out["complete"] is False or rid in out["not_refreshed_ids"], "the break did not land"
    state, tile = _state(st), dr.status_snapshot(st.path, LATER)
    shown = {(it["ref"], it["code"]) for it in tile["items"]}
    for key, alert in before.items():
        assert key in state["alerts"], (world, how, i)
        assert (alert["ref"], alert["code"]) in shown, (world, how, i)
        assert tile["counts"]["by_code"].get(alert["code"], 0) >= 1


def _whole_but_retired(st: SimpleNamespace, world: str) -> None:
    if world == "done":
        st.gh[f"/repos/{PIDEV}/pulls/7"] = merged_pull(7)
        st.gh[f"/repos/{PIDEV}/commits/{SHA_B}"] = {"sha": SHA_B}
    elif world == "merged":
        st.gh[f"/repos/{PIDEV}/compare/{SHA_B}...{OWN}"] = compare_answer(SHA_B, OWN, "identical")


@pytest.mark.parametrize("world", list(READS))
def test_control_a_whole_read_that_no_longer_supports_the_alert_retires_it(monkeypatch: pytest.MonkeyPatch,
                                                                         tmp_path: Path, world: str) -> None:
    """Without this the class test passes for a store that never retires anything."""
    st = _world(monkeypatch, tmp_path, world)
    _whole_but_retired(st, world)
    out = run(st, LATER)
    ref, code = SUBJECT[world]
    assert out["complete"] is True and out["not_refreshed_ids"] == []
    assert not [a for a in _state(st)["alerts"].values() if a["code"] == code]
    assert (ref, code) not in _shown(LATER, st)


def test_a_retired_alert_is_not_shown_again_when_a_later_read_fails(monkeypatch: pytest.MonkeyPatch,
                                                                   tmp_path: Path) -> None:
    st = _world(monkeypatch, tmp_path, "done")
    _whole_but_retired(st, "done")
    run(st, LATER)
    st.gh[f"/repos/{PIDEV}/pulls/7"] = HTTP500()
    st.gql_pages.append(linear_page(_issues("done")))
    third = LATER + timedelta(minutes=10)
    run(st, third)
    assert ("RA-1", "FALSE_DONE") not in _shown(third, st)
    assert not [a for a in _state(st)["alerts"].values() if a["code"] == "FALSE_DONE"]


# ── P1-1: a new mission cut by the budget may own a stored orphan: the orphan and its alerts stay ──
def test_p1_1_new_mission_cut_by_budget_keeps_the_orphan_it_claims(monkeypatch: pytest.MonkeyPatch,
                                                                  tmp_path: Path) -> None:
    st = _world(monkeypatch, tmp_path, "orphan")
    orphan = f"pr:{PIDEV}#9"
    alerts = {k for k, a in _state(st)["alerts"].items() if a["mission_id"] == orphan}
    monkeypatch.setitem(collect.BUDGETS, "github", 1)  # the sweep only
    out = run(st, LATER)
    state = _state(st)
    assert out["complete"] is True  # spec line 112: a per-mission cut does not make the tick incomplete
    assert "RA-77" in out["not_refreshed_ids"] and orphan in out["not_refreshed_ids"]
    assert orphan in state["missions"] and alerts <= set(state["alerts"])
    assert (f"{PIDEV}#9", "UNOWNED_24H") in _shown(LATER, st)


def test_p1_1_other_unclaimed_orphans_are_still_classified(monkeypatch: pytest.MonkeyPatch,
                                                          tmp_path: Path) -> None:
    """Only the orphan the cut mission claims is protected; a new unlinked PR is still found."""
    st = _world(monkeypatch, tmp_path, "orphan")
    st.gh[sweep_path(PIDEV)] = [{**open_pull(9), "created_at": ago(72)}, {**open_pull(11), "created_at": ago(72)}]
    monkeypatch.setitem(collect.BUDGETS, "github", 1)
    run(st, LATER)
    assert f"pr:{PIDEV}#11" in _state(st)["missions"]


# ── P1-2: a failed read of a mission makes its record UNKNOWN and keeps its stored alert on the tile ──
@pytest.mark.parametrize("variant", ["pull_http_500", "attachments_not_whole"])
def test_p1_2_failed_read_keeps_false_done_on_the_tile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                      variant: str) -> None:
    st = _world(monkeypatch, tmp_path, "done")
    stored = _state(st)["missions"]["RA-1"]
    _break(monkeypatch, st, "done", "http" if variant == "pull_http_500" else "links", 1)
    out = run(st, LATER)
    state, shown = _state(st), _shown(LATER, st)
    assert out["complete"] is True and "RA-1" in out["not_refreshed_ids"]
    assert ("RA-1", "FALSE_DONE") in shown
    assert any(a["code"] == "FALSE_DONE" for a in state["alerts"].values())
    assert any(a["code"] == "EVIDENCE_UNKNOWN" and a["last_seen"] == state["last_tick"]
               for a in state["alerts"].values())
    record = state["missions"]["RA-1"]  # spec row 1: UNKNOWN with the failed read's reason; first_seen kept
    assert stored["stage"] == "done" and record["stage"] == "unknown"
    assert record["reason"] == ("http_500" if variant == "pull_http_500" else "links_incomplete")
    assert record["first_seen"] == stored["first_seen"]


# ── P1-3: a contradictory pull answer is malformed, so the record is kept, not counted away ──
def test_p1_3_closed_unmerged_pull_with_a_merge_time_keeps_the_record(monkeypatch: pytest.MonkeyPatch,
                                                                      tmp_path: Path) -> None:
    st = _world(monkeypatch, tmp_path, "done")
    st.gh[f"/repos/{PIDEV}/pulls/7"] = {**open_pull(7), "state": "closed", "merged": False,
                                       "merged_at": ago(0.1), "merge_commit_sha": SHA_B}
    st.gh[sweep_path(PIDEV)] = []
    out = run(st, LATER)
    state = _state(st)
    assert out["closed_unmerged"] == 0 and "RA-1" in state["missions"]
    assert ("RA-1", "FALSE_DONE") in _shown(LATER, st)


# ── Whole reads still retire: scope changes, whole-read verdicts, and read order keeps rotating ──
def test_an_orphan_whose_repo_left_the_registry_is_dropped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _world(monkeypatch, tmp_path, "orphan")
    other = "CleanExpo/ATO"
    st2 = setup_tick(monkeypatch, tmp_path, [reg_entry("ato", other)])  # same state file, Pi-Dev-Ops removed
    st2.gh[sweep_path(other)] = []
    st2.gql_pages.append(linear_page([]))
    out = run(st2, LATER)
    state = _state(st2)
    assert out["complete"] is True and f"pr:{PIDEV}#9" not in out["not_refreshed_ids"]
    assert f"pr:{PIDEV}#9" not in state["missions"]
    assert not [a for a in state["alerts"].values() if a["mission_id"] == f"pr:{PIDEV}#9"]


def test_a_whole_read_with_no_ci_still_retires_the_orphan_it_claims(monkeypatch: pytest.MonkeyPatch,
                                                                   tmp_path: Path) -> None:
    st = _world(monkeypatch, tmp_path, "orphan")
    st.gh[f"/repos/{PIDEV}/commits/{SHA_A}/check-runs?per_page=100&page=1"] = {"total_count": 0, "check_runs": []}
    st.gh[f"/repos/{PIDEV}/commits/{SHA_A}/status"] = {"state": "pending", "total_count": 0, "sha": SHA_A}
    out = run(st, LATER)
    state = _state(st)
    assert state["missions"]["RA-77"]["reason"] == "no_ci" and out["not_refreshed_ids"] == []
    assert f"pr:{PIDEV}#9" not in state["missions"]
    assert (f"{PIDEV}#9", "UNOWNED_24H") not in _shown(LATER, st)


def test_a_mission_whose_read_keeps_failing_does_not_starve_the_others(monkeypatch: pytest.MonkeyPatch,
                                                                      tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    st.gh.update({**pr_paths(PIDEV, 7), **pr_paths(PIDEV, 8)})
    st.gh[f"/repos/{PIDEV}/pulls/7"] = HTTP500()
    st.gh[sweep_path(PIDEV)] = [open_pull(7), open_pull(8)]
    page = linear_page([tick_issue("RA-1", ((PIDEV, 7),)), tick_issue("RA-2", ((PIDEV, 8),))])
    st.gql_pages += [page] * 3
    run(st)
    monkeypatch.setitem(collect.BUDGETS, "github", 6)  # the sweep, RA-1's failing read, and four of RA-2's five
    run(st, LATER)
    third = LATER + timedelta(minutes=10)
    run(st, third)
    assert _state(st)["missions"]["RA-2"]["refreshed_at"] == third.timestamp()
