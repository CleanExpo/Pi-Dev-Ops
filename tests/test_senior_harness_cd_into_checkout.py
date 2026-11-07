"""Outside Git, a bare `cd <path>` into any existing Git checkout folder is allowed.

The exact `cd "<CLAUDE_PROJECT_DIR>"` string (RA-8135) only helps when that variable names a
checkout. A session that left Git any other way was locked out. This rule allows one more
shape: the whole command is `cd <path>` or `cd "<path>"`, the path is absolute with no `..`,
holds no shell-special character, and Git itself says it is inside a work tree.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "senior-harness" / "scripts"))

from setup_state import _outside_git_tool  # noqa: E402


@pytest.fixture()
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "other-repo"
    (root / "sub dir").mkdir(parents=True)
    (root / "plain").mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    # No usable project root, so the RA-8135 exact string cannot be what allows these.
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "missing"))
    return root


def bash(command: str, cwd: Path) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}


def denied(out: object) -> bool:
    return "deny" in str(out).lower()


def real_bash(command: str, cwd: Path) -> Path | None:
    run = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c", f"{command} && pwd -P"],
                         cwd=cwd, env={"PATH": "/usr/bin:/bin", "HOME": str(cwd), "CDPATH": str(cwd)},
                         capture_output=True, text=True)
    return Path(run.stdout.split("\n")[-2]).resolve() if run.returncode == 0 else None


def inside_git(path: Path) -> bool:
    r = subprocess.run(["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout == "true\n"


@pytest.mark.parametrize("cmd", ['cd "{root}"', "cd {root}", 'cd "{root}/sub dir"', "cd {root}/plain",
                                 "cd {root}/plain/", '  cd "{root}/sub dir"\n', "\tcd {root}/plain "])
def test_cd_into_any_checkout_folder_is_allowed_and_lands_in_git(
    checkout: Path, tmp_path: Path, cmd: str
) -> None:
    cmd = cmd.replace("{root}", str(checkout))
    assert not denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse")), cmd
    # Positive control: real Bash, with a hostile CDPATH, lands inside a Git work tree.
    landed = real_bash(cmd.strip(), tmp_path)
    assert landed is not None and inside_git(landed)


def test_symlink_into_a_checkout_is_allowed(checkout: Path, tmp_path: Path) -> None:
    link = tmp_path / "link"
    link.symlink_to(checkout / "plain")
    cmd = f"cd {link}"
    assert not denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse"))
    assert real_bash(cmd, tmp_path) == (checkout / "plain").resolve()


@pytest.mark.parametrize("cmd", [
    "cd {tmp}/not-git", 'cd "{tmp}/not-git"', "cd {tmp}/missing-dir", "cd {root}/file.txt",
    "cd {root}/.git", 'cd "{root}/sub dir/.."', "cd {root}/plain/..", "cd plain", 'cd "sub dir"',
    "cd {root}/plain; rm -rf x", "cd {root}/plain && touch x", "cd {root}/plain | cat",
    "cd {root}/plain > x", "cd {root}/plain < x", "cd {root}/plain &", "cd $HOME", "cd ~",
    "cd ~/x", "cd `pwd`", "cd {root}/pl[a]in", "cd {root}/pl{{a,b}}in", "cd {root}/pl*",
    "cd {root}/pl?in", "cd {root}/(plain)", "cd '{root}/plain'", "cd {root}/sub\\ dir",
    'cd "{root}/sub dir" x', "cd {root}/sub dir", "cd  {root}/plain", "cd\t{root}/plain",
    "cd -P {root}/plain", 'cd "{root}/plain"\r', "cd {root}/plain\x00", 'cd "{root}/pl$x"',
    'cd "{root}/pl`x`"', 'cd "{root}/pl\\ain"', 'cd "{root}/pl!in"', "cd", "cd ''", 'cd ""',
    "pushd {root}/plain", "cd {root}/plain #x",
])
def test_everything_else_stays_denied(checkout: Path, tmp_path: Path, cmd: str) -> None:
    (tmp_path / "not-git").mkdir()
    (checkout / "file.txt").write_text("x")
    cmd = cmd.replace("{root}", str(checkout)).replace("{tmp}", str(tmp_path))
    cmd = cmd.replace("{{", "{").replace("}}", "}")
    assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse")), cmd


_UNSAFE_NAMES = ["a;pwd", "a&b", "a|b", "a<b", "a>b", "a$b", "a`b", "a(b)", "a[b]", "a{b}",
                 "a*b", "a?b", "a#b", "a'b", "a~b", "a\\b", "a!b", 'a"b', "a\tb", "a\nb", "a\x7fb"]


@pytest.mark.parametrize("name", _UNSAFE_NAMES)
@pytest.mark.parametrize("quoted", [False, True])
def test_unsafe_character_is_denied_even_when_the_folder_exists(
    checkout: Path, tmp_path: Path, name: str, quoted: bool
) -> None:
    # The folder is real and inside Git, so only the character check can deny it. Codex
    # showed the old fixture let every punctuation case fail later, on "not a folder".
    (checkout / name).mkdir()
    assert inside_git(checkout / name)
    path = f"{checkout}/{name}"
    cmd = f'cd "{path}"' if quoted else f"cd {path}"
    assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse")), repr(cmd)


def test_relative_and_dotdot_paths_are_denied_even_when_they_resolve_into_git(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Run from inside the checkout so every relative form names a real Git folder.
    monkeypatch.chdir(checkout / "plain")
    for cmd in ["cd ../plain", "cd .", "cd ..", f"cd {checkout}/plain/../plain", "cd plain/.."]:
        assert denied(_outside_git_tool(bash(cmd, tmp_path), "PreToolUse")), cmd


def test_fake_git_dir_is_not_a_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "fake"
    (fake / ".git").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "missing"))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    assert not inside_git(fake)
    assert denied(_outside_git_tool(bash(f"cd {fake}", tmp_path), "PreToolUse"))


def test_inherited_git_overrides_cannot_fake_a_checkout(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "fake"
    fake.mkdir()
    monkeypatch.setenv("GIT_DIR", str(checkout / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(fake))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    assert denied(_outside_git_tool(bash(f"cd {fake}", tmp_path), "PreToolUse"))
    # Positive control: a real checkout folder is still allowed with the overrides set.
    assert not denied(_outside_git_tool(bash(f"cd {checkout}/plain", tmp_path), "PreToolUse"))


def test_non_cd_payload_never_runs_the_git_probe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import setup_cwd

    calls: list[str] = []
    monkeypatch.setattr(setup_cwd, "_inside_git_work_tree", lambda p: calls.append(p) or True)
    for cmd in ["ls", "cd /x; ls", "echo cd /x"]:
        assert not setup_cwd.is_cd_into_git_checkout(bash(cmd, tmp_path))
    assert not setup_cwd.is_cd_into_git_checkout({"tool_name": "Read", "tool_input": {"file_path": "/x"}})
    assert calls == []
