# Evaluator Contract — Pass/Fail Thresholds

## Purpose

Defines the scoring agreement between the generator tier and the evaluator tier. Both tiers must use these definitions when producing and interpreting scores.

---

## Scoring Dimensions

Each dimension is scored 1–10. Scores must be integers.

| Dimension | 1-3 (Fail) | 4-6 (Marginal) | 7-9 (Pass) | 10 (Excellent) |
|-----------|-----------|----------------|------------|----------------|
| **Completeness** | Brief mostly unaddressed | Core requirements met, edge cases missing | All requirements met | Exceeds brief with valuable additions |
| **Correctness** | Critical bugs or security issues | Logic errors that may surface in edge cases | No obvious bugs, sound logic | Provably correct, handles all edge cases |
| **Conciseness** | Significant bloat or dead code | Some redundancy but functional | Clean, DRY, readable | Exemplary simplicity |
| **Format** | Wrong conventions throughout | Minor style violations | Follows CLAUDE.md conventions | Indistinguishable from expert human author |

---

## Pass/Fail Threshold

```
EVALUATOR_THRESHOLD = 7 (default, configurable via TAO_EVALUATOR_THRESHOLD env var)
```

- **PASS:** `OVERALL >= EVALUATOR_THRESHOLD` → session continues to git push
- **BELOW THRESHOLD:** `OVERALL < EVALUATOR_THRESHOLD` → warning logged, push still proceeds (non-blocking Phase 1)
- **Future (Phase 2):** Below-threshold results will trigger a retry loop with the generator before pushing

---

## Score Calculation

```
OVERALL = mean(COMPLETENESS, CORRECTNESS, CONCISENESS, FORMAT)
```

Round to 1 decimal place. Store as `session.evaluator_score: float`.

---

## Output Format Contract

The evaluator **must** produce output in this exact format (parseable by `sessions.py`):

```
COMPLETENESS: <integer>/10 — <one-line reason>
CORRECTNESS: <integer>/10 — <one-line reason>
CONCISENESS: <integer>/10 — <one-line reason>
FORMAT: <integer>/10 — <one-line reason>
OVERALL: <decimal>/10 — PASS or FAIL (threshold: 7/10)
```

Any deviation from this format causes `evaluator_status = "error"` — score cannot be parsed.

---

## Evaluator Status Values

| Status | Meaning |
|--------|---------|
| `pending` | Evaluator not yet run (session created) |
| `running` | Evaluator subprocess active |
| `passed` | Score >= threshold |
| `warned` | Score < threshold (non-blocking) |
| `error` | Output could not be parsed |
| `timeout` | 120s timeout exceeded |
