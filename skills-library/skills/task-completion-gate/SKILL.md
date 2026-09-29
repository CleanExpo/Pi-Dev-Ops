---
name: task-completion-gate
description: "Invoke before reporting a task \"done\", \"complete\", \"fixed\", \"green\", or \"shipped\" — the final gate that blocks a completion claim unless a this-session tool result proves the desired state was reached, tested, and left green. Prevents CASHE (incomplete / untidy / false-result work): stale cache hits, partial summaries, unverified claims. Model: inherits caller tier."
allowed-tools: Bash, Read, Grep, Glob
---

# task-completion-gate — no "done" without green proof

The permanent completion gate for Pi-CEO agents (RA-2141). A task is not done when the
work looks finished; it is done when a **this-session tool result** proves the target
state was reached, tested, and left green. This skill is the last step before any
completion claim leaves an agent.

Founder rule (2026-05-21): *no agent may report "done" or "completed" until the green
confirmation is present.* CASHE = a **C**ache of incomplete / untidy / false-result work
that breaks the autonomous chain. This gate exists to stop CASHE regrowing in emits,
Linear, or the wiki.

## When to invoke
Immediately before emitting any of: "done", "complete", "completed", "fixed", "resolved",
"green", "shipped", "verified", or closing a Linear ticket / posting a done-status comment.
If the draft asserts a finished state, run this gate first.

## The gate — four checks, all must pass

1. **State reached** — the requested end state exists now. Point to the tool result that
   shows it (file contents, PR `state: MERGED`, endpoint 200, row present).
2. **Tested** — the change was exercised, not just written. Point to the test/smoke/CI run
   *from this session* with a pass line (`N passed`, checks `pass`, exit 0). A green run
   from a previous turn is a hypothesis — re-run it.
3. **Green** — zero new failures and no regression. A failing or skipped check blocks the
   claim; report the failure with its output instead of claiming done.
4. **Clean handoff** — no orphaned edits, no stale cache, no half-applied diff. The next
   agent can pick up without rework.

- **Completion criterion:** every check above cites a tool result emitted in the current
  session; if any check has no such evidence, the gate FAILS.

## On FAIL
Do not soften the claim ("mostly done", "should be green") — that is CASHE. Either:
- do the missing work and re-run the gate, or
- report the exact blocker with the failing tool output and what remains.

## CASHE-prevention rules (stop the pattern regrowing)
- **No stale cache hits.** Clear the relevant cache (`.pytest_cache`, build cache,
  `-p no:cacheprovider`) before the confirming run when a prior run could be cached.
- **No unverified claims.** Line numbers, counts, file citations, and env facts must trace
  to a tool result in *this* session — prior audits and memory are hypotheses to re-verify.
- **No partial summaries.** A completion summary states what was verified and how; if a
  part is unverified, name it as unverified rather than folding it into the green claim.
- **"Fixed" needs a positive post-change observation** — an after-state tool result, not
  only the edit that was supposed to fix it.

## Relationship to the other gates
This gate is orthogonal to [verify-test](../verify-test/SKILL.md) (interprets one test run
into a pass/fail verdict) and [production-gate](../production-gate/SKILL.md) (merges after
Phill's approval). Those run *inside* the pipeline; this gate runs at the moment of the
completion claim, for any agent, on any task — including work with no CI.
