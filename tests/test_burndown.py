"""tests/test_burndown.py — RA-6670 bounded daily P3 backlog-burndown.

Mocks the Linear transport + the work/close seams so tests run in milliseconds
without hitting the real API or spawning real build sessions. Pins:
  * No-API-key path returns structured error, claims nothing
  * cap=0 dry-run: fetches candidates but claims none (proves wiring, no spend)
  * Ranks P3 candidates by recency and respects the cap
  * Work-vs-close branch: engineering ticket → worked; no-code → closed
  * Hard-stop file halts the run before the next build session
  * Canceled-state-not-found is recorded, not crashed
  * Telegram summary is edge-triggered (identical signature → no second ping)
  * Cron dispatcher shim invokes run_burndown
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import autonomy, burndown, config, discovery_archive  # noqa: E402


_ONE_PROJECT = [{
    "name": "pi-dev-ops",
    "project_id": "proj-RA",
    "repo_url": "https://github.com/CleanExpo/Pi-Dev-Ops",
    "team_id": "team-RA",
}]


def _issue(i: int, *, updated: str, labels: list[str] | None = None) -> dict:
    return {
        "id": f"iss-{i}",
        "identifier": f"RA-{9000 + i}",
        "title": f"P3 finding {i}",
        "description": "",
        "priority": 3,
        "url": f"https://linear.app/x/RA-{9000 + i}",
        "updatedAt": updated,
        "state": {"id": "s1", "name": "Todo", "type": "unstarted"},
        "labels": {"nodes": [{"name": n} for n in (labels or [])]},
    }


def _patch_fetch(monkeypatch, issues: list[dict]):
    """Wire _load_portfolio_projects + autonomy._gql to return `issues`."""
    monkeypatch.setattr(autonomy, "_load_portfolio_projects", lambda: _ONE_PROJECT)

    def fake_gql(api_key, query, variables=None):
        return {"project": {"issues": {"nodes": issues}}}

    monkeypatch.setattr(autonomy, "_gql", fake_gql)


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch, tmp_path):
    """Each test gets a private state file + a fake Telegram sender + key."""
    monkeypatch.setattr(burndown, "_STATE_FILE", tmp_path / "burndown-state.json")
    monkeypatch.setattr(config, "LINEAR_API_KEY", "fake-key")
    monkeypatch.setattr(autonomy, "_send_watchdog_telegram", lambda *_a, **_k: None)


# ── No API key ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_api_key(monkeypatch):
    monkeypatch.setattr(config, "LINEAR_API_KEY", "")
    report = await burndown.run_burndown(cap=5)
    assert "no_linear_api_key" in report.errors
    assert report.worked == [] and report.closed == []


# ── Dry-run (cap=0) ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cap_zero_dry_run(monkeypatch):
    _patch_fetch(monkeypatch, [_issue(i, updated=f"2026-06-2{i}T00:00:00Z") for i in range(3)])
    report = await burndown.run_burndown(cap=0)
    assert report.candidates == 3           # fetch still happens
    assert report.worked == [] and report.closed == []   # nothing claimed
    assert report.errors == []


# ── Rank + cap ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ranks_by_recency_and_caps(monkeypatch):
    # 6 candidates with ascending timestamps; cap=3 should take the 3 newest.
    issues = [_issue(i, updated=f"2026-06-{10 + i:02d}T00:00:00Z") for i in range(6)]
    _patch_fetch(monkeypatch, issues)
    worked = []

    async def fake_process(cfg, create_session, issue):
        worked.append(issue["identifier"])

    monkeypatch.setattr(autonomy, "_process_autonomy_issue", fake_process)

    report = await burndown.run_burndown(cap=3)
    assert len(report.worked) == 3
    # Newest three are i=5,4,3 → RA-9005, RA-9004, RA-9003
    assert report.worked == ["RA-9005", "RA-9004", "RA-9003"]


# ── Work vs close branch ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_work_vs_close_branch(monkeypatch):
    issues = [
        _issue(1, updated="2026-06-20T00:00:00Z"),                      # engineering → worked
        _issue(2, updated="2026-06-19T00:00:00Z", labels=["no-code"]),  # unworkable → closed
    ]
    _patch_fetch(monkeypatch, issues)

    monkeypatch.setattr(autonomy, "_process_autonomy_issue", AsyncMock())
    monkeypatch.setattr(discovery_archive, "_resolve_canceled_state_id", lambda team_id: "cancel-uuid")
    closed_calls = []
    monkeypatch.setattr(
        discovery_archive, "_close_to_canceled",
        lambda iid, sid, body: closed_calls.append((iid, sid)) or True,
    )

    report = await burndown.run_burndown(cap=5)
    assert report.worked == ["RA-9001"]
    assert report.closed == ["RA-9002"]
    assert closed_calls == [("iss-2", "cancel-uuid")]


# ── Hard-stop halts the run ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hard_stop_halts_before_session(monkeypatch):
    _patch_fetch(monkeypatch, [_issue(1, updated="2026-06-20T00:00:00Z")])
    monkeypatch.setattr(autonomy, "_process_autonomy_issue", AsyncMock())

    from app.server import kill_switch
    def boom():
        raise kill_switch.KillSwitchAbort("HARD_STOP", {"file": "~/.claude/HARD_STOP"})
    monkeypatch.setattr(kill_switch, "check_hard_stop", boom)

    report = await burndown.run_burndown(cap=5)
    assert report.worked == []
    assert "hard_stop" in report.errors


# ── Canceled state missing ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_close_records_state_not_found(monkeypatch):
    _patch_fetch(monkeypatch, [_issue(1, updated="2026-06-20T00:00:00Z", labels=["no-code"])])
    monkeypatch.setattr(discovery_archive, "_resolve_canceled_state_id", lambda team_id: None)

    report = await burndown.run_burndown(cap=5)
    assert report.closed == []
    assert any("canceled_state_not_found:RA-9001" in e for e in report.errors)


# ── Edge-triggered Telegram ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_telegram_edge_triggered(monkeypatch):
    _patch_fetch(monkeypatch, [_issue(1, updated="2026-06-20T00:00:00Z")])
    monkeypatch.setattr(autonomy, "_process_autonomy_issue", AsyncMock())
    sent = {"n": 0}
    monkeypatch.setattr(autonomy, "_send_watchdog_telegram", lambda *_a, **_k: sent.__setitem__("n", sent["n"] + 1))

    r1 = await burndown.run_burndown(cap=5)
    first = burndown._maybe_send_telegram(r1)
    r2 = await burndown.run_burndown(cap=5)
    second = burndown._maybe_send_telegram(r2)   # identical signature → suppressed

    assert first is True and second is False
    assert sent["n"] == 1


@pytest.mark.asyncio
async def test_telegram_silent_on_no_activity(monkeypatch):
    _patch_fetch(monkeypatch, [])
    report = await burndown.run_burndown(cap=5)
    assert burndown._maybe_send_telegram(report) is False


# ── Cron dispatcher shim ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fire_burndown_trigger_invokes_run(monkeypatch):
    import logging
    captured = {"n": 0}

    async def fake_run(cap=None):
        captured["n"] += 1
        return burndown.BurndownReport(candidates=0)

    monkeypatch.setattr(burndown, "run_burndown", fake_run)
    await burndown._fire_burndown_trigger({"id": "burndown-daily", "type": "burndown"}, logging.getLogger("test"))
    assert captured["n"] == 1
