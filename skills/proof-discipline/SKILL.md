---
name: proof-discipline
description: Use whenever about to mark a test, gate, verification, or task as passing / GREEN / complete. Catches vacuous verification — tests that pass without exercising the real production path, claims asserted but not proven against the live system, silent caps that truncate results, deployed-vs-source drift, and security claims proven only in friendly geometry. Triggers on "tests pass", "it's green", "verified", "done", "complete", especially for query plans, indexes (HNSW/btree), RLS/tenant isolation, scale/load, and EXPLAIN.
---

# Proof Discipline

## Overview

**GREEN is a claim about the live production path at real scale — not a statement that an assertion returned true.** A passing test proves nothing until you have shown it exercised the path production actually runs. The root failure this skill prevents: *passing a test without proving the claim.*

This came from a real incident. A pgvector + RLS suite was GREEN, yet the 142-row fixture was below the scale where the HNSW index engages, so the test never touched the production path. Forcing the index (drop btree + `seqscan=off`) produced a plan production never runs. Two load-bearing bugs hid under that false-green, and a subagent's recommended fix value was wrong — both caught only by checking the live system.

**Violating the letter of this checklist is violating the spirit. "It passed" is not evidence. "I reasoned it through" is not evidence. Live output is evidence.**

## The Pre-GREEN Checklist

Before marking ANYTHING passing/GREEN/complete, answer every item **with pasted live output, not assertion.** No item may be skipped.

1. **Real path, not forced.** Run live `EXPLAIN (ANALYZE, BUFFERS)` (or the equivalent: actual plan / dispatched code path / chosen branch). Confirm the plan matches production. If the path under test engages ONLY after forcing — dropping an index, `enable_seqscan=off`, stubbing a guard, monkeypatching — the run is a **mechanism demo, not proof.** Label it as such; it does **not** count toward GREEN.

2. **Scale that self-engages.** The fixture must be large enough that the planner/runtime picks the production path **on its own.** If a different plan is chosen at fixture size than at production size, the test is vacuous. **State the size at which engagement flips** (binary-search it with EXPLAIN if unknown).

3. **Sweep every silent ceiling.** Enumerate every cap that truncates *without erroring*: `max_scan_tuples`, `scan_mem_multiplier × work_mem`, `LIMIT`/`least(count, N)`, `ef_search`, threshold cutoffs, pagination defaults, `maxResults`, batch sizes. Each is a landmine until tested **at and above** it. A result set that silently shrinks is the most dangerous bug class because nothing fails.

4. **Diff deployed vs template/source.** Compare the actually-deployed object (`pg_get_functiondef`, deployed config, running binary) against its source/template. **Drift is a bug until proven benign** — do not assume cosmetic. (In the incident, plpgsql `set_config` vs sql `SET`-clause drift WAS the fix.)

5. **Classify every claim: proven / observed / assumed.** A claim is **proven** only if exercised on the real path, at real scale, against the live system. Security/isolation claims additionally require BOTH the adversarial case (geometry where a leak would be conspicuous — e.g. interleaved tenants, not "other tenant entirely far away") AND the real auth path (signed JWT, real RLS role — not a `set_config('request.jwt.claims')` bypass). Without both, isolation is **observed at best, not proven** — and the test must say so.

6. **Verify recommendations against the live system before adopting.** Any suggested value or fix — from a subagent, a critic, docs, or your own reasoning — is **unverified** until reproduced live. (The `-1` recommendation was out of range; only a live run caught it.) Record the verification command and its output.

## Failure-Mode Catalogue (pattern-match fast)

