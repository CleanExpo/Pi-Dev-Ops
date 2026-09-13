"""UNI-2645 — one helper, every git path, empty token fails closed.

The sandbox re-clone, orchestrator clone, push, and autopr push used to
each invent their own auth (or none). An empty or whitespace-only GITHUB_TOKEN
then reached git, which prompted for a username and died with
`could not read Username` — identical to a rejected credential.
"""
from __future__ import annotations

import inspect
import logging

import pytest

from app.server.git_auth import (
    MISSING_CREDENTIAL,
    GitAuthError,
    git_auth_env,
    resolved_github_token,
)
from app.server import autopr, orchestrator, session_phases
from app.server.session_model import BuildSession


_GITHUB = "https://github.com/CleanExpo/Pi-Dev-Ops"


@pytest.mark.parametrize("value", ["", "   ", "\n", "\t\n", "  \n  "])
def test_empty_or_whitespace_token_fails_closed(monkeypatch, value):
    monkeypatch.setenv("GITHUB_TOKEN", value)
    with pytest.raises(GitAuthError) as ei:
        git_auth_env(_GITHUB)
    assert ei.value.reason == MISSING_CREDENTIAL
    assert "GITHUB_TOKEN" in str(ei.value)


def test_missing_token_fails_closed(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(GitAuthError) as ei:
        resolved_github_token()
    assert ei.value.reason == MISSING_CREDENTIAL


def test_trailing_newline_is_stripped(monkeypatch):
    """Railway/Vercel append a newline; strip must keep a real token usable."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_real_token\n")
    assert resolved_github_token() == "ghp_real_token"
    env = git_auth_env(_GITHUB)
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_VALUE_0"].startswith("AUTHORIZATION: basic ")


def test_non_github_remote_does_not_require_a_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    env = git_auth_env("https://gitlab.com/some/repo")
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert "GIT_CONFIG_VALUE_0" not in env


def test_helper_never_logs_the_token(monkeypatch, caplog):
    secret = "ghp_must_not_appear_in_logs"
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    with caplog.at_level(logging.DEBUG):
        git_auth_env(_GITHUB)
        resolved_github_token()
    assert secret not in caplog.text


def test_named_call_sites_use_the_shared_helper():
    """D3/D4/D5 plus the original clone path must all go through git_auth_env."""
    sources = {
        "clone": inspect.getsource(session_phases._phase_clone),
        "sandbox": inspect.getsource(session_phases._reclone_sandbox),
        "push": inspect.getsource(session_phases._phase_push),
        "orchestrator": inspect.getsource(orchestrator.fan_out),
        "autopr_git": inspect.getsource(autopr._git),
        "autopr_run": inspect.getsource(autopr.run_autopr),
    }
    assert "git_auth_env" in sources["clone"] or "_git_clone_env" in sources["clone"]
    assert "git_auth_env" in sources["sandbox"]
    assert "git_auth_env" in sources["push"]
    assert "resolved_github_token" in sources["push"]
    assert "x-access-token" not in sources["push"]
    assert "_embed_push_token" not in sources["push"]
    assert "set-url" not in sources["push"]
    assert "git_auth_env" in sources["orchestrator"]
    assert "git_auth_env" in sources["autopr_git"]
    assert "resolved_github_token" in sources["autopr_run"]
    assert "_GITHUB_TOKEN" not in sources["autopr_run"]
    assert "x-access-token:{_GITHUB_TOKEN}" not in sources["autopr_run"]
    phases_src = inspect.getsource(session_phases)
    git_auth_src = inspect.getsource(__import__("app.server.git_auth", fromlist=["git_auth"]))
    autopr_src = inspect.getsource(autopr)
    assert "_embed_push_token" not in phases_src
    assert "empty_github_token" not in phases_src
    assert "empty_github_token" not in git_auth_src
    assert "empty_github_token" not in autopr_src
    assert "empty_github_token" not in inspect.getsource(orchestrator)


@pytest.mark.asyncio
async def test_sandbox_reclone_does_not_spawn_git_on_empty_token(monkeypatch, tmp_path):
    spawned: list[tuple] = []

    async def fake_exec(*args, **kwargs):
        spawned.append(args)
        raise AssertionError("git must not spawn when the token is empty")

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(session_phases.config, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(session_phases.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(session_phases.persistence, "save_session", lambda _s: None)
    monkeypatch.setattr(session_phases, "em", lambda *_a, **_k: None)

    session = BuildSession(repo_url=_GITHUB)
    assert await session_phases._reclone_sandbox(session) is False
    assert spawned == []
    assert MISSING_CREDENTIAL in session.error


@pytest.mark.asyncio
async def test_orchestrator_clone_does_not_spawn_git_on_whitespace_token(
    monkeypatch, tmp_path,
):
    calls: list[object] = []

    async def fake_run_cmd(*_a, **_k):
        calls.append(1)
        return 0, "", ""

    monkeypatch.setenv("GITHUB_TOKEN", "   ")
    monkeypatch.setattr(orchestrator, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(orchestrator.config, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(orchestrator, "em", lambda *_a, **_k: None)

    result = await orchestrator.fan_out(_GITHUB, "do a thing", n_workers=1)
    assert result["status"] == "failed"
    assert result["reason"] == MISSING_CREDENTIAL
    assert calls == []


@pytest.mark.asyncio
async def test_autopr_whitespace_token_fails_closed_before_git(monkeypatch):
    spawned: list[tuple] = []

    async def fake_exec(*args, **kwargs):
        spawned.append(args)
        raise AssertionError("autopr must not interpolate an empty token into git")

    monkeypatch.setenv("GITHUB_TOKEN", "\n")
    monkeypatch.setattr(autopr, "_load_fixable_findings", lambda _pid: {
        "dependencies": [{"auto_fixable": True, "file_path": "package.json"}],
    })
    monkeypatch.setattr(autopr.asyncio, "create_subprocess_exec", fake_exec)

    result = await autopr.run_autopr({"id": "pi-dev-ops", "repo": "CleanExpo/Pi-Dev-Ops"})
    assert result["skipped"] is True
    assert result["reason"] == MISSING_CREDENTIAL
    assert spawned == []
