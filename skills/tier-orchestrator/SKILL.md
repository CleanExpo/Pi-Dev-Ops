---
name: tier-orchestrator
description: The orchestrator plans, decomposes briefs, and delegates to lower tiers.
---

# Tier Orchestrator

The orchestrator is the top tier. It receives the brief, decomposes it into features, creates sprint contracts, and delegates to specialists and workers.

## Delegation Patterns
- Fan-out: Independent tasks run in parallel
- Serial: Each depends on the previous
- Hierarchical: Specialists decompose further before workers execute
