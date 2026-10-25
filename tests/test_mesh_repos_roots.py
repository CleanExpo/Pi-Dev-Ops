"""RA-8096 — the runner finds a product checkout outside the home folder.

Phill_Desktop keeps its clones on `D:\\`, the runner looked only in the home
folder, and 42 claims failed with "repo missing". `MESH_REPOS_ROOT` is now an
`os.pathsep` list and, unset on Windows, also covers every drive root. The
origin check still decides: a wider search must never pick a wrong repo.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from mesh_helpers import load_module

SLUG = "CleanExpo/RestoreAssist"


def _guard():
    return load_module("mesh_repo_guard_roots", "mesh/repo_guard.py")


def _clone(path: Path, origin: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", origin],
                   check=True, capture_output=True)
    return path


def test_checkout_under_second_root_is_found(tmp_path):
    """MUTATION CONTROL. With a single home root this returned a no-.git path."""
    guard = _guard()
    home, drive = tmp_path / "home", tmp_path / "D"
    home.mkdir()
    want = _clone(drive / "RestoreAssist", "https://github.com/CleanExpo/RestoreAssist.git")
    got = guard.repo_dir_for(SLUG, tmp_path / "pdo", [home, drive])
    assert got == want.resolve()


def test_wrong_origin_under_a_root_is_still_refused(tmp_path):
    guard = _guard()
    _clone(tmp_path / "D" / "RestoreAssist", "https://github.com/Someone/RestoreAssist.git")
    got = guard.repo_dir_for(SLUG, tmp_path / "pdo", [tmp_path / "home", tmp_path / "D"])
    assert not (got / ".git").exists()
    assert got.name == "not-a-checkout-of-CleanExpo-RestoreAssist"
    assert got.parent == (tmp_path / "home" / "RestoreAssist").resolve()


def test_single_path_root_still_accepted(tmp_path):
    guard = _guard()
    want = _clone(tmp_path / "RestoreAssist", "git@github.com:CleanExpo/RestoreAssist.git")
    assert guard.repo_dir_for(SLUG, tmp_path / "pdo", tmp_path) == want.resolve()


def test_env_list_is_the_whole_answer(tmp_path):
    guard = _guard()
    value = os.pathsep.join([str(tmp_path / "a"), " ", str(tmp_path / "b")])
    roots = guard.repos_roots(value, tmp_path / "home", windows=True)
    assert roots == [tmp_path / "a", tmp_path / "b"]


def test_unset_defaults_to_home_then_drive_roots(tmp_path, monkeypatch):
    guard = _guard()
    monkeypatch.setattr(guard, "_drive_roots", lambda: [Path("D:\\")])
    assert guard.repos_roots(None, tmp_path, windows=True) == [tmp_path, Path("D:\\")]
    assert guard.repos_roots("", tmp_path, windows=False) == [tmp_path]