| # | Failure mode | Smell | Detection command |
|---|---|---|---|
| 1 | **Sub-scale fixture** | "tiny fixture, all green" | `EXPLAIN (ANALYZE)` at fixture size vs a 50k+ row copy — does the plan node change? |
| 2 | **Forced-plan artifact** | test drops an index / sets `seqscan=off` / stubs a guard to make the path fire | grep the test for `drop index`, `enable_seqscan`, `set_config(... iterative ...)`, mocks; if the path needs forcing, it's a demo |
| 3 | **Silent cap** | result set "looks complete" but never tested past a limit | load `cap+1` matching rows; assert count == `cap+1`, not `cap`. Sweep `max_scan_tuples`, `least(count,N)`, `ef_search` |
| 4 | **Deployed/template drift** | "the migration says X" but the live object differs | `pg_get_functiondef('schema.fn'::regproc)` diff against the `.sql` source |
| 5 | **Observed-not-proven security** | "0 leak" seen once, in geometry where a leak couldn't show | rebuild fixture with tenants interleaved in the ranked output; run via signed JWT + real role; assert exact id-set, 0 cross-tenant |
| 6 | **Vacuous control** | "I broke it and the check still passed / caught it" — but the thing you broke was never there | assert the PRECONDITION before trusting the control: the anchor string must exist, the file must be non-empty, the planted token must actually land. `grep -c` it after planting, and fail loudly at zero |

### 6 in full — verify a control's precondition before trusting the control

A negative control only proves something if the thing you removed **was present to remove**.
Delete a token that was never there and you have planted nothing: the suite passes, and the
pass says nothing at all about whether the check can fail.

This is the same class as a query suite going green because 19 DB-gated files silently
skipped, or a `grep` whose alternation never matched — **a clean result from a check that
never ran looks identical to a clean result from a clean system.**

It bites hardest on *exemptions*. When you write a rule and then exempt yourself from it, the
control proving the exemption is still narrow is the only thing standing between "declared" and
"disabled" — so a vacuous control there is worse than none, because it manufactures confidence.

```bash
# WRONG — proves nothing if the token was absent
sed -i 's/disabled/_removed/' target.ts && run_suite     # suite passes… of what?

# RIGHT — the precondition is asserted first, and a no-op is fatal
grep -q 'disabled' target.ts || { echo "anchor absent — control would be vacuous"; exit 1; }
sed -i 's/disabled/_removed/' target.ts
grep -c '_removed' target.ts        # must be >= 1
run_suite                            # NOW a pass/fail means something
```

**If the anchor is absent, do not substitute a different control silently — say the control
could not be run, and find one whose precondition holds.**

**This file was itself failure mode 4.** It lived only at `~/.claude/skills/`, which is
gitignored and does not travel, so the lesson about verification proving nothing existed on
one machine and nowhere else. Deployed-versus-template drift, biting the document that
catalogues it. Ruling 2026-08-01: **the repo is canonical, the machine copy is a deploy
artifact, one-way repo → machine, never the reverse.** Editing `~/.claude/skills/` in place is
editing files on a production server. `skills-drift-check` fails the build if the two diverge.

*Earned 2026-08-01: a per-file per-rule exemption was reported as "controlled" after an attempt
to remove a `disabled` token from a file that contained none. Nothing was planted; the 22/22
pass was meaningless. The real control — planting an **undeclared** construct in the same file —
failed 2 tests, which is what the exemption's narrowness actually rests on.*

## Claim Classification (put this in the report)

- **proven** — exercised on the real path, at real scale, live. The only label allowed in the load-bearing set at "done".
- **observed** — saw the right result once, but on a forced plan, sub-scale, friendly geometry, or bypassed auth. Must be stated as such.
- **assumed** — reasoned, not run. **Zero `assumed` items allowed in the load-bearing set before declaring done.**

> **SPLIT PENDING (founder, 2026-08-02) — after the per-capability tokens work, not mid-hardening.**
> This file now carries two skills. The test is NOT line count: it is whether each half fires on
> its own moment.
> · **control-design discipline** — needed while BUILDING a check: the first run is the failing
>   one, a fixed set goes stale silently, claim-vs-check.
> · **proof discipline** — needed while CLAIMING DONE: green is not proven, null results need a
>   positive control, shipped is not observed.
> Name each for the moment it serves, because the failure mode is that the less
> obviously-named half never loads when it is the one needed.

## A Check That Knows a Fixed Set Is a Check That Goes Stale Silently

**Any check that enumerates the surface it guards will, at some point, guard less than its name
says — and it will not tell you.** The list is right the day it is written and wrong from the
first addition afterwards. Nothing goes red. The suite stays green while covering less.

