"""Canonical LLM model IDs for Pi-Dev-Ops (SSOT).

Official reference:
  https://platform.claude.com/docs/en/about-claude/models/overview

Configured model pins (availability must be verified separately):
  Opus   → claude-opus-5-5
  Sonnet → claude-sonnet-5
  Haiku  → claude-haiku-4-5-20251001  (alias: claude-haiku-4-5)

Opus 5.5 replaced Opus 5 as the top tier on 2026-09-23. Same class of model,
strictly cheaper on every axis this harness spends on — cache reads $0.20/MTok
against $0.50, input $4 against $5, output $20 against $25 — and it uses fewer
tokens per task, which Anthropic measures as ~40% lower cost on typical
workloads. Two behaviour changes that are NOT price:
  - thinking cannot be disabled on Opus 5.5 (no "thinking off" mode exists);
  - cybersecurity work is transparently re-routed to claude-opus-4-8 by the
    model's own safeguards, so a cyber task may report a different model than
    the one requested. That is the vendor's routing, not this harness's.
model_policy classifies on the "claude-opus-" prefix (model_policy.py:168), so
OPUS_ALLOWED_ROLES still gates this id exactly as it gated claude-opus-5.

Sonnet 5.5 and Haiku 5.5 are announced but NOT released — do not pin either
until `claude -p "say OK" --model <id>` answers against a nonsense-id control.

Mythos-class:
  claude-fable-5 — GATED CANARY tier (RA-1099 Wave 3). NOT a default for any
    role. Reachable only when a role is allow-listed via TAO_FABLE_ALLOWED_ROLES
    (default empty = OFF); today that is the `adversary` pre-push review role
    only. Adaptive-thinking-only (no temperature/top_p/top_k/budget_tokens) and
    may return stop_reason="refusal" — the session_sdk fable path strips sampling
    params and falls back to the ANTHROPIC_OPUS tier on a refusal/error.
  claude-mythos-5 (Glasswing only) — still not wired.

OpenRouter boardroom panellist:
  deepseek/deepseek-v4-flash
"""
from __future__ import annotations

MODEL_REGISTRY_AS_OF = "2026-09-23"
# Configuration revision is not evidence of a successful provider verification.
MODEL_REGISTRY_VERIFIED_AT = None
DOCS_MODELS_OVERVIEW = "https://platform.claude.com/docs/en/about-claude/models/overview"

# Official sources are fetched by the existing intel refresh cron. Discovery only
# creates evaluation candidates: it must never rewrite the model pins below.
MODEL_DOCUMENTATION_SOURCES = {
    "anthropic": {
        "models": DOCS_MODELS_OVERVIEW,
        "release-notes": "https://platform.claude.com/docs/en/release-notes/overview",
        "authentication": "https://code.claude.com/docs/en/authentication",
    },
    "openai": {
        "models": "https://developers.openai.com/codex/models",
        "release-notes": "https://developers.openai.com/codex/changelog",
        "authentication": "https://developers.openai.com/codex/auth",
    },
    "google": {
        "models": "https://geminicli.com/docs/cli/model/",
        "release-notes": "https://geminicli.com/docs/changelogs/",
        "authentication": "https://geminicli.com/docs/get-started/authentication/",
    },
    "openrouter": {
        "models": "https://openrouter.ai/docs/guides/overview/models",
        "authentication": "https://openrouter.ai/docs/api/reference/authentication",
    },
}

# ── Anthropic Messages API (direct / Agent SDK) ─────────────────────────────

ANTHROPIC_OPUS = "claude-opus-5-5"
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
