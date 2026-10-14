# ruff: noqa: F811
"""tests/test_mesh_run_journal_r5.py — review round 5 of UNI-2963 (Codex, FAIL at 0c00eef6).

P1 SIGINT-BEFORE-TERMINAL-RECORD: a real SIGINT landing in run_claim's finally before end()
began skipped the whole ending, so the journal never got its outcome and settlement later
sent a bare `released` (a pushed `done` requeued, a `failed` comment dropped).
P1 OUTCOME-WRITE-AND-REMOVE-FAIL: when the outcome could not be journaled the ending went on
to cleanup; with the removal failing too, settlement later sent a bare `released`.
P2: a directory that cannot be opened for fsync counted as written; `replay` did not check
run_id nor limit the keys it sends; no test drove held end() -> Ticker -> server (0 rows).
Each test here fails at 0c00eef6.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from test_mesh_run_journal import agent, journals, orphan, reconcile, run, states  # noqa: E402
from test_mesh_run_journal import runner  # noqa: E402,F401 — the shared fixture; F811 below is pytest injecting it

pytestmark = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")
HOST = "TESTNODE"
CASES = [("echo x > out.txt", "done"), ("echo x > wip.txt\nexit 3", "failed")]


def _outcome(runner):
    return json.loads(journals(runner)[0].read_text()).get("outcome")


# ── P1 SIGINT-BEFORE-TERMINAL-RECORD ─────────────────────────────────────────

@pytest.mark.parametrize("script, state", CASES, ids=["done", "failed"])
def test_r5_a_real_sigint_before_the_ending_still_journals_the_outcome(runner, monkeypatch, tmp_path, script, state):
    agent(runner, monkeypatch, tmp_path, script)
    monkeypatch.setattr(runner.claim_lifecycle, "remove_worktree", lambda *a: False)  # keep the journal to read
    real = runner.run_journal.Outcome

    class Interrupted(real):
        def __init__(self, *a, **k):
            signal.raise_signal(signal.SIGINT)  # the boundary: finally entered, ending not begun
            super().__init__(*a, **k)

    monkeypatch.setattr(runner.run_journal, "Outcome", Interrupted)
    with pytest.raises(KeyboardInterrupt):
        run(runner)
    assert (_outcome(runner) or {}).get("state") == state, "the interrupt skipped the ending"
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


# ── P1 OUTCOME-WRITE-AND-REMOVE-FAIL ─────────────────────────────────────────

def _outcome_write_fails(runner, monkeypatch):
    real = runner.run_journal.Beat.note
    monkeypatch.setattr(runner.run_journal.Beat, "note",
                        lambda self, **f: False if "outcome" in f else real(self, **f))
    return real


def test_r5_an_unjournaled_outcome_holds_the_whole_ending(runner, monkeypatch, tmp_path):
    agent(runner, monkeypatch, tmp_path, "echo x > out.txt")
    _outcome_write_fails(runner, monkeypatch)

    run(runner)

    assert states(runner) == ["working"], "no terminal update before its outcome is journaled"
    assert len(list((tmp_path / "wts").iterdir())) == 1
    entry = json.loads(journals(runner)[0].read_text())
    assert entry.get("ending") is True and "outcome" not in entry


def test_r5_an_ending_without_a_journaled_outcome_is_never_a_bare_release(runner, tmp_path):
    """The runner died after its ending began but before the outcome reached disk: hold."""
    runner.run_journal.PENDING.clear()
    _entry, wt, path = orphan(runner, tmp_path, ending=True)
    out, calls = reconcile(runner)
    assert calls == [] and wt.exists() and path.exists()
    assert "outcome" in out[0]["held"], out


def test_r5_the_tick_sends_the_outcome_the_live_runner_still_remembers(runner, monkeypatch, tmp_path):
    agent(runner, monkeypatch, tmp_path, "echo x > out.txt")
    real = _outcome_write_fails(runner, monkeypatch)
    plan = run(runner)
    monkeypatch.setattr(runner.run_journal.Beat, "note", real)  # storage is back
    sent: list = []
    rt = types.SimpleNamespace(killed=lambda: False, STATE_FILE=runner.STATE_FILE, HOST=HOST,
                               _api=lambda m, p, b=None: sent.append(b) or {}, LOG=runner.LOG)
    runner.run_journal.Ticker()(rt, False)
    assert [(b["state"], b["claim_id"]) for b in sent] == [("done", plan["claim_id"])]
    assert journals(runner) == []


# ── P2 ───────────────────────────────────────────────────────────────────────

def test_r5_an_unopenable_directory_is_not_a_successful_write(runner, monkeypatch, tmp_path):
    real = os.open
    monkeypatch.setattr(runner.run_journal.os, "open",
                        lambda p, flags, *a: (_ for _ in ()).throw(OSError("EACCES"))
                        if Path(p).is_dir() else real(p, flags, *a))
    assert runner.run_journal.write(tmp_path, "abcd1234", {"x": 1}) is False


def test_r5_replay_checks_run_id_and_sends_only_known_keys(runner, tmp_path):
    base = {"linear_id": "UNI-R", "branch": "mesh/testnode/uni-r-abcd1234", "host": HOST,
            "claim_id": "c-1", "state": "done", "run_id": "abcd1234", "duration_s": 1.0,
            "exit_code": 0, "error_code": None}
    entry = {**base, "outcome": {**base, "run_id": "ffff0000"}}
    assert runner.run_journal.replay(entry) is None
    sent = runner.run_journal.replay({**base, "outcome": {**base, "packet_md": "# forged", "title": "x"}})
    assert sent == base


def test_r5_a_held_ending_settles_through_the_real_server_with_zero_rows(runner, monkeypatch, tmp_path):
    """held end() -> Ticker -> the real claim_update, whose PATCH matched no row (already ended)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mesh_reap_helpers import HDR

    agent(runner, monkeypatch, tmp_path, "echo x > out.txt")
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
    rt = types.SimpleNamespace(killed=lambda: False, STATE_FILE=runner.STATE_FILE, HOST=HOST, _api=api, LOG=runner.LOG)
    runner.run_journal.Ticker()(rt, False)
    assert [r.status_code for r in replies] == [200] and patches[0]["state"] == "done" == plan["state"]
    assert requeued == [] and journals(runner) == []
