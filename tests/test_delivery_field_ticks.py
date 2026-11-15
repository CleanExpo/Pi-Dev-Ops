"""RA-8100 B5e: tick-level rows for every field whose bad value could make a record look healthier.

Generated from the inventory (rows with ``tick`` True). Each plants one out-of-domain value into an
otherwise good world over a state that already holds an UNKNOWN record and its alert for every
item, runs one tick, and asserts: no healthy stage from the bad value, the stored records and their
alerts survive and stay shown, and a list read that decides completeness leaves the tick incomplete.
Also the reviewer's exact case (orphan #7 ``head.sha="not-a-sha"``) and its two neighbours.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    ATO, FAKE_REVIEWER, PIDEV, SHA_A, SHA_B, ago, linear_page, merged_paths, open_pull, pr_paths, reg_entry, run,
    setup_tick, stored, sweep_path, tick_issue,
)
from test_delivery_field_domains import NEGATIVES, _set
from test_delivery_field_inventory import INVENTORY

from app.server import delivery_reconcile_status as status
from app.server import delivery_reconcile_store as store

RA = "CleanExpo/RestoreAssist"
ORPHAN = f"pr:{ATO}#7"
STORED = (ORPHAN, "RA-1", "RA-9", f"repo:{RA}")
ENTRIES = [reg_entry("ato", ATO), reg_entry("ra", RA, queryable=False, vercel="prj_fake")]
HEALTHY = {"building", "review_wait", "approval_wait", "merged", "done", "deploying", "verified"}
PICK = {"sha": ("int", "not_hex"), "timestamp": ("int", "no_tz"), "enum": ("int", "unknown"), "bool": ("text",),
        "count": ("negative", "bool"), "posint": ("text", "zero"), "object": ("text",), "login": ("space",),
        "text": ("int", "blank"), "text_any": ("int", "false"), "list": ("dict",)}
P5 = f"/repos/{ATO}/pulls/5"
CHECKS5 = f"/repos/{ATO}/commits/{SHA_A}/check-runs?per_page=100&page=1"
REVIEW = {"id": 1, "user": {"login": FAKE_REVIEWER, "type": "User"}, "state": "APPROVED", "commit_id": SHA_A,
          "submitted_at": ago(2)}
READY = {"state": "READY", "created": 2, "target": "production", "meta": {"githubCommitSha": SHA_A}}


def _plant_state(st: SimpleNamespace) -> dict:
    state = store.empty_state()
    for rid in STORED:
        kind = "orphan_pr" if rid == ORPHAN else ("repo" if rid.startswith("repo:") else "mission")
        held = {"id": rid, "kind": kind, "repo": RA, "ref": RA} if kind == "repo" else \
            {"id": rid, "kind": kind, "stage": "unknown", "reason": "http_500"}  # a repo record has no reason
        state["missions"][rid] = stored(held)
        state["alerts"][f"k-{rid}"] = stored({"key": f"k-{rid}", "mission_id": rid, "code": "EVIDENCE_UNKNOWN"},
                                             alert=True)
    state["checkpoint"]["last_complete"] = 1.0
    assert store.save(st.path, state)
    return state


def _world(st: SimpleNamespace, node: dict | None = None) -> None:
    """RA-1 links open ATO#5 (green, unreviewed); ATO#7 is an open orphan; RA has a READY deploy."""
    st.gql_pages.append(linear_page([node or tick_issue("RA-1", ((ATO, 5),))]))
    st.gh[sweep_path(ATO)] = [open_pull(5), open_pull(7)]
    st.gh.update(pr_paths(ATO, 5))
    st.vc["*"] = {"deployments": [copy.deepcopy(READY)]}


def _break(st: SimpleNamespace, source: str, field: str, value: object) -> str:
    """Plant the value in the world; returns the row kind: list, mission or vercel."""
    if source == "pulls_list":
        st.name_asked = False  # both items are built naming their repo; nothing fills a planted absence
        named = {"base": {"repo": {"full_name": ATO}}}
        item = {**open_pull(7), **named}
        _set(item, field, value)
        st.gh[sweep_path(ATO)] = [{**open_pull(5), **named}, item]
        return "list"
    if source in ("linear_issue", "linear_links"):
        node = tick_issue("RA-1", ((ATO, 5),))
        node["attachments"]["nodes"] = [{"url": f"https://github.com/{ATO}/pull/5"}]
        _set(node, field, value)
        st.gql_pages[:] = [linear_page([node])]
        return "list" if source == "linear_issue" and field not in ("startedAt", "completedAt") else "mission"
    if source == "vercel":
        _set(st.vc["*"]["deployments"][0], field, value)
        return "vercel"
    if source == "pull_merged":
        st.gh.update(merged_paths(ATO, 5))
    if source in ("pull", "pull_merged"):
        _set(st.gh[P5], field, value)
    elif source == "check_runs":
        _set(st.gh[CHECKS5], field, value)
    elif source == "check_run":
        _set(st.gh[CHECKS5]["check_runs"][0], field, value)
    elif source == "status":
        _set(st.gh[f"/repos/{ATO}/commits/{SHA_A}/status"], field, value)
    else:
        review = copy.deepcopy(REVIEW)
        _set(review, field, value)
        st.gh[f"/repos/{ATO}/pulls/5/reviews?per_page=100&page=1"] = [review]
    return "mission"


