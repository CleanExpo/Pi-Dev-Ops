"""
app/server/core — Pi-CEO Ship Chain, minimal layer.

RA-682 (Karpathy-9): this package exposes the pure brief primitives.
RA-1094B: generate/evaluate/decide removed — those paths now live in
`sessions.py` / `pipeline.py` on the Agent SDK (SDK-only mandate, RA-576).

    classify(brief) → intent
    build_spec(brief, intent, repo_url) → spec_str

These are re-exports from the production modules so callers can import
from the same well-known path:

    from app.server.core import classify, build_spec

The `advanced` package wraps this layer with budget tuning, scope enforcement,
confidence routing, plan discovery, and brief complexity tiers.
"""
from app.server.brief import build_structured_brief as build_spec  # noqa: F401
from app.server.brief import classify_intent as classify  # noqa: F401

__all__ = ["classify", "build_spec"]
