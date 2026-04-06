---
name: closed-loop-prompt
description: Self-correcting prompts with embedded verification.
---

# Closed-Loop Prompting

Embed verification INTO the prompt:
1. Build X
2. Run Y to check
3. If Y fails, fix and retry
4. Max 3 attempts

## Patterns
- Test-Fix Loop: implement -> test -> fix -> retest
- Build-Verify-Iterate: build -> verify output -> fix discrepancy
- Multi-Step Cascade: phase 1 verify -> phase 2 verify -> integration verify
