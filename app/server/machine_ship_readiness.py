"""Machine-ship readiness probe — RA-6885.

Surfaces whether Railway/local env can run spec_pipeline build+ship without
printing secret values.
"""
from __future__ import annotations

import os

from .provider_router import select_provider_model

_SPEC_ROLES = (
    "spec_pipeline", "storm_evidence", "prebuild_judge", "spm_runner",
    "spm_gap_resolution", "ceo_board_liaison", "boardroom_panellist_primary",
    "boardroom_panellist_secondary", "boardroom_synthesis", "boardroom_escalation",
)

def _truthy_env(name: str) -> bool:
    return bool((os.environ.get(name) or "").strip())


def machine_ship_readiness() -> dict:
    """Return readiness flags for TAO_MACHINE_SHIP_MODE autonomous ship."""
    mode_enabled = os.environ.get("TAO_MACHINE_SHIP_MODE", "0").strip() == "1"
    checks = {
        "mode_enabled": mode_enabled,
        "github_token": _truthy_env("GITHUB_TOKEN"),
        "github_repo": _truthy_env("GITHUB_REPO"),
        "linear_api_key": _truthy_env("LINEAR_API_KEY"),
    }
    # These roles resolve explicit overrides or subscription/local defaults;
    # selection does not perform a live login check or model request.
    routes = {role: select_provider_model(role, record_observation=False) for role in _SPEC_ROLES}
    supported = all(route.provider in {"claude_print", "codex", "ollama"} for route in routes.values())
    checks.update(llm_route_supported=supported, llm_execution_verified=False)
    configured = (
        mode_enabled
        and checks["github_token"]
        and checks["github_repo"]
        and supported
    )
    blockers: list[str] = []
    if not mode_enabled:
        blockers.append("TAO_MACHINE_SHIP_MODE not 1")
    if not checks["github_token"]:
        blockers.append("GITHUB_TOKEN unset")
    if not checks["github_repo"]:
        blockers.append("GITHUB_REPO unset")
    if not supported:
        blockers.append("Spec pipeline has a paid or unsupported model transport configured")
    blockers.append("Subscription authorization and independent served model identities not verified")
    return {
        "ready": False,
        "configured": configured,
        "status": "runtime_unverified" if configured else "blocked",
        "model_routes": {role: {"provider": route.provider, "requested_model": route.model_id}
                         for role, route in routes.items()},
        "checks": checks,
        "blockers": blockers,
    }
