"""tests/test_mesh_dispatch_scheduled.py — the scheduled mesh dispatcher.

The mesh shipped a working dispatcher that nothing ever called, so an online
fleet stayed idle. These tests pin the pieces that make it fire on a schedule,
and — as CLAUDE.md § Evidence requires — every guard here is shown FAILING as
well as passing. A gate never seen to fail is not known to work:

  * the off switch is proven to stop a tick, AND the tick is proven to run
    when it is on (or "disabled" would pass for "broken");
  * the claim race is driven with a real 409 from the unique index, so the
    skip path is exercised rather than assumed.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import mesh_dispatch_service as svc  # noqa: E402
from app.server.cron_triggers import _fire_trigger, _matches  # noqa: E402


class _Log:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def _rec(self, msg, *args, **kw):
        self.lines.append(str(msg) % args if args else str(msg))

    info = warning = error = _rec


class _FakeMeshRoutes:
    """Stand-in for app.server.routes.mesh with a scripted Supabase."""

    _MESH_AUTO_QUERY = "query"

    def __init__(self, tickets, machines, conflict_on=()):
        self._tickets = tickets
        self._machines = machines
        self._conflict_on = set(conflict_on)
        self.claims: list[dict] = []
        self.reaped = 0
        self.in_progress: list[str] = []

    def _reap_sweep_best_effort(self):
        self.reaped += 1

    def _linear_graphql(self, _q):
        return {"issues": {"nodes": self._tickets}}

    def _online_machines(self):
        return self._machines

    def _open_claim_ids(self):
        return set()

    def _mark_issue_in_progress(self, ticket):
        self.in_progress.append(ticket.get("identifier"))
        return True

    def _sb(self, method, path, body=None, *, prefer=""):
        # The unique partial index answers a racing double-claim with 409.
        if body and body.get("linear_id") in self._conflict_on:
            return 409, '{"code":"23505"}'
        self.claims.append(body)
        return 201, ""


def _patch_routes(monkeypatch, fake):
    """run_dispatch_tick imports routes.mesh lazily; intercept that import."""
    import app.server.routes as routes_pkg
    monkeypatch.setattr(routes_pkg, "mesh", fake, raising=False)
    monkeypatch.setitem(sys.modules, "app.server.routes.mesh", fake)


def test_tick_spreads_work_least_loaded_first(monkeypatch):
    fake = _FakeMeshRoutes(
        tickets=[{"identifier": "RA-1"}, {"identifier": "RA-2"}, {"identifier": "RA-3"}],
        machines=[{"host": "mini"}, {"host": "macbook"}, {"host": "desktop"}],
    )
    _patch_routes(monkeypatch, fake)

    result = svc.run_dispatch_tick()

    assert [c["machine"] for c in fake.claims] == ["mini", "macbook", "desktop"]
    assert len(result["assigned"]) == 3
    assert result["online_machines"] == ["mini", "macbook", "desktop"]
    assert fake.reaped == 1, "a tick must sweep dead-runner claims before assigning"
    assert fake.in_progress == ["RA-1", "RA-2", "RA-3"], "claimed tickets must leave the pool"


def test_tick_skips_a_ticket_the_index_rejects(monkeypatch):
    """Positive control for the race path: a 409 must be skipped, not retried,
    and must NOT consume a machine slot or transition the Linear issue."""
    fake = _FakeMeshRoutes(
        tickets=[{"identifier": "RA-1"}, {"identifier": "RA-2"}],
        machines=[{"host": "mini"}, {"host": "macbook"}],
        conflict_on={"RA-1"},
    )
    _patch_routes(monkeypatch, fake)

    result = svc.run_dispatch_tick()

    assert [a["linear_id"] for a in result["assigned"]] == ["RA-2"]
    assert fake.in_progress == ["RA-2"], "a lost race must not move the other node's ticket"
    # RA-2 takes the first (least-loaded) machine: the loser must not burn a slot.
    assert fake.claims == [{"linear_id": "RA-2", "machine": "mini", "state": "claimed"}]


def test_tick_reports_when_no_machine_is_online(monkeypatch):
    fake = _FakeMeshRoutes(tickets=[{"identifier": "RA-1"}], machines=[])
    _patch_routes(monkeypatch, fake)

    result = svc.run_dispatch_tick()

    assert result == {"assigned": [], "online_machines": [], "reason": "no online machines"}
    assert fake.claims == []


def test_dispatch_enabled_is_off_by_default_and_honours_the_flag(monkeypatch):
    monkeypatch.delenv("MESH_DISPATCH_ENABLED", raising=False)
    assert svc.dispatch_enabled() is False
    monkeypatch.setenv("MESH_DISPATCH_ENABLED", "1")
    assert svc.dispatch_enabled() is True
    monkeypatch.setenv("MESH_DISPATCH_ENABLED", "0")
    assert svc.dispatch_enabled() is False


def test_cron_branch_runs_the_tick_when_enabled(monkeypatch):
    """The other half of the off-switch control: prove the trigger DOES fire."""
    calls: list = []
    monkeypatch.setenv("MESH_DISPATCH_ENABLED", "1")
    import app.server.cron_fire_mesh as cfm
    monkeypatch.setattr(cfm, "run_dispatch_tick", lambda ids: (
        calls.append(ids) or {"assigned": [{"linear_id": "RA-9", "machine": "mini"}],
                              "online_machines": ["mini"]}))

    log = _Log()
    asyncio.run(_fire_trigger({"id": "mesh-dispatch-every-5min", "type": "mesh_dispatch"}, log))

    assert calls == [None], "the tick must run once, with no explicit ticket list"
    assert any("assigned=1" in line for line in log.lines)


def test_cron_branch_skips_when_disabled(monkeypatch):
    calls: list = []
    monkeypatch.setenv("MESH_DISPATCH_ENABLED", "0")
    import app.server.cron_fire_mesh as cfm
    monkeypatch.setattr(cfm, "run_dispatch_tick", lambda ids: calls.append(ids))

    log = _Log()
    asyncio.run(_fire_trigger({"id": "mesh-dispatch-every-5min", "type": "mesh_dispatch"}, log))

    assert calls == [], "a disabled dispatcher must not assign work"
    assert any("MESH_DISPATCH_ENABLED" in line for line in log.lines)
    # A deliberate off switch is not a failure: raising would blank last_fired_at
    # and trip the cron watchdog. Reaching here without an exception is the check.


@pytest.mark.parametrize("minute,expected", [(0, True), (5, True), (55, True), (3, False), (7, False)])
def test_matches_supports_a_minute_list(minute, expected):
    trigger = {"enabled": True, "minute": [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]}
    assert _matches(trigger, 4, minute) is expected


def test_matches_still_takes_a_plain_int_minute():
    """Regression guard: every pre-existing trigger uses a scalar minute."""
    assert _matches({"enabled": True, "minute": 30}, 4, 30) is True
    assert _matches({"enabled": True, "minute": 30}, 4, 31) is False
    assert _matches({"enabled": True, "hour": 3, "minute": 0}, 4, 0) is False


def test_configured_mesh_trigger_is_wired_and_matches_every_five_minutes():
    """The row in cron-triggers.json must actually be dispatchable: a type the
    dispatcher knows, and a schedule _matches accepts."""
    import json
    raw = json.loads((REPO_ROOT / "config/harness/cron-triggers.json").read_text())
    rows = raw["triggers"] if isinstance(raw, dict) else raw
    mesh_rows = [t for t in rows if t.get("type") == "mesh_dispatch"]
    assert mesh_rows, "no mesh_dispatch trigger configured"
    for row in mesh_rows:
        assert row.get("enabled") is True
        fires = [m for m in range(60) if _matches(dict(row), 4, m)]
        assert fires == [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]
