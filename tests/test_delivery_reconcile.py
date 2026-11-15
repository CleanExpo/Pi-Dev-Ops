"""RA-8100 B4b: the read-only reconcile tick (spec ids T1, T2, T6, T7, T8, T9, T10)."""
from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
import threading
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.server import delivery_reconcile as dr
from app.server import delivery_reconcile_store as store
from app.server.delivery_closure import finding_key
from tests._delivery_reconcile_support import (
    ATO, NOW, PIDEV, REPO_ROOT, linear_page, open_pull, pr_paths, reg_entry, run, setup_tick,
    sweep_path, tick_issue,
)

ENTRIES = [reg_entry("pi-dev-ops", PIDEV), reg_entry("ato", ATO)]


def _t1_world(st: SimpleNamespace, ticks: int = 1) -> None:
    """RA-1 links open PR 7; PR 9 is an unlinked human PR in the same swept repo."""
    st.gh.update(pr_paths(PIDEV, 7))
    st.gh[sweep_path(PIDEV)] = [open_pull(7), open_pull(9)]
    st.gh[sweep_path(ATO)] = []
    st.gql_pages.extend([linear_page([tick_issue("RA-1", ((PIDEV, 7),))]), linear_page([])] * ticks)


def _state(st: SimpleNamespace) -> dict:
    return json.loads(Path(st.path).read_text(encoding="utf-8"))


def test_t1_mission_stored_with_pr_and_unlinked_pr_unowned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    _t1_world(st)
    out = run(st)
    assert out["complete"] is True and out["persisted"] is True
    missions = _state(st)["missions"]
    assert missions["RA-1"]["prs"] == [{"repo": PIDEV, "number": 7, "state": "open"}]
    assert missions["RA-1"].get("refreshed_at") == NOW.timestamp()
    orphan = missions[f"pr:{PIDEV}#9"]
    assert orphan["kind"] == "orphan_pr"
    codes = {a["code"] for a in _state(st)["alerts"].values() if a["mission_id"] == f"pr:{PIDEV}#9"}
    assert {"UNOWNED", "UNOWNED_24H"} <= codes
    assert st.net == [] and f"/repos/{PIDEV}/pulls/9" not in st.github


def test_t2_restored_job_keeps_first_seen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    _t1_world(st, ticks=2)
    first = run(st)
    before = _state(st)
    assert first["new_alerts"] == len(before["alerts"]) > 0
    assert before["checkpoint"]["last_complete"] == NOW.timestamp()
    from app.server import delivery_reconcile_gather, delivery_reconcile_status, delivery_reconcile_tick

    for mod in (store, delivery_reconcile_status, delivery_reconcile_gather, delivery_reconcile_tick, dr):
        importlib.reload(mod)
    later = NOW + timedelta(minutes=15)
    second = run(st, later)
    after = _state(st)
    assert second["new_alerts"] == 0 and set(after["alerts"]) == set(before["alerts"])
    for key, alert in after["alerts"].items():
        assert alert["first_seen"] == before["alerts"][key]["first_seen"] == NOW.timestamp()
        assert alert["count"] == 2
    assert after["checkpoint"]["last_complete"] == later.timestamp()


def _stored_key_ok(state: dict) -> None:
    for key, alert in state["alerts"].items():
        rec = state["missions"][alert["mission_id"]]
        head = rec.get("pr_head_sha") if rec["kind"] != "repo" else rec.get("live_unconfirmed")
        stage = "unknown" if rec["stage"] == "missing_commit" else rec["stage"]
        assert key == finding_key(alert["mission_id"], stage, head, alert["code"])


