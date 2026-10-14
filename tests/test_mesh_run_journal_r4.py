# ruff: noqa: F811
"""tests/test_mesh_run_journal_r4.py — review round 4 of UNI-2963 (Codex, FAIL at 56e7ff8b).

P1 HELD-TERMINAL-OUTCOME-LOST: when `end()` held a claim because its worktree would not go,
the loop's later settlement posted a bare `released`. The server then requeued a `done` run
whose work was already pushed (duplicate delivery), dropped a `failed` run's comment and skip
window, and lost a quota release's `agent_quota`. The intended terminal payload is now written
into the journal before cleanup, and settlement replays exactly that; a bare `released` is only
for a run with no recorded outcome (kill -9). P2: a raised removal is logged; the journal is
fsynced. Each test here fails at 56e7ff8b.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from mesh_helpers import load_module  # noqa: E402
from test_mesh_kill9_recovery import git  # noqa: E402
from test_mesh_run_journal import agent, journals, orphan, reconcile, run, states  # noqa: E402
from test_mesh_run_journal import runner  # noqa: E402,F401 — the shared fixture; F811 below is pytest injecting it

pytestmark = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")
HOST = "TESTNODE"


def _payload(state, **extra):
    return {"linear_id": "UNI-R", "branch": "mesh/testnode/uni-r-abcd1234", "host": HOST,
            "claim_id": "c-1", "state": state, "run_id": "abcd1234", "duration_s": 12.5,
            "exit_code": extra.pop("exit_code", 0), "error_code": extra.pop("error_code", None), **extra}


# ── the outcome is journaled before cleanup ──────────────────────────────────

@pytest.mark.parametrize("script, state, code", [("echo x > out.txt", "done", None),
                                                 ("echo x > wip.txt\nexit 3", "failed", "agent_exit")])
def test_r4_a_held_ending_journals_the_exact_terminal_payload(runner, monkeypatch, tmp_path, script, state, code):
    agent(runner, monkeypatch, tmp_path, script)
    monkeypatch.setattr(runner.claim_lifecycle, "remove_worktree", lambda *a: False)

    plan = run(runner)

    assert states(runner) == ["working"]
    outcome = json.loads(journals(runner)[0].read_text())["outcome"]
    assert outcome["state"] == state == plan["state"] and outcome["error_code"] == code
    assert outcome["claim_id"] == plan["claim_id"] and outcome["host"] == HOST
    assert outcome["branch"] == plan["branch"] and isinstance(outcome["duration_s"], float)


# ── settlement replays it ────────────────────────────────────────────────────

@pytest.mark.parametrize("recorded", [
    _payload("done"),
    _payload("failed", exit_code=3, error_code="agent_exit"),
    _payload("released", exit_code=1, error_code="agent_quota"),
], ids=["done", "failed", "quota"])
def test_r4_settlement_replays_the_recorded_payload_exactly(runner, tmp_path, recorded):
    _entry, wt, path = orphan(runner, tmp_path, outcome=recorded)
    _out, calls = reconcile(runner)
    assert calls == [recorded] and not wt.exists() and not path.exists()


def test_r4_no_recorded_outcome_still_releases(runner, tmp_path):
    """kill -9: nothing was recorded, so the run is released for another node."""
    _orphan, _wt, _path = orphan(runner, tmp_path)
    _out, calls = reconcile(runner)
    assert [c["state"] for c in calls] == ["released"] and "error_code" not in calls[0]


@pytest.mark.parametrize("field, value", [("claim_id", "c-OTHER"), ("host", "OTHER"),
                                          ("linear_id", "UNI-X"), ("state", "working")])
def test_r4_an_outcome_for_another_claim_is_not_replayed(runner, tmp_path, field, value):
    _entry, _wt, _path = orphan(runner, tmp_path, outcome={**_payload("done"), field: value})
    _out, calls = reconcile(runner)
    assert [c["state"] for c in calls] == ["released"] and calls[0]["claim_id"] == "c-1"


def test_r4_replays_through_the_real_claim_update(runner, tmp_path, monkeypatch):
    """The replayed payloads, POSTed to the real route: `done` is never requeued, `failed`
    is requeued and commented, a quota release keeps `agent_quota`."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mesh_reap_helpers import HDR

    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    sys.modules.pop("app.server.routes.mesh", None)
    from app.server.routes import mesh
    monkeypatch.setattr(mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    patches, requeued, comments = [], [], []
    monkeypatch.setattr(mesh, "_sb", lambda method, path, body=None, **_k: patches.append(body)
                        or (200, json.dumps([{"machine": HOST, "linear_id": "UNI-R"}])))
    monkeypatch.setattr(mesh, "_mark_issue_reaped", lambda lid: requeued.append(lid) or True)
    monkeypatch.setattr(mesh, "_linear_graphql", lambda q: comments.append(q) or {})
    app = FastAPI()
    app.include_router(mesh.router)
    client = TestClient(app)
    for recorded in (_payload("done"), _payload("failed", exit_code=3, error_code="agent_exit"),
                     _payload("released", exit_code=1, error_code="agent_quota")):
        sent: list = []
        _entry, _wt, path = orphan(runner, tmp_path, outcome=recorded)
        runner.run_journal.reconcile(runner.STATE_FILE.parent, HOST,
                                     lambda m, p, b=None: sent.append(client.post(p, headers=HDR, json=b)) or {})
        assert sent and sent[0].status_code == 200 and not path.exists()
        git(runner.repo, "branch", "-D", recorded["branch"])  # free the fixed branch for the next orphan
    assert [p["state"] for p in patches] == ["done", "failed", "released"]
    assert patches[2]["error_code"] == "agent_quota" and patches[1]["error_code"] == "agent_exit"
    assert requeued == ["UNI-R", "UNI-R"], "done must never go back to Todo"
    assert comments, "a failed run's Linear comment must survive the hold"


# ── P2 ───────────────────────────────────────────────────────────────────────

def test_r4_a_removal_that_raises_is_logged(capsys):
    cl = load_module("claim_lifecycle_r4", "mesh/claim_lifecycle.py")

    def boom():
        raise RuntimeError("git exploded")

    with pytest.raises(RuntimeError):
        cl.end(lambda: pytest.fail("reported"), boom, lambda: None, agent_alive=False, pause=0)
    assert "worktree" in capsys.readouterr().err


def test_r4_the_journal_write_is_fsynced_file_and_directory(runner, monkeypatch, tmp_path):
    synced: list = []
    real = os.fsync
    monkeypatch.setattr(runner.run_journal.os, "fsync", lambda fd: synced.append(fd) or real(fd))
    assert runner.run_journal.write(tmp_path, "abcd1234", {"x": 1}) is True
    assert len(synced) >= 2, "the file and its directory must both be fsynced"
