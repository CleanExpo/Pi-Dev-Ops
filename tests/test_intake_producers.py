"""tests/test_intake_producers.py — UNI-2214 items 1 & 7.

The closed-loop spine drains a queue; these producers FEED it without Phill:
a daily cron heartbeat (item 7 cadence) and an hourly agent-ready Linear pull
(item 1). Proves both self-gate on CLOSED_LOOP_ENABLED, fire on cadence, dedup
Linear tickets, and never crash the cycle on an enqueue failure.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import closed_loop as CL  # noqa: E402
from swarm import config as CFG  # noqa: E402
from swarm import intake_producers as IP  # noqa: E402


@pytest.fixture
def spy_enqueue(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(CL, "enqueue_trigger",
                        lambda text, **kw: calls.append(text))
    return calls


@pytest.fixture(autouse=True)
def _enable_loop(monkeypatch):
    monkeypatch.setattr(CFG, "CLOSED_LOOP_ENABLED", True)


@pytest.fixture(autouse=True)
def _no_linear(monkeypatch):
    """Default: no Linear tickets, so heartbeat tests are isolated."""
    monkeypatch.setattr(IP, "_agent_ready_tickets", lambda: [])


def test_disabled_loop_is_total_noop(monkeypatch, spy_enqueue):
    monkeypatch.setattr(CFG, "CLOSED_LOOP_ENABLED", False)
    state: dict = {}
    assert IP.should_run(state) is False
    res = IP.run_cycle(state)
    assert res.enqueued == []
    assert spy_enqueue == []
    assert state == {}  # no cadence keys written


def test_heartbeat_fires_once_per_day(spy_enqueue):
    state: dict = {}
    assert IP.should_run(state) is True

    res = IP.run_cycle(state)
    assert "heartbeat" in res.sources
    assert len(spy_enqueue) == 1
    assert IP.HEARTBEAT_STATE_KEY in state

    # Same day → heartbeat no longer due, no second enqueue.
    res2 = IP.run_cycle(state)
    assert "heartbeat" not in res2.sources
    assert len(spy_enqueue) == 1


def test_heartbeat_fires_again_next_day(spy_enqueue):
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    state = {IP.HEARTBEAT_STATE_KEY: yesterday,
             # keep linear from also firing in this heartbeat-focused test
             IP.LINEAR_STATE_KEY: datetime.now(timezone.utc).isoformat()}
    res = IP.run_cycle(state)
    assert "heartbeat" in res.sources
    assert len(spy_enqueue) == 1


def test_linear_intake_enqueues_new_tickets_and_dedups(monkeypatch, spy_enqueue):
    monkeypatch.setattr(IP, "_agent_ready_tickets",
                        lambda: [("UNI-100", "Wire X"), ("UNI-101", "Fix Y")])
    # Heartbeat already done today so we isolate the Linear arm.
    state = {IP.HEARTBEAT_STATE_KEY: datetime.now(timezone.utc).date().isoformat()}

    res = IP.run_cycle(state)
    assert sorted(res.sources) == ["linear:UNI-100", "linear:UNI-101"]
    assert any("UNI-100" in t for t in spy_enqueue)
    assert set(state[IP.SEEN_IDS_KEY]) == {"UNI-100", "UNI-101"}

    # Force the hourly gate open again; same tickets must NOT re-enqueue.
    state[IP.LINEAR_STATE_KEY] = (
        datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    spy_enqueue.clear()
    res2 = IP.run_cycle(state)
    assert res2.sources == []
    assert spy_enqueue == []


def test_linear_respects_hourly_gate(monkeypatch, spy_enqueue):
    monkeypatch.setattr(IP, "_agent_ready_tickets",
                        lambda: [("UNI-200", "New")])
    state = {
        IP.HEARTBEAT_STATE_KEY: datetime.now(timezone.utc).date().isoformat(),
        IP.LINEAR_STATE_KEY: datetime.now(timezone.utc).isoformat(),  # just ran
    }
    res = IP.run_cycle(state)
    assert res.sources == []  # within the hour → skipped
    assert spy_enqueue == []


def test_enqueue_failure_does_not_crash(monkeypatch):
    monkeypatch.setattr(CL, "enqueue_trigger",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    state: dict = {}
    # Must not raise; cadence state still advances so it doesn't hot-loop.
    res = IP.run_cycle(state)
    assert res.enqueued == []
    assert IP.HEARTBEAT_STATE_KEY in state
