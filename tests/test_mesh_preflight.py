"""tests/test_mesh_preflight.py — the checks a node passes before it claims (RA-7802).

Each check reproduces one of 28/09's silent failures and must catch it:
  * the Mini's agent ran in a workspace Claude Code had not trusted, so it
    could not write, and every run ended "no commits";
  * the PC's runner raised opening its run log (RA-7801), before any agent ran.
The agent is faked; git and the agent are both reached through `run`.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))
sys.path.insert(0, str(REPO_ROOT / "mesh"))

from mesh_helpers import load_module as _load  # noqa: E402

pf = _load("mesh_preflight_under_test", "mesh/preflight.py")
UNTRUSTED_WARNING = ("Ignoring 37 permissions.allow entries from .claude/settings.json: "
                     "this workspace has not been trusted.")


def fake_run(agent_writes: bool, stderr: str = ""):
    """git creates the worktree; the agent writes the probe file or not."""
    calls = []

    def run(cmd, cwd=None, **kwargs):
        calls.append(cmd)
        if cmd[:4] == ["git", "-C", "/repo", "worktree"] and cmd[4] == "add":
            Path(cmd[6]).mkdir(parents=True)
        elif cmd[0] == "claude" and agent_writes:
            (Path(cwd) / pf.PROBE_FILE).write_text("ok")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr=stderr)

    run.calls = calls
    return run


def test_an_agent_that_writes_passes_and_the_worktree_is_removed():
    run = fake_run(agent_writes=True)
    assert pf.agent_writes(Path("/repo"), "claude", run=run) == ""
    assert run.calls[-1][4:6] == ["remove", "--force"]


def test_an_agent_that_cannot_write_is_caught():
    assert pf.agent_writes(Path("/repo"), "claude", run=fake_run(agent_writes=False)) \
        == "agent could not write a file"


def test_an_untrusted_workspace_is_named_even_if_a_file_appears():
    problem = pf.agent_writes(Path("/repo"), "claude",
                              run=fake_run(agent_writes=True, stderr=UNTRUSTED_WARNING))
    assert problem.startswith("agent workspace not trusted")


def test_a_run_log_that_cannot_open_on_this_platform_is_caught(monkeypatch):
    monkeypatch.setattr(pf.run_record.RunRecord, "__init__",
                        lambda self, *a: (_ for _ in ()).throw(AttributeError("O_NOFOLLOW")))
    assert pf.run_log() == "run log raised AttributeError"


def test_the_run_log_check_passes_where_a_run_log_opens():
    assert pf.run_log() == ""
    assert os.path.exists(pf.tempfile.gettempdir())
