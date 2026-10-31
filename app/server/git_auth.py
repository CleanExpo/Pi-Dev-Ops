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

# RA-8133: the only parent variables a git child may inherit. Everything else,
# including every service secret the server holds, is dropped. Add a name here
# when git genuinely needs it; never fall back to copying the whole environment.
GIT_CHILD_ENV_NAMES = frozenset({
    # process basics
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "TMP", "TEMP", "TZ",
    # Windows process basics (networking needs SYSTEMROOT; git finds HOME via
    # HOMEDRIVE+HOMEPATH, then USERPROFILE)
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "HOMEDRIVE", "HOMEPATH",
    "USERPROFILE", "APPDATA",
    "LOCALAPPDATA", "PROGRAMDATA",
    # locale: git messages and path encoding
    "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES",
    # git config location and commit identity
    "XDG_CONFIG_HOME", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
    "GIT_EXEC_PATH", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
    "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL",
    # askpass and ssh, for non-github remotes
    "GIT_ASKPASS", "SSH_ASKPASS", "GIT_SSH", "GIT_SSH_COMMAND", "SSH_AUTH_SOCK",
    # proxies
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    # TLS trust
    "SSL_CERT_FILE", "SSL_CERT_DIR", "CURL_CA_BUNDLE", "GIT_SSL_CAINFO", "GIT_SSL_CAPATH",
})


def git_child_base_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The allowlisted subset of `environ` (default: the process env)."""
    src = os.environ if environ is None else environ
    return {k: v for k, v in src.items() if k in GIT_CHILD_ENV_NAMES}


class GitAuthError(RuntimeError):
    """Named fail-closed error. `.reason` is the stable machine id."""

    def __init__(self, reason: str | GitAuthReason, message: str) -> None:
        code = reason.value if isinstance(reason, GitAuthReason) else reason
        super().__init__(message)
        self.reason = code


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
    env = {**git_child_base_env(src), "GIT_TERMINAL_PROMPT": "0"}
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
