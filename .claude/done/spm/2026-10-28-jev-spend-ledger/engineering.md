---
type: engineering-requirements
spec: ./spec.md
spec_sha256: 76dba563740114324cc258f54c90b774d3fd4e4de49cc8a1196d9d1ca0495a23
reviewer: bench
seated: [boris, eng-failure, eng-observability, eng-test, eng-concurrency, eng-cost]
reviewed_at: 2026-10-28T08:19:00+10:00
status: PASS
categories:
  data_model:         {state: DECIDED, ref: "#data-model", by: boris, blocking: false}
  invariants:         {state: DECIDED, ref: "#invariants", by: boris}
  failure_modes:      {state: DECIDED, ref: "#failure-modes", by: eng-failure}
  interface_contract: {state: DECIDED, ref: "#interface-contract", by: boris}
  concurrency:        {state: DECIDED, ref: "#concurrency", by: eng-concurrency, blocking: false}
  migration:          {state: DECIDED, ref: "#migration", by: boris, blocking: false}
  rollback:           {state: DECIDED, ref: "#rollback", by: boris}
  observability:      {state: DECIDED, ref: "#observability", by: eng-observability, blocking: false}
  budget:             {state: DECIDED, ref: "#budget", by: eng-cost}
  test_oracle:        {state: DECIDED, ref: "#test-oracle", by: eng-test, blocking: false}
disagreements:
  - "Mirror write order: eng-concurrency said canonical first (orphan canonical row overcounts, safe); boris said the tool's own ledger first, then canonical, so a call refused by the tool's own cap never leaves a phantom canonical row. Chair ruled boris's order, with eng-concurrency's constraint kept: the own-ledger transaction commits before the canonical reserve opens, so no lock is ever held across the two files."
  - "eng-observability asked for UNKNOWN after 26h with no reserve. Chair rejected: Jev is idle for days at a time by design (router needs founder egress approval), so the alert would sit on UNKNOWN permanently, which is the defect being fixed. Instead the watcher prints the newest record time and the path it read in every summary, and alerts separately on refusals and settle failures."
  - "eng-observability asked that JEV_SPEND_LEDGER be an error in non-test processes unless it equals the default. Chair rejected: tests and the seam check need it; the watcher reads the same env default and prints the path it read, which makes a split visible."
---

Round 1 ran against spec rev 1. Every blocking finding is answered in spec rev 2, which is the revision this file is bound to.

## Data model
> `day` and `created_at` are computed inside `reserve` from an injectable UTC clock; callers never pass a day.

Spec rev 2 §5: `day` and `created_at` are computed inside `reserve` from an injectable clock in UTC (`datetime.fromtimestamp(stamp, UTC)`); callers never pass a day. Statuses `attempted`, `answered`, `error`, `refused` (not sent, `actual_usd=0`). Index on `day`. Legacy tables gain nullable `spend_id`. Found by boris: an unstated timezone would file 10 of every 24 Brisbane hours under the wrong UTC day and show a real-looking $0.

## Invariants
> I2 No request leaves without a canonical row that existed before it was sent.

Spec §9 I1-I5: canonical sum is at least true spend; no request leaves without a prior canonical row; a mirrored call counts once; `finish` never raises after a send; `day` is the UTC date of `created_at`. I2 and I4 each have mutants in C4; I3 is C6; I5 has the local-day mutant.

## Failure modes
> `finish(id, status, actual_usd)`: never raises.

Spec §5 and §4: reserve failure refuses the call at all four sites (pinned status strings, transport call count 0). `finish` never raises: it logs, appends a `settle_failed` line, returns False, and the row keeps its reserve (found by eng-failure and eng-concurrency: raising would discard a paid reply and invite a second charge). Bad ledger paths (empty, relative, directory) are rejected. Triage `run()` stops at the first refusal. Own-cap refusal writes no canonical row; canonical failure marks the legacy row `refused`.

## Interface contract
> New error strings `spend_unrecorded`, `spend_cap_reached` from `client.send`

Spec §11: `client.send` gains `spend_unrecorded` and `spend_cap_reached`; `reserve_call` may raise `SpendUnrecorded` (mapped to `SPEND_LEDGER_UNAVAILABLE` by `run_line`, and to a logged lexical fallback by the skill router). The endpoint URL and `http_post` move into `client.py`, with aliases kept in `__main__.py`.

## Concurrency
> one connection per call (`contextlib.closing`), `timeout=10`, `BEGIN IMMEDIATE`,

Spec §5: one connection per call, closed (`contextlib.closing`), `timeout=10`, `BEGIN IMMEDIATE` on insert, rollback journal (no WAL, because the watcher opens read-only), no connection shared across threads, no lock held across the two ledger files. C1 includes a 16-process concurrent reserve test (eng-concurrency).

## Migration
> C6 the real watcher, run by path in dry mode against a tmp canonical ledger plus a mirrored legacy ledger written by this

The watcher is in another repository, so this contract binds it by C6: the real watcher script, from the skills-library worktree, run in dry mode against a ledger written by this code, must report the exact sum with mirrored calls counted once (boris: otherwise both halves go green and nothing changes). Watcher legacy rule: if a legacy table has a `spend_id` column, count only rows where it is NULL; if it has none, count every row, so an un-migrated ledger never makes the day UNKNOWN.

## Rollback
> Revert this PR and the watcher PR together. The ledger file is additive and may be deleted; the watcher then reports UNKNOWN.

Spec §16: revert this PR and the watcher PR as a pair. The ledger file is additive and can be deleted; the watcher then reports UNKNOWN, not $0.

## Observability
> `SpendUnrecorded`, after appending one JSON line (caller, path, exception class, errno, UTC time; never request text)

Refusals and settle failures write a JSON line to `spend-refusals.jsonl` beside the ledger plus one `logging.error` (no request text). The skill-router fallback logs at warning. The watcher companion reports, per day, status counts, `attempted` rows older than 10 minutes, the newest `created_at`, the path it read, and any refusal line from the last 24h as its own alert (eng-observability, eng-failure).

## Budget
> None blocking. Until Phill sets `JEV_DAILY_CAP_USD`, spend is unbounded and alert-only: the $20/day line is an alert, not a stop.

Optional machine-wide cap via `JEV_DAILY_CAP_USD`, checked inside the insert transaction; unset keeps the founder's uncapped decision. Spec §19 states plainly that until a cap is set the $20/day line is an alert, not a stop (eng-cost). Retry layering checked: only `client.send` retries (429, `MAX_RETRIES + 1`), one row per attempt. Pricing: input only at $0.042/M, output free (cited in spec §2).

## Test oracle
> C4 every planted mutant fails C1 with an assertion: reserve removed at each of 4 sites; reserve moved after send (client);

Spec §15 C1: each fake transport asserts from inside the call that an `attempted` row already exists; one row per attempt on a 429 retry; finish-failure keeps the reply with exactly one post; mirror order both ways; cap; 16-process concurrency; the watcher's exact SQL over a ledger written through `client.send`; a 15:00 UTC frozen clock under TZ=Australia/Brisbane. Conftest isolation plus a session guard that fails if the real default ledger changes. C3 census is committed as a test with a planted fixture and was red at base. C4 lists 13 mutants, each required to fail by assertion, not crash (eng-test).
