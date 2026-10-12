---
name: token-budgeter
description: Track and enforce token budgets per tier. Use when a task involves tracking or enforcing token budgets per tier, comparing model costs for Opus, Sonnet or Haiku output and cache tokens, or deciding how spend differs between Claude Code on a Max plan (plan usage limits) and Agent SDK runs (finite API credits, never the plan).
---

# Token Budgeter

## Model costs
Read current model ids from `app/server/model_registry.py`. It holds no price table: take per-token prices from Anthropic's published pricing page at calculation time, and do not pin them here.

On a Claude Max plan, Claude Code sessions count against the plan's usage limits. Agent SDK runs do not: they spend the plan's monthly API credits (finite, no rollover), then any purchased credits, then requests stop. They are never charged to the plan. Source: platform.claude.com/docs/en/about-claude/api-credits-for-subscribers.
