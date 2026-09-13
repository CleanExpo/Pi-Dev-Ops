"""Eligibility for the Nexus One synthetic worker path.

Reuses the existing Max / ``claude --print`` idea from
``app.server.provider_router._run_via_claude_print`` (cost_usd=0 under a
Claude Max session). This module only *names* that lane. It does not
invoke the CLI, Anthropic, or any paid fallback.

SYNTHETIC: no live worker is enrolled. Windows stays review-only.
"""
from __future__ import annotations

from .types import API_LANE, MAX_LANE, MAX_RUNTIME, WorkerDecision

WINDOWS = frozenset({"win32", "windows", "cygwin"})
PAID_LANES = frozenset({API_LANE, "openrouter", "paid_fallback"})
BUILDER_FAMILY = "claude-max-subscription"
REVIEW_FAMILY = "judge-deterministic"


def _platform_key(platform: str) -> str:
    return (platform or "").strip().lower()


def select_worker(
    *,
    platform: str,
    requested_lane: str | None = None,
    capacity_depleted: bool = False,
) -> WorkerDecision:
    """Name the eligible Max-subscription path or refuse with a reason."""
    key = _platform_key(platform)
    if key in WINDOWS:
        return _refuse(platform, "windows_review_only")
    if requested_lane and requested_lane.strip().lower() in PAID_LANES:
        return _refuse(platform, "api_billing_forbidden")
    if capacity_depleted:
        return _refuse(platform, "capacity_depleted_no_paid_fallback")
    if key in {"darwin", "linux", "linux2"}:
        return _admit(platform, key)
    return _refuse(platform, "unknown_platform")


def _admit(platform: str, key: str) -> WorkerDecision:
    role = "admitted_mac_shape" if key == "darwin" else "synthetic_ci_host"
    return WorkerDecision(
        eligible=True,
        lane=MAX_LANE,
        runtime=MAX_RUNTIME,
        platform=platform,
        cost_usd=0.0,
        billing="subscription",
        reason="claude_max_subscription_only",
        platform_role=role,
    )


def _refuse(platform: str, reason: str) -> WorkerDecision:
    return WorkerDecision(
        eligible=False,
        lane="",
        runtime="",
        platform=platform,
        cost_usd=0.0,
        billing="none",
        reason=reason,
        platform_role="refused",
    )
