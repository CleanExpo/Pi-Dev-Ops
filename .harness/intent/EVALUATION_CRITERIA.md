# Pi-Dev-Ops — Evaluation Criteria

## Quality Gates

These thresholds apply to all autonomous builds on this project:

- **COMPLETENESS**: minimum 8.5/10 — every explicit requirement in the brief must be addressed
- **CORRECTNESS**: minimum 9.0/10 — zero confirmed bugs; any security vulnerability is an automatic fail
- **CONCISENESS**: minimum 8.0/10 — no debug prints, no dead code, no TODO stubs
- **FORMAT**: minimum 8.5/10 — must match existing conventions exactly (snake_case, logging not print, type hints)
- **CONFIDENCE**: evaluator self-reported certainty must be ≥ 65% to auto-ship; below 60% triggers review flag

## Zero-Tolerance Failures

Any of the following is an automatic FAIL regardless of dimension scores:

- Hardcoded API keys, tokens, or passwords in any file
- `print()` statements in production code (use `logging.getLogger()`)
- Removed or weakened `--dangerously-skip-permissions` guard
- New `os.system()` or `subprocess.run(shell=True)` calls without explicit justification
- Direct Supabase writes that can raise exceptions (must be wrapped in try/except)

## Lesson Policy

When a build scores below threshold on any dimension, the evaluator must write
a specific lesson to `lessons.jsonl` identifying the root cause — not a generic
"score was low" entry. The lesson must be actionable for the next retry.
