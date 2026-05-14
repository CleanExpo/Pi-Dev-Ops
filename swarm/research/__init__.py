"""swarm.research — citation-grounded research backends for Margot + PM bots.

The E.E.A.T moat for ATIA starts here: every PM bot, board deliberation,
and on-demand research call now ships with verifiable citations sourced
from Google Search grounding via Gemini.

Backends:
  * gemini_research.grounded_research — Gemini + google_search tool
"""
from __future__ import annotations

from swarm.research.gemini_research import (
    AuthError,
    Citation,
    EmptyResponseError,
    GroundedResearchResult,
    GroundingFailedError,
    RateLimitError,
    TimeoutError as GeminiTimeoutError,
    UpstreamError,
    grounded_research,
)

__all__ = [
    "AuthError",
    "Citation",
    "EmptyResponseError",
    "GeminiTimeoutError",
    "GroundedResearchResult",
    "GroundingFailedError",
    "RateLimitError",
    "UpstreamError",
    "grounded_research",
]
