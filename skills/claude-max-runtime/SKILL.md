---
name: claude-max-runtime
description: Execute TAO natively within Claude Max subscription. Use when a task asks to run the TAO loop natively inside a Claude Max subscription, or needs the tier mapping of Opus-tier orchestrator, Sonnet-tier specialist and evaluator, and Haiku-tier worker subagents at zero API cost.
---

# Claude Max Runtime

## Tier Mapping
- Orchestrator: Main Claude Code session (Opus tier, 1M ctx)
- Specialist: Subagent (Sonnet tier)
- Worker: Subagent (Haiku tier)
- Evaluator: Subagent (Sonnet tier, read-only)

Exact model ids: `app/server/model_registry.py`.

Zero API cost. Everything included in Max subscription.
