"""tests/test_mesh_repo_roots.py — RA-8096: the runner must find a product
checkout that is not under the home folder.

On Phill_Desktop the checkouts live on `D:\\` (`D:\\RestoreAssist`, ...), the
runner looked only under `MESH_REPOS_ROOT` (default: home), nothing set the
variable, and 42 claims failed "repo missing". The fix: `repo_roots()` turns
`MESH_REPOS_ROOT` into a path LIST, and when it is unset searches home plus
every drive root on Windows. `repo_dir_for()` tries each root in order and
still accepts a candidate only when its `origin` is the claimed repo.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "mesh"))

import repo_guard  # noqa: E402


def _clone_with_origin(path: Path, origin: str) -> Path:
    """A real git checkout at `path` whose origin is `origin`."""
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", origin],
                   check=True, capture_output=True)
    return path


def test_checkout_on_a_second_root_is_found(tmp_path):
    home, drive = tmp_path / "home", tmp_path / "D"
    home.mkdir()
    ra = _clone_with_origin(drive / "RestoreAssist", "https://github.com/CleanExpo/RestoreAssist.git")
    own = _clone_with_origin(tmp_path / "pdo", "https://github.com/CleanExpo/Pi-Dev-Ops.git")
    got = repo_guard.repo_dir_for("CleanExpo/RestoreAssist", own, [home, drive])
    assert got == ra.resolve()


def test_single_path_root_still_works(tmp_path):
    ra = _clone_with_origin(tmp_path / "RestoreAssist", "https://github.com/CleanExpo/RestoreAssist.git")
    own = _clone_with_origin(tmp_path / "pdo", "https://github.com/CleanExpo/Pi-Dev-Ops.git")
    assert repo_guard.repo_dir_for("CleanExpo/RestoreAssist", own, tmp_path) == ra.resolve()


def test_wrong_origin_on_every_root_is_still_refused(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _clone_with_origin(a / "RestoreAssist", "https://github.com/someone-else/RestoreAssist.git")
    _clone_with_origin(b / "RestoreAssist", "https://github.com/CleanExpo/Synthex.git")
    own = _clone_with_origin(tmp_path / "pdo", "https://github.com/CleanExpo/Pi-Dev-Ops.git")
    got = repo_guard.repo_dir_for("CleanExpo/RestoreAssist", own, [a, b])
    assert not (got / ".git").exists()
    assert "not-a-checkout-of-CleanExpo-RestoreAssist" in str(got)


def test_env_value_is_a_path_list(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    roots = repo_guard.repo_roots(f"{a}{os.pathsep}{b}", home=tmp_path / "h", drives=[tmp_path / "X"])
    assert roots == [a, b]


def test_unset_env_searches_home_then_drive_roots(tmp_path):
    home, d = tmp_path / "h", tmp_path / "D"
    assert repo_guard.repo_roots("", home=home, drives=[d]) == [home, d]
    assert repo_guard.repo_roots("  ", home=home, drives=[]) == [home]


def test_windows_drive_roots_only_on_windows(monkeypatch):
    monkeypatch.setattr(repo_guard.os, "name", "posix")
    assert repo_guard.windows_drive_roots() == []
