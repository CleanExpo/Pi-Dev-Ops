"""cd lockout fix (RA-8135): outside Git, allow only exact `cd "<project root>"` strings."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "senior-harness" / "scripts"))

from setup_state import _outside_git_tool  # noqa: E402

VAR_FORMS = ['cd "$CLAUDE_PROJECT_DIR"', 'cd "${CLAUDE_PROJECT_DIR}"']


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    (root / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    return root


def bash(command: str, cwd: Path) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}


def denied(out: object) -> bool:
    return "deny" in str(out).lower()


def real_bash(command: str, cwd: Path, env_extra: dict[str, str] | None = None) -> Path | None:
    """Where real Bash lands for `command` (physical path), or None when cd fails."""
    env = {"PATH": "/usr/bin:/bin", "HOME": str(cwd)} | (env_extra or {})
    run = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c", f"{command} && pwd -P"],
                         cwd=cwd, env=env, capture_output=True, text=True)
    # A cd found through CDPATH prints the directory first, so the last line is `pwd -P`.
    # Split on newlines only: a root may end in a space, which a bare strip() would drop.
    return Path(run.stdout.split("\n")[-2]).resolve() if run.returncode == 0 else None


@pytest.mark.parametrize("cmd", ['cd "{root}"', '  cd "{root}"\n', '\tcd "{root}" '])
def test_exact_recovery_strings_allowed_and_land_in_root(repo: Path, tmp_path: Path, cmd: str) -> None:
    cmd = cmd.replace("{root}", str(repo))
    assert not denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))
    # Positive control: real Bash, with a hostile CDPATH, really lands in the root.
    env = {"CLAUDE_PROJECT_DIR": str(repo), "CDPATH": str(tmp_path)}
    assert real_bash(cmd.strip(), tmp_path, env) == repo.resolve()


# `cd "{root}/sub"`, `cd {root}` and `cd "{root}/"` are allowed by the cd-into-checkout
# rule; see tests/test_senior_harness_cd_into_checkout.py.
@pytest.mark.parametrize("cmd", ['cd "{root}" && rm -rf x', "cd /tmp",
                                 'cd "$CLAUDE_PROJECT_DIR"; touch x', "ls", "cd $HOME", "cd ~",
                                 "cd $CLAUDE_PROJECT_DIR", "cd ${{CLAUDE_PROJECT_DIR}}", "cd  \"{root}\"",
                                 "cd '{root}'", 'cd "{root}"\r', *VAR_FORMS, '\tcd "$CLAUDE_PROJECT_DIR" ', 'cd "{root}"\xa0', "", "cd"])
def test_outside_git_denies_everything_else(repo: Path, tmp_path: Path, cmd: str) -> None:
    cmd = cmd.replace("{root}", str(repo)).replace("{{", "{").replace("}}", "}")
    assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))


@pytest.mark.parametrize("value", ["relative/proj", "{tmp}/proj/sub/..", "{tmp}/not-git", "{tmp}/a$b",
                                   "{tmp}/a`b", '{tmp}/a"b', "{tmp}/a\\b", "{tmp}/a!b", ""])
def test_unsafe_or_non_git_project_dir_never_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
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


def test_relative_project_dir_never_recovers_even_if_it_is_a_checkout(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A relative value resolves against the hook's cwd but Bash searches CDPATH: never trust it.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "proj")
    for cmd in ['cd "proj"', *VAR_FORMS]:
        assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))


def test_deny_message_names_the_exact_command(repo: Path, tmp_path: Path) -> None:
    out = str(_outside_git_tool(bash("ls", tmp_path), "PreToolUse"))
    assert f'run exactly this command and nothing else: cd "{repo}"' in out


# Regression tests for every bypass the parser-based check let through (Codex rounds 1-2).
# Each one shows real Bash landing in a different checkout, then that the hook denies it.


def test_symlink_then_parent_stays_denied(repo: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    (other / ".git").mkdir(parents=True)
    (other / "link").symlink_to(repo / "sub")
    cmd = f'cd "{other}/link/.."'
    assert real_bash(cmd, tmp_path) == other.resolve()
    assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))


def test_quoted_tilde_stays_denied(repo: Path, tmp_path: Path) -> None:
    decoy = tmp_path / "~" / "proj"
    (decoy / ".git").mkdir(parents=True)
    cmd = 'cd "~/proj"'
    assert real_bash(cmd, tmp_path, {"HOME": str(tmp_path)}) == decoy.resolve()
    assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))


def test_cdpath_relative_name_stays_denied(repo: Path, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "proj" / ".git").mkdir(parents=True)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    cmd = 'cd "proj"'
    assert real_bash(cmd, cwd, {"CDPATH": str(elsewhere)}) == (elsewhere / "proj").resolve()
    assert denied(_outside_git_tool(bash(cmd, cwd), "PreToolUse"))


def test_variable_forms_denied_because_bash_lacks_the_variable(repo: Path, tmp_path: Path) -> None:
    # Claude Code does not export CLAUDE_PROJECT_DIR to Bash: `cd ""` succeeds but stays put.
    for cmd in VAR_FORMS:
        assert real_bash(cmd, tmp_path) == tmp_path.resolve()
        assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))


@pytest.mark.parametrize("kind", ["empty-dir", "stale-file"])
def test_fake_git_entry_is_not_a_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
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


def test_subdirectory_of_checkout_is_not_the_root(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub = repo / "sub"
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(sub))
    out = _outside_git_tool(bash("ls", tmp_path), "PreToolUse")
    assert denied(out) and "run exactly" not in str(out)
    # The cd itself is allowed by the cd-into-checkout rule, not offered as the project root.
    out = str(_outside_git_tool(bash(f'cd "{sub}"', tmp_path), "PreToolUse"))
    assert not denied(out) and "Git checkout folder" in out


def test_inherited_git_overrides_cannot_fake_a_checkout(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "fake"
    fake.mkdir()
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(fake))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(fake))
    out = _outside_git_tool(bash(f'cd "{fake}"', tmp_path), "PreToolUse")
    assert denied(out) and "run exactly" not in str(out)
    # Positive control: the real checkout still recovers with the same overrides set.
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    assert not denied(_outside_git_tool(bash(f'cd "{repo}"', tmp_path), "PreToolUse"))


def test_root_ending_in_a_space_recovers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Git prints the root plus one newline; trimming more would drop the trailing space.
    root = tmp_path / "proj "
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    cmd = f'cd "{root}"'
    assert real_bash(cmd, tmp_path) == root.resolve()
    assert not denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))
    assert f"run exactly this command and nothing else: {cmd}" in str(
        _outside_git_tool(bash("ls", tmp_path), "PreToolUse"))


def test_non_bash_payload_never_runs_the_git_probe(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import setup_cwd

    calls: list[None] = []
    monkeypatch.setattr(setup_cwd, "recovery_command", lambda: calls.append(None) or None)
    assert not setup_cwd.is_cd_to_project_root({"tool_name": "Read", "tool_input": {"file_path": "x"}})
    assert calls == []


@pytest.mark.parametrize("cmd", ['cd "{root}"', "ls"])
def test_outside_git_tool_probes_the_root_once(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cmd: str
) -> None:
    import setup_cwd
    import setup_state

    calls: list[None] = []
    real = setup_cwd.recovery_command

    def counted() -> str | None:
        calls.append(None)
        return real()

    monkeypatch.setattr(setup_state, "recovery_command", counted)
    monkeypatch.setattr(setup_cwd, "recovery_command", counted)
    _outside_git_tool(bash(cmd.replace("{root}", str(repo)), tmp_path), "PreToolUse")
    assert len(calls) == 1
