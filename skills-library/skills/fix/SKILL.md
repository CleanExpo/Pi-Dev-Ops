---
name: fix
description: Minimal quick fix. Use for small bugs, type errors, lint issues, or surgical one-file changes. Keeps token usage minimal.
---

Fix: $ARGUMENTS

## Protocol

1. Read ONLY the file(s) directly implicated by the error.
2. Make the **minimum viable change** to resolve the issue.
3. Run the relevant check: `pnpm type-check`, test, or lint.
4. Report: what changed + verification result.

## Rules
- Do NOT refactor surrounding code.
- Do NOT read unrelated files.
- Do NOT expand scope beyond the reported issue.
- If the fix requires touching more than 3 files, switch to `/implement`.

**Output UNDER 80 words.**
