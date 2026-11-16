"""RA-8100 B5g: whether a mission was read whole comes only from its READS, never from its verdict.

The class test crosses every failed-read kind with every link shape (one pull; two pulls with the
first, the second or both failing; the same pull linked twice in different letter case). Each row
starts from a stored founder or critical alert. After the failed tick the mission must be held, its
alert still stored and still on the tile, and its record never healthy. Cells that cannot exist are
listed in ``SKIPPED`` and the row count is asserted, so a lost row fails.
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
    HTTP404, NOW, PIDEV, SHA_A, SHA_B, SHA_C, linear_page, merged_paths, open_pull, pr_paths, reg_entry, run,
    setup_tick, sweep_path, tick_issue,
)

from app.server import delivery_collect as collect
from app.server import delivery_reconcile as dr

OWN = "d" * 40
SHA_E = "e" * 40
LATER = NOW + timedelta(minutes=10)
LOWER = PIDEV.lower()
HEALTHY = {"building", "review_wait", "approval_wait", "merged", "done", "deploying", "verified"}


class HTTP500(Exception):
    code = 500


# world -> (mission, alert code, first pull (number, commit), second pull (number, commit))
WORLDS = {"done": ("RA-1", "FALSE_DONE", (7, SHA_A), (8, SHA_C)),
          "merged": ("RA-4", "DEPLOY_UNVERIFIED_24H", (4, SHA_B), (5, SHA_E))}
KINDS = ("http_500", "head_404", "merge_404", "malformed", "compare_failed", "clock_mid_read")
SHAPES = ("one", "first_fails", "second_fails", "both_fail", "same_pull_two_cases")
# A merged pull never reads its head commit; an open pull has no merge commit and no compare.
SKIPPED = {("done", "merge_404"), ("done", "compare_failed"), ("merged", "head_404")}


def _state(st: SimpleNamespace) -> dict:
    return json.loads(Path(st.path).read_text(encoding="utf-8"))


def _refs(world: str, shape: str) -> tuple:
    first, second = WORLDS[world][2][0], WORLDS[world][3][0]
    return {"one": ((PIDEV, first),), "first_fails": ((PIDEV, first), (PIDEV, second)),
            "second_fails": ((PIDEV, second), (PIDEV, first)), "both_fail": ((PIDEV, first), (PIDEV, second)),
            "same_pull_two_cases": ((PIDEV, first), (LOWER, first))}[shape]


def _issue(world: str, refs: tuple) -> dict:
    if world == "done":
        return tick_issue("RA-1", refs, state="completed", completed=0.5)
    return tick_issue("RA-4", refs)


def _world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, world: str) -> SimpleNamespace:
    """Tick 1 stores the mission's alert from one whole pull; both pulls then answer whole."""
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    (n1, c1), (n2, c2) = WORLDS[world][2], WORLDS[world][3]
    if world == "done":
        st.gh.update({**pr_paths(PIDEV, n1, c1), **pr_paths(PIDEV, n2, c2)})
        st.gh[sweep_path(PIDEV)] = [open_pull(n1, c1), open_pull(n2, c2)]
    else:
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", OWN)
        st.gh.update({**merged_paths(PIDEV, n1, c1), **merged_paths(PIDEV, n2, c2, 40)})
        for sha in (c1, c2):
            st.gh[f"/repos/{PIDEV}/compare/{sha}...{OWN}"] = compare_answer(sha, OWN, "behind")
        st.gh[sweep_path(PIDEV)] = []
    st.gql_pages.append(linear_page([_issue(world, ((PIDEV, n1),))]))
    run(st)
    assert (WORLDS[world][0], WORLDS[world][1]) in _shown(st, NOW)  # positive control: the alert exists
    return st


def _shown(st: SimpleNamespace, now) -> set[tuple]:  # type: ignore[no-untyped-def]
    return {(i["ref"], i["code"]) for i in dr.status_snapshot(st.path, now)["items"]}


def _fail(monkeypatch: pytest.MonkeyPatch, st: SimpleNamespace, kind: str, number: int, sha: str) -> None:
    """Make pull ``number`` (commit ``sha``) fail to read, the ``kind`` way."""
    base = f"/repos/{PIDEV}"
    if kind in ("http_500", "malformed"):
        st.gh[f"{base}/pulls/{number}"] = HTTP500() if kind == "http_500" else "garbage"
    elif kind in ("head_404", "merge_404"):
        st.gh[f"{base}/commits/{sha}"] = HTTP404()
    elif kind == "compare_failed":
        st.gh[f"{base}/compare/{sha}...{OWN}"] = HTTP500()
    else:  # the clock runs out right after this pull's first read: a cut in the middle of the mission
        start, path = len(st.github), f"{base}/pulls/{number}"
        clock = lambda: 1000.0 if path in st.github[start:] else 0.0  # noqa: E731
        monkeypatch.setattr(collect, "Tick", functools.partial(collect.Tick, clock=clock))


def _rows() -> list:
    rows = [pytest.param(w, k, s, id=f"{w}-{k}-{s}") for w in WORLDS for k in KINDS for s in SHAPES
            if (w, k) not in SKIPPED]
    assert len(rows) == (len(WORLDS) * len(KINDS) - len(SKIPPED)) * len(SHAPES) == 45
    return rows


