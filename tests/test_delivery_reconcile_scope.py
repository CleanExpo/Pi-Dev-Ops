"""RA-8100 B4b: reconcile tick scope (spec ids F1 real registry, F2 link scope, G3 live source per tick)."""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.server import delivery_collect as collect
from app.server import delivery_reconcile as dr
from app.server import delivery_reconcile_store as store
from app.server import delivery_stage as stage
from tests._delivery_reconcile_support import (
    API_KEY, ATO, HTTP404, NOW, PIDEV, SHA_A, SHA_B, linear_page, merged_paths, open_pull, pr_paths, reg_entry,
    run, setup_tick, sweep_path, tick_issue,
)


def _state(st: SimpleNamespace) -> dict:
    return json.loads(Path(st.path).read_text(encoding="utf-8"))


def test_f1_real_registry_complete_and_retention(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, None)
    registry = collect.load_registry()
    st.gql_pages.extend(linear_page([]) for _ in registry.queryable)
    st.gh.update({sweep_path(repo): [] for repo in registry.swept})
    planted = store.empty_state()
    planted["missions"] = {"GONE-1": {"id": "GONE-1", "kind": "mission", "project_id": "removed-project"}}
    planted["alerts"] = {"k-gone": {"key": "k-gone", "mission_id": "GONE-1", "code": "STALE_24H"}}
    assert store.save(st.path, planted)
    out = run(st)
    assert out["complete"] is True and out["persisted"] is True and out["incomplete"] == {}
    assert "oh-my-codex" in out["unqueryable_projects"]
    state = _state(st)
    assert state["checkpoint"]["last_complete"] == NOW.timestamp()
    # B5g round 2: its project is not in the registry, so it was never read: held, never retired.
    assert state["missions"]["GONE-1"] == planted["missions"]["GONE-1"] and "k-gone" in state["alerts"]
    assert out["not_refreshed_ids"] == ["GONE-1"]
    assert len(st.gql) == len(registry.queryable) and st.net == []
    assert [p for p in st.github if "ccw" in p.lower()] == []


def test_f2_out_of_scope_links_never_read_or_stored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    st.gh[sweep_path(PIDEV)] = [open_pull(7)]
    st.gh.update(pr_paths(PIDEV, 7))
    refs = (("CleanExpo/CCW-CRM", 5), ("SomeoneElse/Unregistered-Repo", 6), (PIDEV, 7))
    st.gql_pages.append(linear_page([tick_issue("RA-1", refs)]))
    out = run(st)
    assert out["refs_outside_scope"] == 2 and out["complete"] is True
    assert [p for p in st.github if "ccw" in p.lower() or "unregistered" in p.lower()] == []
    text = Path(st.path).read_text(encoding="utf-8")
    assert "RA-1" in json.loads(text)["missions"]
    for needle in ("CCW-CRM", "ccw-crm", "Unregistered-Repo", "SECRET-DESCRIPTION-MARKER", API_KEY):
        assert needle not in text


def _g3_world(st: SimpleNamespace) -> None:
    st.gh[sweep_path(ATO)] = []
    st.gh.update(merged_paths(ATO, 4, merged=30))
    page = linear_page([tick_issue("RA-3", ((ATO, 4),))])
    st.gql_pages += [page, page]


def _shown(st: SimpleNamespace, mission_id: str) -> set[str]:
    state = _state(st)
    return {a["code"] for a in state["alerts"].values()
            if a["mission_id"] == mission_id and a["last_seen"] == state["last_tick"]}


def test_g3_live_source_change_takes_effect_next_tick(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("ato", ATO)])
    _g3_world(st)
    run(st)
    assert _shown(st, "RA-3") == {"LIVE_CANNOT_VERIFY"}
    assert "DEPLOY_UNVERIFIED_24H" not in dr.status_snapshot(st.path, NOW)["counts"]["by_code"]
    monkeypatch.setitem(stage.LIVE_SOURCE, ATO.lower(), "provable")
    later = NOW + timedelta(minutes=15)
    run(st, later)
    shown = _shown(st, "RA-3")
    assert "LIVE_CANNOT_VERIFY" not in shown and "DEPLOY_UNVERIFIED_24H" in shown
    by_code = dr.status_snapshot(st.path, later)["counts"]["by_code"]
    assert "LIVE_CANNOT_VERIFY" not in by_code and by_code.get("DEPLOY_UNVERIFIED_24H") == 1


