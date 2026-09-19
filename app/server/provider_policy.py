"""Shared no-API-credit boundary. Configuration is never proof of execution.

Subscription CLI status is checked immediately before dispatch; it is not a
guarantee of unused quota or zero invoiced cost. SDK use binds the verified
subscription CLI to its execution environment; metered routes stay blocked.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlsplit


class ProviderPolicyError(RuntimeError):
    """The selected transport cannot prove compliance with subscription-only use."""


CLAUDE_ROUTING_ENV = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
    "CLAUDE_CODE_USE_ANTHROPIC_AWS",
)
CODEX_ROUTING_ENV = ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL")


def check_claude_configuration(env: dict[str, str] | None = None) -> None:
    """Reject explicit API routing even when a caller would scrub it for a child."""
    if any(os.environ.get(key, "").strip() for key in CLAUDE_ROUTING_ENV):
        raise ProviderPolicyError("subscription_only: ambient API credentials or provider override present")
    if env is not None and any(env.get(key, "").strip() for key in CLAUDE_ROUTING_ENV):
        raise ProviderPolicyError("subscription_only: child API credentials or provider override present")


def require_transport(provider: str, *, endpoint_url: str | None = None,
                      cli_path: str | None = None, env: dict[str, str] | None = None) -> dict:
    """Authorize the actual execution transport immediately before dispatch."""
    if provider == "ollama":
        return _require_local(endpoint_url)
    if provider == "codex":
        return _require_codex()
    return _require_claude(provider, cli_path, env)


def _require_local(endpoint_url):
    try:
        endpoint = urlsplit(endpoint_url if endpoint_url is not None else
                            (os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"))
    except ValueError:
        raise ProviderPolicyError("subscription_only: invalid Ollama endpoint") from None
    if endpoint.scheme not in {"http", "https"} or endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ProviderPolicyError("subscription_only: unverified remote Ollama transport")
    return {"billing_class": "local", "auth_verified": True, "source": "loopback_transport"}


def _require_codex():
    if any(os.environ.get(key, "").strip() for key in CODEX_ROUTING_ENV):
        raise ProviderPolicyError("subscription_only: ambient Codex API credentials or endpoint override present")
    try:
        status = subprocess.run(
            [os.environ.get("CODEX_CLI", "codex"), "login", "status"],
            capture_output=True, text=True, timeout=10, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        raise ProviderPolicyError("subscription_only: Codex subscription login could not be verified") from None
    # Do not log the output: API-key login status may include key fragments.
    if status.returncode != 0 or (status.stdout + status.stderr).strip() != "Logged in using ChatGPT":
        raise ProviderPolicyError("subscription_only: ChatGPT subscription login not verified")
    return {"billing_class": "subscription", "auth_verified": True,
            "source": "codex_login_status", "cost_verified": False,
            "checked_at": datetime.now(timezone.utc).isoformat()}


def _require_claude(provider, cli_path, env):
    if provider not in {"claude_print", "anthropic_agent_sdk"}:
        raise ProviderPolicyError(f"subscription_only: paid or unverified transport blocked ({provider})")
    if provider == "anthropic_agent_sdk" and (
        not cli_path or not os.path.isabs(cli_path) or env is None
    ):
        raise ProviderPolicyError("subscription_only: SDK requires a bound CLI and execution environment")
    check_claude_configuration(env)
    try:
        status = subprocess.run(
            [cli_path or os.environ.get("CLAUDE_CLI", "claude"), "auth", "status"],
            capture_output=True, text=True, timeout=10, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            **({"env": env} if env is not None else {}),
        )
        payload = json.loads(status.stdout) if status.returncode == 0 else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        raise ProviderPolicyError("subscription_only: subscription login could not be verified") from None
    if not isinstance(payload, dict) or payload.get("loggedIn") is not True or payload.get("authMethod") != "claude.ai" or payload.get("subscriptionType") not in {"max", "pro", "team", "enterprise"}:
        raise ProviderPolicyError("subscription_only: active supported subscription login not verified")
    if provider == "anthropic_agent_sdk" and payload.get("apiProvider") != "firstParty":
        raise ProviderPolicyError("subscription_only: first-party subscription provider not verified")
    return {
        "billing_class": "subscription", "auth_verified": True,
        "source": "claude_auth_status", "checked_at": datetime.now(timezone.utc).isoformat(),
        "cost_verified": False,
    }


def independent_identity(primary: dict, secondary: dict) -> bool:
    """Two role labels or routes to the same model are not independent models."""
    for item in (primary, secondary):
        if not (item.get("auth_verified") is True and item.get("model_verified") is True
                and item.get("actual_model") and item.get("provider") and item.get("source")):
            return False
    def model(item: dict) -> str:
        return str(item["actual_model"]).strip().lower().rsplit("/", 1)[-1]
    def vendor(item: dict) -> str:
        provider = str(item["provider"]).lower()
        return {"claude_print": "anthropic", "anthropic_agent_sdk": "anthropic",
                "codex": "openai"}.get(provider, provider)
    return vendor(primary) != vendor(secondary) and model(primary) != model(secondary)
