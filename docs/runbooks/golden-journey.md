# Golden journey (UNI-2652)

This is the check that the autonomous loop actually works: one instruction
becomes one tested draft PR, five times in a row, and then one planted crash
is recovered without a fake pass.

The existing pipeline smoke (`scripts/smoke_test_pipeline.py`) still owns
assertions A1–A7. It is at its 166-line function cap, so this runbook uses
the wrapper `scripts/golden_journey.py` instead of growing it.

## What the extra assertions prove

| # | Check | Meaning |
|---|---|---|
| A8 | `/api/health/ready` (or `/ready`) returned 200 *before* the run | The machine could clone. Depends on UNI-2646. |
| A9 | Gate row and session status agree | `complete` only when shipped/push succeeded (UNI-2643). |
| A10 | PR body maps Requirement → Change → Test | A reviewer can see what was asked, what changed, and how it was tested. |

## Commands

One live journey (A8 + A1–A7 + A9 + A10):

```bash
DASHBOARD_PASSWORD=... python3 scripts/golden_journey.py
```

Five consecutive journeys, then the planted failure (the ticket's 5+1):

```bash
DASHBOARD_PASSWORD=... \
PI_CEO_URL=https://pi-dev-ops-production.up.railway.app \
python3 scripts/golden_journey.py --runs 5 --plant-failure
```

Planted failure only (no password, no prod, safe in CI):

```bash
python3 scripts/golden_journey.py --plant-failure
```

The planted run kills a dummy claimant mid-work and checks five facts:

1. the worktree is still on disk
2. the claim becomes free after the lease expires
3. a second machine is the one that resumes
4. a third machine cannot take the same claim
5. the killed run did not print PASS

## What CI runs

`pytest tests/test_golden_journey.py tests/test_golden_journey_planted.py`
covers the checkers and the planted failure. It does **not** fire five
20-minute live builds. That 5+1 path stays local or prod, on purpose:
each journey is the real autonomous pipeline.

The nightly job `.github/workflows/smoke_pipeline.yml` still runs one
A1–A7 smoke. Point it at `scripts/golden_journey.py` once UNI-2646's
`/api/health/ready` is live and a single journey is passing.

## Sibling tickets this journey may wait on

- UNI-2646 — `/api/health/ready` clone probe (A8)
- UNI-2643 — complete requires push (A9)
- UNI-2650 — coverage-gated loop
- UNI-2656 — workspace trust (already on main)

If A8 fails with HTTP 404, UNI-2646 has not landed yet. That is a real
fail, not a skip.
