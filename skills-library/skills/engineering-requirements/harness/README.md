# The seeded-defect harness

A rig for answering one question with evidence instead of prose: **does `METHOD.md` change what a
bench seat finds, or does it only change how a seat writes?**

It exists because two attempts to answer that question failed. The second failed because the
dispatch prompt named `METHOD.md` directly, so every method citation had a simpler explanation
than the one being tested. This harness removes that explanation by construction.

## What is here

| Path | What it is |
|---|---|
| `fixture/` | A small repository with eight planted defects and a `spec.md` that does not mention any of them. |
| `defects.json` | The manifest: for each defect, the mechanism, the seat that should own it, and the text signature that counts as finding it. |
| `score.py` | Scores an emitted artifact against the manifest. Ships with three controls. |
| `make_arms.py` | Derives both arms from the live seat files so they cannot drift apart by hand. |
| `arms/with-method/`, `arms/no-method/` | The generated arms. Do not edit these; regenerate them. |
| `PROMPT.md` | The one dispatch template used for every seat in every arm. |

## The eight defects

Every one is a pattern a real bench run already surfaced on a real repository during the
2026-07-29 sessions. Nothing was invented to be findable, and nothing was invented to be missable.

| ID | Seat | Defect |
|---|---|---|
| D1 | `eng-concurrency` | `nextAttemptAt` is written by `incrementRetry` and never read by `drainQueue` — backoff exists in the data and not in the behaviour. |
| D2 | `eng-observability` | `getSyncStatus` counts pending and conflict, so entries moved to `failed` report as `SYNCED`. |
| D3 | `eng-failure` | `sendEmail` swallows every error; `runWatchdog` records `alerted = true` regardless. |
| D4 | `eng-authz` | RLS enabled, then a `USING (true)` policy plus a `GRANT` to `anon`. |
| D5 | `eng-data` | Cascade from `User` to `Inspection` to `AuditLog` — deleting a user destroys the evidence of what they did. |
| D6 | `eng-release` | `003_rls_fix.sql` is committed and absent from the ledger. The repository looks fixed; the database is not. |
| D7 | `eng-test` | The only test file matches no `vitest` include glob. The suite is green because it is empty. |
| D8 | `eng-release` | `/api/health` falls back to a hardcoded version, so you cannot tell which build is live after a bad deploy. |

## Running it

**Always run the controls first.** A scorer that has never registered a miss is indistinguishable
from one that cannot.

```bash
python3 ~/.claude/skills/engineering-requirements/harness/score.py --self-test
```

Three controls must pass: a synthetic artifact naming every mechanism scores 8/8, an empty artifact
scores 0/8, and a decoy artifact naming every *file* but no *mechanism* scores 0/8. The decoy is the
one that matters — it has already caught a signature of mine that was matching the filename
`APPLIED_LEDGER.txt` rather than any claim about drift.

Then regenerate the arms and confirm the single variable:

```bash
python3 ~/.claude/skills/engineering-requirements/harness/make_arms.py
```

It fails closed if a strip pattern matches nothing. That guard has already fired once, on a
control-arm file that still carried the sentence "the method wins".

Dispatch each seat with the template in `PROMPT.md`, save each reply to a file, then:

```bash
python3 score.py --json runs/with-method/*.md > armA.json
```

```bash
python3 score.py --compare armA.json armB.json
```

## What a number from this does and does not mean

**Recall is machine-scored. Precision is not.** A seat emitting forty claims scores well here and
is useless in practice — which is what the caps in `CONTRACT.md` exist to prevent. Count the
off-target claims by hand before reading recall as quality. `score.py` prints this warning on every
report rather than letting the number stand alone.

**One run per arm is a coin toss.** Variance across seat dispatches is large enough to produce any
ordering you like. Several runs per arm, or the result is decoration.

**A delta is evidence only if the arms differed in exactly one variable.** `diff` the two arm files
before believing any comparison. For `eng-release` the entire difference is four lines, all of them
the `METHOD.md` reference.

**The defects are not a representative sample of all defects.** They are eight mechanisms chosen
because they were already found once. A method layer could improve judgement on defects unlike
these and score flat here.
