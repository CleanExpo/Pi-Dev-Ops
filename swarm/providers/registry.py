"""swarm/providers/registry.py — env-based provider selection.

``select_provider()`` reads ``TAO_CFO_PROVIDER`` and returns the matching
callable. Default ``synthetic`` keeps tests stable and the orchestrator's
first cycle non-empty even without real credentials.
"""
from __future__ import annotations

import logging
import os
from typing import Callable

from ..cfo import RawMetrics

log = logging.getLogger("swarm.providers.registry")

ProviderFn = Callable[[], list[RawMetrics]]


def select_provider() -> ProviderFn:
    """Pick a CFO metrics provider by ``TAO_CFO_PROVIDER`` env.

    Values:
    * ``synthetic`` (default) — deterministic fixtures, no external calls
    * ``stripe_xero`` — real Stripe MRR + per-business synthetic fallback
    """
    name = (os.environ.get("TAO_CFO_PROVIDER") or "synthetic").strip().lower()
    if name == "stripe_xero":
        from .stripe_xero import stripe_xero_provider
        log.debug("provider: stripe_xero selected")
        return stripe_xero_provider
    if name not in ("synthetic", ""):
        log.warning("provider: unknown TAO_CFO_PROVIDER=%r — using synthetic", name)
    from .synthetic import synthetic_provider
    log.debug("provider: synthetic selected")
    return synthetic_provider


# ── CS-tier1 provider (RA-1862, Wave 4 A4) ──────────────────────────────────


def select_cs_provider():
    """Pick a CS provider by ``TAO_CS_PROVIDER`` env.

    Values:
    * ``synthetic`` (default)
    * ``zendesk`` / ``intercom`` — real helpdesk pull (stub today; falls
      back to synthetic with a warning until connector wired)
    """
    name = (os.environ.get("TAO_CS_PROVIDER") or "synthetic").strip().lower()
    if name in ("zendesk", "intercom"):
        log.warning(
            "provider: %s selected but not yet implemented — using synthetic_cs",
            name,
        )
    if name not in ("synthetic", "zendesk", "intercom", ""):
        log.warning(
            "provider: unknown TAO_CS_PROVIDER=%r — using synthetic_cs", name,
        )
    from .synthetic_cs import synthetic_cs_provider
    return synthetic_cs_provider


# ── CTO platform provider (RA-1861, Wave 4 A3) ──────────────────────────────


def select_platform_provider():
    """Pick a CTO platform provider by ``TAO_CTO_PROVIDER`` env.

    Values:
    * ``synthetic`` (default) — deterministic fixtures
    * ``github_actions`` — real DORA quartet from GitHub Actions
      workflow_runs + per-business synthetic fallback for p99/uptime/cost
    """
    name = (os.environ.get("TAO_CTO_PROVIDER") or "synthetic").strip().lower()
    if name == "github_actions":
        from .github_actions import github_actions_provider
        log.debug("provider: github_actions selected")
        return github_actions_provider
    if name not in ("synthetic", ""):
        log.warning(
            "provider: unknown TAO_CTO_PROVIDER=%r — using synthetic_platform",
            name,
        )
    from .synthetic_platform import synthetic_platform_provider
    log.debug("provider: synthetic_platform selected")
    return synthetic_platform_provider


# ── CMO marketing provider (RA-1860, Wave 4 A2) ─────────────────────────────


def select_marketing_provider():
    """Pick a CMO marketing provider by ``TAO_CMO_PROVIDER`` env.

    Values:
    * ``synthetic`` (default) — deterministic fixtures, no external calls
    * ``google_ads`` — real Google Ads spend per business + synthetic
      fallback for non-Google channels and businesses without a customer ID
    * ``ad_platforms`` — alias kept for backwards-compat; today routes to
      ``google_ads`` (LinkedIn / Meta connectors land as follow-ups)
    """
    name = (os.environ.get("TAO_CMO_PROVIDER") or "synthetic").strip().lower()
    if name in ("google_ads", "ad_platforms"):
        from .google_ads import google_ads_provider
        log.debug("provider: google_ads selected")
        return google_ads_provider
    if name not in ("synthetic", ""):
        log.warning(
            "provider: unknown TAO_CMO_PROVIDER=%r — using synthetic_marketing",
            name,
        )
    from .synthetic_marketing import synthetic_marketing_provider
    log.debug("provider: synthetic_marketing selected")
    return synthetic_marketing_provider


__all__ = [
    "select_provider", "select_marketing_provider",
    "select_platform_provider", "select_cs_provider",
    "ProviderFn",
]
