"""RA-8100 B5f: the smaller K1 faces. A failed tick shows on the tile, odd stored data does not stop
ticks, extreme timestamps are bad timestamps, skipped checks are not passing tests, a cross-repo
merge is never verified live, the sweep and Vercel answers say what they claim, and a future source
time is not a source.
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from _delivery_reconcile_support import (
    ALLOWED, ATO, NOW, PIDEV, SHA_A, SHA_B, ago, install_fakes, linear_page, merged_paths, open_facts,
    open_pull, pr_paths, reg_entry, run, setup_tick, stored, summary_of, sweep_path, tick_issue,
)

from app.server import delivery_collect as collect
from app.server import delivery_collect_github as gh
from app.server import delivery_reconcile as dr
from app.server import delivery_reconcile_gather as gather
from app.server import delivery_reconcile_store as store
from app.server import delivery_stage
from app.server.delivery_collect_fields import instant

LATER = NOW + timedelta(minutes=10)


def _state(st) -> dict:  # type: ignore[no-untyped-def]
    return json.loads(Path(st.path).read_text(encoding="utf-8"))


def _good_tick(st) -> None:  # type: ignore[no-untyped-def]
    st.gh.update(pr_paths(PIDEV, 7))
    st.gh[sweep_path(PIDEV)] = [open_pull(7)]
    st.gql_pages.append(linear_page([tick_issue("RA-1", ((PIDEV, 7),), state="completed", completed=0.5)]))


# ── P2-2: a tick that fails for any reason is on the tile; odd stored counts do not fail ticks ──
def test_an_unexpected_tick_failure_is_reported_until_a_good_tick(monkeypatch: pytest.MonkeyPatch,
                                                                  tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    _good_tick(st)
    run(st)
    assert dr.status_snapshot(st.path, NOW)["complete"] is True

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("planted")

    monkeypatch.setattr(store, "apply_tick", boom)
    _good_tick(st)
    out = dr.run_reconcile_tick(now=LATER, path=str(st.path))
    snap = dr.status_snapshot(st.path, LATER)
    assert out["error"] == "tick_failed_RuntimeError"
    assert snap["complete"] is False and "tick_failed_RuntimeError" in snap["errors"]
    monkeypatch.undo()
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])  # same state path, fresh fakes
    dr.record_tick({"skipped": "lease_held"})  # a skipped tick neither sets nor clears the error
    dr.record_tick({"error": "tick_failed_RuntimeError"})
    dr.record_tick({"skipped": "lease_held"})
    assert "tick_failed_RuntimeError" in dr.status_snapshot(st.path, LATER)["errors"]
    _good_tick(st)
    run(st, LATER + timedelta(minutes=10))
    snap = dr.status_snapshot(st.path, LATER + timedelta(minutes=10))
    assert snap["complete"] is True and snap["errors"] == []


def test_a_store_merge_error_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    monkeypatch.setattr(gather, "gather", lambda *_a: ([{"kind": "no id"}], []))
    out = run(st)
    snap = dr.status_snapshot(st.path, NOW)
    assert out["error"] == "merge_failed_record_missing_id"
    assert snap["complete"] is False and "merge_failed_record_missing_id" in snap["errors"]


@pytest.mark.parametrize("bad", [None, "3", True, -1, 0, 1.5, []])
def test_a_bad_stored_count_is_state_unreadable_never_repaired(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                              bad: object) -> None:
    """D33: a stored count of the wrong shape means the file is not ours; it is not silently restarted."""
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    _good_tick(st)
    run(st)
    state = _state(st)
    assert state["alerts"]  # positive control: there is a count to break
    for alert in state["alerts"].values():
        alert["count"] = bad
    Path(st.path).write_text(json.dumps(state), encoding="utf-8")
    body = Path(st.path).read_bytes()
    _good_tick(st)
    out = dr.run_reconcile_tick(now=LATER, path=str(st.path))
    assert out.get("error") == "state_unreadable" and out["persisted"] is False
    assert Path(st.path).read_bytes() == body
    assert dr.status_snapshot(st.path, LATER)["state"] == "unreadable"


# ── P2-1: an extreme but valid timestamp is a bad timestamp, never an escape ──
@pytest.mark.parametrize("ts", ["0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00"])
def test_extreme_timestamp_is_out_of_domain(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ts: str) -> None:
    assert instant(ts) is None
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    st.gh.update(pr_paths(PIDEV, 7))
    st.gh[sweep_path(PIDEV)] = [{**open_pull(9), "created_at": ts}, open_pull(7)]
    issue = tick_issue("RA-1", ((PIDEV, 7),))
    issue["startedAt"] = ts
    st.gql_pages.append(linear_page([issue]))
    out = run(st)  # fails the test if the tick escapes with tick_failed_*
    assert out["complete"] is False


# ── P2-3: skipped or neutral check runs are not CI evidence ──
@pytest.mark.parametrize("conclusions", [["skipped"], ["neutral"], ["skipped", "neutral"]])
def test_all_skipped_or_neutral_checks_are_no_ci(conclusions: list[str]) -> None:
    pr = open_facts(checks="none")
    pr["check_runs"] = [{"status": "completed", "conclusion": c, "completed_at": ago(70)} for c in conclusions]
    rec, _ = delivery_stage.classify(tick_issue("RA-5", ((PIDEV, 7),)), [pr], {}, NOW, repo=PIDEV, project_id="p")
    assert rec["tests_passed"] is False and (rec["stage"], rec["reason"]) == ("unknown", "no_ci")


def test_success_beside_skipped_still_passes() -> None:
    pr = open_facts()
    pr["check_runs"].append({"status": "completed", "conclusion": "skipped", "completed_at": ago(70)})
    rec, _ = delivery_stage.classify(tick_issue("RA-5", ((PIDEV, 7),)), [pr], {}, NOW, repo=PIDEV, project_id="p")
    assert rec["tests_passed"] is True


# ── P2-4: only a merged PR in the provable repo itself is compared with the own revision ──
def test_a_cross_repo_merge_is_never_verified_live(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV), reg_entry("ato", ATO)])
    own = "d" * 40
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", own)
    st.gh.update(merged_paths(ATO, 3))
    st.gh[f"/repos/{ATO}/compare/{SHA_B}...{own}"] = {"status": "ahead"}
    st.gh[sweep_path(PIDEV)] = st.gh[sweep_path(ATO)] = []
    st.gql_pages += [linear_page([tick_issue("RA-7", ((ATO, 3),))]), linear_page([])]
    run(st)
    assert _state(st)["missions"]["RA-7"]["verified_sha"] is None
    assert not [p for p in st.github if "/compare/" in p]


# ── P2-5: an open-PR sweep item must say it is open ──
@pytest.mark.parametrize("change,ok", [({"state": "closed"}, False), ({"merged": True}, False),
                                       ({"state": "closed", "merged": True, "merged_at": ago(1)}, False),
                                       ({"merged": None}, True), ({}, True)])
def test_sweep_item_must_be_open(monkeypatch: pytest.MonkeyPatch, change: dict, ok: bool) -> None:
    st = install_fakes(monkeypatch)
    item = {**open_pull(9), **change}
    if change == {"merged": None}:
        item.pop("merged")
    st.gh[sweep_path(PIDEV)] = [open_pull(7), item]
    tick = collect.Tick(allowed=ALLOWED)
    if ok:
        assert len(gh.open_prs(PIDEV, tick=tick)) == 2
    else:
        with pytest.raises(collect.Unknown, match="malformed_pull"):
            gh.open_prs(PIDEV, tick=tick)


# ── P2-6: only a production deployment counts ──
VERCEL_ENTRY = {"id": "x", "repo": "CleanExpo/Synthex", "vercel_project_id": "prj1"}


def _ready(sha: str, created: int, target: object) -> dict:
    return {"state": "READY", "created": created, "target": target, "meta": {"githubCommitSha": sha}}


@pytest.mark.parametrize("deps,want", [
    ([_ready(SHA_A, 5, "preview")], None), ([_ready(SHA_A, 5, None)], None),
    ([_ready(SHA_A, 5, "production")], SHA_A),
    ([_ready(SHA_A, 1, "production"), _ready(SHA_B, 9, "preview")], SHA_A),
    ([_ready(SHA_A, 5, 5)], "malformed_deployments"), ([_ready(SHA_A, 5, "")], "malformed_deployments"),
])
def test_vercel_counts_only_production(monkeypatch: pytest.MonkeyPatch, deps: list, want: str | None) -> None:
    st = install_fakes(monkeypatch)
    st.vc["*"] = {"deployments": deps}
    tick = collect.Tick(allowed=frozenset({"cleanexpo/synthex"}))
    try:
        got = collect.vercel_latest_ready(VERCEL_ENTRY, tick=tick)
    except collect.Unknown as exc:
        got = exc.reason
    assert got == want


# ── A future source time is not a source: an UNKNOWN record still reaches its 24-hour alert ──
def test_future_started_at_falls_through_to_first_seen() -> None:
    issue = tick_issue("RA-8", ((PIDEV, 7),))
    issue["startedAt"] = "2030-01-01T00:00:00Z"
    err = {"repo": PIDEV, "number": 7, "error": "unknown", "reason": "http_500", "created_at": None}
    first = (NOW - timedelta(hours=30)).timestamp()
    rec, found = delivery_stage.classify(issue, [err], {}, NOW, repo=PIDEV, project_id="p", first_seen=first)
    assert rec["age_source"] == "local_first_seen"
    assert "EVIDENCE_UNKNOWN_24H" in [f["code"] for f in found]


@pytest.mark.parametrize("bad", [NOW.timestamp() + 86400, "x", None, True])
def test_store_never_keeps_a_future_or_bad_first_seen(bad: object) -> None:
    state = store.empty_state()
    state["missions"]["M"] = {"id": "M", "first_seen": bad}
    out, _ = store.apply_tick(state, [{"id": "M"}], [], NOW.timestamp())  # no scope: an incomplete tick
    assert out["missions"]["M"]["first_seen"] == NOW.timestamp()


def test_tile_survives_a_stored_extreme_since(tmp_path: Path) -> None:
    """A stored ``since`` whose UTC instant overflows has no age; the tile still renders."""
    state = store.empty_state()
    state["last_tick"] = NOW.timestamp()
    state["summary"] = summary_of(complete=True)
    state["checkpoint"]["last_complete"] = NOW.timestamp()
    for key, since in (("A", "0001-01-01T00:00:00+14:00"), ("B", "9999-12-31T23:59:59-14:00")):
        state["alerts"][key] = stored({"key": key, "mission_id": key, "code": "X", "severity": "founder", "ref": key,
                                       "since": since, "age_source": "startedAt"}, NOW.timestamp(), alert=True)
    path = tmp_path / "s.json"
    assert store.save(path, state)
    snap = dr.status_snapshot(path, NOW)
    assert snap["state"] == "ok" and [i["age_hours"] for i in snap["items"]] == [None, None]
