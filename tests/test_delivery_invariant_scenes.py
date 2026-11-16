"""RA-8100 D55: no real tick builds a state its own rules refuse, across every stage and every change of stage.

``save`` refuses a state that breaks a row of ``delivery_invariants.STATE``, so a rule that a real tick can
break would stop the reconcile from ever saving again. The rows about a record's stage, its pulls and its
alerts are the ones at risk, so every scene below puts mission RA-1 at one stage through the real readers
and the real classifier. Then: every scene after every other scene (the record changes stage on top of what
the earlier tick stored), and every scene again under each way a tick can be cut short, with a later clock
and a clock that went back. Each tick must be saved and the saved file must load.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    ATO, FAKE_REVIEWER, NOW, PIDEV, SHA_A, SHA_B, SHA_C, ago, compare_answer, linear_page, merged_paths, open_pull,
    pr_paths, reg_entry, run, setup_tick, sweep_path, tick_issue,
)

from app.server import delivery_collect as collect
from app.server import delivery_reconcile_schema as schema
from app.server import delivery_reconcile_status as status
from app.server import delivery_reconcile_store as store
from app.server import delivery_reconcile_tick as tick

RA, LIVE = "CleanExpo/RestoreAssist", "d" * 40
P5, COMPARE = f"/repos/{PIDEV}/pulls/5", f"/repos/{PIDEV}/compare/{SHA_B}...{LIVE}"
RUNS = f"/repos/{PIDEV}/commits/{SHA_A}/check-runs?per_page=100&page=1"
REVIEWS = f"/repos/{PIDEV}/pulls/5/reviews?per_page=100&page=1"
LINKED = [tick_issue("RA-1", ((PIDEV, 5),))]


def _approval(commit: str) -> dict:
    return {"id": 1, "user": {"login": FAKE_REVIEWER, "type": "User"}, "state": "APPROVED", "commit_id": commit,
            "submitted_at": ago(2)}


def _open(st: SimpleNamespace, *, runs: list | None = None, reviews: tuple = (), issues: list | None = None,
          **pull: object) -> tuple[list, list]:
    """Mission RA-1 links open pull 5: green checks and no review unless said otherwise."""
    st.gh.update(pr_paths(PIDEV, 5))
    st.gh[sweep_path(PIDEV)] = [open_pull(5), open_pull(9)]
    st.gh[P5] = {**st.gh[P5], **pull}
    st.gh[REVIEWS] = list(reviews)
    if runs is not None:
        st.gh[RUNS] = {"total_count": len(runs), "check_runs": runs}
    return (LINKED if issues is None else issues), []


def _merged(st: SimpleNamespace, compare: object) -> tuple[list, list]:
    st.gh.update(merged_paths(PIDEV, 5, SHA_B))
    st.gh[COMPARE] = compare
    return LINKED, []


def _two_open(st: SimpleNamespace) -> tuple[list, list]:
    _open(st)
    st.gh.update(pr_paths(PIDEV, 6, SHA_C))
    return [tick_issue("RA-1", ((PIDEV, 5), (PIDEV, 6)))], []


def _elsewhere(st: SimpleNamespace) -> tuple[list, list]:
    st.gh.update(merged_paths(RA, 6))
    return [], [tick_issue("RA-2", ((RA, 6),))]


def _failed(st: SimpleNamespace) -> tuple[list, list]:
    st.gh[P5] = RuntimeError("down")
    return LINKED, []


RED = [{"id": 1, "status": "completed", "conclusion": "failure", "completed_at": ago(72), "head_sha": SHA_A}]
DONE = [tick_issue("RA-1", ((PIDEV, 5),), state="completed", started=50, completed=1)]
# scene -> (how the outside world looks, the stage RA-1 is stored at; None: no record of it)
SCENES: dict[str, tuple[Callable[[SimpleNamespace], tuple[list, list]], str | None]] = {
    "review_wait": (_open, "review_wait"),
    "stale_approval": (lambda st: _open(st, reviews=(_approval(SHA_C),)), "review_wait"),
    "approval_wait": (lambda st: _open(st, reviews=(_approval(SHA_A),)), "approval_wait"),
    "red_checks": (lambda st: _open(st, runs=RED, reviews=(_approval(SHA_A),)), "building"),
    "draft": (lambda st: _open(st, draft=True), "building"),
    "done": (lambda st: _open(st, issues=DONE), "done"),
    "no_ci": (lambda st: _open(st, runs=[]), "unknown"),
    "no_head": (lambda st: _open(st, head=None), "missing_commit"),
    "two_open": (_two_open, "unknown"),
    "pull_read_fails": (_failed, "unknown"),
    "merged_verified": (lambda st: _merged(st, compare_answer(SHA_B, LIVE, "ahead")), "merged"),
    "merged_behind": (lambda st: _merged(st, compare_answer(SHA_B, LIVE, "behind")), "merged"),  # not verified
    "merged_compare_fails": (lambda st: _merged(st, RuntimeError("down")), "unknown"),
    "no_pull": (lambda st: ([tick_issue("RA-1")], []), None),
    "left_the_list": (lambda st: ([], []), None),
    "merged_in_another_repo": (_elsewhere, None),
}


def _world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    entries = [reg_entry("pi-dev-ops", PIDEV), reg_entry("ato", ATO), reg_entry("ra", RA, vercel="prj_fake")]
    st = setup_tick(monkeypatch, tmp_path, entries)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", LIVE)
    monkeypatch.setenv("TAO_DELIVERY_HUMAN_REVIEWERS", FAKE_REVIEWER)
    st.vc["*"] = {"deployments": [{"state": "READY", "created": 5, "target": "production",
                                   "meta": {"githubCommitSha": SHA_B}}]}
    return st


def _scene(st: SimpleNamespace, name: str) -> None:
    """Replace the outside world by scene ``name``: an open orphan pull 9, and RA-1 as the scene says."""
    st.gh.clear()
    st.gh.update({sweep_path(PIDEV): [open_pull(9)], sweep_path(ATO): [], sweep_path(RA): []})
    issues, elsewhere = SCENES[name][0](st)
    st.gql_pages[:] = [linear_page(issues), linear_page([]), linear_page(elsewhere)]


def _saved_and_whole(st: SimpleNamespace, out: dict) -> dict:
    assert out["persisted"] is True, out  # the writer never builds a state its own rules refuse
    state = store.load(st.path)
    assert schema.problems(state) == []
    return state


@pytest.mark.parametrize("scene", sorted(SCENES))
def test_the_scene_puts_the_mission_at_its_stage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, scene: str) -> None:
    """The control: each scene really reaches the stage it is named for, so the tests below cover that stage."""
    st = _world(monkeypatch, tmp_path)
    _scene(st, scene)
    record = _saved_and_whole(st, run(st))["missions"].get("RA-1")
    assert (record and record["stage"]) == SCENES[scene][1], record
    assert {s for _, s in SCENES.values()} == {None, "building", "review_wait", "approval_wait", "done", "merged",
                                               "unknown", "missing_commit"}  # every stage the schema allows


@pytest.mark.parametrize("after", sorted(SCENES))
@pytest.mark.parametrize("before", sorted(SCENES))
def test_every_change_of_stage_is_saved_and_loads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, before: str,
                                                  after: str) -> None:
    st = _world(monkeypatch, tmp_path)
    _scene(st, before)
    _saved_and_whole(st, run(st))
    for step, name in enumerate((after, after, before), 1):  # the change, the same again, and back
        _scene(st, name)
        _saved_and_whole(st, run(st, NOW + timedelta(minutes=15 * step)))


def _clock_spent(mp: pytest.MonkeyPatch, st: SimpleNamespace) -> None:
    mp.setattr(collect, "READ_SECONDS", -1.0)


def _cut_after(reads: int) -> Callable[[pytest.MonkeyPatch, SimpleNamespace], None]:
    def cut(mp: pytest.MonkeyPatch, st: SimpleNamespace) -> None:
        real, spent = collect.Tick.spend, [0]

        def spend(self: collect.Tick, kind: str) -> object:
            spent[0] += 1
            if spent[0] > reads:
                raise collect.BudgetExhausted("clock")
            return real(self, kind)

        mp.setattr(collect.Tick, "spend", spend)
    return cut


CUTS: dict[str, Callable[[pytest.MonkeyPatch, SimpleNamespace], None]] = {
    "clock_spent": _clock_spent, "cut_after_2_reads": _cut_after(2), "cut_after_5_reads": _cut_after(5),
    "cut_after_8_reads": _cut_after(8), "github_budget_2": lambda mp, st: mp.setitem(collect.BUDGETS, "github", 2),
    "no_linear_key": lambda mp, st: mp.setattr(tick, "_api_key", lambda: ""),
    "vercel_down": lambda mp, st: st.vc.update({"*": RuntimeError("down")}),
    "linear_down": lambda mp, st: st.gql_pages.__setitem__(0, RuntimeError("down")),
    "sweep_down": lambda mp, st: st.gh.update({sweep_path(PIDEV): RuntimeError("down")}),
}


@pytest.mark.parametrize("when", [timedelta(minutes=15), timedelta(hours=-1)], ids=["later", "clock_went_back"])
@pytest.mark.parametrize("cut", sorted(CUTS))
@pytest.mark.parametrize("scene", sorted(SCENES))
def test_every_scene_cut_short_is_saved_and_loads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, scene: str,
                                                  cut: str, when: timedelta) -> None:
    st = _world(monkeypatch, tmp_path)
    _scene(st, scene)
    _saved_and_whole(st, run(st))
    _scene(st, scene)
    with pytest.MonkeyPatch.context() as mp:
        CUTS[cut](mp, st)
        _saved_and_whole(st, run(st, NOW + when))
    _scene(st, scene)  # and the next whole tick still saves on top of the cut one
    _saved_and_whole(st, run(st, NOW + timedelta(minutes=30)))
    assert status.build(st.path, NOW + timedelta(minutes=30), True, True)["state"] == "ok"
