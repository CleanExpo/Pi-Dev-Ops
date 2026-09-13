"""GET /api/health/ready — real clone-credential probe (UNI-2646).

``/health`` is Railway's healthcheckPath and must stay liveness-only. A 503
there restarts the deploy. This route runs a bounded ``git ls-remote`` with
the same token the clone path uses, and returns 503 when that probe fails.

Never logs the token. Never puts the token on argv or in the JSON body.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse


log = logging.getLogger("pi-ceo.health_ready")

router = APIRouter()

LS_REMOTE_TIMEOUT_S = 8.0
_DEFAULT_SLUG = "CleanExpo/Pi-Dev-Ops"


def configured_repo_url() -> str:
    """Repo the clone path would actually hit. Prefer explicit URL, then slug."""
    explicit = (os.environ.get("GITHUB_REPO_URL") or "").strip()
    if explicit:
        return explicit
    slug = (os.environ.get("GITHUB_REPO") or _DEFAULT_SLUG).strip()
    if slug.startswith(("https://", "http://", "git@")):
        return slug
    slug = slug.removeprefix("github.com/").removesuffix(".git")
    return f"https://github.com/{slug}.git"


def redact_secrets(text: str) -> str:
    """Strip token values and embedded basic-auth from any operator-facing string."""
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        text = text.replace(token, "[redacted]")
    text = re.sub(r"https://[^/\s]+@", "https://[redacted]@", text)
    return text[:240]


def _probe_env(repo_url: str) -> dict[str, str] | None:
    """Same extraheader auth as clone, plus no TTY prompt so a dead token cannot hang."""
    from ..session_phases import _git_clone_env

    env = _git_clone_env(repo_url)
    if env is None:
        return None
    return {**env, "GIT_TERMINAL_PROMPT": "0"}


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


async def _wait_ls_remote(
    proc: asyncio.subprocess.Process,
    timeout_s: float,
) -> tuple[int | None, bytes, str]:
    """Wait for ls-remote. Returns (returncode, stderr, reason). reason is set on timeout."""
    try:
        _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return None, b"", "timeout"
    return proc.returncode, stderr or b"", ""


def _fail(reason: str, started: float, detail: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "reason": reason, "elapsed_ms": _elapsed_ms(started)}
    if detail:
        payload["detail"] = redact_secrets(detail)
    return payload


async def run_ls_remote(
    repo_url: str,
    timeout_s: float = LS_REMOTE_TIMEOUT_S,
) -> dict[str, Any]:
    """Bounded ``git ls-remote`` using the configured GitHub token. Never logs secrets."""
    started = time.monotonic()
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return _fail("github_token_missing", started)
    env = _probe_env(repo_url)
    if env is None:
        return _fail("clone_auth_unavailable", started)

    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-remote",
            "--exit-code",
            repo_url,
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError:
        return _fail("git_missing", started)
    except Exception as exc:
        return _fail("probe_error", started, str(exc))

    returncode, stderr, timeout_reason = await _wait_ls_remote(proc, timeout_s)
    if timeout_reason:
        return _fail(timeout_reason, started)
    if returncode == 0:
        return {"ok": True, "reason": "ok", "elapsed_ms": _elapsed_ms(started)}
    detail = redact_secrets(stderr.decode("utf-8", errors="replace").strip())
    log.warning("clone readiness probe failed: %s", detail or f"exit {returncode}")
    return _fail("ls_remote_failed", started, detail or f"exit {returncode}")


def public_ready_payload(repo_url: str, result: dict[str, Any]) -> dict[str, Any]:
    """Operator-facing body. Every string is redacted so a leaky probe cannot echo the token."""
    payload: dict[str, Any] = {
        "ok": bool(result.get("ok")),
        "ready": bool(result.get("ok")),
        "probe": "git_ls_remote",
        "repo": redact_secrets(repo_url),
        "timeout_s": LS_REMOTE_TIMEOUT_S,
    }
    for key in ("reason", "detail", "elapsed_ms"):
        if key not in result:
            continue
        value = result[key]
        payload[key] = redact_secrets(value) if isinstance(value, str) else value
    return payload


@router.get("/api/health/ready")
async def health_ready() -> JSONResponse:
    repo_url = configured_repo_url()
    payload = public_ready_payload(repo_url, await run_ls_remote(repo_url))
    return JSONResponse(payload, status_code=200 if payload["ok"] else 503)