def _rows() -> list:
    out = []
    for source, field, domain, *_, tick in INVENTORY:
        if not tick or source == "compare":
            continue
        for label, value in NEGATIVES[domain]:
            if label in PICK[domain]:
                out.append(pytest.param(source, field, value, id=f"{source}.{field}-{label}"))
    return out


def _after(st: SimpleNamespace) -> tuple[dict, dict, list]:
    state = json.loads(Path(st.path).read_text(encoding="utf-8"))
    return state["missions"], state["alerts"], status._shown(state, state.get("summary") or {})


@pytest.mark.parametrize("source,field,value", _rows())
def test_bad_field_never_looks_healthier(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, source: str, field: str,
                                         value: object) -> None:
    monkeypatch.setenv("TAO_DELIVERY_HUMAN_REVIEWERS", FAKE_REVIEWER)
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    planted = _plant_state(st)
    _world(st)
    kind = _break(st, source, field, value)
    out = run(st)
    missions, alerts, shown = _after(st)
    assert "error" not in out, out
    if kind == "list":
        affected = ORPHAN if source == "pulls_list" else "RA-1"
        assert out["complete"] is False and missions[affected] == planted["missions"][affected]
    else:
        affected = "RA-1" if kind == "mission" else f"repo:{RA}"
        assert affected in out["not_refreshed_ids"]  # held: its stored alert stays and is shown
        if kind == "mission":  # a failed read makes the record UNKNOWN (spec row 1), never a healthy stage
            assert missions[affected]["stage"] in ("unknown", "missing_commit")
            assert missions[affected]["tests_passed"] is False and missions[affected]["reviewed_head_sha"] is None
        else:
            assert out["vercel_unreadable"] == 1 and missions[affected]["live_unconfirmed"] is None
    assert missions[affected]["stage"] not in HEALTHY
    assert f"k-{affected}" in alerts
    for rid in (ORPHAN, "RA-1", f"repo:{RA}"):
        assert rid in missions, rid
    assert any(a.get("mission_id") == affected for a in shown), affected


def test_positive_control_good_world_is_healthy_and_complete(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TAO_DELIVERY_HUMAN_REVIEWERS", FAKE_REVIEWER)
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    _plant_state(st)
    _world(st)
    st.gh[f"/repos/{ATO}/pulls/5/reviews?per_page=100&page=1"] = [REVIEW]
    out = run(st)
    missions = _after(st)[0]
    assert out["complete"] is True and out["vercel_unreadable"] == 0
    assert missions["RA-1"]["stage"] == "approval_wait" and missions[ORPHAN]["stage"] == "building"


def test_reviewer_case_orphan_not_a_sha_keeps_record_and_alert(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The exact finding: orphan #7 with ``head.sha="not-a-sha"`` beside valid linked #5."""
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    planted = _plant_state(st)
    _world(st)
    st.gh[sweep_path(ATO)] = [open_pull(5), open_pull(7, sha="not-a-sha")]
    out = run(st)
    missions, alerts, shown = _after(st)
    assert out["complete"] is False and out["incomplete"].get(ATO) == "malformed_sha"
    assert missions[ORPHAN] == planted["missions"][ORPHAN] and f"k-{ORPHAN}" in alerts
    assert any(a.get("mission_id") == ORPHAN and a.get("code") == "EVIDENCE_UNKNOWN" for a in shown)


@pytest.mark.parametrize("head", [None, {"sha": ""}, {"sha": None}, {}], ids=["head_null", "sha_empty", "sha_null",
                                                                            "sha_absent"])
@pytest.mark.parametrize("author", ["User", "Bot"])
def test_neighbours_orphan_with_no_head_is_missing_commit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                          head: object, author: str) -> None:
    """Spec row 4 comes before rows 13 and 14: an open PR with no head SHA is MISSING_COMMIT, bot or not."""
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    _plant_state(st)
    _world(st)
    st.gh[sweep_path(ATO)] = [open_pull(5), {**open_pull(7, user_type=author), "head": head}]
    out = run(st)
    missions, alerts, shown = _after(st)
    assert out["complete"] is True
    record = missions[ORPHAN]
    assert (record["stage"], record["reason"], record["pr_head_sha"]) == ("missing_commit", "empty_head", None)
    assert any(a.get("mission_id") == ORPHAN and a.get("code") == "MISSING_COMMIT" for a in shown)
    assert missions["RA-1"]["stage"] == "review_wait"  # the valid linked PR beside it is still judged


@pytest.mark.parametrize("value", [v for _, v in NEGATIVES["enum"]] + ["AHEAD", "", None],
                         ids=[k for k, _ in NEGATIVES["enum"]] + ["wrong_case", "empty", "null"])
def test_bad_compare_status_never_verifies_live(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: object) -> None:
    own = "d" * 40
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", own)
    st.gh[sweep_path(PIDEV)] = []
    st.gh.update(merged_paths(PIDEV, 4, SHA_B))
    st.gh[f"/repos/{PIDEV}/compare/{SHA_B}...{own}"] = {"status": value}
    st.gql_pages.append(linear_page([tick_issue("RA-4", ((PIDEV, 4),))]))
    out = run(st)
    record = _after(st)[0]["RA-4"]
    assert "error" not in out and record["verified_sha"] is None and record["deployed_sha"] is None
