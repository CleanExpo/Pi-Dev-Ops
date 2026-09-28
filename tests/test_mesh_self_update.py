"""tests/test_mesh_self_update.py — a runtime moves to origin/main only if the new code passes (RA-7802).

Runtimes never updated themselves, so each runner fix meant carrying it to three
machines by hand, and on 28/09 two machines ran different code. These tests use
REAL git repositories: an "origin", and a runtime cloned from it, with the new
commit's `mesh/preflight.py` deciding whether the move sticks.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

from mesh_helpers import load_module as _load  # noqa: E402

su = _load("mesh_self_update_under_test", "mesh/self_update.py")
hb = _load("mesh_heartbeat_version", "mesh/heartbeat.py")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def commit_preflight(repo: Path, exit_code: int, message: str) -> str:
    """Commit a mesh/preflight.py that prints `message` and exits `exit_code`."""
    (repo / "mesh").mkdir(exist_ok=True)
    commit_preflight.n += 1  # identical commits are ONE commit to git: keep each distinct
    (repo / "mesh" / "preflight.py").write_text(
        f"import sys\n# {commit_preflight.n}\nprint({message!r})\nsys.exit({exit_code})\n")
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


commit_preflight.n = 0


def origin_and_runtime(tmp_path: Path) -> tuple[Path, Path, str]:
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    old = commit_preflight(origin, 0, "ok")
    runtime = tmp_path / "runtime"
    subprocess.run(["git", "clone", "-q", str(origin), str(runtime)], check=True)
    git(runtime, "checkout", "-q", "--detach", old)
    return origin, runtime, old


def test_nothing_new_is_current(tmp_path):
    _, runtime, old = origin_and_runtime(tmp_path)
    assert su.Updater(runtime, "claude").try_update() == "current"
    assert git(runtime, "rev-parse", "HEAD") == old


def test_new_code_that_passes_its_own_preflight_is_taken(tmp_path):
    origin, runtime, _ = origin_and_runtime(tmp_path)
    new = commit_preflight(origin, 0, "ok")
    assert su.Updater(runtime, "claude").try_update() == "updated"
    assert git(runtime, "rev-parse", "HEAD") == new


def test_new_code_that_fails_its_own_preflight_is_rolled_back(tmp_path):
    origin, runtime, old = origin_and_runtime(tmp_path)
    commit_preflight(origin, 1, "agent could not write a file")
    assert su.Updater(runtime, "claude").try_update() == "rolled back: agent could not write a file"
    assert git(runtime, "rev-parse", "HEAD") == old


def test_a_rewritten_main_is_refused_not_followed(tmp_path):
    origin, runtime, old = origin_and_runtime(tmp_path)
    git(origin, "checkout", "-q", "--orphan", "rewrite")
    commit_preflight(origin, 0, "ok")
    git(origin, "branch", "-q", "-D", "main")
    git(origin, "branch", "-q", "-m", "main")
    assert su.Updater(runtime, "claude").try_update().startswith("update refused")
    assert git(runtime, "rev-parse", "HEAD") == old


def test_the_heartbeat_reports_the_runner_version_and_its_gate():
    crumb = {"state": "quarantined", "version": "a" * 40}
    assert hb.node_version(crumb) == "nexus-mesh/" + "a" * 12
    assert hb.node_status([], crumb) == "quarantined"
    assert hb.node_status([{"runtime": "claude"}], {"state": "idle"}) == "working"
    assert hb.node_version({}) == "nexus-mesh/0.1"
