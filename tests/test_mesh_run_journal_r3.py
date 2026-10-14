# ruff: noqa: F811
"""tests/test_mesh_run_journal_r3.py — review round 3 of UNI-2963 (Codex, FAIL at 8b5d740c).

P1 TERMINAL-REPORT-PRECEDES-WORKTREE-REMOVAL: `end()` reported the claim terminal and only
then removed the worktree, so a removal that failed left the server holding a finished claim
over a worktree still on disk. The order is now preserve -> remove -> report only once the
worktree is proven gone -> forget. P2: `remove_worktree` had no git timeout, so a hung git
could stall the poll loop's tick. Each test here fails at 8b5d740c.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

from mesh_helpers import load_module  # noqa: E402
from test_mesh_run_journal import agent, journals, run, states  # noqa: E402
from test_mesh_run_journal import runner  # noqa: E402,F401 — the shared fixture; F811 below is pytest injecting it

pytestmark = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")
cl = load_module("claim_lifecycle_r3", "mesh/claim_lifecycle.py")


def _end(removed: bool) -> list:
    steps: list = []
    cl.end(lambda: steps.append("report") or {}, lambda: steps.append("remove") or removed,
           lambda: steps.append("idle"), agent_alive=False, pause=0,
           preserve=lambda: steps.append("preserve"), forget=lambda: steps.append("forget"))
    return steps


def test_r3_end_removes_the_worktree_before_it_reports():
    assert _end(True) == ["preserve", "remove", "report", "forget", "idle"]


def test_r3_end_sends_nothing_when_the_worktree_would_not_go():
    assert _end(False) == ["preserve", "remove", "idle"]


def test_r3_a_run_whose_worktree_would_not_go_sends_no_terminal_report(runner, monkeypatch, tmp_path):
    agent(runner, monkeypatch, tmp_path, "echo x > wip.txt\nexit 1")
    monkeypatch.setattr(runner.claim_lifecycle, "remove_worktree", lambda *a: False)

    run(runner)

    assert states(runner) == ["working"], "no terminal report may precede a removal that failed"
    assert len(journals(runner)) == 1 and len(list((tmp_path / "wts").iterdir())) == 1


def test_r3_remove_worktree_bounds_git_with_a_timeout(monkeypatch, tmp_path):
    worktree = tmp_path / "wt"
    worktree.mkdir()
    seen: dict = {}

    def hung_git(args, **kw):
        seen.update(kw)
        raise subprocess.TimeoutExpired(args, kw.get("timeout"))

    monkeypatch.setattr(cl.subprocess, "run", hung_git)
    assert cl.remove_worktree(tmp_path, worktree) is False, "a hung git proves nothing gone"
    assert isinstance(seen.get("timeout"), (int, float)) and 0 < seen["timeout"] <= 300
