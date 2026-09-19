"""Candidate Git metadata cannot launch helpers in the privileged host process."""
import asyncio
import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from app.server import session_phases, spec_pipeline

_REAL_RUN = subprocess.run


@pytest.fixture
def repo(monkeypatch, tmp_path):
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)
    for key, value in {
        "GIT_AUTHOR_NAME": "Pipeline Test", "GIT_AUTHOR_EMAIL": "pipeline@example.test",
        "GIT_COMMITTER_NAME": "Pipeline Test", "GIT_COMMITTER_EMAIL": "pipeline@example.test",
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    }.items():
        monkeypatch.setenv(key, value)
    def raw(*args):
        return _REAL_RUN(
            ["git", *args], cwd=tmp_path, check=True, text=True, capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        ).stdout.strip()
    raw("init")
    (tmp_path / "file.txt").write_text("base\n", encoding="utf-8")
    raw("add", "-A")
    raw("commit", "-m", "Seed test")
    (tmp_path / "file.txt").write_text("changed\n", encoding="utf-8")
    raw("add", "-A")
    return tmp_path, raw


def guarded_call(entry, root, *args):
    if entry == "spec":
        try:
            return 0, spec_pipeline._git(str(root), *args), ""
        except RuntimeError as exc:
            return 1, "", str(exc)
    return asyncio.run(session_phases.run_cmd(str(root), "git", *args))


@pytest.mark.parametrize("entry", ["spec", "session"])
def test_candidate_precommit_hook_cannot_execute(repo, entry):
    root, _ = repo
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nprintf injected > hook-fired\n", encoding="utf-8")
    hook.chmod(0o755)
    rc, _, err = guarded_call(entry, root, "commit", "-m", "Candidate")
    assert not (root / "hook-fired").exists()
    assert rc == 0, err


@pytest.mark.parametrize("entry", ["spec", "session"])
def test_candidate_filter_configuration_cannot_execute(repo, entry):
    root, raw = repo
    (root / ".gitattributes").write_text("*.txt filter=hostile\n", encoding="utf-8")
    (root / "file.txt").write_text("new content\n", encoding="utf-8")
    raw("config", "filter.hostile.clean", "echo injected > filter-fired; cat")
    guarded_call(entry, root, "add", "-A")
    assert not (root / "filter-fired").exists()


@pytest.mark.parametrize("entry", ["spec", "session"])
def test_global_git_configuration_is_not_loaded(repo, monkeypatch, entry):
    root, _ = repo
    hooks = root / "external-hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\nprintf injected > global-hook-fired\n", encoding="utf-8")
    hook.chmod(0o755)
    global_config = root / "global.config"
    global_config.write_text(f'[core]\n hooksPath = "{hooks.as_posix()}"\n', encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    rc, _, err = guarded_call(entry, root, "commit", "-m", "Candidate")
    assert not (root / "global-hook-fired").exists()
    assert rc == 0, err


def test_explicit_clone_header_survives_but_inherited_command_config_does_not(repo, monkeypatch):
    root, _ = repo
    monkeypatch.setenv("GITHUB_TOKEN", "test-only-header-token")
    authorized = session_phases._git_clone_env("https://github.com/example/repo")
    authorized["GIT_CONFIG_COUNT"] = "2"
    authorized["GIT_CONFIG_KEY_1"] = "core.sshCommand"
    authorized["GIT_CONFIG_VALUE_1"] = "hostile-command"
    proc = Mock(returncode=0, communicate=AsyncMock(return_value=(b"", b"")))
    create = AsyncMock(return_value=proc)
    monkeypatch.setattr(session_phases.asyncio, "create_subprocess_exec", create)
    assert asyncio.run(session_phases.run_cmd(root, "git", "status", env=authorized))[0] == 0
    args = create.call_args.args
    env = create.call_args.kwargs["env"]
    assert "test-only-header-token" not in " ".join(args)
    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert env["GIT_CONFIG_VALUE_0"] == authorized["GIT_CONFIG_VALUE_0"]
    assert "hostile-command" not in env.values()
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert Path(args[0]).is_absolute()


@pytest.mark.parametrize("entry", ["spec", "session"])
def test_repository_include_cannot_load_executable_config(repo, entry):
    root, raw = repo
    included = root / "included.config"
    included.write_text('[filter "hostile"]\n clean = echo injected > include-fired; cat\n', encoding="utf-8")
    raw("config", "include.path", str(included))
    (root / ".gitattributes").write_text("*.txt filter=hostile\n", encoding="utf-8")
    (root / "file.txt").write_text("new content\n", encoding="utf-8")
    rc, _, _ = guarded_call(entry, root, "add", "-A")
    assert rc != 0
    assert not (root / "include-fired").exists()


def test_managed_worktree_remains_usable(repo):
    root, _ = repo
    worktree = root.parent / (root.name + "-worker")
    rc, _, err = guarded_call("session", root, "worktree", "add", str(worktree), "-b", "worker")
    assert rc == 0, err
    rc, output, err = guarded_call("session", worktree, "rev-parse", "HEAD")
    assert rc == 0, err
    assert len(output.strip()) == 40
