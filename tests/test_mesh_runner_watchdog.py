"""tests/test_mesh_runner_watchdog.py — a dead runner pages (RA-7910 follow-up).

Pins, node side (mesh/node_health.runner_down + heartbeat status):
  * a breadcrumb older than 15 min is a dead runner; a fresh one is not;
  * an old "working" breadcrumb with a live agent is a long build, not dead;
  * no breadcrumb means no runner on the node, never "down".
Server side (app/server/cron_watchdog_mesh):
  * runner-down and silent nodes page once per outage, with a ticket;
  * recovery is announced and clears the ticket memory;
  * an unreadable fleet is a problem, never "all healthy".
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "mesh"))

import node_health  # noqa: E402
from app.server import cron_watchdog_mesh as wd  # noqa: E402

NOW = 1_800_000_000.0
LOG = logging.getLogger("test")


def _crumb(tmp_path, age_s: float, state: str = "idle") -> str:
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"state": state, "ts": NOW - age_s}))
    return str(p)


# ── node side ────────────────────────────────────────────────────────────────

def test_a_stale_idle_breadcrumb_is_a_dead_runner(tmp_path):
    assert node_health.runner_down(_crumb(tmp_path, 901), [], now=lambda: NOW) is True


def test_a_fresh_breadcrumb_is_alive(tmp_path):
    assert node_health.runner_down(_crumb(tmp_path, 60), [], now=lambda: NOW) is False


def test_a_long_build_with_a_live_agent_is_not_down(tmp_path):
    path = _crumb(tmp_path, 3600, state="working")
    assert node_health.runner_down(path, [{"runtime": "claude"}], now=lambda: NOW) is False
    # ...but the same breadcrumb with no agent running means the runner died mid-task.
    assert node_health.runner_down(path, [], now=lambda: NOW) is True


@pytest.mark.parametrize("content", [None, "not json", "[]", '{"ts": "x"}'])
def test_no_readable_breadcrumb_is_never_down(tmp_path, content):
    p = tmp_path / "state.json"
    if content is not None:
        p.write_text(content)
    assert node_health.runner_down(str(p), [], now=lambda: NOW) is False


def test_heartbeat_reports_runner_down_above_everything():
    import heartbeat as hb
    assert hb.node_status([], {"state": "quarantined"}, True) == "runner-down"
    assert hb.node_status([], {"state": "quarantined"}) == "quarantined"


# ── server side ──────────────────────────────────────────────────────────────

def _iso(age_s: float) -> str:
    return datetime.fromtimestamp(NOW - age_s, tz=timezone.utc).isoformat()


def _fetch(rows=None, status=200):
    return lambda path: (status, json.dumps(rows if rows is not None else []))


@pytest.fixture
def sent(monkeypatch):
    wd._filed.clear()
    wd._active.clear()
    log = {"telegram": [], "tickets": []}
    monkeypatch.setattr(wd, "_telegram", lambda k, m, lg, severity="high": log["telegram"].append((k, severity)))

    def ticket(k, m, lg):
        log["tickets"].append(k)
        wd._filed.add(k)
    monkeypatch.setattr(wd, "_ticket", ticket)
    return log


def test_runner_down_pages_once_with_one_ticket(sent):
    rows = [{"host": "Phills-Mac-mini", "status": "runner-down", "last_seen": _iso(20)},
            {"host": "Phill_Desktop", "status": "online", "last_seen": _iso(20)}]
    assert list(wd.run(_fetch(rows), NOW, LOG)) == ["runner-down:Phills-Mac-mini"]
    wd.run(_fetch(rows), NOW, LOG)
    assert sent["tickets"] == ["runner-down:Phills-Mac-mini"]  # not re-filed next cycle


def test_a_silent_node_pages(sent):
    rows = [{"host": "Phills-MacBook-Pro", "status": "online", "last_seen": _iso(1200)}]
    found = wd.run(_fetch(rows), NOW, LOG)
    assert "silent:Phills-MacBook-Pro" in found and "20 min" in found["silent:Phills-MacBook-Pro"]


def test_recovery_is_announced_and_a_second_outage_files_again(sent):
    down = [{"host": "h", "status": "runner-down", "last_seen": _iso(5)}]
    up = [{"host": "h", "status": "online", "last_seen": _iso(5)}]
    wd.run(_fetch(down), NOW, LOG)
    assert wd.run(_fetch(up), NOW, LOG) == {}
    assert ("runner-down:h", "info") in sent["telegram"]
    wd.run(_fetch(down), NOW, LOG)
    assert sent["tickets"] == ["runner-down:h", "runner-down:h"]


@pytest.mark.parametrize("fetch", [_fetch(status=401), lambda p: (200, "<html>"), lambda p: (_ for _ in ()).throw(OSError())])
def test_an_unreadable_fleet_is_a_problem_not_healthy(sent, fetch):
    assert list(wd.run(fetch, NOW, LOG)) == ["fleet-read"]


def test_the_watchdog_runs_every_cycle():
    src = (REPO / "app" / "server" / "cron_scheduler.py").read_text()
    assert "await _watchdog_mesh_runners(log)" in src