def test_failed_pr_reads_become_error_items(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    st.gh.update(pr_paths(PIDEV, 7))
    st.gh[f"/repos/{PIDEV}/commits/{SHA_A}"] = HTTP404()
    st.gh[f"/repos/{PIDEV}/pulls/8"] = RuntimeError("down")
    st.gh[sweep_path(PIDEV)] = [open_pull(7), open_pull(8)]
    st.gql_pages.append(linear_page([tick_issue("RA-5", ((PIDEV, 7),)), tick_issue("RA-6", ((PIDEV, 8),))]))
    run(st)
    missions = _state(st)["missions"]
    assert (missions["RA-5"]["stage"], missions["RA-5"]["reason"]) == ("missing_commit", "head_not_found")
    assert (missions["RA-6"]["stage"], missions["RA-6"]["reason"]) == ("unknown", "error_RuntimeError")
    assert f"pr:{PIDEV}#8" not in missions


def _verified_world(st: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> str:
    own = "d" * 40
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", own)
    st.gh[sweep_path(PIDEV)] = []
    st.gh.update(merged_paths(PIDEV, 4, SHA_B))
    st.gh[f"/repos/{PIDEV}/compare/{SHA_B}...{own}"] = {"status": "ahead"}
    page = linear_page([tick_issue("RA-4", ((PIDEV, 4),))])
    st.gql_pages += [page, page]
    return own


def test_own_revision_compare_verifies_and_budget_cut_keeps_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    _verified_world(st, monkeypatch)
    run(st)
    assert _state(st)["missions"]["RA-4"]["verified_sha"] == SHA_B
    monkeypatch.setitem(collect.BUDGETS, "github", 2)
    out = run(st, NOW + timedelta(minutes=15))
    assert out["not_refreshed_ids"] == ["RA-4"]
    state = _state(st)
    assert state["missions"]["RA-4"]["verified_sha"] == SHA_B
    assert not [a for a in state["alerts"].values() if a["code"].startswith("DEPLOY_UNVERIFIED")]


def test_vercel_failure_is_counted_unreadable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = "CleanExpo/Synthex"  # live_unconfirmed: the only kind whose Vercel answer is used
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("syn", repo, vercel="prj_fake")])
    st.gh[sweep_path(repo)] = []
    st.vc["*"] = RuntimeError("down")
    st.gql_pages.append(linear_page([]))
    out = run(st)
    assert out["vercel_unreadable"] == 1 and len(st.vercel) == 1 and out["complete"] is True


def test_vercel_budget_spent_only_on_live_unconfirmed_repos(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    unused = ["CleanExpo/ATO", "CleanExpo/CARSI", "CleanExpo/DR-Sandbox", PIDEV]  # kinds none and provable
    used = ["CleanExpo/RestoreAssist", "CleanExpo/Synthex", "CleanExpo/Unite-Group"]  # live_unconfirmed
    entries = [reg_entry(f"p{i}", repo, vercel=f"prj_{i}") for i, repo in enumerate(unused + used)]
    st = setup_tick(monkeypatch, tmp_path, entries)
    st.gh.update({sweep_path(repo): [] for repo in unused + used})
    st.gql_pages.extend(linear_page([]) for _ in entries)
    st.vc["*"] = {"deployments": [{"state": "READY", "created": 1, "target": "production", "meta": {"githubCommitSha": SHA_A}}]}
    run(st)
    assert len(st.vercel) == len(used) and not any(f"projectId=prj_{i}&" in p for i in range(4) for p in st.vercel)
    missions = _state(st)["missions"]
    assert [missions[f"repo:{repo}"]["live_unconfirmed"] for repo in used] == [SHA_A] * 3
