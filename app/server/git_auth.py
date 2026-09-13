"""Shared GitHub auth env for every Pi-CEO git invocation (UNI-2645).

One helper. The credential is stripped (Railway/Vercel append a trailing newline).
Empty or whitespace-only values fail closed with reason `missing_credential`
instead of letting git prompt for a username on a headless host.
The credential never enters argv or the remote URL.
"""
from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from enum import Enum


class GitAuthReason(str, Enum):
    """Stable machine ids. Values must not look like credential assignments."""

    MISSING = "missing_credential"


MISSING_CREDENTIAL = GitAuthReason.MISSING


class GitAuthError(RuntimeError):
    """Named fail-closed error. `.reason` is the stable machine id."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def resolved_github_token(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    token = (env.get("GITHUB_TOKEN") or "").strip()
    if not token:
        raise GitAuthError(
            MISSING_CREDENTIAL,
            "GITHUB_TOKEN is empty or whitespace-only",
        )
    return token


def git_auth_env(
    repo_url: str = "",
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Process-scoped GitHub auth. Raises GitAuthError on an empty token.

    Non-github remotes get a prompt-disabled env and do not require a token.
    """
    src = os.environ if environ is None else environ
    env = {**src, "GIT_TERMINAL_PROMPT": "0"}
    if repo_url and not repo_url.startswith("https://github.com/"):
        return env
    token = resolved_github_token(src)
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
    env["GIT_CONFIG_VALUE_0"] = f"AUTHORIZATION: basic {basic}"
    return env


def github_clone_env(repo_url: str) -> dict[str, str] | None:
    """Auth env for github remotes. None for others. Raises on an empty token."""
    if not repo_url.startswith("https://github.com/"):
        return None
    return git_auth_env(repo_url)
