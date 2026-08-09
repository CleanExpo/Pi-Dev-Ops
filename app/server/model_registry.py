"""Canonical LLM model IDs for Pi-Dev-Ops (SSOT).

Official reference:
  https://platform.claude.com/docs/en/about-claude/models/overview

As of Aug 09 2026 (Anthropic "Latest models comparison"):
  Opus   → claude-opus-5
  Sonnet → claude-sonnet-5
  Haiku  → claude-haiku-4-5-20251001  (alias: claude-haiku-4-5)

Mythos-class:
  claude-fable-5 — GATED CANARY tier (RA-1099 Wave 3). NOT a default for any
    role. Reachable only when a role is allow-listed via TAO_FABLE_ALLOWED_ROLES
    (default empty = OFF); today that is the `adversary` pre-push review role
    only. Adaptive-thinking-only (no temperature/top_p/top_k/budget_tokens) and
    may return stop_reason="refusal" — the session_sdk fable path strips sampling
    params and falls back to claude-opus-5 on a refusal/error.
  claude-mythos-5 (Glasswing only) — still not wired.

OpenRouter boardroom panellist:
  deepseek/deepseek-v4-flash
"""
from __future__ import annotations

MODEL_REGISTRY_AS_OF = "July 01 2026"
DOCS_MODELS_OVERVIEW = "https://platform.claude.com/docs/en/about-claude/models/overview"

# ── Anthropic Messages API (direct / Agent SDK) ─────────────────────────────

ANTHROPIC_OPUS = "claude-opus-5"
ANTHROPIC_SONNET = "claude-sonnet-5"
ANTHROPIC_HAIKU = "claude-haiku-4-5-20251001"
# RA-1099 Wave 3 — gated canary tier (adversary role only; env-flag off by default).
ANTHROPIC_FABLE = "claude-fable-5"

# Convenience aliases from Anthropic docs (pinned snapshots, not evergreen pointers)
ANTHROPIC_ALIASES: dict[str, str] = {
    ANTHROPIC_OPUS: ANTHROPIC_OPUS,
    ANTHROPIC_SONNET: ANTHROPIC_SONNET,
    ANTHROPIC_HAIKU: "claude-haiku-4-5",
    ANTHROPIC_FABLE: ANTHROPIC_FABLE,
}

SHORT_TO_ANTHROPIC: dict[str, str] = {
    "opus": ANTHROPIC_OPUS,
    "sonnet": ANTHROPIC_SONNET,
    "haiku": ANTHROPIC_HAIKU,
    "fable": ANTHROPIC_FABLE,
}

# ── OpenRouter slugs (provider/model) ───────────────────────────────────────

OPENROUTER_SONNET = "anthropic/claude-sonnet-5"
OPENROUTER_OPUS = "anthropic/claude-opus-5"
OPENROUTER_DEEPSEEK_FLASH = "deepseek/deepseek-v4-flash"

# Tier-0 paid spill default (cheap JSON + tools)
OPENROUTER_DEEPSEEK_PAID = OPENROUTER_DEEPSEEK_FLASH