This is the same class as enumerating navigation *forms* (four review rounds, four patterns), and
it is not a tuning problem: **a fixed enumeration cannot notice what it does not contain.**

**Where it was found, 2026-08-01/02 — note the trend in consequence:**

| Check | Fixed set | What it stopped covering |
|---|---|---|
| navigation detector | `href=`, `fetch(`, `router.push` spellings | computed `<Link href={expr}>` |
| C12 entry pages | four listed pages | any page added later |
| auth suite pages | four listed pages | any page added later |
| **auth suite API routes** | **one route** | **`/api/command-centre/provider-usage`, live, with no coverage at all** |
| C12 freshness inputs | four source roots | a new top-level source directory |

The fourth row is the one to sit with. That check exists **because** an anonymous-access hole
reached production behind a service-role client — and as written, it would not have noticed the
next one. **A control built to close a hole should be the last place a fixed list survives.**

**The rule.** Derive the set; do not list it. Walk the route tree, the filesystem, the registry —
whatever defines the surface in reality — and let the check grow on its own.

**Two obligations that come with it, because discovery has its own failure mode:**

1. **A positive control that the discovery is non-empty.** A broken walk returns zero items, and
   zero items means every per-item assertion silently does not exist. That is a green run over
   nothing — the same shape as a scan that reads no blobs.
2. **A control that a NEW surface is picked up without editing a list.** Plant a page and a route,
   assert coverage grows, remove them, assert it returns. Without this, "we use discovery now" is
   an assertion about code you changed once. See `C-DISCOVERY` in `scripts/prove-controls.sh` —
   12 → 14 → 12, observed.

**When a fixed list is legitimate:** when it enumerates the *rules* rather than the *surface* —
the tracked-construct regexes, the guard patterns, the gate list. Those are the check's own
definition. The test is whether the world can add a member behind your back. It can add a page; it
cannot add a rule.

## When the Claim Is Wider Than the Check, Decide WHICH One Is Wrong

A review that says *"this covers less than you say it does"* has found a mismatch, not a
verdict. **Two different defects produce that same sentence, and telling them apart is the
skill.** Get it wrong and you either ship an overclaim or grind forever.

- **Mechanism defect** — the check genuinely misses something it should catch. **Fix the check.**
- **Documentation defect** — the check does the right thing; the words around it promise more.
  **Fix the claim.**

The failure mode is treating every mismatch as the first kind. That is how you end up extending
a check to make a *word* come true — the same error as adding the next pattern to a detector,
aimed at prose instead of at a regex.

**Worked example, 2026-08-01/02, navigation coverage (G1).** Four review rounds all reported the
claim being wider than the check. They were not the same finding:

| Round | What was wrong | Right fix |
|---|---|---|
| 1 | no timeouts; stale build passed; query strings dropped | **check** — real misses |
| 2 | only slash-prefixed hrefs matched, so relative links unmeasured | **check** — real miss, fixed by RESOLVING urls rather than adding a pattern |
| 3 | redirect-to-missing passed green; freshness walk too narrow | **check** — real misses |
| 3 | *"G1 is CLOSED"* over a mechanism the reviewer called sound | **claim** — downgraded to *substantially mitigated, with named residue* |

Round 3 carried both kinds at once, which is why it needs reading carefully rather than
actioning in one direction.

**The test for which one you have:** ask what a *complete* version of the check would look like.
If you can describe it and build it, the check is at fault. If completing it would require
something the tool structurally cannot do — running a browser, submitting live POSTs, predicting
unrendered branches — then the check is finished and **the claim is what is wrong.**

**"Substantially mitigated, with named residue" is a better outcome than a false "closed."** A
bounded, declared gap is in a different condition from an undiscovered one; only the second is
dangerous. Honest descriptions are the product a verifier exists to produce — a verifier that
overstates itself has failed at its only job, whatever its exit code says.

**Guard against the abuse.** Downgrading a claim to escape a failing check is moving the
goalposts. The test is whether the new claim is *more honest*, not whether it is *easier to
satisfy*. Legitimate downgrades usually arrive alongside the check getting stronger, not instead
of it.

