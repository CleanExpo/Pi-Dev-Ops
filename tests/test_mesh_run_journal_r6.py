# ruff: noqa: F811
"""tests/test_mesh_run_journal_r6.py — review round 6 of UNI-2963 (Codex, FAIL at 5ff82b46).

P1 PREPARING-KNOWN-FAILED-OUTCOME-NEVER-SETTLES: the `launching` write failed, so no agent
ever started and the run ended `failed`; with the journal unwritable the ending held and its
outcome waited in PENDING. The runner's own Ticker then held the on-disk `preparing`/no-pid
journal before it could replay PENDING, so the claim stayed `working` although this runner
knew no agent existed. P2: PENDING kept every successful run's entry; a held Ctrl-C was lost
when end() raised; the zero-row route test covered `done` only. Each test fails at 5ff82b46.
"""
from __future__ import annotations

import os
import signal
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from mesh_helpers import load_module  # noqa: E402
from test_mesh_kill9_recovery import dead_pid  # noqa: E402
from test_mesh_run_journal import agent, journals, orphan, reconcile, run, states  # noqa: E402
from test_mesh_run_journal import runner  # noqa: E402,F401 — the shared fixture; F811 below is pytest injecting it

pytestmark = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")
HOST = "TESTNODE"


@pytest.fixture(autouse=True)
def _fresh_pending(runner):
    """PENDING is process-wide; other suites' held endings must not leak into these asserts."""
    runner.run_journal.PENDING.clear()


def _rt(runner, api):
    return types.SimpleNamespace(killed=lambda: False, STATE_FILE=runner.STATE_FILE, HOST=HOST, _api=api, LOG=runner.LOG)


def _unwritable_after_first(runner, monkeypatch):
    """Every journal write after the very first fails (the r2 scenario); returns the real write."""
    real, count = runner.run_journal.write, [0]

    def write(*a):
        count[0] += 1
        return real(*a) if count[0] == 1 else False

    monkeypatch.setattr(runner.run_journal, "write", write)
    return real


# ── P1 PREPARING-KNOWN-FAILED-OUTCOME-NEVER-SETTLES ─────────────────────────

def test_r6_the_ticker_settles_a_run_it_knows_never_launched(runner, monkeypatch, tmp_path):
    marker = tmp_path / "agent-ran"
    agent(runner, monkeypatch, tmp_path, f"touch '{marker}'")
    real = _unwritable_after_first(runner, monkeypatch)
    plan = run(runner)
    assert not marker.exists() and states(runner) == ["working"]
    pending = dict(runner.run_journal.PENDING[plan["branch"].rsplit("-", 1)[1]])
    monkeypatch.setattr(runner.run_journal, "write", real)  # storage is back

    sent: list = []
    runner.run_journal.Ticker()(_rt(runner, lambda m, p, b=None: sent.append(b) or {}), False)

    assert sent == [pending] and pending["state"] == "failed" and pending["claim_id"] == plan["claim_id"]
    assert journals(runner) == [] and runner.run_journal.PENDING == {}


def test_r6_a_foreign_preparing_journal_is_still_held(runner, tmp_path):
    """Owner decision (a) stands for any journal without in-process proof: hold it."""
    _entry, wt, path = orphan(runner, tmp_path, phase="preparing", agent_pid=None, agent_pgid=None, owner_pid=os.getpid())
    _out, calls = reconcile(runner)  # own=False
    out = runner.run_journal.reconcile(runner.STATE_FILE.parent, HOST, lambda *a, **k: calls.append(a) or {}, own=True)
    assert calls == [] and wt.exists() and path.exists() and "unrecorded" in out[0]["held"]


# ── P2 ───────────────────────────────────────────────────────────────────────

def test_r6_a_successful_ending_leaves_nothing_pending(runner, monkeypatch, tmp_path):
    agent(runner, monkeypatch, tmp_path, "echo x > out.txt")
    run(runner)
    assert states(runner) == ["working", "done"] and runner.run_journal.PENDING == {}


def test_r6_a_held_ctrl_c_survives_an_ending_that_raises():
    cl = load_module("claim_lifecycle_r6", "mesh/claim_lifecycle.py")

    def preserve():
        signal.raise_signal(signal.SIGINT)  # held: the ending goes on

    def remove():
        raise ValueError("git exploded")

    with pytest.raises(KeyboardInterrupt) as raised:
        cl.end(lambda: pytest.fail("reported"), remove, lambda: None, agent_alive=False, pause=0, preserve=preserve)
    assert isinstance(raised.value.__context__ or raised.value.__cause__, ValueError)
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


@pytest.mark.parametrize("script, state", [("echo x > out.txt", "done"), ("echo x > wip.txt\nexit 3", "failed")])
def test_r6_a_held_ending_settles_through_the_real_server_with_zero_rows(runner, monkeypatch, tmp_path, script, state):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mesh_reap_helpers import HDR

    agent(runner, monkeypatch, tmp_path, script)
    real_remove = runner.claim_lifecycle.remove_worktree
    monkeypatch.setattr(runner.claim_lifecycle, "remove_worktree", lambda *a: False)
    plan = run(runner)
    monkeypatch.setattr(runner.claim_lifecycle, "remove_worktree", real_remove)
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    sys.modules.pop("app.server.routes.mesh", None)
    from app.server.routes import mesh
    monkeypatch.setattr(mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    patches, requeued = [], []
    monkeypatch.setattr(mesh, "_sb", lambda m, p, body=None, **_k: patches.append(body) or (200, "[]"))
    monkeypatch.setattr(mesh, "_mark_issue_reaped", lambda lid: requeued.append(lid) or True)
    app = FastAPI()
    app.include_router(mesh.router)
    client, replies = TestClient(app), []
    api = lambda m, p, b=None: replies.append(client.post(p, headers=HDR, json=b)) or replies[-1].json()  # noqa: E731
    runner.run_journal.Ticker()(_rt(runner, api), False)
    assert [r.status_code for r in replies] == [200] and patches[0]["state"] == state == plan["state"]
    assert requeued == [], "a PATCH that matched no row must not requeue anything"
    assert journals(runner) == [] and runner.run_journal.PENDING == {}


@pytest.mark.parametrize("own, launched, pending", [(False, True, True), (True, False, True), (True, True, False)],
                         ids=["not-own", "no-launch-proof", "nothing-pending"])
def test_r6_the_bypass_needs_all_three_proofs(runner, tmp_path, own, launched, pending):
    """Own journal, in-process proof the launch was aborted, and a PENDING outcome: all, or hold.
    `not-own` is a DEAD foreign runner's journal, so only the bypass's own check can hold it."""
    owner = os.getpid() if own else dead_pid()
    entry, wt, path = orphan(runner, tmp_path, phase="preparing", agent_pid=None, agent_pgid=None, owner_pid=owner)
    rj, calls = runner.run_journal, []
    if launched:
        rj.NEVER_LAUNCHED.add(entry["run_id"])
    if pending:
        rj.PENDING[entry["run_id"]] = {k: entry[k] for k in ("linear_id", "branch", "host", "claim_id", "run_id")} | {
            "state": "failed"}
    try:
        out = rj.reconcile(runner.STATE_FILE.parent, HOST, lambda *a, **k: calls.append(a) or {}, own=own)
    finally:
        rj.NEVER_LAUNCHED.discard(entry["run_id"])
    assert calls == [] and wt.exists() and path.exists(), out
