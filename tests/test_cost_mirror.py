"""tests/test_cost_mirror.py — the LLM cost mirror stays off the event loop."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def isolated_log(tmp_path, monkeypatch):
    """Point budget_tracker at a temp log path and reload."""
    log = tmp_path / "llm-cost.jsonl"
    monkeypatch.setenv("BUDGET_TRACKER_LOG_PATH", str(log))
    sys.modules.pop("swarm.budget_tracker", None)
    from swarm import budget_tracker  # noqa: PLC0415
    yield budget_tracker, log
    sys.modules.pop("swarm.budget_tracker", None)


def _cost_kwargs():
    return dict(provider="anthropic_agent_sdk", role="planner", model="m",
                cost_usd=0.1, tokens_in=1, tokens_out=1)


def test_mirror_stays_synchronous_off_the_event_loop(isolated_log, monkeypatch):
    bt, _ = isolated_log
    sent = []
    monkeypatch.setattr("app.server.supabase_log._insert",
                        lambda table, row: sent.append(table) or True, raising=False)
    bt.record_cost(**_cost_kwargs())
    assert sent == ["llm_costs"]


def test_mirror_does_not_block_a_running_event_loop(isolated_log, monkeypatch):
    import asyncio
    import threading

    from swarm import cost_mirror

    bt, log = isolated_log
    release, started, sent = threading.Event(), threading.Event(), []

    def slow_insert(table, row):
        started.set()
        release.wait(5)
        sent.append(table)
        return True

    monkeypatch.setattr("app.server.supabase_log._insert", slow_insert, raising=False)

    async def go():
        bt.record_cost(**_cost_kwargs())  # returns while the write is still blocked
        assert not sent
        assert log.exists()               # the local row is written first
        release.set()

    asyncio.run(go())
    assert started.wait(5)
    assert cost_mirror.wait_idle(5)  # worker drained
    assert sent == ["llm_costs"]
    assert cost_mirror._queue.unfinished_tasks == 0


def test_a_failing_queued_mirror_does_not_raise(isolated_log, monkeypatch):
    import asyncio

    from swarm import cost_mirror

    bt, _ = isolated_log

    def boom(*a, **kw):
        raise RuntimeError("supabase down")

    monkeypatch.setattr("app.server.supabase_log._insert", boom, raising=False)

    async def go():
        bt.record_cost(**_cost_kwargs())

    asyncio.run(go())
    assert cost_mirror.wait_idle(5)
    assert cost_mirror._queue.unfinished_tasks == 0


def test_a_full_backlog_drops_extra_mirrors_but_keeps_the_local_row(isolated_log, monkeypatch):
    import asyncio
    import threading

    from swarm import cost_mirror

    bt, log = isolated_log
    release = threading.Event()
    monkeypatch.setattr(cost_mirror, "_write", lambda row: release.wait(5))
    monkeypatch.setattr(cost_mirror, "_queue", cost_mirror.queue.Queue(maxsize=2))

    async def go():
        for _ in range(6):
            bt.record_cost(**_cost_kwargs())

    asyncio.run(go())
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 6                       # every row is in the local log
    assert cost_mirror._queue.qsize() <= 2       # the mirror queue never grew past its bound
    release.set()


def test_a_normal_exit_does_not_wait_for_queued_mirrors():
    import subprocess
    import textwrap
    import time

    script = textwrap.dedent("""
        import asyncio, time
        from swarm import cost_mirror
        cost_mirror._write = lambda row: time.sleep(1.0)
        async def go():
            for _ in range(6):
                cost_mirror.mirror({"cost_usd": 0.1})
        asyncio.run(go())
    """)
    started = time.monotonic()
    subprocess.run([sys.executable, "-c", script], cwd=REPO_ROOT, check=True, timeout=30)
    assert time.monotonic() - started < 3.0     # draining six 1 s writes would take 6 s+
