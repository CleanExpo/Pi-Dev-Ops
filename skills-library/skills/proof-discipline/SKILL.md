---
name: proof-discipline
description: Use whenever about to mark a test, gate, verification or task as passing / GREEN / complete / fixed / shipped — the moment a CLAIM is made, not when a check is written. Catches vacuous verification, claims asserted but never checked against the live system, silent caps, deployed-vs-source drift, coverage gaps that hide non-functioning code, and green results whose control was aimed at the wrong target. Triggers on "tests pass", "it's green", "verified", "done", "complete", "fixed", "shipped".
---

# Proof Discipline

**This is the CLAIM-TIME half. Its sibling, [`control-design`](../control-design/SKILL.md), is
the BUILD-TIME half — load that one when writing or changing a check, gate, exclusion or
fixture, before its result is ever read.**

Split from a single 480-line file on 2026-08-02, by moment rather than by size.

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

## THE THESIS — a control's health tells you about the control's AIM, not about the world

Every structural limit above is an instance of one statement:

> **A green control reports that the control found nothing where it looked. It says nothing
> about whether it looked at the right thing.**

Health and correctness are different claims, and a control can only ever make the first. The
second requires knowing the aim was right, which no control checks about itself.

**Four instances, all found on 2026-08-02, in unrelated systems:**

1. **The kill switch displayed `state: "OFF"`.** That value came from `fallback()` after the
   upstream call failed. The dashboard reported the swarm as stopped because it could not ask,
   and "OFF" is the reassuring answer. A failure rendered as a reading.
2. **Control 1b hashed the wrong file.** It existed to detect a reviewer widening its own
   permissions, and it watched `~/.codex/config.toml`. The permissions lived in
   `~/.codex/hooks.json`. It reported "unchanged" truthfully, all day, about a file that did
   not hold the capability.
3. **The smoke contract certified the hole.** `kill-switch-status-nosig` asserted
   `expected_status: 200` for an unauthenticated GET, and the route's own comment cited that
   surface as the reason the GET could stay public. The test justified the code and the code
   justified the test. Neither referenced a requirement.
4. **A positive control passed on a wrong target.** Searching for `middleware.ts`, finding
   none, and confirming the glob worked — while Next.js 16 had renamed it `proxy.ts`. The
   instrument was verified; the aim never was. See failure mode 7.

**What follows.** Ask of any green check: *what would this look like if it were pointed at
nothing?* If the answer is "the same", you have measured the instrument, not the world. The
escape is always the same shape — go around the check and ask reality directly. Every one of
these four was broken open by an external observation, never by more careful reading of the
same source.

## THE REPAIR PATH REMOVES THE CONTROL

A control fails honestly. The obvious repair is reasonable. Applying it deletes coverage, and
the suite goes green with **less** protection than before the failure.

This is the nastier sibling of *the test that encodes pre-fix behaviour*. There, the test
argues for reverting the fix, and the argument is visible — you can see the test defending the
bug. Here nothing argues with you: the failure is genuine, the repair is correct-looking, and
the loss is silent.

**The instance (2026-08-04, Pi-Dev-Ops).** The API auth classifier walked `app/api` with a
hardcoded `/api` URL prefix. Moving a route out of that root made it **undiscovered, not
unclassified** — and "every surface is classified" only inspects what was discovered. What
*did* fail was phantom detection: declared entries with no handler on disk. The obvious repair
is to delete the stale declarations. Do that, and the moved routes — the ones about to be
exposed at a public front door — are outside classification entirely, with a green suite.

**Ask, on every failing control, before repairing it:** *does this repair restore the
property, or only silence the report?* If the fix is "delete the assertion / delete the
declaration / narrow the scope", you are removing the control. Repair the aim instead.

**Two corollaries earned in the same change:**
- **A floor cannot detect a relocation.** `SURFACES.length > 10` passed at 28 surfaces while
  the moved ones were invisible; the survivors hold the count up. Replace floors with a
  **relocation canary** — plant an artefact on the surface the claim covers, outside the old
  scope, and require discovery to find it. Prove it both ways: narrow the scope, watch it fail
  by name; restore, watch it pass.
- **Discover by what a thing IS, not where it lives.** A walk root is a fixed list of one, and
  adding a second root makes it a fixed list of two. A fixed list is legitimate only when it
  enumerates *rules*, never *surfaces*.

### Negative controls: use the tool, do not hand-roll it

