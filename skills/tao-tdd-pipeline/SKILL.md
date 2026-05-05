---
name: tao-tdd-pipeline
description: Test-first iteration pipeline. Composes on tao-loop + tao-judge to enforce red→green→refactor discipline. The judge is bound to "all tests pass + new test files modified". Without test files in the diff, GOAL_MET is rejected.
owner_role: Tier-Orchestrator (uses generator + evaluator at sonnet per RA-1099)
status: wave-2
linear: RA-1992
---

# tao-tdd-pipeline

Drives a TDD discipline on top of `tao_loop.run_until_done`. The user
provides a goal that names the test scenarios first, the implementation
last; the worker writes failing tests, makes them pass, refactors. The
pipeline gates "done" on three conjunctive conditions:

1. The standard `tao_judge.judge` returns `done=True` (`GOAL_MET`).
2. `git diff --name-only HEAD` includes at least one file matching
   pytest test conventions (`test_*.py`, `*_test.py`, `tests/*.py`,
   `conftest.py`).
3. `python -m pytest -q tests/` exits 0 with a `passed` summary line.

If the loop reports `GOAL_MET` but #2 or #3 fail, the result is
returned with `done=False`, `reason='TESTS_NOT_GREEN'` or
`'NO_TEST_FILES_MODIFIED'`, and `discipline_violations` populated for
the caller to act on.

## When to trigger

- A user issues a TDD-style brief — explicitly mentions tests, scenarios,
  red/green, or asks for "test-first" / "TDD" / "test-driven".
- The orchestrator wants stronger guarantees than vanilla `tao-loop`
  for ambiguous correctness goals (e.g. "fix this bug" → "add a
  regression test, then fix").

## Public API

```python
from app.server.tao_tdd_pipeline import run_tdd, TddResult

result = await run_tdd(
    goal="implement a hex-string parser; tests cover empty / non-hex / "
         "uppercase / mixed-case / leading-0x cases",
    workspace="/path/to/repo",
    max_iters=15,
    max_cost_usd=2.00,
    timeout_per_iter_s=600,
    on_event=lambda evt: ...,
    session_id="tdd-hex-parser-001",
)

# result.done                   — True iff loop AND tests AND test-files
# result.reason                 — composite (see TddResult.reason)
# result.loop                   — full LoopResult from tao_loop
# result.test_files_modified    — list of paths matching test convention
# result.final_pytest_passed    — pytest exit-code 0 + passed summary
# result.final_pytest_summary   — last 1500 chars of pytest combined output
# result.discipline_violations  — strings explaining loop.done but result.done=False
```

## Autoresearch envelope

| Slot | Value |
| --- | --- |
| Single metric | `iters_to_green` / `cost_to_green` |
| Time budget | inherited from `TAO_MAX_ITERS` + `TAO_MAX_COST_USD` |
| Constrained scope | `app/server/tao_tdd_pipeline.py` only |
| Strategy/tactic split | user → test scenarios; agent → red→green→refactor |
| Kill-switch | inherited via tao_loop's LoopCounter (MAX_ITERS, MAX_COST, HARD_STOP) |

## CLI

```bash
python scripts/run_tao_tdd.py \
    --goal "..." \
    --workspace /path/to/repo \
    --max-iters 10 \
    --max-cost 1.50 \
    --judge-every 1
```

Exit codes: `0` done, `1` loop met but discipline violated, `2`
kill-switched / never met goal.

## Composition with other Wave 1+2 modules

- **tao-context-prune (RA-1990):** runs upstream of the SDK call so the
  worker's transcript stays small across iters.
- **tao-context-mode (RA-1969):** sharper file-expand decisions during
  the implementation phase.
- **tao-judge (RA-1970):** unchanged — the TDD discipline is added as a
  post-loop gate so the existing judge contract isn't fractured.

## Behaviour invariants

- Goal is enriched with a `_TDD_PREAMBLE` describing the red→green→refactor
  order. Idempotent — if "test-first discipline" already appears in the
  goal we don't double-add.
- The worker is NOT prevented from deciding to skip tests; the gate is
  retrospective. This keeps the existing `tao_loop` contract clean and
  surfaces discipline violations as data the caller can route on
  (e.g. flag-as-needs-review rather than auto-merge).
- Pytest invocation uses `-q --tb=line` so summary lines parse reliably.
- Test-file regex is liberal: `test_*.py`, `*_test.py`, `conftest.py`,
  `tests/*.py`. Conservative regression risk if a project uses a
  non-pytest convention (e.g. `nose2`); document and override per repo
  if that turns up.
