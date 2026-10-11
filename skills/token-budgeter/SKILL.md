---
name: token-budgeter
description: Track and enforce token budgets per tier. Use when a task involves tracking or enforcing token budgets per tier, comparing model costs for Opus, Sonnet or Haiku output and cache tokens, or deciding how spend differs on Claude Max where Agent SDK execution bills the subscription, not per token.
---

# Token Budgeter

## Model costs
Read current model ids from `app/server/model_registry.py`. It holds no price table: take per-token prices from Anthropic's published pricing page at calculation time, and do not pin them here.

On Claude Max, Agent SDK runs bill the subscription, not per token.
