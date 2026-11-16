"""RA-8100 B5f round 2 (lead decision, spec row 1): a mission whose own read failed or came back not
whole becomes UNKNOWN with that read's reason code; it never keeps an earlier healthy stage. Its stored
alerts stay stored and shown until a whole read retires them, and first_seen is kept. A mission only cut
by the per-mission GitHub budget (spec line 112) keeps its stored record unchanged.
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
    FAKE_REVIEWER, NOW, PIDEV, SHA_A, SHA_B, ago, linear_page, merged_paths, open_pull, pr_paths, reg_entry,
    run, setup_tick, stored, sweep_path, tick_issue,
)

from app.server import delivery_collect as collect
from app.server import delivery_reconcile as dr

OWN = "d" * 40
LATER = NOW + timedelta(minutes=10)
BASE = f"/repos/{PIDEV}"
OPEN_READS = [f"{BASE}/pulls/7", f"{BASE}/commits/{SHA_A}", f"{BASE}/commits/{SHA_A}/check-runs?per_page=100&page=1",
              f"{BASE}/commits/{SHA_A}/status", f"{BASE}/pulls/7/reviews?per_page=100&page=1"]
READS = {"building": OPEN_READS, "review_wait": OPEN_READS, "approval_wait": OPEN_READS,
         "merged": [f"{BASE}/pulls/4", f"{BASE}/commits/{SHA_B}", f"{BASE}/compare/{SHA_B}...{OWN}"]}
PLANTED = {"key": "planted-critical", "mission_id": "RA-1", "code": "FALSE_DONE", "severity": "critical",
           "ref": "RA-1", "next_owner": "SPM", "message": "planted", "since": ago(1),
           "age_source": "startedAt"}


class HTTP500(Exception):
    code = 500


def _state(st: SimpleNamespace) -> dict:
    return json.loads(Path(st.path).read_text(encoding="utf-8"))


def _healthy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stage: str) -> SimpleNamespace:
    """Tick 1 stores RA-1 at ``stage``; a critical alert is planted beside it; tick 2's fakes are whole."""
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    monkeypatch.setenv("TAO_DELIVERY_HUMAN_REVIEWERS", FAKE_REVIEWER)
    if stage == "merged":
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", OWN)
        st.gh.update(merged_paths(PIDEV, 4))
        st.gh[f"{BASE}/compare/{SHA_B}...{OWN}"] = compare_answer(SHA_B, OWN, "ahead")
        st.gh[sweep_path(PIDEV)] = []
        refs: tuple = ((PIDEV, 4),)
    else:
        st.gh.update(pr_paths(PIDEV, 7))
        st.gh[sweep_path(PIDEV)] = [open_pull(7)]
        refs = ((PIDEV, 7),)
        if stage == "building":
            st.gh[f"{BASE}/pulls/7"] = {**st.gh[f"{BASE}/pulls/7"], "draft": True}
        if stage == "approval_wait":
            st.gh[OPEN_READS[4]] = [{"id": 1, "user": {"login": FAKE_REVIEWER, "type": "User"}, "state": "APPROVED",
                                     "commit_id": SHA_A, "submitted_at": ago(2)}]
    page = linear_page([tick_issue("RA-1", refs)])
    st.gql_pages += [page, page, page]
    run(st)
    state = _state(st)
    assert state["missions"]["RA-1"]["stage"] == stage  # positive control: the stored record is healthy
    state["alerts"][PLANTED["key"]] = stored(PLANTED, NOW.timestamp(), alert=True)
    Path(st.path).write_text(json.dumps(state), encoding="utf-8")
    return st


def _clock_after(monkeypatch: pytest.MonkeyPatch, st: SimpleNamespace, calls: int) -> None:
    base = len(st.gql) + len(st.github)
    clock = lambda: 0.0 if len(st.gql) + len(st.github) - base < calls else 1000.0  # noqa: E731
    monkeypatch.setattr(collect, "Tick", functools.partial(collect.Tick, clock=clock))