## The First Run of a New Control Is the FAILING One

**Rule: a new check is not trusted until it has been observed to FAIL — and to fail for the
reason you think.** Write it, aim it at a defect you have planted, and watch it go red. Only
then aim it at the real system. A control whose first observed state is green has been tested
for its ability to agree with you.

**Verify the failure, not just the exit code.** "It failed" is not enough — read the message and
confirm it names the planted defect. Four of the misfires below "failed" or "passed" for a
reason entirely unrelated to what was being tested.

**Controls fail toward green, and the bias is directional, not random.** On 2026-08-01/02, four
control mis-designs in one session, **all four green**:

| # | Control | What went wrong | Read as |
|---|---|---|---|
| 1 | review tree-integrity | planted file at `*.tmp`, covered by `.gitignore` repo-wide | "no mutation" |
| 2 | secrets-scan coverage | planted secret in `.md`, which is in `_SKIP_EXTS` | "no secrets" |
| 3 | build-freshness | exit code measured through `\| head`, so it reported head's 0 | "control passed" |
| 4 | route-exercise | attached to an orphaned server serving the **previous** build | "no broken route" |

Plus a fifth in the tool built to check for exactly this: a history scanner whose input paths all
carried a stray `\r`, so it read **0 blobs** and printed "no secrets found" over 6160 paths.

Five of five landed on green. That is not chance — you write a test expecting it to pass, so
every accident lands on the side you expected. **Assume your control is green because it is
broken until you have seen it red.**

**The one that went the other way, and why it does not soften the rule.** A sixth misfire
reported FAIL against a *working* scanner: the check ran `scanner | grep -q`, and the scanner
exits 1 when it finds a violation — the success case — so under `set -o pipefail` the pipeline
was non-zero even though grep matched. A false RED. It cost ten minutes and was self-correcting,
because a red result gets investigated. **The asymmetry is the point: a false green is never
investigated, because nobody audits good news.** Both are bugs; only one is dangerous.

Three habits that catch all five:
- **Plant the defect where the check must look**, not merely nearby. Check the ignore rules, the
  extension filters and the path prefixes of the thing you are testing *first*.
- **Never measure an exit code through a pipe.** `cmd > file; echo $?`, never `cmd | head`.
- **Assert the scan did work**: blobs read > 0, files scanned > 0, paths exercised > 0. A checker
  that examined nothing must fail, not pass.

## Red Flags — STOP, you are about to ship a false-green

- "The test passes, so it's green." (Passing ≠ proving.)
- "EXPLAIN would show HNSW." (Then run it. Don't predict the planner.)
- "It works the same at scale." (Prove the plan self-engages at scale.)
- "The filter is the default `{}` / count is small — close enough." (Untested cap = landmine.)
- "The migration sets it, so the deployed fn does too." (Diff the live object.)
- "No leak appeared." (In what geometry? Via what auth path?)
- "The subagent/doc says use value V." (Unverified until reproduced live.)
- "I'll mark it done and note the residual." (A residual in the load-bearing set means NOT done.)

## Rationalization Table

| Excuse | Reality |
|---|---|
| "Forcing the index is basically the same as production" | Production never forces it. A plan that requires forcing is a mechanism demo, not proof. |
| "142 rows is enough to show the logic" | At 142 rows the planner picks a *different, complete* path; the bug lives only on the path that engages at scale. |
| "Nothing failed, so the result is complete" | Silent caps shrink results with zero errors. Absence of failure is not presence of completeness. |
| "The deployed object matches the migration" | Verify with `pg_get_functiondef`. Drift hides in the gap between source and live. |
| "Isolation held in the test" | Held against far-apart tenants via a JWT bypass ≠ held against interleaved tenants via signed auth. |
| "The recommended value is obviously right" | Reproduce it live. `-1` was out of range. |

## The Bottom Line

Run it live. Diff the deployed object. Sweep every cap. Make the planner choose the path itself. Then — and only then — classify each claim as **proven**, and write the word "GREEN".
