# Prove mode — a change ships only after it beats the current version

Adapted from Hamish Davison's `prove-it-better` (MIT, github.com/IncomeStreamSurfer/prove-it-better,
commit ccb5445; licence in `../LICENSE-prove-it-better`). Estate changes: the judge defaults to a
non-Anthropic model through OpenRouter, shipping goes through `pr-release-gate`, and the report
lands on the Linear issue.

## Contents
- [The rule](#the-rule)
- [Phase 0 — Access](#phase-0--access)
- [Phase 1 — Research](#phase-1--research)
- [Phase 2 — Plan](#phase-2--plan)
- [Phase 3 — Build the challenger behind a switch](#phase-3--build-the-challenger-behind-a-switch)
- [Phase 4 — Prove it](#phase-4--prove-it)
- [Phase 5 — Iterate on defects](#phase-5--iterate-on-defects)
- [Phase 6 — Ship reversibly](#phase-6--ship-reversibly)
- [Phase 7 — Verify live](#phase-7--verify-live)
- [Phase 8 — Report](#phase-8--report)
- [Verdict rules](#verdict-rules)
- [Common mistakes](#common-mistakes)

## The rule

The current version is the opponent. A change ships only after it beats the current version on
real cases, judged blind, with hard checks. It ships in a way you can undo, and then it is
confirmed live. Work through the phases in order; each ends on a required output, and the next
phase starts only when that output exists.

## Phase 0 — Access

Before reading code or proposing anything, check: `git status`; the stack and its scripts; the
environments (local / staging / production); which CLIs are installed and logged in (`gh`,
`vercel`, `supabase`, `railway`); which secrets exist, **names only, never values**, starting with
`~/.hermes/.env`; which connectors and MCP servers are authorised (analytics, payments, email,
search console, Linear).

Then list what the job needs and is missing. Usually that is read access to real usage data, a
judge key from a vendor other than the contestants (OpenRouter is the default), a safe place to
run (dev or staging), and the guardrails: no production writes, sends, spend or merges by the
agent; Phill approves shipping.

**Done when:** an access table exists (item · have / missing · what it is for), and anything
missing is asked for in one message.

## Phase 1 — Research

- The thing's job in one sentence; who uses it and how much, in real numbers from the data.
- What people complain about, what failed before, what was already tried and with what result.
- Read the current implementation end to end.
- Collect **10–30 real cases** from production, customers or history. Synthetic cases only when
  real ones do not exist, labelled synthetic in every report and replaced as soon as possible.
- Define "better" as 3–5 criteria tied to the job, not to style
  ([`prove-judging.md`](prove-judging.md)), and list every **hard check** that needs no opinion:
  links load, facts match the source, numbers add up, cost per run, latency, test suite, real
  conversion data.
- Measure the current version on the hard checks.

**Done when:** a research brief (job · usage · known failures · cases · criteria · hard checks ·
baseline numbers) is posted on the Linear issue before anything is built.

## Phase 2 — Plan

Split the work into units that can win or lose independently (one feature, one page, one cost
line) and fill the tracker in [`prove-templates.md`](prove-templates.md). Write the ship gate
before any result exists: the challenger wins on consistent verdicts, no hard check gets worse,
and its cost is acceptable.

**Done when:** the tracker and the ship gate are written.

## Phase 3 — Build the challenger behind a switch

Leave the current version intact. Make the challenger selectable per unit (flag, env var or
config) with a fallback to the current version on error, so both run on the same input.

**Done when:** both versions run on one case from the set.

## Phase 4 — Prove it

1. Run current and challenger on the **same** cases.
2. Judge pairwise and blind with `scripts/prove_judge.py`: outputs are A and B, never old/new;
   every pair is judged twice with the order swapped; a win counts only when both orders agree.
3. The judge is never the author and never the contestants' vendor. Default:
   `--provider openrouter` with a free model. If every available judge shares a vendor with a
   contestant, decide on hard checks only.
4. Run the hard checks (`scripts/prove_checks.py`) and pass each result to the judge as the
   case's `current_check` / `challenger_check`.
5. Where the real outcome is human behaviour (opens, clicks, sign-ups, revenue), the judge is a
   pre-screen; a live A/B test or the live metric decides.
6. Where every criterion is a hard number (cost, latency, error rate, pass rate), the hard checks
   are the verdict and no judge runs.
7. Tally with `scripts/prove_scoreboard.py`.

**Done when:** the scoreboard and the hard-check table exist for every unit.

## Phase 5 — Iterate on defects

Read the judge's reasons for every loss and tie, fix those specific defects, rerun on the same
cases, then confirm on a **fresh** sample before calling it a win. When stuck, change one thing
at a time. After 3–5 rounds with no consistent win, keep the current version and record why;
that is a result. A full sweep that moves nothing goes to `goal-circuit-breaker`.

**Done when:** each unit is a confirmed win or a recorded keep-current.

## Phase 6 — Ship reversibly

Code changes ship through `pr-release-gate` (independent reviewer, CI mirror, receipt) and wait
for their merge lane; the agent never merges. Ship behind the per-unit switch with the fallback
in place, and never during another risky operation (a send, a migration, an incident).

**Done when:** the PR is open with a receipt, or the change is live behind its switch with
Phill's go recorded.

## Phase 7 — Verify live

Confirm the new version is what is actually running (deployment id, build id, function
signature), watch logs for the new path and for fallbacks, run one real case in production, and
schedule the live-metric comparison for when the data can exist (a scheduled task, not a memory).

**Done when:** the live check is recorded and the follow-up comparison is scheduled.

## Phase 8 — Report

Fill the report in [`prove-templates.md`](prove-templates.md) and post it on the Linear issue:
per-unit scoreboard (W–L–T), hard checks before and after, what did not ship and why, how to roll
back. Any announcement uses measured claims only.

## Verdict rules

| Result | Decision |
|---|---|
| Consistent wins ≥ 2× losses, no hard check worse | Ship, after a fresh-sample confirm |
| Ties on at least half the cases, or wins ≈ losses | Iterate (sharpen the criteria), or keep current |
| Any hard check worse | Do not ship until fixed |
| Fewer than ~8 cases | Not enough evidence; get more cases |

## Common mistakes

| Mistake | Instead |
|---|---|
| Improving from a generic best-practice list | Prove each change against the current version |
| Judging your own work | Independent judge from another vendor, blind, both orders |
| Invented test inputs when real ones exist | Real cases from production or history |
| Averaged 1–10 scores | Pairwise verdicts plus hard checks |
| Shipping the first winning number | Confirm on a fresh sample |
| No way back | Per-unit switch and automatic fallback |
| Stopping at "deployed" | Verify live, then compare the live metric |
| Starting before access is sorted | Phase 0 first; ask for everything in one message |
