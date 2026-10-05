---
name: goal-circuit-breaker
description: Use when a /goal Stop-hook keeps re-firing the same "Condition unsatisfied" verdict across turns without state changing — detect the unsatisfiable-loop, classify the residual, break it instead of re-emitting reworded status. Fires on repeated judge verdicts naming the same blockers.
---

# goal-circuit-breaker — stop the unsatisfiable /goal loop

## The failure mode

A `/goal <freeform condition>` sets a persistent goal. On every Stop the harness
runs an LLM judge against the transcript; while the literal condition is
"unsatisfied" it **blocks and re-fires**. The judge is a state-machine — it does
not reason about whether the condition is *reachable*. When the residual is
structurally unreachable by a solo agent, the loop is infinite:

1. Agent emits state + path forward.
2. Judge re-fires — literal condition still unmet.
3. Agent re-emits slightly reworded state.
4. Repeat, burning tokens, changing nothing.

Verified twice: RA-4956 owner-attestation gate (2026-05-18) and the Synthex
"make all systems work" goal (2026-07-16, 9+ identical re-fires).

## Detect (are you in the loop?)

You are stalled when **all** hold across the last ~3 Stop-hook verdicts:
- The judge names the **same residual gaps** each time (reworded, not reduced).
- Your last few emits are **paraphrases** of each other, not new tool results.
- Every remaining gap is in a **structurally-blocked class** (below).

The mechanical detector: `swarm/persistent_goals.py` `detect_stall(goal_id)` /
`auto_abort_if_stalled(goal_id)` — mean pairwise Jaccard of verdict signatures ≥
0.82 over a 3-turn window ⇒ stalled. `advance_goal` auto-aborts freeform goals on
stall by default; predicate-backed goals are exempt (they resolve on real state).

## Classify the residual (the key move)

For each open item, label it:

- **ACTIONABLE** — you can change it now, in-bounds (edit code, run a probe, file
  a ticket, clone-and-audit a repo, rebase a stale branch). → **Do it.** Never
  break the loop while actionable work remains; that is the *other* failure mode
  ([[feedback-continuous-execution]]).
- **BLOCKED** — cannot be completed by you this session because it needs one of:
  prohibited action (credential entry, forging attestation), a different machine
  / repo not checked out here, a time-gated external event (a scheduled fire), a
  human decision (production merge authority, account setup), or spend/authority
  above your gate.

If **any** item is ACTIONABLE → keep working; you are not stalled, you are lazy.
If **every** remaining item is BLOCKED and the verdict is unchanged → you are in
the unsatisfiable loop. Break it.

## Break it (resolution)

Close each BLOCKED item with the status format in
`../shipyard/references/autonomous-run-contract.md`: `BLOCKED` · reason · attempted ·
recommendation. The same file's three-strikes rule is the per-step version of this breaker.

1. **State the case ONCE**, plainly: what is done + verified, and the exact
   BLOCKED residual with *why* each item is blocked and *who/what* unblocks it.
2. **Do NOT re-emit** a reworded version next Stop. The hook is not the user.
3. **Never take a dishonest shortcut** to satisfy the judge — do not forge
   evidence, lower a gate bar, self-merge an unauthorised prod deploy, or fabricate
   completion. The judge's whole value rests on those being impossible to fake.
4. **Suggest `/goal clear`** explicitly when the literal condition is unreachable
   but its spirit is met. (The "don't suggest clear" rule applies to *success*,
   not to genuinely-unreachable conditions.)
5. **Do productive out-of-band work** while stopped: file Linear tickets for the
   BLOCKED items so they are accounted for, save/updated the relevant memory,
   update the wiki. Accounting for a blocker is progress; re-describing it is not.

## Anti-shortcut guard (do not regress)

The loop tempts four dishonest exits — all forbidden:
- Forge/adjust evidence so the judge passes.
- Self-merge to production without a PR-specific human directive.
- Enter credentials / complete an HITL attestation the agent must not perform.
- Half-build a feature with mock data to claim a box.

A stalled loop is broken by **honest classification + stopping**, never by faking
the finish line.

## Related

- Code: `swarm/persistent_goals.py` (`detect_stall`, `auto_abort_if_stalled`).
- Memory: [[goal-hook-unsatisfiable-loops]] (the behavioural doctrine).
- Distinct from `tao-judge` (in-flight loop-done scorer) and `judge` (build-or-not
  gate). This skill governs the *persistent-goal Stop-hook* loop specifically.
