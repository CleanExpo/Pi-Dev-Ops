# Evaluator Agent — Tier 3 Specification

**Role:** Quality gate. Grades generator output against 4 dimensions. Produces pass/fail verdict.

**Model:** `claude-sonnet-4-6` (sufficient for structured evaluation; cost-efficient)

**Responsibilities:**
1. Receive the workspace diff (`git diff HEAD~1`) from the completed generator run
2. Grade against 4 dimensions (each 1-10):
   - **Completeness** — does it address the full brief?
   - **Correctness** — are there bugs, logic errors, or security issues?
   - **Conciseness** — is the code clean without unnecessary bloat?
   - **Format compliance** — follows project conventions and style?
3. Parse OVERALL score (average of 4 dimensions)
4. Compare against `EVALUATOR_THRESHOLD` (default: 7/10)
5. Return verdict: PASS / BELOW THRESHOLD

**Output format (strict — must be parseable):**
```
COMPLETENESS: <score>/10 — <reason>
CORRECTNESS: <score>/10 — <reason>
CONCISENESS: <score>/10 — <reason>
FORMAT: <score>/10 — <reason>
OVERALL: <average>/10 — PASS or FAIL
```

**Inputs:**
- `git diff HEAD~1` (stat + full diff, truncated to 8000 chars)
- Original brief (for completeness scoring)
- `EVALUATOR_THRESHOLD` from config

**Outputs:**
- Structured score text (streamed to WebSocket)
- `evaluator_score: float` on `BuildSession`
- `evaluator_status`: "passed" | "warned" | "error" | "timeout"

**Constraints:**
- 120 second timeout — if exceeded, mark `evaluator_status = "timeout"` and proceed
- Non-blocking: below-threshold score logs warning but does not block git push (for now)

**Config reference:** `.harness/config.yaml` tier: `evaluator`
