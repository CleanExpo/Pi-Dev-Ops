---
type: engineering-requirements
spec: ./spec.md
spec_sha256: f773deff764e46e7c70abe907c5de2db1223a0b15accb6d7e37277b78243e852
reviewer: bench
review_round: 2
seated: [boris, eng-failure, eng-observability, eng-test, eng-rollback, eng-secrets, eng-authz, eng-contract, eng-release]
contributed: [eng-secrets, eng-release]
reviewed_at: 2026-11-17T02:49:10+00:00
status: PASS
categories:
  data_model:         {state: N/A, reason: "Nothing is persisted: no row or table is created. The only state is three Railway environment variables and a per-process limiter map lost on restart.", by: boris}
  invariants:         {state: DECIDED, ref: "#invariants", by: eng-authz}
  failure_modes:      {state: DECIDED, ref: "#failure-modes", by: eng-failure}
  interface_contract: {state: DECIDED, ref: "#interface-contract", by: eng-contract}
  concurrency:        {state: DECIDED, ref: "#concurrency", by: boris}
  migration:          {state: DECIDED, ref: "#migration", by: boris}
  rollback:           {state: DECIDED, ref: "#rollback", by: eng-rollback}
  observability:      {state: DECIDED, ref: "#observability", by: eng-observability}
  budget:             {state: DECIDED, ref: "#budget", by: boris}
  test_oracle:        {state: DECIDED, ref: "#test-oracle", by: eng-test}
disagreements:
  - "Round 1: every seat that owned a category marked it PRESCRIBED and blocking against the first spec. The lead folded all of them into spec amendment 1. Round 2: the chair re-read the amended text and ruled all ten blocking findings CLOSED, with four non-blocking wording gaps, which were then written into the spec. The other eight seats did not re-read the amendment; their closure rests on the chair's ruling."
  - "eng-secrets asked whether a fixed dummy compare value is safe; resolved in the spec as a random value generated once per process. No seat disagreed with another."
---

# Engineering requirements: RA-8408 two-key fleet secret

Nine seats reviewed the first written spec cold and in parallel. Every finding below was missing
from that spec and is now in the amended spec; each section quotes the sentence that answers it.

Open, not blocking, carried as unknowns in the spec (U2 to U7, U9): what n8n holds; who posts
`/api/webhook/routine-complete`; Railway redeploy and batching behaviour; Railway log retention;
which start config is live; whether Railway Rollback restores variables (reported from Railway's
documentation by eng-release, not read by the lead); whether the new key value appears in any
transcript. The migration-ledger comparison could not run (no database address); this change adds
no migration, and the check is follow-up (e).

## Invariants

Found by eng-authz: nothing warned when the current key silently came from the old fallback
variable, or when the read-only key equalled a write key; wrappers branched on a list of refusal
states; no test proved every route taking the header refuses a blank one.

> The read-only key is refused everywhere else, and a next value equal to it is not honoured.

> Wrappers branch on this, never on a list of refusal states.

Also adopted: start-up warnings 6 and 7, and the route-enumeration test (AC-4) with a planted
extra route as its control.

## Failure modes

Found by eng-failure and eng-release: silence was treated as proof before the swap; a weekly and a
manual-only holder would have been locked out days later with nobody watching.

> Never set the current slot back alone.

> a route family with no log line at all is UNKNOWN, not quiet

## Interface contract

Found by eng-contract: the next value was trimmed and the current value was not, so a padded
current value would make the swap look finished while holders were only getting in through the
next slot.

> Each of the seven route helpers keeps its name, signature, status codes and exact error texts

> All three are stripped the same way.

## Concurrency

Ruled by the chair: the limiter map is unsynchronised and per process; the worst case is one
duplicate log line.

> It is per process; the window restarts on every deploy; a race can only duplicate a line. No lock, no shared store.

## Migration

Found by the chair, eng-secrets and eng-contract: the holder list missed n8n and an unknown poster;
mid-swap the start-up line printed the stop signal; the exposed value stayed as a hidden fallback
after the rotation.

> Removing NEXT first locks out every moved holder.

> Until this step, deleting either newer variable would silently bring the exposed key back.

## Rollback

Found by eng-rollback and eng-release: "revert the PR" is safe only before a holder moves; after
that a revert or a Railway Rollback is the 15/11 outage again.

> From the first move onward: ROLL FORWARD ONLY.

> How to undo: ONE combined change

## Observability

Found by eng-observability: a refused key wrote nothing on the server, so a lockout at the swap was
invisible; the swap gate had no positive control.

> Refusals, always on: WARNING `internal_secret: rejected reason=<missing|mismatch> where=<label>`, at most once per (reason, label) per 600 s.

## Budget

> limiter map bounded at 8 labels × 4 keys

No spend. Up to four digests and three constant-time compares per authenticated request.

## Test oracle

Found by eng-test: five acceptance criteria could pass without proving their claim ("not 401"
passing on a 422; red-first satisfied by an import error; a leak check passing on an empty
capture; a boundary and a rate limit no test pinned).

> must not import the owner module at file level

> a refusal where success is expected

Contributed without owning a category: eng-secrets (step 0 key provenance, pipe-only transfer,
step 6, the corrected founder sentence); eng-release (deploy-and-read-that-deployment's-line rule,
no Railway Rollback, the two GitHub secret names listed separately).
