# ruff: noqa: F811
"""tests/test_mesh_run_journal_r7.py — review round 7 of UNI-2963 (Codex, FAIL at 617f9134).

P1 POST-LAUNCH-NO-AGENT-OUTCOME-NEVER-SETTLES, and its whole class. The r6 proof that no agent
exists ("never launched") was set on ONE path only: a failed `launching` write. Every other way
a run ends with no agent process left it out, so a held ending with no journaled pid stayed
`working` for good. The proof is now taken in one place, the ending (`run_settle.no_agent`),
from the run's own RunRecord, for every path:

  a  the `launching` write failed           (make_cmd raised; rec.proc is None)
  b  building the prompt raised             (make_cmd raised; rec.proc is None)
  c  building the argv raised               (make_cmd raised; rec.proc is None)
  d  Popen raised (missing executable)      (Popen reaps a child that failed to exec)
  e  the RunRecord could not be built       (holder empty: Popen never ran)
  f  the worktree could not be added        (run_agent never called: holder empty)
  h  the agent ran and was reaped, but its pid never reached the journal (stop() proved it gone)
  g  an interrupt inside Popen              NO proof: a child may exist that nobody saw

Each settling case ends with its terminal report REJECTED (the claim stays `working`), then the
runner's own Ticker must send exactly one `failed` and clear the journal, PENDING and
NEVER_LAUNCHED. Several tests are adapted from the reviewer's r7 helper tests
(~/session-handoffs/durable-slice1-review-r7-codex-report-evidence/tests/).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from test_mesh_run_journal import agent, journals, run, states  # noqa: E402
from test_mesh_run_journal import runner  # noqa: E402,F401 — the shared fixture; F811 below is pytest injecting it

pytestmark = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")
HOST = "TESTNODE"


@pytest.fixture(autouse=True)
def _fresh_memory(runner):
    runner.run_journal.PENDING.clear()
    runner.run_journal.NEVER_LAUNCHED.clear()


def _rt(runner, api):
    return types.SimpleNamespace(killed=lambda: False, STATE_FILE=runner.STATE_FILE, HOST=HOST, _api=api, LOG=runner.LOG)


def _reject_terminal(runner, monkeypatch) -> list:
    posts: list = []

    def api(_m, _p, body=None):
        posts.append(dict(body or {}))
        return {"error": "HTTP 502"} if (body or {}).get("state") in ("done", "failed", "released") else {}

    monkeypatch.setattr(runner, "_api", api)
    monkeypatch.setattr(runner, "MESH_KILL_POLL_SECONDS", 0)
    return posts


def _no_pid_in_journal(runner, monkeypatch):
    """Keep agent_pid/pgid out of the journal, as a fast exit or failed beats would."""
    real = runner.run_journal.write
    monkeypatch.setattr(runner.run_journal, "write", lambda b, r, e: real(
        b, r, {k: v for k, v in e.items() if k not in ("agent_pid", "agent_pgid")}))


def _path_a(runner, monkeypatch, tmp_path):
    """Only the `launching` write itself fails; storage then works (as in the reviewer's helper)."""
    real, failed = runner.run_journal.write, [False]

    def write(b, r, e):  # main thread only: a heartbeat landing first must not use up the failure
        if e.get("phase") == "launching" and not failed[0] and threading.current_thread() is threading.main_thread():
            failed[0] = True
            return False
        return real(b, r, e)

    monkeypatch.setattr(runner.run_journal, "write", write)


def _path_b(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "build_prompt", lambda *a: (_ for _ in ()).throw(ValueError("prompt")))


def _path_c(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(runner.agent_sandbox, "agent_argv", lambda *a: (_ for _ in ()).throw(ValueError("argv")))


def _path_d(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "AGENT_CMD", str(tmp_path / "no-such-agent"))


def _path_e(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(runner.run_record, "RunRecord", lambda *a: (_ for _ in ()).throw(OSError("log")))


def _path_f(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(runner.claim_lifecycle, "add_worktree", lambda *a: False)


PATHS = {"a-launching-write": _path_a, "b-prompt": _path_b, "c-argv": _path_c,
         "d-popen": _path_d, "e-runrecord": _path_e, "f-worktree-add": _path_f}


@pytest.mark.parametrize("path", list(PATHS))
def test_r7_every_no_agent_path_settles_after_a_rejected_report(runner, monkeypatch, tmp_path, path):
    marker = tmp_path / "agent-ran"
    agent(runner, monkeypatch, tmp_path, f"touch '{marker}'")
    PATHS[path](runner, monkeypatch, tmp_path)
    posts = _reject_terminal(runner, monkeypatch)

    plan = run(runner)
    rid = plan["branch"].rsplit("-", 1)[1]

    assert not marker.exists() and plan["state"] == "failed"
    assert [p["state"] for p in posts] == ["working", "failed", "failed", "failed"]
    entry = json.loads(journals(runner)[0].read_text())
    assert entry["outcome"]["state"] == "failed" and "agent_pid" not in entry
    assert rid in runner.run_journal.PENDING and rid in runner.run_journal.NEVER_LAUNCHED, "state lost on rejection"
    sent: list = []
    runner.run_journal.Ticker()(_rt(runner, lambda m, p, b=None: sent.append(b) or {}), False)
    assert [b["state"] for b in sent] == ["failed"] and sent[0] == entry["outcome"]
    assert journals(runner) == [] and runner.run_journal.PENDING == {} and runner.run_journal.NEVER_LAUNCHED == set()


def test_r7_h_a_reaped_agent_whose_pid_never_reached_the_journal_settles(runner, monkeypatch, tmp_path):
    agent(runner, monkeypatch, tmp_path, "exit 3")
    _no_pid_in_journal(runner, monkeypatch)
    _reject_terminal(runner, monkeypatch)
    plan = run(runner)
    rid = plan["branch"].rsplit("-", 1)[1]
    assert "agent_pid" not in json.loads(journals(runner)[0].read_text())
    assert rid in runner.run_journal.NEVER_LAUNCHED, "stop() proved the agent gone; that is the proof"
    sent: list = []
    runner.run_journal.Ticker()(_rt(runner, lambda m, p, b=None: sent.append(b) or {}), False)
    assert [b["state"] for b in sent] == ["failed"] and journals(runner) == []


def test_r7_g_an_interrupt_inside_popen_gets_no_proof_and_holds(runner, monkeypatch, tmp_path):
    """A KeyboardInterrupt inside Popen may leave a child nobody saw: never a proof."""
    agent(runner, monkeypatch, tmp_path, "exit 0")

    real = runner.run_record.subprocess.Popen

    def popen(cmd, *a, **k):  # only the agent's start is interrupted; git keeps working
        if cmd and cmd[0] == runner.AGENT_CMD:
            raise KeyboardInterrupt
        return real(cmd, *a, **k)

    monkeypatch.setattr(runner.run_record.subprocess, "Popen", popen)
    with pytest.raises(KeyboardInterrupt):
        run(runner)
    rid = journals(runner)[0].stem
    assert rid not in runner.run_journal.NEVER_LAUNCHED
    sent: list = []
    runner.run_journal.Ticker()(_rt(runner, lambda m, p, b=None: sent.append(b) or {}), False)
    assert sent == [] and len(journals(runner)) == 1


def test_r7_after_a_restart_the_in_memory_proof_is_gone_and_the_journal_holds(runner, monkeypatch, tmp_path):
    """Adapted from the reviewer's test_round6_restart_loses_in_memory_proofs_and_holds."""
    agent(runner, monkeypatch, tmp_path, "exit 0")
    _path_d(runner, monkeypatch, tmp_path)
    _reject_terminal(runner, monkeypatch)
    run(runner)
    runner.run_journal.PENDING.clear()  # a new runner process remembers nothing
    runner.run_journal.NEVER_LAUNCHED.clear()
    sent: list = []
    runner.run_journal.Ticker()(_rt(runner, lambda m, p, b=None: sent.append(b) or {}), False)
    assert sent == [] and len(journals(runner)) == 1


def test_r7_a_done_run_leaves_no_proof_and_nothing_pending(runner, monkeypatch, tmp_path):
    """Adapted from the reviewer's test_done_run_clears_both_in_memory_entries."""
    agent(runner, monkeypatch, tmp_path, "echo x > out.txt")
    run(runner)
    assert states(runner) == ["working", "done"]
    assert runner.run_journal.PENDING == {} and runner.run_journal.NEVER_LAUNCHED == set()


def test_r7_the_proof_comes_from_one_place_only():
    """The launching path no longer sets the proof itself: one rule, in the ending."""
    src = (REPO_ROOT / "mesh" / "run_journal.py").read_text()
    assert "NEVER_LAUNCHED.add(" not in src
    assert subprocess.run(["grep", "-c", "NEVER_LAUNCHED.add(", str(REPO_ROOT / "mesh" / "run_settle.py")],
                          capture_output=True, text=True).stdout.strip() == "1"


@pytest.mark.parametrize("held, proof", [
    ([], True),                                                                       # e, f
    ([types.SimpleNamespace(proc=None, reaped=True)], True),                          # a-d
    ([types.SimpleNamespace(proc=object(), reaped=True)], True),                      # h
    ([types.SimpleNamespace(proc=object(), reaped=None)], False),                     # never stopped
    ([types.SimpleNamespace(proc=object(), reaped=False)], False),                    # unstoppable
    ([types.SimpleNamespace(proc=None, reaped=None, unseen_agent=True)], False),      # g
], ids=["no-record", "no-process", "reaped", "not-stopped", "unreaped", "unseen-child"])
def test_r7_no_agent_rule_table(runner, held, proof):
    """The one rule, directly: in run_claim an unseen child is already gated by agent_alive, so
    the `unseen_agent` clause is pinned here (it is the rule's own statement, not dead weight)."""
    assert sys.modules["run_settle"].no_agent(held) is proof
