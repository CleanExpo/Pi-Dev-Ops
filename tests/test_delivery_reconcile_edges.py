"""RA-8100 B4b: reconcile tick edges (spec ids E3, E4, E5, E6, E10 corrupt file, missing key, unread links)."""
from __future__ import annotations

import functools
import json
import sys
import types
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.server import delivery_collect as collect
from app.server import delivery_reconcile as dr
from app.server import delivery_reconcile_store as store
from tests._delivery_reconcile_support import (
    ATO, NOW, PIDEV, SHA_B, linear_page, open_pull, pr_paths, reg_entry, run, setup_tick, stored, sweep_path,
    tick_issue,
)

ENTRIES = [reg_entry("pi-dev-ops", PIDEV), reg_entry("ato", ATO)]


def _state(st: SimpleNamespace) -> dict:
    return json.loads(Path(st.path).read_text(encoding="utf-8"))


def _plant(st: SimpleNamespace) -> dict:
    planted = store.empty_state()
    planted["missions"] = {"RA-OLD": stored({"id": "RA-OLD", "kind": "mission", "stage": "review_wait"})}
    planted["alerts"] = {"k-old": stored({"key": "k-old", "mission_id": "RA-OLD", "code": "STALE_24H"}, alert=True)}
    planted["checkpoint"]["last_complete"] = 1.0
    assert store.save(st.path, planted)
    return planted


def test_e3_timezone_less_mission_is_unknown_others_classify(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES[:1])
    st.gh.update({**pr_paths(PIDEV, 7), **pr_paths(PIDEV, 8, SHA_B)})
    st.gh[sweep_path(PIDEV)] = [open_pull(7), open_pull(8, SHA_B)]
    naive = tick_issue("RA-1", ((PIDEV, 7),), state="completed", completed=2)
    naive["completedAt"] = "2026-11-15T01:00:00"
    st.gql_pages.append(linear_page([naive, tick_issue("RA-2", ((PIDEV, 8),))]))
    out = run(st)
    missions = _state(st)["missions"]
    assert out["complete"] is True and out["persisted"] is True
    assert missions["RA-1"]["stage"] == "unknown" and missions["RA-1"]["reason"] == "bad_timestamp"
    assert missions["RA-2"]["stage"] == "review_wait"


def test_e4_registry_unreadable_drops_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    from app.server import config_loader

    monkeypatch.setattr(config_loader, "PROJECTS_JSON", tmp_path / "missing.json")
    planted = _plant(st)
    out = run(st)
    assert out.get("error") == "registry_unreadable" and out["complete"] is False and out["persisted"] is True
    after = _state(st)
    assert after["missions"] == planted["missions"] and set(after["alerts"]) == {"k-old"}
    assert after["checkpoint"] == planted["checkpoint"] and after["summary"]["error"] == "registry_unreadable"
    assert st.gql == st.github == st.vercel == st.net == []


def test_missing_linear_key_reads_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    monkeypatch.delenv("LINEAR_API_KEY")
    fake = types.ModuleType("app.server.config")
    fake.LINEAR_API_KEY = "  "  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.server.config", fake)
    monkeypatch.setattr(sys.modules["app.server"], "config", fake, raising=False)
    planted = _plant(st)
    out = run(st)
    assert out.get("error") == "no_linear_key" and out["complete"] is False and out["persisted"] is True
    assert _state(st)["missions"] == planted["missions"]
    assert st.gql == st.github == st.vercel == st.net == []


def test_e5_ccw_entry_any_case_is_never_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    entries = [reg_entry("pi-dev-ops", PIDEV), reg_entry("crm-mixed", "CleanExpo/ccw-CRM")]
    st = setup_tick(monkeypatch, tmp_path, entries)
    st.gh[sweep_path(PIDEV)] = []
    st.gql_pages.append(linear_page([]))
    out = run(st)
    assert out["complete"] is True and out["skipped_repos"] == ["CleanExpo/ccw-CRM"]
    assert [v["projectId"] for _, v in st.gql] == ["proj-pi-dev-ops"]
    assert [p for p in st.github if "ccw" in p.lower()] == [] and st.vercel == []
    state = _state(st)
    assert "ccw" not in json.dumps([state["missions"], state["alerts"]]).lower()
    assert "crm-mixed" not in json.dumps(out)


def _two_missions(st: SimpleNamespace, ticks: int) -> None:
    st.gh.update({**pr_paths(PIDEV, 7), **pr_paths(PIDEV, 8, SHA_B)})
    st.gh[sweep_path(PIDEV)] = [open_pull(7), open_pull(8, SHA_B)]
    page = linear_page([tick_issue("RA-1", ((PIDEV, 7),)), tick_issue("RA-2", ((PIDEV, 8),))])
    st.gql_pages.extend([page] * ticks)