A mutation that silently fails to apply reads exactly like a control that is working. This
recurred three times before being wired, which is the signal that prose was the wrong
container — **a lesson that keeps recurring does not need restating, it needs a tool.**

    ~/.claude/skills/proof-discipline/mutate-assert.py \
      --file <path> --find <regex> --replace <text> --run "<cmd>" --expect-fail

**Three answers, not two.** Exit 2 means the target never matched and **nothing was run**.
Exit 3 means the mutated program did not RUN - a syntax, name or import error the mutation
itself introduced. Exit 1 means the control stayed green with its subject broken, which is
the real finding. Under `--expect-fail` a crashing mutant makes the command fail, so before
exit 3 existed it printed *PASS - the control fired* over a program that never ran. The tool
re-runs the ORIGINAL when it sees a crash signature, so a command that was already broken is
reported as such rather than credited to the mutation. The file is restored byte-identically
in a `finally`, so it will not renormalise line endings. Do not open-code a
mutate-run-restore loop; that is the exact shape that failed.

### A COUNTING PROBE NEEDS A KNOWN-N FIXTURE, NOT A NON-EMPTY ASSERTION

`mutate-assert.py` cannot catch this class, and that is the point: it proves a probe **found
something**. It cannot prove the probe is **counting the right thing**. The target matches, the
output is non-empty, the control fires — and the number is still wrong.

Every instance returned a plausible, specific number that nobody had a known-correct value to
compare against:

| probe | reported | actual | mechanism |
|---|---|---|---|
| `grep -c $'\r' f` | 120 / 53 / 83 | 0 | `$'\r'` did not expand → `grep -c ''` matches every line, so the counts were file *lengths* |
| `find -maxdepth 4` | 146 | 1,021 | depth cap silently truncated the walk |
| `MANIFEST*` glob | 83 | 19 | matched a JSON schema that was not the skills manifest |

**The rule: before believing a count, plant a fixture whose N you chose, and assert the probe
returns exactly that N.** Three CRLF lines → expect 3. Nine files at depth 6 → expect 9. If the
probe cannot see the planted fixture, every number it has ever produced is uninterpreted.

A count is a measurement. `> 0` is not a calibration.

## A DEFAULT BRANCH IS THE UNTESTED BRANCH

When a parameter has a fallback, tests supply the parameter. The default path is the one
nobody exercises — and it is where the wrong destination, the loop, and the unvalidated input
all sit.

**The instance.** A login page reads `?redirect=`, falling back to a hardcoded path. Three
defects lived on the no-param branch at once: the fallback pointed outside the zone (a
post-login 404 on success), the login path was inside its own protected prefix (redirect
loop), and the param was passed to `router.push` unvalidated (an open redirect, which on a
public login page is a phishing primitive). A redirect round-trip test always supplies the
param, so it passes over all three.

Three defects behind one blind spot is not coincidence — it is a test-design defect. **Probe
the default branch explicitly**, by omitting the parameter, not by supplying a typical one.

## AN UNCLASSIFIED THING IS NOT MERELY UNGUARDED — SUSPECT IT IS ALSO BROKEN

The most useful correlation of 2026-08-02, and it was visible only once two separate
investigations were laid side by side.

- The routes with **no auth classification** — outside both proxy prefix lists, absent from
  `api-auth-classification.json` — were `kill-switch`, `zte`, `swarm-status`,
  `curator-proposals`.
- The routes sending the **wrong credential type upstream**, and therefore never working at
  all, were `kill-switch`, `zte`, `swarm-status`, `curator-proposals`.

The same four. Not a coincidence, and not two bugs: **routes nobody classified are routes
nobody thought about, and unexamined code is broken at whatever rate code is born broken.** The
missing guard and the missing wiring have one cause, which is that no one ever looked.

**So a classification file is not a security artefact. It is a map of what has been thought
about.** Read it that way and it says more than it was built to say:

- An entry means someone reasoned about this surface. The reasoning may be wrong, but it exists.
- **A gap means nobody has.** Treat the gap as evidence of *general* neglect, not merely of a
  missing guard — check whether the thing works at all, not just whether it is protected.

The practical rule: when a coverage map shows a hole, do not only close the hole. **Go and test
whether the uncovered thing functions.** In this instance every unclassified route was also
non-functional, and the non-functionality had been invisible for 92 days because the routes
returned quiet 200s. Finding the gap was cheap; only looking through it found the real defect.

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
