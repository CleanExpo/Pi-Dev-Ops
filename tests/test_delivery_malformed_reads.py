"""RA-8100 B5c class guard: one malformed item in any outside list fails that whole read.

One row per outside list. Each plants a single malformed item next to valid ones and runs a tick
over a state that already holds stored records and their alerts. A list read that decides
completeness must leave the tick incomplete; a per-mission read must make that mission UNKNOWN.
In every row the stored records and alerts survive and the malformed item never becomes a record.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    ATO, SHA_A, ago, linear_page, open_pull, pr_paths, reg_entry, run, setup_tick, stored, sweep_path, tick_issue,
)
from _delivery_stored_support import planted as planted_state

from app.server import delivery_collect as dc
from app.server import delivery_reconcile_store as store

RA = "CleanExpo/RestoreAssist"  # live_unconfirmed: its Vercel read decides the repo record
ORPHAN = f"pr:{ATO}#7"
REPO_REC = f"repo:{RA}"
STORED = (ORPHAN, "RA-1", "RA-9", REPO_REC)
LEGIT = {*STORED, f"repo:{ATO}"}
ENTRIES = [reg_entry("ato", ATO), reg_entry("ra", RA, queryable=False, vercel="prj_fake")]
PULL5 = f"/repos/{ATO}/pulls/5"
CHECKS5 = f"/repos/{ATO}/commits/{SHA_A}/check-runs?per_page=100&page=1"
REVIEWS5 = f"/repos/{ATO}/pulls/5/reviews?per_page=100&page=1"


def _plant(st: SimpleNamespace) -> dict:
    state = planted_state()
    for rid, kind in ((ORPHAN, "orphan_pr"), ("RA-1", "mission"), ("RA-9", "mission"), (REPO_REC, "repo")):
        held = {"id": rid, "kind": kind, "repo": RA, "ref": RA} if kind == "repo" else \
            {"id": rid, "kind": kind, "stage": "building", "project_id": "ato"}  # a repo record has no stage here
        state["missions"][rid] = stored(held)
        state["alerts"][f"k-{rid}"] = stored({"key": f"k-{rid}", "mission_id": rid, "code": "EVIDENCE_UNKNOWN"},
                                             alert=True)
    state["checkpoint"]["last_complete"] = 1.0
    assert store.save(st.path, state)
    return state


def _world(st: SimpleNamespace) -> None:
    """A good world: RA-1 links open ATO#5 (green, unreviewed); ATO#7 is an open orphan."""
    st.gql_pages.append(linear_page([tick_issue("RA-1", ((ATO, 5),))]))
    st.gh[sweep_path(ATO)] = [open_pull(5), open_pull(7)]
    st.gh.update(pr_paths(ATO, 5))
    st.vc["*"] = {"deployments": [dict(READY)]}


def _sweep(item: dict) -> Callable[[SimpleNamespace], None]:
    return lambda st: st.gh.__setitem__(sweep_path(ATO), [open_pull(5), item])


def _pages(*pages: dict) -> Callable[[SimpleNamespace], None]:
    return lambda st: st.gql_pages.__setitem__(slice(None), list(pages))


def _set(path: str, value: object) -> Callable[[SimpleNamespace], None]:
    return lambda st: st.gh.__setitem__(path, value)


def _issue(**over: object) -> Callable[[SimpleNamespace], None]:
    return _pages(linear_page([{**tick_issue("RA-1", ((ATO, 5),)), **over}]))


def _deploys(*items: object) -> Callable[[SimpleNamespace], None]:
    return lambda st: st.vc.__setitem__("*", {"deployments": list(items)})


def _run(state: str = "completed", conclusion: object = "success") -> dict:
    return {"total_count": 1, "check_runs": [{"id": 1, "status": state, "conclusion": conclusion,
                                              "completed_at": ago(72)}]}


def _review(state: str, at: float, rid: int) -> dict:
    return {"id": rid, "user": None, "state": state, "commit_id": SHA_A, "submitted_at": ago(at)}