def _fail(monkeypatch: pytest.MonkeyPatch, st: SimpleNamespace, stage: str, how: str, i: int) -> None:
    if how == "links":
        st.gql_pages[1]["project"]["issues"]["nodes"][0]["attachments"]["pageInfo"]["hasNextPage"] = True
    elif how == "clock":  # the Linear page, the sweep and the mission's first read, then the clock runs out
        _clock_after(monkeypatch, st, 3)
    else:
        st.gh[READS[stage][i]] = HTTP500() if how == "http" else "garbage"


def _failed_rows() -> list:
    rows = []
    for stage, reads in READS.items():
        rows += [pytest.param(stage, how, i, id=f"{stage}-{how}-read{i}") for i in range(len(reads))
                 for how in ("http", "malformed")]
        rows += [pytest.param(stage, "links", 0, id=f"{stage}-links_not_whole"),
                 pytest.param(stage, "clock", 0, id=f"{stage}-clock_mid_read")]
    return rows


def _alert_shown(st: SimpleNamespace, now) -> bool:  # type: ignore[no-untyped-def]
    snap = dr.status_snapshot(st.path, now)
    return ("RA-1", "FALSE_DONE") in {(i["ref"], i["code"]) for i in snap["items"]} \
        and snap["counts"]["by_code"].get("FALSE_DONE", 0) >= 1


@pytest.mark.parametrize("stage,how,i", _failed_rows())
def test_a_failed_read_makes_the_record_unknown_and_keeps_its_alerts(monkeypatch: pytest.MonkeyPatch,
                                                                     tmp_path: Path, stage: str, how: str,
                                                                     i: int) -> None:
    st = _healthy(monkeypatch, tmp_path, stage)
    first_seen = _state(st)["missions"]["RA-1"]["first_seen"]
    _fail(monkeypatch, st, stage, how, i)
    out = run(st, LATER)
    record = _state(st)["missions"]["RA-1"]
    assert record["stage"] == "unknown" and isinstance(record["reason"], str) and record["reason"]
    assert record["first_seen"] == first_seen and "RA-1" in out["not_refreshed_ids"]
    assert PLANTED["key"] in _state(st)["alerts"] and _alert_shown(st, LATER)
    assert any(a["code"] == "EVIDENCE_UNKNOWN" and a["mission_id"] == "RA-1" for a in _state(st)["alerts"].values())


def _budget_rows() -> list:
    return [pytest.param(stage, b, id=f"{stage}-budget{b}") for stage, reads in READS.items()
            for b in range(1, len(reads) + 1)]  # the sweep, then 0..n-1 of the mission's own reads


@pytest.mark.parametrize("stage,budget", _budget_rows())
def test_a_budget_cut_keeps_the_stored_record_unchanged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                        stage: str, budget: int) -> None:
    st = _healthy(monkeypatch, tmp_path, stage)
    before = _state(st)["missions"]["RA-1"]
    monkeypatch.setitem(collect.BUDGETS, "github", budget)
    out = run(st, LATER)
    after = _state(st)["missions"]["RA-1"]
    drop = lambda r: {k: v for k, v in r.items() if k != "refreshed_at"}  # noqa: E731
    assert drop(after) == drop(before) and "RA-1" in out["not_refreshed_ids"]
    assert _alert_shown(st, LATER)


def test_a_whole_read_after_a_failed_one_restores_the_stage_and_only_then_retires(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = _healthy(monkeypatch, tmp_path, "review_wait")
    good = st.gh[OPEN_READS[0]]
    st.gh[OPEN_READS[0]] = HTTP500()
    run(st, LATER)
    assert _state(st)["missions"]["RA-1"]["stage"] == "unknown" and PLANTED["key"] in _state(st)["alerts"]
    st.gh[OPEN_READS[0]] = good
    third = LATER + timedelta(minutes=10)
    out = run(st, third)
    state = _state(st)
    assert state["missions"]["RA-1"]["stage"] == "review_wait" and out["not_refreshed_ids"] == []
    assert PLANTED["key"] not in state["alerts"] and not _alert_shown(st, third)
