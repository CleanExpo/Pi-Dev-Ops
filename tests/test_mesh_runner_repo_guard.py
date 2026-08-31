"""tests/test_mesh_runner_repo_guard.py — the runner must not trust any path
handed to it as its default repo (RA-7375 item 2).

`DEFAULT_REPO_DIR` is `os.environ.get("MESH_REPO_DIR", <this checkout>)`, read
at module scope, and `_repo_dir_for()` falls back to it for every claim that
carries no explicit `repo_dir`. Honouring the variable is deliberate — a
relocated runner needs it, and `bootstrap.sh` sets it in the launchd plist.
Silently INHERITING it is the failure mode: on `Phills-Mac-mini` it was
exported into the ambient session pointing at a Codex worktree on an external
volume, so every claim would have defaulted into the wrong repository.

Runtime cannot tell deliberate from inherited — that was established while
fixing RA-7370, and no test can separate them either. What it CAN tell is
whether the resolved path is a checkout of the same repository the runner
itself ships in, which is the substitute this guard uses: a deliberate
relocation is to a valid clone, an accidental inheritance usually is not.

The authority is the runner's OWN checkout's `origin`, not a hardcoded repo
name — self-describing, and it keeps working on a fork.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mesh_helpers import load_module  # noqa: E402

OWN_ORIGIN = "https://github.com/CleanExpo/Pi-Dev-Ops"


def _git(*args: str, cwd: Path) -> None:
    """Run a git command in `cwd`, failing loudly if it does not succeed."""
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _repo_with_origin(path: Path, origin: str) -> Path:
    """A real git checkout at `path` whose `origin` is `origin`."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    _git("remote", "add", "origin", origin, cwd=path)
    return path


def _runner_with(monkeypatch, value: str | None):
    """Load `mesh/runner.py` with MESH_REPO_DIR set to `value` (None = unset).

    It must be set BEFORE the import: `DEFAULT_REPO_DIR` is read at module
    scope, so setting it afterwards would test nothing.
    """
    if value is None:
        monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    else:
        monkeypatch.setenv("MESH_REPO_DIR", value)
    return load_module("mesh_runner_guard", "mesh/runner.py")


# ── the guard refuses what it cannot validate ────────────────────────────────


def test_a_default_repo_that_is_not_a_checkout_is_refused(monkeypatch, tmp_path):
    """THE REGRESSION TEST. An inherited path need not be a repo at all."""
    not_a_repo = tmp_path / "not-a-checkout"
    not_a_repo.mkdir()
    mod = _runner_with(monkeypatch, str(not_a_repo))
    problem = mod.default_repo_dir_problem()
    assert problem, "a non-checkout must be refused"
    assert str(not_a_repo) in problem


def test_a_default_repo_from_a_different_project_is_refused(monkeypatch, tmp_path):
    """The actual RA-7375 shape: a real checkout, of the wrong repository.

    This is what the Codex worktree was — `.git` present, so the existing
    `run_claim` check would have passed it straight through.
    """
    foreign = _repo_with_origin(tmp_path / "codex-worktree", "https://github.com/other/thing")
    mod = _runner_with(monkeypatch, str(foreign))
    problem = mod.default_repo_dir_problem()
    assert problem, "a checkout of another repository must be refused"
    assert "other/thing" in problem


def test_main_refuses_to_start_and_says_why(monkeypatch, tmp_path, capsys):
    """Refusing has to be legible and non-zero.

    Non-zero matters operationally: the launchd plist is
    `KeepAlive {SuccessfulExit: false}`, so a non-zero exit is retried every
    ThrottleInterval. The node keeps announcing the misconfiguration and starts
    working by itself the moment the operator fixes it — where exit 0 would
    leave it silently stopped until someone noticed.
    """
    foreign = _repo_with_origin(tmp_path / "elsewhere", "https://github.com/other/thing")
    mod = _runner_with(monkeypatch, str(foreign))
    # BOUND THE FAILURE MODE with `--once`, which terminates on BOTH branches:
    # with the guard, main() refuses before the loop; without it, one pass runs
    # and returns 0, so a regression fails this assertion instead of wedging.
    # There is no pytest-timeout here, so a hanging test stalls CI outright —
    # the first draft of this test did exactly that, for 60s, twice.
    monkeypatch.setattr(mod, "_api", lambda *a, **k: {})
    monkeypatch.setattr(sys, "argv", ["runner", "--once"])

    assert mod.main() != 0
    assert "REFUSED" in capsys.readouterr().out


# ── green controls: it must not refuse what is legitimate ────────────────────


def test_an_unset_variable_is_not_a_problem(monkeypatch):
    """GREEN CONTROL. The overwhelmingly common case must stay silent, and it
    must not even consult git — the default IS this checkout."""
    mod = _runner_with(monkeypatch, None)
    assert mod.default_repo_dir_problem() == ""


def test_pointing_at_this_very_checkout_is_not_a_problem(monkeypatch):
    """GREEN CONTROL. `bootstrap.sh` sets MESH_REPO_DIR to the node's own repo
    in the launchd plist, which is the intended use and must keep working."""
    mod = _runner_with(monkeypatch, str(REPO_ROOT))
    assert mod.default_repo_dir_problem() == ""


def test_a_deliberate_relocation_to_the_same_project_is_allowed(monkeypatch, tmp_path):
    """THE GREEN CONTROL THAT MATTERS MOST.

    RA-7375 is explicit that the variable is useful for a deliberately
    relocated runner. A guard that refused every override would satisfy all
    three refusal tests above while breaking that entirely — so a different
    directory, same `origin`, must be allowed.
    """
    clone = _repo_with_origin(tmp_path / "relocated", OWN_ORIGIN)
    mod = _runner_with(monkeypatch, str(clone))
    assert mod.default_repo_dir_problem() == ""


def test_main_does_not_refuse_when_the_default_is_sound(monkeypatch):
    """GREEN CONTROL for the startup gate: it must let a normal runner run.

    `--once` with no work returns 0 rather than looping; what is asserted here
    is only that the guard did not short-circuit startup.
    """
    mod = _runner_with(monkeypatch, None)
    monkeypatch.setattr(mod, "_api", lambda *a, **k: {})
    monkeypatch.setattr(sys, "argv", ["runner", "--once"])
    assert mod.main() == 0