@pytest.mark.parametrize("world,kind,shape", _rows())
def test_a_failed_read_holds_the_mission_whatever_the_link_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                                  world: str, kind: str, shape: str) -> None:
    st = _world(monkeypatch, tmp_path, world)
    rid, code, first, second = WORLDS[world]
    before = {k: a for k, a in _state(st)["alerts"].items() if a["severity"] in ("founder", "critical")}
    assert before
    failing = [first, second] if shape == "both_fail" else [first]
    for number, sha in failing:
        _fail(monkeypatch, st, kind, number, sha)
    st.gql_pages.append(linear_page([_issue(world, _refs(world, shape))]))
    out = run(st, LATER)
    state, tile = _state(st), dr.status_snapshot(st.path, LATER)
    shown = {(i["ref"], i["code"]) for i in tile["items"]}
    assert rid in out["not_refreshed_ids"], (world, kind, shape)
    for key, alert in before.items():
        assert key in state["alerts"], (world, kind, shape)
        assert (alert["ref"], alert["code"]) in shown, (world, kind, shape)
        assert tile["counts"]["by_code"].get(alert["code"], 0) >= 1
    assert state["missions"][rid]["stage"] not in HEALTHY, (world, kind, shape)


def test_control_two_readable_distinct_pulls_are_multiple_prs_and_whole(monkeypatch: pytest.MonkeyPatch,
                                                                       tmp_path: Path) -> None:
    """Spec row 10: two pulls both read whole is a verdict from a whole read, so nothing is held."""
    st = _world(monkeypatch, tmp_path, "done")
    st.gql_pages.append(linear_page([_issue("done", _refs("done", "first_fails"))]))
    out = run(st, LATER)
    rec = _state(st)["missions"]["RA-1"]
    assert (rec["stage"], rec["reason"]) == ("unknown", "multiple_prs")
    assert out["not_refreshed_ids"] == [] and out["complete"] is True
    assert ("RA-1", "FALSE_DONE") not in _shown(st, LATER)  # the whole read retires what it no longer supports


def test_control_a_whole_read_with_no_ci_is_whole(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = _world(monkeypatch, tmp_path, "done")
    st.gh[f"/repos/{PIDEV}/commits/{SHA_A}/check-runs?per_page=100&page=1"] = {"total_count": 0, "check_runs": []}
    st.gh[f"/repos/{PIDEV}/commits/{SHA_A}/status"] = {"state": "pending", "total_count": 0, "sha": SHA_A}
    st.gql_pages.append(linear_page([tick_issue("RA-1", ((PIDEV, 7),))]))
    out = run(st, LATER)
    rec = _state(st)["missions"]["RA-1"]
    assert (rec["stage"], rec["reason"]) == ("unknown", "no_ci") and out["not_refreshed_ids"] == []


@pytest.mark.parametrize("shape", ["one", "with_a_readable_open_pull"])
def test_an_open_pull_with_no_head_is_an_answer_read_whole(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                           shape: str) -> None:
    """Spec row 4: an empty head SHA was read and says there is no commit; it is whole, not held."""
    st = _world(monkeypatch, tmp_path, "done")
    st.gh[f"/repos/{PIDEV}/pulls/7"] = {**open_pull(7), "head": {"sha": None}}
    refs = ((PIDEV, 7),) if shape == "one" else ((PIDEV, 7), (PIDEV, 8))
    st.gql_pages.append(linear_page([tick_issue("RA-1", refs)]))
    out = run(st, LATER)
    rec = _state(st)["missions"]["RA-1"]
    want = ("missing_commit", "empty_head") if shape == "one" else ("unknown", "multiple_prs")
    assert (rec["stage"], rec["reason"]) == want and out["not_refreshed_ids"] == []


def test_a_merged_pull_with_no_merge_sha_is_an_answer_read_whole(monkeypatch: pytest.MonkeyPatch,
                                                                 tmp_path: Path) -> None:
    st = _world(monkeypatch, tmp_path, "merged")
    st.gh[f"/repos/{PIDEV}/pulls/4"] = {**st.gh[f"/repos/{PIDEV}/pulls/4"], "merge_commit_sha": None}
    st.gql_pages.append(linear_page([tick_issue("RA-4", ((PIDEV, 4),))]))
    out = run(st, LATER)
    rec = _state(st)["missions"]["RA-4"]
    assert (rec["stage"], rec["reason"]) == ("missing_commit", "no_merge_sha") and out["not_refreshed_ids"] == []


@pytest.mark.parametrize("kind,want", [("head_404", ("missing_commit", "head_not_found")),
                                       ("http_500", ("unknown", "http_500"))])
def test_a_failed_read_beside_a_readable_pull_is_that_reads_verdict(monkeypatch: pytest.MonkeyPatch,
                                                                    tmp_path: Path, kind: str, want: tuple) -> None:
    """A pull that failed to read is never counted as an open pull: no ``multiple_prs`` from a failed read."""
    st = _world(monkeypatch, tmp_path, "done")
    _fail(monkeypatch, st, kind, 8, SHA_C)
    st.gql_pages.append(linear_page([tick_issue("RA-1", ((PIDEV, 7), (PIDEV, 8)))]))
    run(st, LATER)
    rec = _state(st)["missions"]["RA-1"]
    assert (rec["stage"], rec["reason"]) == want
