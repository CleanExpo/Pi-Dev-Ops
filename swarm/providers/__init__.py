"""swarm.providers — pluggable metrics providers for senior-agent bots.

Closes Wave 4.1b on RA-1850 / RA-1859. The CFO bot's
``_default_metrics_provider`` previously returned ``[]``; now it routes
through ``registry.select_provider`` which picks synthetic, stripe_xero, or
a custom test provider based on ``TAO_CFO_PROVIDER``.
"""
from __future__ import annotations

from .registry import (
    select_marketing_provider,
    select_platform_provider,
    select_provider,
)

__all__ = [
    "select_provider",
    "select_marketing_provider",
    "select_platform_provider",
]
