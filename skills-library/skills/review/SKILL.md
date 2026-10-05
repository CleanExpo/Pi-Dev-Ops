---
name: review
description: Isolated code review. Use for "review this", "check this code", "audit changes". Read-only, prioritised findings. Runs in a forked context.
context: fork
agent: Explore
---

Review: $ARGUMENTS

## Protocol

1. Run `git diff --stat` to see what changed.
2. Run `git diff` to read the actual changes.
3. Review ONLY changed lines for: correctness, security, performance.
4. Check against project CLAUDE.md rules if it exists.
5. Do NOT review pre-existing code that wasn't modified.

## Output Format

**Critical** (blocks merge):
- `file:line` — issue — fix

**Warning** (should fix):
- `file:line` — issue — fix

**Note** (optional improvement):
- `file:line` — suggestion

**Verdict**: PASS / WARN / FAIL

**UNDER 200 words total.** Only findings with high confidence.
