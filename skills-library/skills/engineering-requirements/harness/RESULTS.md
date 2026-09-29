# Results

## Run 2 — 2026-07-29, seven seats, both arms, 14 agents

**Verdict: no signal. Two metrics, pointing opposite ways, each by a single defect.**

| | treatment (METHOD) | control (no METHOD) |
|---|---|---|
| recall across all 8 defects, 7 runs per arm | 4.00 / 8 | **4.14 / 8** |
| the defect each seat *owns* | **8 / 8** | 7 / 8 |

Every seeded defect had its owning seat in the room, so the structural cap that made run 1
uninformative is gone. What replaced it is a genuine tie.

**Own-seat is the cleaner measure and it favours the treatment by exactly one defect.** Six of
seven seats found their own defect in both arms. The single difference: control-arm
`eng-concurrency` never mentioned `nextAttemptAt` — verified, the string appears zero times in that
file — so it missed D1, the backoff that is computed, stored and never read. It found three other
real concurrency defects instead (double-drain, lost update on `retryCount`, replay ordering).

**All-defect recall is the noisier measure and it favours the control by exactly one defect.**
That metric counts incidental cross-domain mentions, so it rewards a seat wandering outside its
lane — which is the behaviour `CONTRACT.md`'s cap exists to suppress. I would not weight it above
own-seat, and I am recording both rather than picking the one that flatters the layer I built.

One defect either way, at one run per seat per arm. That is not evidence.

## The scorer was wrong again, and again the run caught it

Own-seat first read 8/8 against 6/8, which looked like a result. It was not: control-arm `eng-test`
had found D7 explicitly — its own section heading is "the suite does not collect the only test
file", and it states the config "matches neither glob" and that "the number of test cases that
execute is zero". My signature listed `not collected` and `matches no` and none of the phrasings the
seat actually used. A scorer false negative, invented against the arm I expected to lose.

Fixed by adding those phrasings. The gap halved, from two defects to one.

That is now **three** signature defects the harness has caught in itself:

1. D6 matched the filename `APPLIED_LEDGER.txt` rather than any claim about drift — caught by the
   decoy control before any run existed.
2. D8 fired on a concurrency review containing no `/api/health`, no `route.ts` and no `1.0.0`,
   matching "un**health**y", "version" and "stale" — caught by run 1.
3. D7 missed a seat that found the defect and phrased it differently — caught by run 2.

Every one was found by a check. None was found by reading the manifest. The pattern is consistent
enough to state plainly: **a hand-written signature is wrong until a run disagrees with it**, and
the harness's real output so far is corrections to itself.

## What the seats found that the manifest cannot score

Both of these were confirmed against the files directly, not taken on the agents' word.

- **`003_rls_fix.sql` cannot apply at all.** `grep -rn user_tenant_access` over the fixture returns
  exactly one hit — the `USING` clause that reads the table. No migration creates it. I introduced
  this by accident while writing the fixture; twelve of the fourteen runs found it, several tracing
  the two partial-apply outcomes (transaction wrapper → fails open on the permissive policy; no
  wrapper → RLS on with zero policies, a silent total read outage). It is a better defect than the
  drift I planted deliberately, and the manifest cannot score it.
- **`migration_drift.py` reports drift inverted.** `migration_drift.py:238` sets
  `--ref` default `origin/main`; against an untracked path the repository side comes back empty and
  the tool names the two healthy migrations as applied-out-of-band while never mentioning the
  unapplied security fix. Same exit code, opposite diagnosis. Both `eng-release` runs found it and
  the treatment run found the working invocation (`--ref worktree`) and reported the caveat beside
  its evidence. Live defect in shipped tooling, not fixed here.

## Run 1 — two seats, both arms

Kept for comparison under `runs/r1/`. Structurally uninformative: five of eight defects had no
owning seat dispatched. Control 4.00, treatment 3.50, entire gap one cross-domain aside.

## What a third run would need to settle it

Repeat each arm three or more times. Both differences observed so far are single defects at n=1 per
seat, which is inside the range a re-roll would move. Until then the honest statement is the one
from the start of this file: **`METHOD.md` is unproven — now against a real fixture, with numbers,
rather than against prose.**
