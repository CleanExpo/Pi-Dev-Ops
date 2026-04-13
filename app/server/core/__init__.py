"""
app/server/core — Pi-CEO Ship Chain, minimal layer.

RA-682 (Karpathy-9): this package exposes the five pure functions that make
up the Ship Chain. No external services, no Supabase, no Telegram, no budget.

    classify(brief) → intent
    build_spec(brief, intent, repo_url) → spec_str
    generate(spec, workspace, model) → bool
    evaluate(workspace, brief, threshold) → (score, text)
    decide(score, threshold, attempt, max_retries) → 'pass'|'retry'|'warn'

These are re-exports from the production modules so both callers can import
from the same well-known path:

    from app.server.core import classify, build_spec, generate, evaluate, decide

The `advanced` package wraps this layer with budget tuning, scope enforcement,
confidence routing, plan discovery, and brief complexity tiers.
"""
from app.server.brief import build_structured_brief as build_spec  # noqa: F401
from app.server.brief import classify_intent as classify

# generate / evaluate / decide live in sessions.py because they depend on
# the async SDK infrastructure.  They are re-exported here as thin wrappers
# so callers can import from `core` without taking on all of sessions.py.
from app.server.core._chain import decide, evaluate, generate  # noqa: F401

__all__ = ["classify", "build_spec", "generate", "evaluate", "decide"]
