"""RA-8100 B4a: delivery reconcile status snapshot (spec ids E10 status half, T7)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.server import delivery_reconcile as dr
from app.server import delivery_reconcile_store as store

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
TICK = NOW.timestamp() - 600


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAO_DELIVERY_RECONCILE", raising=False)
    monkeypatch.setattr(dr, "_last_save_ok", None)
    monkeypatch.setattr(dr, "_last_tick_error", None, raising=False)


def _alert(key: str, **over: Any) -> dict[str, Any]:
    a = {
        "key": key, "mission_id": f"M-{key}", "code": "CHECKS_GREEN_NO_REVIEW",
        "severity": "founder", "next_owner": "founder", "message": f"msg {key}",
        "ref": f"RA-{key}", "repo": "o/r", "since": (NOW - timedelta(hours=72)).isoformat(),
        "age_source": "checks_green", "url": f"https://example.test/{key}",
        "first_seen": TICK, "last_seen": TICK, "count": 1,
    }
    a.update(over)
    return a


def _write(path: Path, alerts: list[dict[str, Any]], last_tick: float | None = TICK,
           summary: dict[str, Any] | None = None) -> None:
    st = store.empty_state()
    st["alerts"] = {a["key"]: a for a in alerts}
    st["last_tick"] = last_tick
    if summary is not None:
        st["summary"] = summary
    assert store.save(path, st)


def _summary(**over: Any) -> dict[str, Any]:
    s: dict[str, Any] = {"complete": True, "not_refreshed_ids": [], "missions": 3,
                         "refs_outside_scope": 0, "bot_prs": 1, "closed_unmerged": 0,
                         "started_without_pr": 0, "completed_without_pr": 0,
                         "not_refreshed": 0, "vercel_unreadable": 0,
                         "skipped_repos": [], "unqueryable_projects": [], "incomplete": {}}
    s.update(over)
    return s


def test_e10_status_never_run_missing_file(tmp_path: Path) -> None:
    out = dr.status_snapshot(tmp_path / "none.json", NOW)
    assert set(out) == {"enabled", "state", "last_tick", "complete", "counts", "items", "errors"}
    assert out["state"] == "never_run" and out["complete"] is False
    assert out["last_tick"] is None and out["counts"] is None and out["items"] == []


def test_status_never_run_when_last_tick_none(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    _write(p, [_alert("A")], last_tick=None)
    out = dr.status_snapshot(p, NOW)
    assert out["state"] == "never_run" and out["counts"] is None and out["items"] == []
    assert out["complete"] is False


def test_e10_status_stale(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    old = NOW.timestamp() - 46 * 60
    _write(p, [_alert("A", last_seen=old)], old, _summary())
    out = dr.status_snapshot(p, NOW)
    assert out["state"] == "stale" and out["complete"] is False
    assert "stale_state" in out["errors"]
    _write(p, [], NOW.timestamp() - 44 * 60, _summary())
    assert dr.status_snapshot(p, NOW)["state"] == "ok"


@pytest.mark.parametrize("body", [b"{not json", b"", b"[]"])
def test_e10_status_unreadable_and_untouched(tmp_path: Path, body: bytes) -> None:
    p = tmp_path / "s.json"
    p.write_bytes(body)
    out = dr.status_snapshot(p, NOW)
    assert out["state"] == "unreadable" and out["errors"] == ["state_unreadable"]
    assert out["counts"] is None and out["complete"] is False
    assert p.read_bytes() == body
    assert sorted(x.name for x in tmp_path.iterdir()) == ["s.json"]


def test_t7_founder_alert_shown_with_age(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    _write(p, [_alert("A")], summary=_summary())
    out = dr.status_snapshot(p, NOW)
    assert out["state"] == "ok" and out["complete"] is True and out["errors"] == []
    assert out["items"] == [{
        "ref": "RA-A", "code": "CHECKS_GREEN_NO_REVIEW", "age_hours": 72.0,
        "age_source": "checks_green", "owner": "founder", "next_action": "msg A",
        "url": "https://example.test/A"}]
    assert out["counts"]["by_severity"] == {"founder": 1}
    assert out["counts"]["by_code"] == {"CHECKS_GREEN_NO_REVIEW": 1}
    assert out["counts"]["bot_prs"] == 1 and out["counts"]["missions"] == 3
    assert out["last_tick"] == datetime.fromtimestamp(TICK, timezone.utc).isoformat()


def test_t7_old_last_seen_not_shown_or_counted(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    _write(p, [_alert("A"), _alert("OLD", last_seen=TICK - 900, mission_id="M-OLD")],
           summary=_summary())
    out = dr.status_snapshot(p, NOW)
    assert [i["ref"] for i in out["items"]] == ["RA-A"]
    assert out["counts"]["by_severity"] == {"founder": 1}


def test_t7_not_refreshed_mission_alert_is_shown(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    _write(p, [_alert("OLD", last_seen=TICK - 900, mission_id="M-NR")],
           summary=_summary(not_refreshed_ids=["M-NR"], complete=False))
    out = dr.status_snapshot(p, NOW)
    assert [i["ref"] for i in out["items"]] == ["RA-OLD"]
    assert out["complete"] is False


def test_t7_item_cap_and_order_and_severity_filter(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    alerts = [_alert(f"F{i:02d}", since=(NOW - timedelta(hours=i + 1)).isoformat())
              for i in range(25)]
    alerts.append(_alert("WARN", severity="warning", since=(NOW - timedelta(hours=999)).isoformat()))
    alerts.append(_alert("CRIT", severity="critical", since=(NOW - timedelta(hours=500)).isoformat()))
    _write(p, alerts, summary=_summary())
    out = dr.status_snapshot(p, NOW)
    assert len(out["items"]) == 20
    assert out["items"][0]["ref"] == "RA-CRIT"
    hours = [i["age_hours"] for i in out["items"]]
    assert hours == sorted(hours, reverse=True)
    assert all(i["ref"] != "RA-WARN" for i in out["items"])
    assert out["counts"]["by_severity"] == {"founder": 25, "warning": 1, "critical": 1}


def test_age_hours_none_when_since_missing_or_bad(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    _write(p, [_alert("A", since=None), _alert("B", since="garbage")], summary=_summary())
    out = dr.status_snapshot(p, NOW)
    assert [i["age_hours"] for i in out["items"]] == [None, None]


def test_record_save_false_marks_incomplete(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    _write(p, [], summary=_summary())
    assert dr.status_snapshot(p, NOW)["complete"] is True
    dr.record_save(False)
    out = dr.status_snapshot(p, NOW)
    assert out["complete"] is False and "state_write_failed" in out["errors"]
    dr.record_save(True)
    out = dr.status_snapshot(p, NOW)
    assert out["complete"] is True and out["errors"] == []


def test_summary_incomplete_or_error_reported(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    _write(p, [], summary=_summary(complete=False, error="linear_unreadable"))
    out = dr.status_snapshot(p, NOW)
    assert out["complete"] is False and "linear_unreadable" in out["errors"]
    _write(p, [], summary=None)
    assert dr.status_snapshot(p, NOW)["complete"] is False


def test_status_reads_do_not_write_or_lease(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    _write(p, [_alert("A")], summary=_summary())
    before = p.read_bytes()
    with store.lease(tmp_path / "s.lock") as got:
        assert got
        dr.status_snapshot(p, NOW)
    assert p.read_bytes() == before
    assert sorted(x.name for x in tmp_path.iterdir()) == ["s.json", "s.lock"]


def test_state_paths_are_under_harness() -> None:
    assert dr.STATE_FILE.parts[-2:] == (".harness", "delivery-reconcile-state.json")
    assert dr.LOCK_FILE.name == "delivery-reconcile.lock"
    assert dr.LOCK_FILE.parent == dr.STATE_FILE.parent




def test_incomplete_tick_still_shows_unread_mission_alerts(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    old = _alert("OLD", last_seen=TICK - 900, mission_id="M-UNREAD")
    _write(p, [old], summary=_summary(complete=False, not_refreshed_ids=[]))
    out = dr.status_snapshot(p, NOW)
    assert [i["ref"] for i in out["items"]] == ["RA-OLD"]
    assert out["counts"]["by_severity"] == {"founder": 1} and out["complete"] is False
    _write(p, [old], summary=_summary(complete=True, not_refreshed_ids=[]))
    mirror = dr.status_snapshot(p, NOW)
    assert mirror["items"] == [] and mirror["counts"]["by_severity"] == {}
