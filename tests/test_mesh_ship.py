"""Regression coverage for the Nexus Mesh ship wrapper (RA-7376).

`autogit ship` stages, commits and pushes UNCOMMITTED work. With a clean tree it
returns silently and pushes nothing — including commits already on the branch.
Every gate in this estate requires an agent to commit its own turn with a real
message, so a well-behaved agent ends with nothing staged and the Stop hook
becomes a guaranteed no-op: zero refs/heads/mesh/* ever reach origin.

These tests drive mesh/hooks/mesh_ship.sh against real local git repositories.
The autogit stub reproduces the defect exactly: it returns 0 and pushes nothing
when the tree is clean, which is what index.js v0.4.1 does at its
`if (!staged.length) return;` guard.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIP = REPO_ROOT / "mesh" / "hooks" / "mesh_ship.sh"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Mesh Test",
    "GIT_AUTHOR_EMAIL": "mesh@example.invalid",
    "GIT_COMMITTER_NAME": "Mesh Test",
    "GIT_COMMITTER_EMAIL": "mesh@example.invalid",
}


def _git(*args: str, cwd: Path) -> str:
    """Run a git command in cwd and return stdout, failing loudly on error."""
    out = subprocess.run(
        ["git", *args], cwd=cwd, env={"PATH": "/usr/bin:/bin", **GIT_ENV},
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def _commit(clone: Path, name: str) -> None:
    """Create a committed change, leaving the working tree clean."""
    (clone / name).write_text(name, encoding="utf-8")
    _git("add", "-A", cwd=clone)
    _git("commit", "-q", "-m", f"add {name}", cwd=clone)


def _remote_heads(origin: Path) -> list[str]:
    """List branch names present on the bare origin."""
    out = _git("for-each-ref", "--format=%(refname:short)", "refs/heads", cwd=origin)
    return [line for line in out.splitlines() if line]


@pytest.fixture()
def mesh(tmp_path: Path):
    """A bare origin plus a clone on a mesh/* work branch with an opt-in marker."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git("init", "--bare", "-q", cwd=origin)

    clone = tmp_path / "work"
    clone.mkdir()
    _git("init", "-q", cwd=clone)
    _git("remote", "add", "origin", str(origin), cwd=clone)
    (clone / ".autogit.json").write_text("{}\n", encoding="utf-8")
    _git("add", "-A", cwd=clone)
    _git("commit", "-q", "-m", "seed", cwd=clone)
    _git("checkout", "-q", "-b", "mesh/test-node/ra-7376-abc123", cwd=clone)
    return {"origin": origin, "clone": clone, "log": tmp_path / "ship.log"}


def _run(mesh: dict, *, autogit_bin: Path | None = None, cwd: Path | None = None):
    """Invoke mesh_ship.sh with a controlled PATH and log destination."""
    path = "/usr/bin:/bin"
    if autogit_bin is not None:
        path = f"{autogit_bin}:{path}"
    return subprocess.run(
        ["bash", str(SHIP)],
        cwd=cwd or mesh["clone"],
        env={
            "PATH": path,
            "HOME": str(mesh["log"].parent),
            "MESH_SHIP_LOG": str(mesh["log"]),
            **GIT_ENV,
        },
        input="", capture_output=True, text=True,
    )


@pytest.fixture()
def autogit_noop(tmp_path: Path) -> Path:
    """An autogit stub reproducing the v0.4.1 clean-tree return: exit 0, push nothing."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "autogit"
    stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    return bindir


def test_autogit_alone_ships_nothing_when_the_tree_is_clean(mesh, autogit_noop):
    """RED: the defect itself — autogit is a no-op, so origin stays empty."""
    _commit(mesh["clone"], "turn-output.txt")
    subprocess.run(
        ["autogit", "ship"], cwd=mesh["clone"],
        env={"PATH": f"{autogit_noop}:/usr/bin:/bin", **GIT_ENV},
        input="", capture_output=True, text=True, check=True,
    )
    assert _remote_heads(mesh["origin"]) == [], "precondition: autogit pushed nothing"


def test_wrapper_pushes_already_committed_work(mesh, autogit_noop):
    """GREEN: the wrapper ships the commits autogit leaves behind."""
    _commit(mesh["clone"], "turn-output.txt")
    result = _run(mesh, autogit_bin=autogit_noop)
    assert result.returncode == 0
    assert "mesh/test-node/ra-7376-abc123" in _remote_heads(mesh["origin"])
    local = _git("rev-parse", "HEAD", cwd=mesh["clone"])
    remote = _git("rev-parse", "refs/heads/mesh/test-node/ra-7376-abc123", cwd=mesh["origin"])
    assert local == remote
    assert "pushed:" in mesh["log"].read_text(encoding="utf-8")


def test_wrapper_ships_without_autogit_installed(mesh):
    """RA-6505's symptom: a missing autogit must not stop committed work shipping."""
    _commit(mesh["clone"], "turn-output.txt")
    result = _run(mesh)
    assert result.returncode == 0
    assert "mesh/test-node/ra-7376-abc123" in _remote_heads(mesh["origin"])
    assert "autogit not on PATH" in mesh["log"].read_text(encoding="utf-8")


def test_second_run_is_a_no_op(mesh, autogit_noop):
    """Shipping twice must not error and must report up-to-date, not a fresh push."""
    _commit(mesh["clone"], "turn-output.txt")
    _run(mesh, autogit_bin=autogit_noop)
    mesh["log"].write_text("", encoding="utf-8")
    result = _run(mesh, autogit_bin=autogit_noop)
    assert result.returncode == 0
    assert "up-to-date:" in mesh["log"].read_text(encoding="utf-8")


@pytest.mark.parametrize("branch", ["main", "feat/thing", "fix/thing", "feature/thing"])
def test_protected_and_review_branches_are_never_pushed(mesh, autogit_noop, branch):
    """A protected or human review branch must never be auto-shipped."""
    _git("checkout", "-q", "-b", branch, cwd=mesh["clone"])
    _commit(mesh["clone"], "turn-output.txt")
    result = _run(mesh, autogit_bin=autogit_noop)
    assert result.returncode == 0
    assert _remote_heads(mesh["origin"]) == []
    assert "skip: protected/review branch" in mesh["log"].read_text(encoding="utf-8")


def test_non_mesh_branch_is_not_pushed(mesh, autogit_noop):
    """Only mesh/* work branches are shipped, even though autogit may still run."""
    _git("checkout", "-q", "-b", "scratch/experiment", cwd=mesh["clone"])
    _commit(mesh["clone"], "turn-output.txt")
    result = _run(mesh, autogit_bin=autogit_noop)
    assert result.returncode == 0
    assert _remote_heads(mesh["origin"]) == []
    assert "not a mesh/* work branch" in mesh["log"].read_text(encoding="utf-8")


def test_repo_without_optin_marker_is_skipped(mesh, autogit_noop):
    """The .autogit.json opt-in was documented but never enforced; now it is."""
    (mesh["clone"] / ".autogit.json").unlink()
    _git("add", "-A", cwd=mesh["clone"])
    _git("commit", "-q", "-m", "drop opt-in", cwd=mesh["clone"])
    result = _run(mesh, autogit_bin=autogit_noop)
    assert result.returncode == 0
    assert _remote_heads(mesh["origin"]) == []
    assert "no .autogit.json opt-in" in mesh["log"].read_text(encoding="utf-8")


def test_diverged_remote_fails_loudly_and_never_forces(mesh, autogit_noop, tmp_path):
    """A rejected push must be logged and surfaced, not swallowed by `|| true`."""
    branch = "mesh/test-node/ra-7376-abc123"
    _commit(mesh["clone"], "turn-output.txt")
    _run(mesh, autogit_bin=autogit_noop)
    other = tmp_path / "other"
    other.mkdir()
    _git("clone", "-q", str(mesh["origin"]), str(other), cwd=tmp_path)
    _git("checkout", "-q", branch, cwd=other)
    _commit(other, "someone-else.txt")
    _git("push", "-q", "origin", f"HEAD:refs/heads/{branch}", cwd=other)
    remote_before = _git("rev-parse", f"refs/heads/{branch}", cwd=mesh["origin"])

    _commit(mesh["clone"], "diverged.txt")
    mesh["log"].write_text("", encoding="utf-8")
    result = _run(mesh, autogit_bin=autogit_noop)

    assert result.returncode == 0, "a ship failure must never break the agent turn"
    assert "PUSH FAILED" in mesh["log"].read_text(encoding="utf-8")
    assert "push of" in result.stderr
    assert _git("rev-parse", f"refs/heads/{branch}", cwd=mesh["origin"]) == remote_before, (
        "the wrapper must never force-push over someone else's work"
    )


def test_non_git_directory_is_skipped(mesh, tmp_path):
    """Outside a repository the hook must exit quietly, not error."""
    plain = tmp_path / "plain"
    plain.mkdir()
    result = _run(mesh, cwd=plain)
    assert result.returncode == 0
    assert "not a git repository" in mesh["log"].read_text(encoding="utf-8")
