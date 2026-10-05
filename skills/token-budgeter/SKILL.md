---
name: token-budgeter
description: Track and enforce token budgets per tier. Use when a task involves tracking or enforcing token budgets per tier, comparing model costs for Opus, Sonnet or Haiku output and cache tokens, or deciding how spend differs on Claude Max where execution via the claude CLI subprocess costs $0.
---

# Token Budgeter

## Model Costs (April 2026)
- Opus 4.7: $15.00 / M output tokens ($75 input cache write, $3.75 cache read)
- Sonnet 4.6: $3.00 / M output tokens ($3 input, $0.30 cache read)
- Haiku 4.5: $1.25 / M output tokens ($0.80 input, $0.08 cache read)

On Claude Max: $0 for everything — all execution is via `claude` CLI subprocess.
