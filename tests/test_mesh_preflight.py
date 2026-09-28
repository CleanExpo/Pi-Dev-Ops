"""tests/test_mesh_preflight.py — the checks a node passes before it claims (RA-7802).

Each check reproduces one of 28/09's silent failures and must catch it:
  * the Mini's agent ran in a workspace Claude Code had not trusted, so it
    could not write, and every run ended "no commits";
  * the PC's runner raised opening its run log (RA-7801), before any agent ran.
The agent is faked; git and the agent are both reached through `run`.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))
sys.path.insert(0, str(REPO_ROOT / "mesh"))

from mesh_helpers import load_module as _load, short_temp_alias  # noqa: E402

pf = _load("mesh_preflight_under_test", "mesh/preflight.py")
REPO = Path("/repo")  # str() of it is "\\repo" on Windows: never compare it as a literal
UNTRUSTED_WARNING = ("Ignoring 37 permissions.allow entries from .claude/settings.json: "
                     "this workspace has not been trusted.")


def fake_run(agent_writes: bool, stderr: str = "", *, content: str = "ok", exit_code: int = 0,
             tracked: dict[str, str] | None = None):
    """git creates the worktree, holding any `tracked` files; the agent writes the
    file its prompt names, or not, and exits `exit_code`."""
    calls = []

    def run(cmd, cwd=None, **kwargs):
        calls.append(cmd)
        if cmd[:4] == ["git", "-C", str(REPO), "worktree"] and cmd[4] == "add":
            Path(cmd[6]).mkdir(parents=True)
            for name, text in (tracked or {}).items():
                (Path(cmd[6]) / name).write_text(text)
        elif cmd[0] == "claude":
            if agent_writes:
                (Path(cwd) / re.search(r"named (\S+) in", cmd[-1]).group(1)).write_text(content)
            return subprocess.CompletedProcess(cmd, exit_code, stdout="", stderr=stderr)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr=stderr)

    run.calls = calls
    return run


def test_an_agent_that_writes_passes_and_the_worktree_is_removed():
    run = fake_run(agent_writes=True)
    assert pf.agent_writes(REPO, "claude", run=run) == ""
    assert run.calls[-1][4:6] == ["remove", "--force"]


def test_an_agent_that_cannot_write_is_caught():
    assert pf.agent_writes(REPO, "claude", run=fake_run(agent_writes=False)) \
        == "agent could not write a file"


def test_an_untrusted_workspace_is_named_even_if_a_file_appears():
    problem = pf.agent_writes(REPO, "claude",
                              run=fake_run(agent_writes=True, stderr=UNTRUSTED_WARNING))
    assert problem.startswith("agent workspace not trusted")


def test_a_run_log_that_cannot_open_on_this_platform_is_caught(monkeypatch):
    monkeypatch.setattr(pf.run_record.RunRecord, "__init__",
                        lambda self, *a: (_ for _ in ()).throw(AttributeError("O_NOFOLLOW")))
    assert pf.run_log() == "run log raised AttributeError"


def test_the_run_log_check_passes_where_a_run_log_opens():
    assert pf.run_log() == ""
    assert os.path.exists(pf.tempfile.gettempdir())


def test_a_probe_file_already_in_the_repo_does_not_pass_for_the_agent():
    """Codex round 1: with a fixed probe name, a tracked MESH_PREFLIGHT.txt made an
    agent that wrote nothing, and exited 1, pass."""
    run = fake_run(agent_writes=False, exit_code=1, tracked={"MESH_PREFLIGHT.txt": "ok"})
    assert pf.agent_writes(REPO, "claude", run=run) != ""


def test_an_agent_that_writes_but_exits_non_zero_fails():
    assert pf.agent_writes(REPO, "claude", run=fake_run(agent_writes=True, exit_code=1)) \
        == "agent exited 1"


def test_an_agent_that_writes_the_wrong_thing_fails():
    assert pf.agent_writes(REPO, "claude", run=fake_run(agent_writes=True, content="nope")) \
        == "agent could not write a file"


def test_each_preflight_asks_for_a_different_file():
    first, second = fake_run(agent_writes=True), fake_run(agent_writes=True)
    pf.agent_writes(REPO, "claude", run=first)
    pf.agent_writes(REPO, "claude", run=second)
    prompts = [c[-1] for r in (first, second) for c in r.calls if c[0] == "claude"]
    assert len(prompts) == 2 and prompts[0] != prompts[1]


def test_a_probe_name_already_present_is_refused(monkeypatch):
    """The random name makes a collision near impossible; the absence check makes it harmless."""
    monkeypatch.setattr(pf.uuid, "uuid4", lambda: type("U", (), {"hex": "fixed"})())
    run = fake_run(agent_writes=False, tracked={"mesh-preflight-fixed.txt": "ok"})
    assert pf.agent_writes(REPO, "claude", run=run) == "scratch worktree already holds the probe file"


def test_a_candidate_whose_runner_cannot_load_fails_its_own_preflight(tmp_path):
    """Codex round 4: the candidate's preflight never loaded runner.py, so a commit
    with a syntax error in it passed, and the runner restarted onto code that died."""
    import shutil
    mesh = tmp_path / "mesh"
    shutil.copytree(REPO_ROOT / "mesh", mesh, ignore=shutil.ignore_patterns("__pycache__"))
    (mesh / "runner.py").write_text((mesh / "runner.py").read_text() + "\ndef broken(:\n")
    done = subprocess.run([sys.executable, str(mesh / "preflight.py"), str(tmp_path / "no-repo"), "claude"],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 1
    assert done.stdout.strip().splitlines()[-1] == "runner.py does not compile"


def test_the_runner_in_this_checkout_loads():
    assert pf.runner_loads(REPO_ROOT / "mesh") == ""


def test_a_candidate_runner_that_exits_on_import_is_named(tmp_path, monkeypatch):
    (tmp_path / "runner.py").write_text("import sys\nsys.exit(0)\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "runner", raising=False)
    assert pf.runner_loads(tmp_path) == "runner does not import: SystemExit"


def test_the_scratch_worktree_is_made_under_the_long_temp_path(tmp_path, monkeypatch):
    """RA-7801: the PC's runner got a short TEMP, so preflight's worktree read as
    untrusted and the node stayed blocked after its folder was trusted."""
    alias, real = short_temp_alias(tmp_path)
    monkeypatch.setattr(pf.tempfile, "tempdir", str(alias))
    run = fake_run(agent_writes=True)
    assert pf.agent_writes(REPO, "claude", run=run) == ""
    added = next(c for c in run.calls if c[:2] == ["git", "-C"] and c[3:5] == ["worktree", "add"])
    assert Path(added[6]).parent.parent == real
