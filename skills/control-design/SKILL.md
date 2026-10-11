---
name: control-design
description: Use BEFORE writing or changing any check, test, gate, guard, assertion, exclusion, fixture or startup config branch — while the control is being built, not when its result is read. Catches controls that cannot fail, exclusions whose premise has expired, checks that know a fixed set and go stale, verifications that require handling the thing they protect, and missing-config branches that invent a credential instead of refusing to start. Triggers on "add a check", "write a test for", "gate this", "skip/exclude this path", "assert that", "guard against", or any first run of a new control.
---

# Control Design

**This is the BUILD-TIME half. Its sibling, [`proof-discipline`](../proof-discipline/SKILL.md),
is the CLAIM-TIME half — load that one when about to say something is green, done or verified.**

Split from a single 480-line file on 2026-08-02. The two halves fire at different moments and
one document could only ever be loaded at one of them. The risk being removed is not length —
it is that the half you needed was inside a document you opened for the other reason.

**The one line to carry:** *a control that cannot fail is worth exactly as much as no control,
and it is more expensive because it also buys false confidence.* Before a control is finished,
make it go red on purpose and watch it.

## Failure-Mode Catalogue (pattern-match fast)

| # | Failure mode | Smell | Detection command |
|---|---|---|---|
| 1 | **Sub-scale fixture** | "tiny fixture, all green" | `EXPLAIN (ANALYZE)` at fixture size vs a 50k+ row copy — does the plan node change? |
| 2 | **Forced-plan artifact** | test drops an index / sets `seqscan=off` / stubs a guard to make the path fire | grep the test for `drop index`, `enable_seqscan`, `set_config(... iterative ...)`, mocks; if the path needs forcing, it's a demo |
| 3 | **Silent cap** | result set "looks complete" but never tested past a limit | load `cap+1` matching rows; assert count == `cap+1`, not `cap`. Sweep `max_scan_tuples`, `least(count,N)`, `ef_search` |
| 4 | **Deployed/template drift** | "the migration says X" but the live object differs | `pg_get_functiondef('schema.fn'::regproc)` diff against the `.sql` source |
| 5 | **Observed-not-proven security** | "0 leak" seen once, in geometry where a leak couldn't show | rebuild fixture with tenants interleaved in the ranked output; run via signed JWT + real role; assert exact id-set, 0 cross-tenant |
| 6 | **Vacuous control** | "I broke it and the check still passed / caught it" — but the thing you broke was never there | assert the PRECONDITION before trusting the control: the anchor string must exist, the file must be non-empty, the planted token must actually land. `grep -c` it after planting, and fail loudly at zero |
| 7 | **Misaimed instrument** | "I searched and found nothing — and I proved my search works" | a positive control validates the INSTRUMENT, not the AIM. Confirm the target exists under the name/path/shape you searched for, in the version you are on, before reading absence as evidence. Cheapest disproof: probe the live system, which answers about reality rather than about your query |

## Failure modes 6 and 7 in full

Read `references/failure-modes-6-and-7.md` for failure mode 6 (verify a control's precondition before trusting the control) and failure mode 7 (a positive control validates the instrument, not the aim), each with its WRONG and RIGHT example.

## Test Fixtures Generate Secret-Shaped Values; They Never Write Them as Literals

A secrets scanner **cannot tell a fixture from a credential by reading it.** That is not a
limitation to work around — it is the correct behaviour, and the reason the estate's JWT
pattern was deliberately left broad enough to match public anon keys.

**Rule:** a test needing a password, token, secret or key generates it at runtime
(`randomBytes(24).toString("hex")`). Never a literal, however obviously fake it looks.

**Why the obvious alternative is the trap.** When a fixture trips the scanner, adding a skip
prefix or widening the placeholder regex looks like the reasonable fix. It is not: it narrows
the scanner's scope permanently to accommodate one file, and **that is the path by which a real
secret eventually walks through.** Same shape as `.gitignore` as a silent scope reducer — the
fix that makes today's alarm stop is the one that disables tomorrow's.

**Two instances, both mine, both caught by the scanner rather than by review:**
- `scripts/route-exercise.mjs` — a hardcoded probe password (2026-08-02)
- `dashboard/__tests__/kill-switch-auth.test.ts` — `const KS_SECRET = "kill-switch-shared-secret"`,
  which failed CI on PR #603. Its sibling on the line above escaped only by accident:
  `"kill-switch-test-secret"` contains `test-secret`, which the placeholder regex excludes.

Both were fixed by generating the value, not by teaching the scanner to look away. The third
instance will arrive on a day when a skip prefix looks reasonable; this entry exists for that day.

## Further failure modes

Read `references/design-failures.md` for these, in full: naming the risk is not covering it; a verification that requires handling the thing it protects; a check that knows a fixed set goes stale (structural limit 2); deciding which one is wrong when the claim is wider than the check; the first run of a new control is the failing one; a service that invents its own credential.

## Claim shape and canary placement

Read `references/claim-shape-and-canary.md` when you are about to state what a check proved, or when choosing where to plant a canary. It holds the CLAIM-SHAPE RULE and the CANARY-PLACEMENT RULE with their worked examples.

