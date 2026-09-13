"""UNI-2646 — /api/health/ready is a real clone probe; /health stays liveness.

Done means:
  * GET /api/health/ready runs bounded ``git ls-remote`` with the configured token
  * 200 on success, 503 on failure (missing token, auth reject, timeout)
  * /health never 503s for disk — it is Railway's healthcheckPath
  * railway.toml / railway.json healthcheckPath stays ``/health``
  * the token never appears in the response or in git argv
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from app.server.routes import health_ready


REPO = Path(__file__).resolve().parents[1]


class _FakeProc:
    def __init__(self, rc: int = 0, stderr: bytes = b"", hang: bool = False) -> None:
        self.returncode = rc
        self._stderr = stderr
        self._hang = hang
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._hang:
            await asyncio.sleep(60)
        return b"abc123\tHEAD\n", self._stderr

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> None:
        self.returncode = -9


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(health_ready.router)
    return TestClient(app)


def _patch_ls_remote(monkeypatch, result: dict) -> None:
    async def fake(_repo_url: str, timeout_s: float = health_ready.LS_REMOTE_TIMEOUT_S):
        return result

    monkeypatch.setattr(health_ready, "run_ls_remote", fake)


def test_ready_returns_200_when_ls_remote_succeeds(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_ok")
    _patch_ls_remote(monkeypatch, {"ok": True, "reason": "ok", "elapsed_ms": 12})
    resp = _client().get("/api/health/ready")
    body = resp.json()
    assert resp.status_code == 200
    assert body["ok"] is True
    assert body["ready"] is True
    assert body["probe"] == "git_ls_remote"


def test_ready_returns_503_when_ls_remote_fails(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_dead")
    _patch_ls_remote(
        monkeypatch,
        {"ok": False, "reason": "ls_remote_failed", "detail": "Authentication failed", "elapsed_ms": 40},
    )
    resp = _client().get("/api/health/ready")
    body = resp.json()
    assert resp.status_code == 503
    assert body["ok"] is False
    assert body["ready"] is False
    assert body["reason"] == "ls_remote_failed"


def test_ready_503_when_token_missing_does_not_spawn_git(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    spawned: list[tuple] = []

    async def boom(*args, **kwargs):
        spawned.append((args, kwargs))
        raise AssertionError("git must not run when the token is missing")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", boom)
    result = asyncio.run(health_ready.run_ls_remote("https://github.com/CleanExpo/Pi-Dev-Ops.git"))
    assert result["ok"] is False
    assert result["reason"] == "github_token_missing"
    assert spawned == []
    resp = _client().get("/api/health/ready")
    assert resp.status_code == 503
    assert resp.json()["reason"] == "github_token_missing"


@pytest.mark.asyncio
async def test_ready_503_on_timeout_kills_the_process(monkeypatch):
    secret = "ghp_timeout_must_not_leak"
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    hung = _FakeProc(hang=True)

    async def fake_exec(*_args, **_kwargs):
        return hung

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = await health_ready.run_ls_remote(
        "https://github.com/CleanExpo/Pi-Dev-Ops.git",
        timeout_s=0.05,
    )
    assert result["ok"] is False
    assert result["reason"] == "timeout"
    assert hung.killed is True
    assert secret not in json.dumps(result)


@pytest.mark.asyncio
async def test_ls_remote_uses_configured_token_and_never_puts_it_on_argv(monkeypatch):
    secret = "ghp_argv_must_stay_clean"
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    captured: dict[str, object] = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env")
        return _FakeProc(rc=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = await health_ready.run_ls_remote("https://github.com/CleanExpo/Pi-Dev-Ops.git")
    assert result["ok"] is True
    assert captured["args"][:3] == ("git", "ls-remote", "--exit-code")
    assert secret not in " ".join(str(a) for a in captured["args"])
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert secret not in env["GIT_CONFIG_VALUE_0"]


@pytest.mark.asyncio
async def test_ready_redacts_token_from_git_stderr(monkeypatch):
    secret = "ghp_stderr_secret_value"
    monkeypatch.setenv("GITHUB_TOKEN", secret)

    async def fake_exec(*_args, **_kwargs):
        return _FakeProc(rc=128, stderr=f"fatal: {secret} rejected\n".encode())

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = await health_ready.run_ls_remote("https://github.com/CleanExpo/Pi-Dev-Ops.git")
    assert result["ok"] is False
    dumped = json.dumps(result)
    assert secret not in dumped
    assert "[redacted]" in result["detail"]


def test_ready_never_leaks_token_in_http_body(monkeypatch):
    secret = "ghp_http_body_must_not_contain_this"
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    monkeypatch.setenv("GITHUB_REPO_URL", f"https://{secret}@github.com/CleanExpo/Pi-Dev-Ops.git")
    _patch_ls_remote(monkeypatch, {"ok": False, "reason": "ls_remote_failed", "detail": secret, "elapsed_ms": 1})
    resp = _client().get("/api/health/ready")
    raw = resp.content.decode()
    assert secret not in raw
    assert resp.status_code == 503


def test_health_stays_liveness_200_when_disk_check_fails(monkeypatch):
    """The pre-UNI-2646 bug: disk_free_gb is None flipped /health to 503."""
    import shutil

    from app.server.routes.health import health as health_fn

    monkeypatch.delenv("TAO_PASSWORD", raising=False)

    def boom(*_a, **_k):
        raise OSError("no disk")

    monkeypatch.setattr(shutil, "disk_usage", boom)
    req = MagicMock()
    req.headers = Headers({})
    req.cookies = {}
    response = asyncio.run(health_fn(req))
    body = json.loads(response.body)
    assert response.status_code == 200
    assert body["disk_free_gb"] is None


def test_railway_healthcheck_path_stays_liveness():
    """A 503 on Railway's healthcheckPath deploy-loops. That path stays /health."""
    toml = (REPO / "railway.toml").read_text(encoding="utf-8")
    assert 'healthcheckPath = "/health"' in toml
    assert "/api/health/ready" not in toml
    manifest = json.loads((REPO / "railway.json").read_text(encoding="utf-8"))
    assert manifest["deploy"]["healthcheckPath"] == "/health"
    audit = (REPO / "scripts" / "railway_manifest_audit.py").read_text(encoding="utf-8")
    assert '"deploy.healthcheckPath": "/health"' in audit
