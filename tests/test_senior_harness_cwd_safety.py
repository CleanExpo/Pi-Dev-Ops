"""cd lockout fix (RA-8135): outside Git, allow only exact `cd "<project root>"` strings."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "senior-harness" / "scripts"))

from setup_state import _outside_git_tool  # noqa: E402

VAR_FORMS = ['cd "$CLAUDE_PROJECT_DIR"', 'cd "${CLAUDE_PROJECT_DIR}"']


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


def real_bash(command, cwd, env_extra=None):
    """Where real Bash lands for `command` (physical path), or None when cd fails."""
    env = {"PATH": "/usr/bin:/bin", "HOME": str(cwd)} | (env_extra or {})
    run = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c", f"{command} && pwd -P"],
                         cwd=cwd, env=env, capture_output=True, text=True)
    # A cd found through CDPATH prints the directory first, so the last line is `pwd -P`.
    return Path(run.stdout.strip().splitlines()[-1]).resolve() if run.returncode == 0 else None


@pytest.mark.parametrize("cmd", ['cd "{root}"', '  cd "{root}"\n', '\tcd "{root}" '])
def test_exact_recovery_strings_allowed_and_land_in_root(repo, tmp_path, cmd):
    cmd = cmd.replace("{root}", str(repo))
    assert not denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))
    # Positive control: real Bash, with a hostile CDPATH, really lands in the root.
    env = {"CLAUDE_PROJECT_DIR": str(repo), "CDPATH": str(tmp_path)}
    assert real_bash(cmd.strip(), tmp_path, env) == repo.resolve()


@pytest.mark.parametrize("cmd", ['cd "{root}" && rm -rf x', 'cd "{root}/sub"', "cd /tmp", "cd {root}",
                                 'cd "$CLAUDE_PROJECT_DIR"; touch x', "ls", "cd $HOME", "cd ~",
                                 "cd $CLAUDE_PROJECT_DIR", "cd ${{CLAUDE_PROJECT_DIR}}", "cd  \"{root}\"",
                                 "cd '{root}'", 'cd "{root}"\r', *VAR_FORMS, '\tcd "$CLAUDE_PROJECT_DIR" ', 'cd "{root}"\xa0', 'cd "{root}/"', "", "cd"])
def test_outside_git_denies_everything_else(repo, tmp_path, cmd):
    cmd = cmd.replace("{root}", str(repo)).replace("{{", "{").replace("}}", "}")
    assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))


@pytest.mark.parametrize("value", ["relative/proj", "{tmp}/proj/sub/..", "{tmp}/not-git", "{tmp}/a$b",
                                   "{tmp}/a`b", '{tmp}/a"b', "{tmp}/a\\b", "{tmp}/a!b", ""])
def test_unsafe_or_non_git_project_dir_never_recovers(tmp_path, monkeypatch, value):
    value = value.replace("{tmp}", str(tmp_path))
    (tmp_path / "proj" / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(tmp_path / "proj")], check=True)
    (tmp_path / "not-git").mkdir()
    if value.startswith(str(tmp_path)) and ".." not in value and "not-git" not in value:
        os.makedirs(value, exist_ok=True)
        subprocess.run(["git", "init", "-q", value], check=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", value)
    for cmd in [f'cd "{value}"', *VAR_FORMS]:
        out = _outside_git_tool(bash(cmd, tmp_path), "PreToolUse")
        assert denied(out) and "run exactly" not in str(out)


def test_relative_project_dir_never_recovers_even_if_it_is_a_checkout(repo, tmp_path, monkeypatch):
    # A relative value resolves against the hook's cwd but Bash searches CDPATH: never trust it.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "proj")
    for cmd in ['cd "proj"', *VAR_FORMS]:
        assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))


def test_deny_message_names_the_exact_command(repo, tmp_path):
    out = str(_outside_git_tool(bash("ls", tmp_path), "PreToolUse"))
    assert f'run exactly this command and nothing else: cd "{repo}"' in out


# Regression tests for every bypass the parser-based check let through (Codex rounds 1-2).
# Each one shows real Bash landing in a different checkout, then that the hook denies it.


def test_symlink_then_parent_stays_denied(repo, tmp_path):
    other = tmp_path / "other"
    (other / ".git").mkdir(parents=True)
    (other / "link").symlink_to(repo / "sub")
    cmd = f'cd "{other}/link/.."'
    assert real_bash(cmd, tmp_path) == other.resolve()
    assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))


def test_quoted_tilde_stays_denied(repo, tmp_path):
    decoy = tmp_path / "~" / "proj"
    (decoy / ".git").mkdir(parents=True)
    cmd = 'cd "~/proj"'
    assert real_bash(cmd, tmp_path, {"HOME": str(tmp_path)}) == decoy.resolve()
    assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))


def test_cdpath_relative_name_stays_denied(repo, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "proj" / ".git").mkdir(parents=True)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    cmd = 'cd "proj"'
    assert real_bash(cmd, cwd, {"CDPATH": str(elsewhere)}) == (elsewhere / "proj").resolve()
    assert denied(_outside_git_tool(bash(cmd, cwd), "PreToolUse"))


def test_variable_forms_denied_because_bash_lacks_the_variable(repo, tmp_path):
    # Claude Code does not export CLAUDE_PROJECT_DIR to Bash: `cd ""` succeeds but stays put.
    for cmd in VAR_FORMS:
        assert real_bash(cmd, tmp_path) == tmp_path.resolve()
        assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))


@pytest.mark.parametrize("kind", ["empty-dir", "stale-file"])
def test_fake_git_entry_is_not_a_checkout(tmp_path, monkeypatch, kind):
    root = tmp_path / "fake"
    root.mkdir()
    if kind == "empty-dir":
        (root / ".git").mkdir()
    else:
        (root / ".git").write_text("gitdir: /nonexistent\n")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    out = _outside_git_tool(bash(f'cd "{root}"', tmp_path), "PreToolUse")
    assert denied(out) and "run exactly" not in str(out)


def test_subdirectory_of_checkout_is_not_the_root(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo / "sub"))
    out = _outside_git_tool(bash(f'cd "{repo / 'sub'}"', tmp_path), "PreToolUse")
    assert denied(out) and "run exactly" not in str(out)