RA1 = tick_issue("RA-1", ((ATO, 5),))
READY = {"state": "READY", "created": 2, "target": "production", "meta": {"githubCommitSha": SHA_A}}
# (row id, kind, the item the malformed read would otherwise drop or mark healthy, how to break the world)
ROWS = [
    ("sweep_number_none", "list", ORPHAN, _sweep({**open_pull(7), "number": None})),  # the reviewer's case
    ("sweep_number_bool", "list", ORPHAN, _sweep({**open_pull(7), "number": True})),
    ("sweep_number_text", "list", ORPHAN, _sweep({**open_pull(7), "number": "7"})),
    ("sweep_number_zero", "list", ORPHAN, _sweep({**open_pull(7), "number": 0})),
    ("sweep_duplicate", "list", ORPHAN, _sweep(open_pull(5))),
    ("sweep_head_not_dict", "list", ORPHAN, _sweep({**open_pull(7), "head": "x"})),
    ("sweep_head_sha_not_text", "list", ORPHAN, _sweep({**open_pull(7), "head": {"sha": 5}})),
    ("sweep_created_not_text", "list", ORPHAN, _sweep({**open_pull(7), "created_at": 5})),
    ("linear_identifier_not_text", "list", "RA-9", _pages(linear_page([RA1, {**tick_issue("RA-9"), "identifier": 42}]))),
    ("linear_id_not_text", "list", "RA-9", _pages(linear_page([RA1, {**tick_issue("RA-9"), "id": 5}]))),
    ("linear_duplicate_across_pages", "list", "RA-9", _pages(linear_page([RA1], "c1"), linear_page([RA1]))),
    ("linear_duplicate_one_page", "list", "RA-9", _pages(linear_page([RA1, RA1]))),
    ("check_run_status_not_text", "mission", "RA-1", _set(CHECKS5, _run(state=["completed"]))),  # type: ignore[arg-type]
    ("check_run_conclusion_not_text", "mission", "RA-1", _set(CHECKS5, _run(conclusion=1))),
    ("reviews_without_login", "mission", "RA-1",
     _set(REVIEWS5, [_review("CHANGES_REQUESTED", 5, 1), _review("APPROVED", 2, 2)])),
    ("pull_head_not_dict", "mission", "RA-1", _set(PULL5, {**open_pull(5), "head": "x"})),
    ("link_attachment_url_not_text", "mission", "RA-1",
     _issue(attachments={"pageInfo": {"hasNextPage": False}, "nodes": [{"url": 123}]})),
    ("link_description_not_text", "mission", "RA-1", _issue(description={"text": "x"})),
    ("vercel_item_not_dict", "vercel", REPO_REC, _deploys("junk", READY)),
    ("vercel_meta_not_dict", "vercel", REPO_REC, _deploys({**READY, "meta": "x"})),
    ("vercel_sha_malformed", "vercel", REPO_REC, _deploys({**READY, "meta": {"githubCommitSha": "zzz"}})),
    ("vercel_created_bool", "vercel", REPO_REC, _deploys({**READY, "created": True})),
    ("vercel_state_not_text", "vercel", REPO_REC, _deploys(READY, {**READY, "state": None, "created": 9})),
]


@pytest.mark.parametrize("kind,affected,breaks", [r[1:] for r in ROWS], ids=[r[0] for r in ROWS])
def test_malformed_item_fails_its_read_and_drops_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str, affected: str,
    breaks: Callable[[SimpleNamespace], None],
) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    planted = _plant(st)
    _world(st)
    breaks(st)
    out = run(st)
    state = json.loads(Path(st.path).read_text(encoding="utf-8"))
    missions, alerts = state["missions"], state["alerts"]
    assert "error" not in out, out  # the designed path, never a crash caught by the tick
    assert set(missions) <= LEGIT  # the malformed item never becomes a record of its own
    if kind == "list":
        assert out["complete"] is False
        assert missions[affected] == planted["missions"][affected]  # kept exactly as stored, not re-judged
        expect = STORED
    else:
        assert affected in out["not_refreshed_ids"]  # held: its stored alert stays and is shown
        if kind == "mission":  # a failed read makes the record UNKNOWN (spec row 1)
            assert missions[affected]["stage"] in ("unknown", "missing_commit")
        else:
            assert out["vercel_unreadable"] == 1 and missions[affected]["live_unconfirmed"] is None
        expect = (ORPHAN, "RA-1", REPO_REC)
    assert f"k-{affected}" in alerts
    for rid in expect:
        assert rid in missions, rid


def test_good_world_is_complete_so_each_row_isolates_its_break(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Positive control: without a break the same tick is complete and judges every item."""
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    _plant(st)
    _world(st)
    out = run(st)
    missions = json.loads(Path(st.path).read_text(encoding="utf-8"))["missions"]
    assert "error" not in out and out["complete"] is True and out["vercel_unreadable"] == 0
    assert missions["RA-1"]["stage"] == "review_wait" and missions[ORPHAN]["stage"] == "building"
    assert missions[REPO_REC]["live_unconfirmed"] == SHA_A and "RA-9" not in missions


def test_reviewer_case_number_none_keeps_orphan_and_alert(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The exact finding: an open PR with number None must not let a complete tick clear pr:<repo>#7."""
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    _plant(st)
    _world(st)
    st.gh[sweep_path(ATO)] = [open_pull(5), {**open_pull(7), "number": None}]
    out = run(st)
    state = json.loads(Path(st.path).read_text(encoding="utf-8"))
    assert out["complete"] is False and out["incomplete"].get(ATO) == "malformed_pull"
    assert ORPHAN in state["missions"] and f"k-{ORPHAN}" in state["alerts"]


@pytest.mark.parametrize("refs", [[(None, 5)], [(ATO, "5")], [(ATO, True)], [(ATO, 0)], [("not a repo", 5)]],
                         ids=["repo_none", "number_text", "number_bool", "number_zero", "repo_shape"])
def test_in_scope_refuses_a_malformed_ref(refs: list) -> None:
    with pytest.raises(dc.Unknown) as err:
        dc.in_scope(refs, frozenset({ATO.lower()}))
    assert err.value.reason == "malformed_ref"
