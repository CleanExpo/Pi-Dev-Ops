"""Canonical LLM model IDs for Pi-Dev-Ops (SSOT).

Update this file when Anthropic or OpenRouter ship new pinned snapshots.

As of July 01 2026:
  Opus   → claude-opus-4-8        (Anthropic GA May 2026)
  Sonnet → claude-sonnet-5        (Anthropic GA June 30 2026)
  Haiku  → claude-haiku-4-5-20251001
  Panel  → deepseek/deepseek-v4-flash (OpenRouter)
"""
from __future__ import annotations

MODEL_REGISTRY_AS_OF = "July 01 2026"

# ── Anthropic Messages API (direct / Agent SDK) ─────────────────────────────

ANTHROPIC_OPUS = "claude-opus-4-8"
ANTHROPIC_SONNET = "claude-sonnet-5"
ANTHROPIC_HAIKU = "claude-haiku-4-5-20251001"

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