def test_e6_budget_cut_keeps_records_and_reads_oldest_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES[:1])
    _two_missions(st, 3)
    run(st)
    monkeypatch.setitem(collect.BUDGETS, "github", 6)
    st.github.clear()
    t2 = NOW + timedelta(minutes=15)
    out = run(st, t2)
    assert out["complete"] is True and out["not_refreshed"] == 1 and out["not_refreshed_ids"] == ["RA-2", f"repo:{PIDEV}"]
    assert len(st.github) == 6 and not [p for p in st.github if "/pulls/8" in p]
    state = _state(st)
    assert state["missions"]["RA-2"]["refreshed_at"] == NOW.timestamp()
    assert state["missions"]["RA-1"]["refreshed_at"] == t2.timestamp()
    assert any(a["mission_id"] == "RA-2" for a in state["alerts"].values())
    assert "RA-2" in [i["ref"] for i in dr.status_snapshot(st.path, t2)["items"]]
    out3 = run(st, t2 + timedelta(minutes=15))
    assert out3["not_refreshed_ids"] == ["RA-1", f"repo:{PIDEV}"]  # the repo record is derived from it: held too


def _clock_patch(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [0.0]
    monkeypatch.setattr(collect, "Tick", functools.partial(collect.Tick, clock=lambda: now[0]))
    return now


def test_e6_clock_past_limit_stops_reads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    clock = _clock_patch(monkeypatch)
    st.after_gql = lambda _st: clock.__setitem__(0, 91.0)
    st.gql_pages.append(linear_page([]))
    out = run(st)
    assert len(st.gql) == 1 and st.github == [] and st.net == []
    assert out["complete"] is False and out["incomplete"]["ato"] == "clock"


def test_e6_linear_budget_cut_is_incomplete(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    monkeypatch.setitem(collect.BUDGETS, "linear", 1)
    st.gh[sweep_path(PIDEV)] = []
    st.gh[sweep_path(ATO)] = []
    st.gql_pages.append(linear_page([]))
    out = run(st)
    assert len(st.gql) == 1 and out["complete"] is False and out["incomplete"] == {"ato": "budget_linear"}


def test_e6_open_pr_sweep_cut_is_incomplete(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES[:1])
    monkeypatch.setitem(collect.BUDGETS, "github", 0)
    st.gql_pages.append(linear_page([]))
    planted = _plant(st)
    out = run(st)
    assert st.github == [] and out["complete"] is False and out["incomplete"] == {PIDEV: "budget_github"}
    assert _state(st)["checkpoint"] == planted["checkpoint"] and "RA-OLD" in _state(st)["missions"]


def test_e10_corrupt_state_file_untouched_by_tick_and_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    Path(st.path).write_bytes(b'{"missions": [not json')
    out = run(st)
    assert out == {"error": "state_unreadable", "complete": False, "persisted": False}
    assert Path(st.path).read_bytes() == b'{"missions": [not json'
    assert dr.status_snapshot(st.path, NOW)["state"] == "unreadable"
    assert Path(st.path).read_bytes() == b'{"missions": [not json'
    assert st.gql == st.github == st.net == []


def test_unread_links_skip_orphans_and_keep_stored_orphans(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A mission whose attachments did not arrive whole may link any open PR: no PR is called unowned."""
    st = setup_tick(monkeypatch, tmp_path, ENTRIES[:1])
    st.gh[sweep_path(PIDEV)] = [open_pull(9)]
    st.gql_pages += [linear_page([]), linear_page([tick_issue("RA-1", links_whole=False)])]
    run(st)
    orphan_id = f"pr:{PIDEV}#9"
    assert orphan_id in _state(st)["missions"]
    out = run(st, NOW + timedelta(minutes=15))
    state = _state(st)
    # D48: a cut link list makes the tick incomplete
    assert out["complete"] is False and out["incomplete"] == {"RA-1": "links_incomplete"}
    assert state["missions"][orphan_id]["refreshed_at"] == NOW.timestamp()
    assert not [a for a in state["alerts"].values()
                if a["mission_id"] == orphan_id and a["last_seen"] == state["last_tick"]]
    assert orphan_id in state["summary"]["not_refreshed_ids"]  # so the tile still shows its alert
    shown = dr.status_snapshot(path=st.path, now=NOW + timedelta(minutes=16))["counts"]["by_code"]
    assert shown.get("UNOWNED") == 1
