"""cd lockout fix (RA-8135): outside Git, allow exactly `cd <project root>` and nothing else."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "senior-harness" / "scripts"))

from setup_state import _outside_git_tool  # noqa: E402


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    return root


def bash(command, cwd):
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}


def denied(out):
    return "deny" in str(out).lower()


@pytest.mark.parametrize("cmd", ['cd "$CLAUDE_PROJECT_DIR"', "cd ${{CLAUDE_PROJECT_DIR}}", "cd {root}"])
def test_cd_back_to_root_allowed_outside_git(repo, tmp_path, cmd):
    out = _outside_git_tool(bash(cmd.format(root=repo), tmp_path), "PreToolUse")
    assert not denied(out)


@pytest.mark.parametrize("cmd", ['cd "$CLAUDE_PROJECT_DIR" && rm -rf x', "cd {root}/sub", "cd /tmp",
                                 'cd "$CLAUDE_PROJECT_DIR"; touch x', "ls", "cd $HOME"])
def test_outside_git_still_denies_everything_else(repo, tmp_path, cmd):
    out = _outside_git_tool(bash(cmd.format(root=repo), tmp_path), "PreToolUse")
    assert denied(out)


def test_cd_root_not_allowed_when_project_dir_not_git(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert denied(_outside_git_tool(bash(f"cd {tmp_path}", tmp_path), "PreToolUse"))


@pytest.mark.parametrize("cmd", ["cd '$CLAUDE_PROJECT_DIR'", "cd \\$CLAUDE_PROJECT_DIR", "cd '${CLAUDE_PROJECT_DIR}'"])
def test_quoted_project_var_is_not_recovery(tmp_path, monkeypatch, cmd):
    import setup_cwd

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    outside = tmp_path / "outside"
    outside.mkdir()
    payload = {"tool_name": "Bash", "cwd": str(outside), "tool_input": {"command": cmd}}
    assert setup_cwd.is_cd_to_project_root(payload) is False


@pytest.mark.parametrize("cmd", ["cd proj", "cd ./proj", "cd proj/sub/.."])
def test_relative_cd_is_not_recovery(repo, tmp_path, monkeypatch, cmd):
    # Bash looks a relative name up in CDPATH first, so it may land outside the project root.
    monkeypatch.setenv("CDPATH", str(tmp_path / "elsewhere"))
    assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))


def test_symlink_then_parent_is_not_recovery(repo, tmp_path):
    # Bash cd is logical: it drops `link/..` as text, so it lands in `other`, not in the project.
    other = tmp_path / "other"
    (other / ".git").mkdir(parents=True)
    (other / "link").symlink_to(repo / "sub")
    cmd = f"cd {other}/link/.."
    landed = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c", f"{cmd} && pwd -P"],
                            capture_output=True, text=True, check=True).stdout.strip()
    assert Path(landed).resolve() == other.resolve()
    assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))
