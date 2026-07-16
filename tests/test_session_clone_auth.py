from __future__ import annotations

from pathlib import Path

import pytest

from app.server.session_model import BuildSession
from app.server import session_phases


@pytest.mark.asyncio
async def test_clone_uses_process_scoped_auth_for_private_github_repo(monkeypatch, tmp_path: Path):
    token = "test-token-value"
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def fake_run_cmd(cwd, *args, **kwargs):
        calls.append((args, kwargs))
        if args[1:3] == ("remote", "get-url"):
            return 0, "https://github.com/CleanExpo/Pi-Dev-Ops.git\n", ""
        return 0, "", ""

    monkeypatch.setenv("GITHUB_TOKEN", token)
    monkeypatch.setattr(session_phases.config, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(session_phases, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(session_phases.persistence, "save_session", lambda _session: None)
    monkeypatch.setattr(session_phases, "_emit_phase_metric", lambda *_args, **_kwargs: None)

    session = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
    assert await session_phases._phase_clone(session, "") is True

    clone_args, clone_kwargs = calls[0]
    assert clone_args[:4] == ("git", "clone", "--depth", "1")
    assert clone_args[4] == session.repo_url
    assert token not in " ".join(str(arg) for arg in clone_args)

    auth_env = clone_kwargs["env"]
    assert isinstance(auth_env, dict)
    assert auth_env["GIT_CONFIG_COUNT"] == "1"
    assert auth_env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert auth_env["GIT_CONFIG_VALUE_0"].startswith("AUTHORIZATION: basic ")
    assert token not in auth_env["GIT_CONFIG_VALUE_0"]


@pytest.mark.asyncio
async def test_clone_does_not_add_auth_env_without_token(monkeypatch, tmp_path: Path):
    calls: list[dict[str, object]] = []

    async def fake_run_cmd(cwd, *args, **kwargs):
        calls.append(kwargs)
        if args[1:3] == ("remote", "get-url"):
            return 0, "https://github.com/example/public.git\n", ""
        return 0, "", ""

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(session_phases.config, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(session_phases, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(session_phases.persistence, "save_session", lambda _session: None)
    monkeypatch.setattr(session_phases, "_emit_phase_metric", lambda *_args, **_kwargs: None)

    session = BuildSession(repo_url="https://github.com/example/public")
    assert await session_phases._phase_clone(session, "") is True
    assert calls[0].get("env") is None
