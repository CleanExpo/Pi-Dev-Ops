---
type: engineering-requirements
spec: ./spec.md
spec_sha256: 2b9b3982851bde7ad5dca9a5755e1fb87ff5c0b730b0fea85a07faaa46c60335
reviewer: bench
seated: [boris, eng-failure, eng-observability, eng-test, eng-data, eng-concurrency, eng-cost, eng-release]
reviewed_at: 2026-10-28T16:04:12+10:00
status: PASS
categories:
  data_model:         {state: DECIDED,    ref: "#data-model", by: eng-data, blocking: false}
  invariants:         {state: DECIDED,    ref: "#invariants", by: boris, blocking: false}
  failure_modes:      {state: DECIDED,    ref: "#failure-modes", by: eng-failure}
  interface_contract: {state: DECIDED,    ref: "#interface-contract", by: boris}
  concurrency:        {state: DECIDED,    ref: "#concurrency", by: eng-concurrency, blocking: false}
  migration:          {state: DECIDED,    ref: "#migration", by: eng-release, blocking: false}
  rollback:           {state: DECIDED,    ref: "#rollback", by: boris}
  observability:      {state: PRESCRIBED, ref: "#observability", by: eng-observability, blocking: false}
  budget:             {state: DECIDED,    ref: "#budget", by: eng-cost}
  test_oracle:        {state: DECIDED,    ref: "#test-oracle", by: eng-test, blocking: false}
disagreements:
  - "eng-release and boris said keep `.harness/jev-spend.json` in the watcher's optional legacy list until every writer is updated. Author ruled against: jev_triage.py at head still records each call in jev-spend.json AND reserves it in the machine ledger, so reading both double-counts every triage call permanently. The under-count they guard against (a pre-#955 checkout writing only jev-spend.json) is closed instead by spec 17.3a-b: the watcher is not installed until every writer checkout is on the merged commit. Overturnable if a writer is found that cannot be updated."
  - "eng-observability asked for a separate P2 job W-TYPESAFE-LEDGER-SPLIT for orphan links. Author folded it into W-TYPESAFE-CAP-UNKNOWN: an unmatched mirrored call id proves a reset or split, and a reset can also lose unmirrored spend, so the day's total is a lower bound, which is what UNKNOWN means. orphan_links is still in the summary line."
  - "boris asked that C5 not depend on the main checkout's venv. Narrowed: the venv supplies only the interpreter; the code under test is the reviewed Pi-Dev-Ops worktree at the verified HEAD, and the watcher is extracted by `git show` at commit 44cb639a, so neither worktree drift nor the venv's site-packages can change what C5 proves."
  - "eng-observability asked for refusal counts by kind and a watcher heartbeat; eng-cost asked that the cap survive a reset. All three are pre-existing and outside this change: filed as Linear tickets (spec 5, non-goals)."
---

Round 1 ran against spec rev 1 and the code at Pi-Dev-Ops 1ed45211 / skills-library 97bf51d0. Every blocking
finding is answered in spec rev 2 and the code at Pi-Dev-Ops 44c6acfd / skills-library 44cb639a, which this file
is bound to.

## Data model
> `spend.finish(row, ..., call_id=)` updates `WHERE id=? AND call_id=?`; a settle matching no row returns False and writes `settle_missing` beside the ledger (eng-data).

eng-data (blocking, resolved): `finish()` settled `WHERE id=?`, so after a reset mid-call it overwrote a different
call that had taken the same row id. Now every caller settles by call id, and the mirror keeps `(row, call id)` per
call. Tests reserve A, reset, collide the row id, settle A, and assert the colliding row is unchanged, once per
caller; mutants revert each caller to row-id settling. A missed settle is reported with or without a call id.

## Invariants
> Each case must over-count (alert early) or report UNKNOWN, never a quiet under-count.

boris (blocking, resolved): the old spec promised "never under-count", which no watcher can keep for calls nothing
mirrors once their ledger file is gone. The spec now promises UNKNOWN with a lower bound and names the three reset
signs. Residual, recorded: a reset and a refill to the same row count between two runs, with no mirrored call that
day and an unchanged oldest row, is not detectable.

## Failure modes
> The watcher is not installed until every one is, because a checkout left on c195d3e0 is double-counted every day

