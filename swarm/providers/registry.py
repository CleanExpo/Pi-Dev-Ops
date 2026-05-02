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


# ── CMO marketing provider (RA-1860, Wave 4 A2) ─────────────────────────────


def select_marketing_provider():
    """Pick a CMO marketing provider by ``TAO_CMO_PROVIDER`` env.

    Values:
    * ``synthetic`` (default) — deterministic fixtures, no external calls
    * ``ad_platforms`` — real Google Ads / LinkedIn / Meta + per-business
      synthetic fallback (follow-up ticket; not implemented yet → falls back
      to synthetic with a warning)
    """
    name = (os.environ.get("TAO_CMO_PROVIDER") or "synthetic").strip().lower()
    if name == "ad_platforms":
        log.warning(
            "provider: ad_platforms selected but not yet implemented — "
            "using synthetic_marketing"
        )
    if name not in ("synthetic", "ad_platforms", ""):
        log.warning(
            "provider: unknown TAO_CMO_PROVIDER=%r — using synthetic_marketing",
            name,
        )
    from .synthetic_marketing import synthetic_marketing_provider
    log.debug("provider: synthetic_marketing selected")
    return synthetic_marketing_provider


__all__ = ["select_provider", "select_marketing_provider", "ProviderFn"]
