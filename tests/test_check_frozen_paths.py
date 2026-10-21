"""Tests for scripts/check_frozen_paths.py — each runs the guard against a throwaway git repo."""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_frozen_paths.py"
spec = importlib.util.spec_from_file_location("check_frozen_paths", SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def sh(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def write(repo, rel, text):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def commit(repo, msg):
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", msg)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                          text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    sh(tmp_path, "init", "-q")
    write(tmp_path, "app/server/tao_loop.py", "x = 1\n")
    write(tmp_path, "app/server/spec_pipeline/execution.py", "y = 1\n")
    write(tmp_path, "app/server/mesh_lanes.py", "z = 1\n")
    write(tmp_path, ".github/frozen-paths.txt",
          "# comment\napp/server/tao_*.py\napp/server/spec_pipeline/**\n")
    base = commit(tmp_path, "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path, base


def run(base, head):
    return guard.main(["--base", base, "--head", head])


def test_frozen_file_edit_fails(repo, capsys):
    r, base = repo
    write(r, "app/server/tao_loop.py", "x = 2\n")
    head = commit(r, "edit frozen")
    assert run(base, head) == 1
    assert "app/server/tao_loop.py" in capsys.readouterr().out


def test_frozen_directory_edit_fails(repo):
    r, base = repo
    write(r, "app/server/spec_pipeline/execution.py", "y = 2\n")
    assert run(base, commit(r, "edit frozen dir")) == 1


def test_unfrozen_edit_passes(repo, capsys):
    r, base = repo
    write(r, "app/server/mesh_lanes.py", "z = 2\n")
    assert run(base, commit(r, "edit open file")) == 0
    assert "PASS" in capsys.readouterr().out


def test_delete_and_rename_of_frozen_file_fail(repo):
    r, base = repo
    sh(r, "mv", "app/server/tao_loop.py", "app/server/renamed.py")
    assert run(base, commit(r, "rename frozen")) == 1


def test_star_does_not_cross_directories(repo):
    r, base = repo
    write(r, "app/server/tao_sub/inner.py", "q = 1\n")
    assert run(base, commit(r, "nested file under a tao_ dir")) == 0


def test_same_change_manifest_edit_cannot_unfreeze(repo):
    r, base = repo
    write(r, ".github/frozen-paths.txt", "app/server/spec_pipeline/**\n")
    write(r, "app/server/tao_loop.py", "x = 3\n")
    assert run(base, commit(r, "drop pattern and edit")) == 1


def test_manifest_only_unfreeze_then_edit_passes(repo):
    r, base = repo
    write(r, ".github/frozen-paths.txt", "app/server/spec_pipeline/**\n")
    unfreeze = commit(r, "unfreeze tao")
    assert run(base, unfreeze) == 0
    write(r, "app/server/tao_loop.py", "x = 4\n")
    assert run(unfreeze, commit(r, "edit after unfreeze")) == 0


def test_empty_manifest_fails(repo):
    r, base = repo
    write(r, ".github/frozen-paths.txt", "# nothing\n")
    empty = commit(r, "empty manifest")
    write(r, "app/server/mesh_lanes.py", "z = 5\n")
    assert run(empty, commit(r, "any edit")) == 1


def test_verify_manifest_flags_dead_pattern(repo, capsys):
    r, _ = repo
    write(r, ".github/frozen-paths.txt", "app/server/tao_*.py\napp/server/gone_*.py\n")
    commit(r, "dead pattern")
    assert guard.main(["--verify-manifest"]) == 1
    assert "gone_*.py" in capsys.readouterr().out


def test_verify_manifest_min_files(repo):
    r, _ = repo
    assert guard.main(["--verify-manifest"]) == 0
    assert guard.main(["--verify-manifest", "--min-files", "50"]) == 1


def test_git_error_exits_2(repo):
    assert run("no-such-rev", "HEAD") == 2