eng-failure: every path traced at head over-counts. The danger is a writer checkout lagging the merge: on c195d3e0
its mirrored calls are counted twice every day (false 80% and 100% alerts at about $8 and $10, which teaches the
founder to ignore the alert), and one from before #955 writes spend the new watcher does not read. Both are closed by
the install order in spec 17.3. Step 3 of the shadow mirror failing leaves the machine row `attempted` and the
legacy link NULL; the watcher counts both and `stale_attempted` shows it within 600 s.

## Interface contract
> `finish()` keeps its positional signature; `call_id` is a new keyword.

`reserve()` still returns an int (mutant `reserve-returns-tuple`). `reserve_call()` returns `(row, call_id)`.
`spend.add_column()` is new and public, used by both upgrade paths.

## Concurrency
> The machine ledger's sum and call ids come from one SELECT (eng-concurrency): two reads let a call landing between them be skipped in the legacy ledger and missing from the total.

eng-concurrency (blocking, resolved): test `test_a_call_landing_between_the_watchers_reads_is_counted_once_not_zero_times`
writes a call between the watcher's statements; mutant `twins-read-separately` restores the two reads and is killed.
The orphan check re-reads the machine ledger after the legacy reads, and a mirror commits its machine row before its
link, so a call landing mid-run is found there and raises no false UNKNOWN. The upgrade-day ALTER race (two
processes, one old ledger) is handled once in `spend.add_column` (boris, eng-failure); mutants cover both directions.

## Migration
> Update each to the merged commit (a descendant of this PR's head) and restart any process running it.

eng-release (blocking, resolved), observed live on the Mini: no writer checkout (`~/Pi-Dev-Ops`, `~/relint/pdo`,
`code/pdo-jev-runner`) has `spend.py`; the Mission Control ledger has no `spend_id`/`spend_call_id`; the live machine
ledger has no `call_id`; the installed watcher still reads `jev-spend.json`. Columns are added in place on the next
connect; old rows keep NULL ids and count (over-count, safe). Test
`test_a_legacy_ledger_that_already_has_spend_id_gains_spend_call_id` pins the live Mini state, with a mutant.

## Rollback
> Restore the watcher from `~/.local/bin/jev-cap-watcher.py.bak-*` or reinstall, then run the post-install check (section 17).

Reverting only Pi-Dev-Ops while the new watcher stays installed over-counts every mirrored call; both PRs revert
independently and neither drops data.

## Observability
Prescribed by eng-observability (non-blocking), built: the watcher's one-line JSON summary carries, per ledger,
`counted`, `skipped_twin` and `skipped_twin_usd`, `unlinked` and `unlinked_usd`, `orphan` and `orphan_usd`; plus
`orphan_links`, `optional_skipped`, `machine_call_id` and `reset`. A lagging writer shows on its first run as
`unlinked` rows in a ledger that should carry links. Test `test_the_summary_line_says_what_each_ledger_contributed`
and mutant `summary-counts-skipped`. The post-install check (spec 17.3d) looks for these keys in the live log.

## Budget
> This change makes the alert truthful. It does not make the cap survive a reset

eng-cost: no new paid call, network path or job. `JEV_DAILY_CAP_USD` sums only the current machine-ledger file, so a
reset re-opens the day's allowance; ticketed rather than fixed here.

## Test oracle
> reports the machine ledger UNKNOWN with the lower bound that excludes only the lost unmirrored call

eng-test (blocking, resolved): the earlier C5 expected (1000+2000+2000)*PRICE+0.25 with nothing UNKNOWN, a total
1,000 tokens short of true spend; it passed on the under-count. C5 now asserts the exact total before the reset and
UNKNOWN plus the lower bound after it, against the watcher extracted at commit 44cb639a. Control: the same check
against watcher 97bf51d0 exits 1 (it reports $0.25021 with nothing UNKNOWN). Mixed-day twins have a test and the
`day-filter-dropped` mutant. The watcher mutants are committed beside its tests
(`skills/guardian/tests/jev_cap_watcher_mutants.py`, 16 killed). Known weak kill, kept: `call-id-reused` is killed
by the unique index raising, which is the behaviour the index exists for.
