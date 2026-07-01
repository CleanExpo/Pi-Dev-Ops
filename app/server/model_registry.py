"""Canonical LLM model IDs for Pi-Dev-Ops (SSOT).

Official reference:
  https://platform.claude.com/docs/en/about-claude/models/overview

As of July 01 2026 (Anthropic "Latest models comparison"):
  Opus   → claude-opus-4-8
  Sonnet → claude-sonnet-5
  Haiku  → claude-haiku-4-5-20251001  (alias: claude-haiku-4-5)

Mythos-class (not wired by default — safety-classifier refusal risk):
  claude-fable-5, claude-mythos-5 (Glasswing only)

OpenRouter boardroom panellist:
  deepseek/deepseek-v4-flash
"""
from __future__ import annotations

MODEL_REGISTRY_AS_OF = "July 01 2026"
DOCS_MODELS_OVERVIEW = "https://platform.claude.com/docs/en/about-claude/models/overview"

# ── Anthropic Messages API (direct / Agent SDK) ─────────────────────────────

ANTHROPIC_OPUS = "claude-opus-4-8"
ANTHROPIC_SONNET = "claude-sonnet-5"
ANTHROPIC_HAIKU = "claude-haiku-4-5-20251001"

# Convenience aliases from Anthropic docs (pinned snapshots, not evergreen pointers)
ANTHROPIC_ALIASES: dict[str, str] = {
    ANTHROPIC_OPUS: ANTHROPIC_OPUS,
    ANTHROPIC_SONNET: ANTHROPIC_SONNET,
    ANTHROPIC_HAIKU: "claude-haiku-4-5",
}

SHORT_TO_ANTHROPIC: dict[str, str] = {
    "opus": ANTHROPIC_OPUS,
    "sonnet": ANTHROPIC_SONNET,
    "haiku": ANTHROPIC_HAIKU,
}

# ── OpenRouter slugs (provider/model) ───────────────────────────────────────

OPENROUTER_SONNET = "anthropic/claude-sonnet-5"
OPENROUTER_OPUS = "anthropic/claude-opus-4-8"
OPENROUTER_DEEPSEEK_FLASH = "deepseek/deepseek-v4-flash"

# Tier-0 paid spill default (cheap JSON + tools)
OPENROUTER_DEEPSEEK_PAID = OPENROUTER_DEEPSEEK_FLASH