def test_t6_idempotent_ticks_and_one_lease(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    _t1_world(st, ticks=7)
    for i in range(5):
        run(st, NOW + timedelta(minutes=i))
    once = _state(st)
    entered, release, results = threading.Event(), threading.Event(), []

    def hold(_st: SimpleNamespace) -> None:
        if not entered.is_set():
            entered.set()
            release.wait(10)

    st.after_gql = hold
    first = threading.Thread(target=lambda: results.append(run(st, NOW + timedelta(minutes=6))))
    first.start()
    assert entered.wait(10)
    second = threading.Thread(target=lambda: results.append(run(st, NOW + timedelta(minutes=7))))
    second.start()
    second.join(10)
    release.set()
    first.join(10)
    assert [r for r in results if r == {"skipped": "lease_held"}] == [{"skipped": "lease_held"}]
    final = _state(st)
    assert set(final["missions"]) == set(once["missions"]) and set(final["alerts"]) == set(once["alerts"])
    assert all(a["count"] == 6 for a in final["alerts"].values())
    _stored_key_ok(final)


def test_t7_three_day_overdue_reaches_status_items(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES[:1])
    st.gh.update(pr_paths(PIDEV, 7, check_done=72))
    st.gh[sweep_path(PIDEV)] = [open_pull(7)]
    st.gql_pages.append(linear_page([tick_issue("RA-7", ((PIDEV, 7),))]))
    out = run(st)
    founder = [a for a in _state(st)["alerts"].values() if a["severity"] == "founder" and a["ref"] == "RA-7"]
    assert founder and "RA-7" in out["founder_or_critical"]
    items = [i for i in dr.status_snapshot(st.path, NOW)["items"] if i["ref"] == "RA-7"]
    assert items and abs(items[0]["age_hours"] - 72) < 0.5
    assert items[0]["url"] == f"https://github.com/{PIDEV}/pull/7"


def test_t8_second_page_failure_keeps_missions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    links = {"RA-1": (PIDEV, 1), "RA-9": (PIDEV, 2), "RA-5": (ATO, 5)}  # linked PRs, so each mission is stored
    st.gh[sweep_path(PIDEV)] = [open_pull(1), open_pull(2)]
    st.gh[sweep_path(ATO)] = [open_pull(5)]
    for repo, number in links.values():
        st.gh.update(pr_paths(repo, number))
    st.gql_pages += [linear_page([tick_issue(m, (links[m],)) for m in ("RA-1", "RA-9")]),
                     linear_page([tick_issue("RA-5", (links["RA-5"],))])]
    run(st)
    checkpoint = _state(st)["checkpoint"]
    assert checkpoint["last_complete"] == NOW.timestamp()  # D48: link lists whole, so the first tick is complete
    st.gql_pages += [linear_page([tick_issue("RA-1", (links["RA-1"],))], "cursor-1"), RuntimeError("boom"),
                     linear_page([tick_issue("RA-5", (links["RA-5"],))])]
    out = run(st, NOW + timedelta(minutes=15))
    assert out["complete"] is False and out["incomplete"] == {"pi-dev-ops": "error_RuntimeError"}
    after = _state(st)
    assert after["checkpoint"] == checkpoint
    assert {"RA-1", "RA-9", "RA-5"} <= set(after["missions"])


def test_t9_failed_save_leaves_file_and_reports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    _t1_world(st, ticks=2)
    run(st)
    before = Path(st.path).read_bytes()

    def refuse(*_a: object, **_k: object) -> None:
        raise OSError("planted")

    monkeypatch.setattr(store.os, "replace", refuse)
    out = run(st, NOW + timedelta(minutes=15))
    assert out["persisted"] is False
    assert Path(st.path).read_bytes() == before
    snap = dr.status_snapshot(st.path, NOW + timedelta(minutes=16))
    assert "state_write_failed" in snap["errors"] and snap["complete"] is False
    assert [p.name for p in Path(st.path).parent.iterdir() if p.suffix == ".tmp"] == []


NEW_MODULES = ["delivery_reconcile_tick", "delivery_reconcile_gather"] + sorted(
    p.stem for p in (REPO_ROOT / "app/server").glob("delivery_reconcile_*.py")
    if p.stem not in ("delivery_reconcile_tick", "delivery_reconcile_gather", "delivery_reconcile_store",
                      "delivery_reconcile_status"))
WRITE_MODULES = ("supabase", "ticket_sweeper_write", "session_linear", "ship_gate", "telegram", "slack",
                 "linear_pulse")
FORBIDDEN = re.compile(r"urlopen|\brequests\b|httpx|github_post|github_get|_vercel_get|_gql\(|linear_pulse"
                       r"|\b(?:http_)?(?:post|put|patch|delete)\(")


@pytest.mark.parametrize("module", NEW_MODULES)
def test_t10_import_pulls_in_no_write_helper(module: str) -> None:
    code = f"import json, sys, app.server.{module}; print(json.dumps(sorted(sys.modules)))"
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-500:]
    mods = json.loads(out.stdout.strip().splitlines()[-1])
    assert [m for m in mods if m.startswith("app.") and any(w in m for w in WRITE_MODULES)] == []


@pytest.mark.parametrize("module", NEW_MODULES)
def test_t10_source_reaches_services_only_through_collector(module: str) -> None:
    text = (REPO_ROOT / f"app/server/{module}.py").read_text(encoding="utf-8")
    assert FORBIDDEN.findall(text) == []
