"""tests/test_mesh_kill9_recovery.py — SIGKILL a real runner mid-run and lose nothing (UNI-2963).

The proof target of Durable Agent Harness slice 1. A real runner process (the real
`run_claim`, real git, a real agent child) is killed with SIGKILL while its agent is
working, so no `finally`, no signal handler and no cleanup of the runner runs. Then
the next runner's startup reconcile must:

  * leave the claim alone while the orphaned agent is still alive (it leads its own
    session, so the runner's death does not end it, and it is still writing);
  * once that agent is gone, commit its uncommitted output on the run's own mesh/*
    branch, remove the worktree, clear the journal, and report the claim `released`
    with its claim_id and host, so the ticket can be claimed again.

Before slice 1 the same kill left the claim `working` for good and the work only in
an orphaned temp worktree. Only the network is faked: the claim API writes JSON lines
to a file. Nothing reaches Supabase or GitHub; `origin` is a local bare repository.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "mesh"))

from mesh_helpers import load_module  # noqa: E402

pytestmark = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")
HOST = "TESTNODE"
CLAIM_ID = "99999999-8888-7777-6666-555555555555"


# Real-git helpers, shared with tests/test_mesh_run_journal.py (it sits at the 300-line convention).
def git(cwd, *args) -> str:
    """Fixture git, failing loudly."""
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def show(repo, branch, name):
    """The file `name` as committed on `branch`, or None when it is not committed there."""
    out = subprocess.run(["git", "-C", str(repo), "show", f"{branch}:{name}"],
                         capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def make_repo(tmp_path) -> Path:
    """A bare origin and a checkout with one pushed commit."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    repo = tmp_path / "checkout"
    git(tmp_path, "clone", "-q", str(origin), str(repo))
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    (repo / "README").write_text("base\n")
    git(repo, "add", "README")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    return repo


def dead_pid() -> int:
    """A pid that existed and is now proven gone."""
    proc = subprocess.Popen(["true"])
    proc.wait()
    return proc.pid


def sleeper() -> subprocess.Popen:
    """A live process that leads its own group."""
    return subprocess.Popen(["sleep", "60"], start_new_session=True)

CHILD = textwrap.dedent("""
    import json, sys
    from pathlib import Path
    sys.path.insert(0, {tests!r})
    from mesh_helpers import load_module
    tmp = Path({tmp!r})
    runner = load_module("mesh_runner_kill9", "mesh/runner.py")
    runner.HOST = {host!r}
    runner.STATE_FILE = tmp / "home" / "state.json"
    runner.HARD_STOP = tmp / "HARD_STOP"
    runner.AGENT_CMD = str(tmp / "agent.sh")
    runner.MESH_KILL_POLL_SECONDS = 0.05
    runner.run_journal.BEAT_SECONDS = 0.05
    runner.claim_lifecycle.temp_root = lambda: tmp / "wts"

    def api(method, path, body=None):
        with open(tmp / "calls.jsonl", "a") as fh:
            fh.write(json.dumps({{"path": path, "body": body}}) + "\\n")
        return {{}}

    runner._api = api
    runner.run_claim({{"linear_id": "UNI-K9", "id": {claim!r}, "repo_dir": str(tmp / "checkout"),
                      "title": "t", "description": "d"}}, dry_run=False)
""")


def _wait_for(predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _journal(tmp_path):
    found = list((tmp_path / "home" / "mesh-runs").glob("*.json"))
    return json.loads(found[0].read_text()) if len(found) == 1 else None


def _group_alive(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # darwin answers EPERM for a group whose last member is a zombie
        return True
    return True


def _start_runner(tmp_path):
    """A real runner process, mid-run: its agent has written uncommitted work and sleeps."""
    repo = make_repo(tmp_path)
    (tmp_path / "wts").mkdir()
    pidfile = tmp_path / "agent.pid"
    agent = tmp_path / "agent.sh"
    agent.write_text(f"#!/bin/sh\necho 'work in progress' > wip.txt\necho $$ > '{pidfile}'\nexec sleep 600\n")
    agent.chmod(0o755)
    script = tmp_path / "child.py"
    script.write_text(CHILD.format(tests=str(REPO_ROOT / "tests"), tmp=str(tmp_path), host=HOST,
                                   claim=CLAIM_ID))
    return repo, pidfile, subprocess.Popen([sys.executable, str(script)], cwd=str(REPO_ROOT))


def _kill_runner(child, tmp_path, repo) -> dict:
    """SIGKILL the runner, then show what it left: only `working` sent, work uncommitted."""
    os.kill(child.pid, signal.SIGKILL)  # THE KILL: no finally, no handler, no cleanup runs
    child.wait(timeout=10)
    sent = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert [c["body"]["state"] for c in sent] == ["working"], "the dead runner reported nothing terminal"
    entry = _journal(tmp_path)
    assert (Path(entry["worktree"]) / "wip.txt").exists() and show(repo, entry["branch"], "wip.txt") is None
    return entry


def test_a_sigkilled_runner_leaves_a_committed_wip_branch_and_a_released_claim(tmp_path):
    repo, pidfile, child = _start_runner(tmp_path)
    pgid, released = None, []
    api = lambda m, p, b=None: released.append(b) or {}  # noqa: E731
    try:
        assert _wait_for(lambda: pidfile.exists() and (_journal(tmp_path) or {}).get("agent_pgid")), \
            "the runner never recorded its agent"
        pgid = _journal(tmp_path)["agent_pgid"]
        assert pgid == int(pidfile.read_text())
        entry = _kill_runner(child, tmp_path, repo)
        journal = load_module("run_journal_kill9", "mesh/run_journal.py")
        journal.reconcile(tmp_path / "home", HOST, api)
        assert released == [], "released while the orphaned agent was still writing"
        os.killpg(pgid, signal.SIGKILL)  # the orphaned agent ends on its own in real life
        assert _wait_for(lambda: not _group_alive(pgid)), "the agent group never emptied"
        out = journal.reconcile(tmp_path / "home", HOST, api)
    finally:
        if child.poll() is None:
            child.kill()
        if pgid and _group_alive(pgid):
            os.killpg(pgid, signal.SIGKILL)
    assert [(b["state"], b["claim_id"], b["host"], b["linear_id"]) for b in released] == [
        ("released", CLAIM_ID, HOST, "UNI-K9")]
    assert show(repo, entry["branch"], "wip.txt") == "work in progress\n"
    assert git(repo, "branch", "--list", entry["branch"]), "the WIP branch must survive"
    assert not Path(entry["worktree"]).exists() and _journal(tmp_path) is None
    assert out[0]["released"] is True
