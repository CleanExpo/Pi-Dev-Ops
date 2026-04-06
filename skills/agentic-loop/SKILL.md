---
name: agentic-loop
description: Infinite self-correcting iteration until completion criteria met.
---

# Agentic Loop

Two-prompt system: task prompt + stop guard.
Agent works -> tries to stop -> guard checks criteria -> not met -> continues.

## Safety Rails
- max_iterations: 20
- max_tokens: 200000
- max_runtime_minutes: 60
- Detect oscillation (fix A breaks B) after 3 iterations
