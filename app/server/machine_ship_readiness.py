"""Machine-ship readiness probe — RA-6885.

Surfaces whether Railway/local env can run spec_pipeline build+ship without
printing secret values.
"""
from __future__ import annotations

import os


def _truthy_env(name: str) -> bool:
    return bool((os.environ.get(name) or "").strip())


def machine_ship_readiness() -> dict:
    """Return readiness flags for TAO_MACHINE_SHIP_MODE autonomous ship."""
    mode_enabled = os.environ.get("TAO_MACHINE_SHIP_MODE", "0").strip() == "1"
    checks = {
        "mode_enabled": mode_enabled,
        "github_token": _truthy_env("GITHUB_TOKEN"),
        "github_repo": _truthy_env("GITHUB_REPO"),
        "openrouter_api_key": _truthy_env("OPENROUTER_API_KEY"),
        "linear_api_key": _truthy_env("LINEAR_API_KEY"),
    }
    llm_ready = checks["openrouter_api_key"]
    ship_ready = (
        mode_enabled
        and checks["github_token"]
        and checks["github_repo"]
        and llm_ready
    )
    blockers: list[str] = []
    if not mode_enabled:
        blockers.append("TAO_MACHINE_SHIP_MODE not 1")
    if not checks["github_token"]:
        blockers.append("GITHUB_TOKEN unset")
    if not checks["github_repo"]:
        blockers.append("GITHUB_REPO unset")
    if not llm_ready:
        blockers.append("OPENROUTER_API_KEY unset")
    return {
        "ready": ship_ready,
        "checks": checks,
        "blockers": blockers,
    }
