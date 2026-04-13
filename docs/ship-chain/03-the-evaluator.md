# 03 — The Evaluator

After the generator commits code, a second AI pass reads the git diff and
scores it against the original brief. The evaluator is what makes Pi-CEO
self-correcting.

---

## What the evaluator does

1. Runs `git diff HEAD~1` in the workspace to get the last commit's changes
2. Sends the diff + original brief to a scoring model
3. Parses the score from a structured `OVERALL: <n>/10` line
4. Routes to pass / retry / warn based on score + threshold

---

## The four scoring dimensions

Every evaluation scores on exactly these dimensions:

| Dimension | What it checks |
|-----------|---------------|
| **Completeness** | Every requirement in the brief is fully addressed — not started, not partial. |
| **Correctness** | No bugs, no logic errors, no null dereferences, no hardcoded secrets. |
| **Conciseness** | No dead code, debug prints, or TODO stubs. No over-engineering. |
| **Format** | Naming, indentation, import order match the existing codebase exactly. |

The overall score is the average. Default pass threshold: **8.0/10**.

---

## Production evaluator: parallel Sonnet + Haiku

In production (`sessions.py::_phase_evaluate()`), two model calls run in parallel:

- **Sonnet** — primary scorer
- **Haiku** — fast secondary scorer

If their scores diverge by more than 2 points, the session escalates to
**Opus** for a tiebreaker. This reduces single-model hallucination in the
eval and provides a consensus score.

The final `evaluator_consensus` string in session state records all three
per-model scores for audit.

---

## Three-tier confidence routing (RA-674)

The evaluator also reports a `CONFIDENCE: <n>%` estimate. This unlocks
three routing tiers instead of binary pass/fail:

| Tier | Condition | Outcome |
|------|-----------|---------|
| **AUTO-SHIP FAST** | score ≥ 9.5 AND confidence ≥ 90% | Ship immediately, skip low-confidence check |
| **PASS** | score ≥ threshold AND confidence ≥ 60% | Normal pass, ship |
| **PASS + FLAG** | score ≥ threshold AND confidence < 60% | Pass but fire Telegram alert for human review |
| **RETRY** | score < threshold | Inject evaluator feedback into spec, regenerate |

Thresholds are configurable via env vars:

```bash
TAO_EVAL_AUTOSHIP_SCORE=9.5       # default
TAO_EVAL_AUTOSHIP_CONFIDENCE=90   # default
TAO_EVAL_FLAG_CONFIDENCE=60       # default
TAO_EVALUATOR_THRESHOLD=8         # default retry/pass boundary
```

---

## Retry loop

When the outcome is `retry`, Pi-CEO:

1. Appends the evaluator feedback to the generator spec:
   ```
   --- RETRY 1: previous score 6.2/10 ---
   COMPLETENESS: 5/10 — brief requires X but only Y was implemented...
   ```
2. Re-runs the generator with the enriched spec
3. Re-evaluates the new diff
4. Repeats up to `TAO_EVALUATOR_MAX_RETRIES` times (default: 2)

If the score never reaches the threshold, the session ends with `"warn"` status
and the lesson is logged to `.harness/lessons.jsonl` for future builds.

---

## Observability

Every evaluation result is written to Supabase `gate_checks` table (fire-and-forget):

```
pipeline_id, session_id, gate_checks[], review_score, shipped,
confidence, scope_adhered, files_modified
```

Source: `app/server/supabase_log.py::log_gate_check()`

---

## Next

[04 — Karpathy Optimisations](04-karpathy-optimisations.md): the Sprint 9
enhancement layer — budget, scope contract, plan discovery, and more.
