# Spec: one canonical Jev spend ledger per machine

Status: rev 2, 28/10/2026 (Mini, spm). Lane full, tier T1, review Tier 2 (internal tooling).
Rev 2 folds in bench round 1 (boris, eng-failure, eng-observability, eng-test, eng-concurrency, eng-cost); see engineering.md.
Repo: CleanExpo/Pi-Dev-Ops, base origin/main 41cf4aee. Branch worktree-jev-spend-ledger.
Companion: the Guardian watcher (`~/.claude/skills/guardian/scripts/jev-cap-watcher.py`, skills-library repo). Its change is
built under its own skills-library contract, but this contract cannot pass without it: C6 runs the real watcher on a ledger
this code wrote.

## 1. Outcome
Every TypeSafe Jev request this repository's code sends is recorded, before it is sent, in one ledger with a fixed absolute
location on the machine. The Guardian watcher reads that ledger and reports a real daily number (with the newest record time
and the path it read) or an honest UNKNOWN.

## 2. Context and evidence (Grounded 28/10/2026)
- Board alert W-TYPESAFE-CAP-UNKNOWN names ~/relint/pdo/.harness/jev-shadow-ledger.sqlite and jev-spend.json as missing (ops/jobs.json).
- Watcher hardcodes `REPO = ~/relint/pdo` (jev-cap-watcher.py:15), a stale checkout (board job M-PDO-LOCAL-STALE); its query is
  `SELECT COALESCE(actual_usd, reserved_usd) FROM calls WHERE day=?` with UTC `day`.
- `jev_platform/client.py:166` Budget is in-memory; `send()` (line 219) is the only transport path for ask/scout/agent/engine/cli_scale.
- `jev_platform/__main__.py:21-24` defines the endpoint URL and `http_post`, used only through `client.send`.
- `evals/jev_constitution/harness.py:129` `ask_jev` posts with no ledger.
- `scripts/jev_triage.py:147` records after the call, and nothing when the transport raises.
- `scripts/mission_control_jev_shadow.py:174-200` reserve_call/finish_call record before send into a caller-chosen ledger;
  `app/server/skill_routing.py:29` defaults that to relative `.harness/skill-router-ledger.sqlite`.
- TypeSafe openapi.json has only `/v1/models` and `/v1/systemone`: no usage endpoint. Price $0.042 per million input tokens,
  output free (`scripts/jev_triage.py:44`, docs.typesafe.ai/models as cited there, 2026-09-28).
- Census of endpoint files at base 41cf4aee: 5 files, 3 unrecorded (harness.py, jev_platform/__main__.py, jev_triage.py);
  output saved, exit 1 (red before the build).
- Done selftest 28/10/2026: 8 passed.

## 3. Why now
Phill (28/10/2026): "go, fix spend tracking then review triage". More Jev use is only safe when every dollar is counted.
Zero incremental cost: no live Jev call in this change or its tests.

## 4. Who it serves
Phill, who owns spend; the Guardian watcher that alerts at 80% and 100% of $20/day.
Hard-day card: the ledger is locked, deleted or the disk is full mid calibration run. Impact: calls must not go out unrecorded.
Behaviour: reserve fails, the call is not sent, a refusal line goes to the sidecar file, and the watcher raises a refusal alert.
A settle failure after a paid reply never loses the reply and never retries.

## 5. Scope
In:
- `jev_platform/spend.py`:
  - Path: env `JEV_SPEND_LEDGER` if set, else `~/.local/state/jev/spend.sqlite`; resolved on every call, never at import.
    Empty, relative, or a directory path is rejected (`SpendUnrecorded`), never resolved against the cwd.
  - Table `calls(id, day, caller, reserved_usd, actual_usd, input_tokens, status, created_at)`, plus index on `day`.
    `day` and `created_at` are computed inside `reserve` from an injectable UTC clock; callers never pass a day.
  - `reserve(caller, reserved_usd) -> id`: one connection per call (`contextlib.closing`), `timeout=10`, `BEGIN IMMEDIATE`,
    default rollback journal (no WAL; the watcher opens read-only). Optional machine-wide daily cap: env `JEV_DAILY_CAP_USD`;
    unset = uncapped (founder decision 2026-09-28 unchanged). Set = inside the same transaction, if
    `SUM(COALESCE(actual_usd, reserved_usd)) + reserved_usd > cap` raise `SpendCapReached`. Any write failure raises
    `SpendUnrecorded`, after appending one JSON line (caller, path, exception class, errno, UTC time; never request text)
    to `spend-refusals.jsonl` beside the ledger (best effort) and one `logging.error`.
  - `finish(id, status, actual_usd)`: never raises. On failure it logs at error with the row id, appends a `settle_failed`
    refusal line, and returns False; the row keeps its reserve (overcount, the safe direction).
  - Statuses: `attempted`, `answered`, `error` (sent, no valid usage), `refused` (not sent, `actual_usd=0`).
- Record at every choke point; reserve strictly before the request leaves; settle after:
  1. `client.send`: one row per attempt, retries included (caller `jev_platform`, reserve `RESERVE_USD`).
     `SpendUnrecorded` -> `{"error": "spend_unrecorded"}`; `SpendCapReached` -> `{"error": "spend_cap_reached"}`; no post.
     The endpoint URL and `http_post` move from `__main__.py` into `client.py` (`__main__` keeps the names as aliases).
  2. `harness.ask_jev` (caller `evals.jev_constitution`, reserve `client.RESERVE_USD`): refusal returns status 0 and no post.
  3. `jev_triage.evaluate` (caller `jev_triage`, reserve = its pre-call estimate): refusal -> status `SPEND_UNRECORDED` or
     `SPEND_CAP`, no transport call; a transport exception finishes the row `error` (keeps the reserve); `run()` stops at the
     first refusal and reports where it stopped.
  4. `mission_control_jev_shadow.reserve_call/finish_call` (caller = `skill_router` when the ledger file is named
     `skill-router-ledger.sqlite`, else `mission_control_jev_shadow`). Order: the tool's own cap check and insert commit
     first; then the canonical reserve (no lock held across the two files). Own cap refuses -> no canonical row. Canonical
     reserve fails -> the legacy row is finished `refused` with `actual_usd=0` and `reserve_call` raises `SpendUnrecorded`.
     The legacy table gains a nullable `spend_id` column (idempotent `ALTER TABLE`) holding the canonical id; `finish_call`
     settles both rows. `run_line` maps the raise to reason `SPEND_LEDGER_UNAVAILABLE`; the skill router logs a warning and
     falls back to lexical routing.
- `tests/conftest.py`: autouse fixture sets `JEV_SPEND_LEDGER` to a per-test tmp file. A session guard fails the run if the
  real default ledger file was created or changed during the session.
- Committed census test `tests/test_jev_spend_census.py`: every non-test module whose text matches `typesafe\.ai`
  (case-insensitive) calls `spend.reserve(`, `reserve_call(` or `client.send(`; a planted fixture file without one is flagged.
Out:
- No cap is set; no per-tool cap changes.
- Gemini spend in `jev_platform/agent.py` (other vendor): follow-up ticket.
- Other machines report only their own ledger; fleet view is a follow-up.
- Reaping old `attempted` rows: DEFERRED until a cap is set (they only overcount today).

## 6. Search before build
`git grep -nE 'api\.typesafe\.ai|Budget\(|ledger|LEDGER|reserve_call'` on origin/main; reused the shadow ledger schema and
reserve-before-send pattern. `skills/index.md` grep "spend|ledger": no shared ledger.

## 7. Options
- A (chosen): canonical ledger plus mirror; per-tool caps unchanged; optional machine-wide cap.
- B: tools use the canonical ledger as their own. Rejected: the router's $1/day cap would count calibration spend.
- C: vendor usage API. None exists.

## 8. Judge
Independent reads: the bench (engineering.md) and one Codex round. Rollback = revert this PR and the watcher PR together.

## 9. Behaviour invariants
- I1 For any UTC day the canonical sum of `COALESCE(actual_usd, reserved_usd)` is at least true spend.
- I2 No request leaves without a canonical row that existed before it was sent.
- I3 A mirrored call counts once in the watcher total.
- I4 `finish` never raises to a caller after a send; the reply is returned and not retried.
- I5 `day` equals the UTC date of `created_at`.
Settle: `actual_usd = input_tokens * 0.042e-6` only when the reply reports a valid token count; otherwise the reserve stands.

## 10. Data
New per-machine file outside any repo, parent dir created with mode 0700. Legacy ledgers gain `spend_id` on first use.

## 11. Interfaces
New error strings `spend_unrecorded`, `spend_cap_reached` from `client.send`; callers of `send`/`ask` checked for exhaustive
matching in review. `reserve_call` keeps `int | None`; it may now raise `SpendUnrecorded`. New env `JEV_SPEND_LEDGER`;
`JEV_DAILY_CAP_USD` now also binds machine-wide when set.

## 12. Security and privacy
Ledger and sidecar hold amounts, caller names, error classes and times only. No request text, no keys.

## 13-14. Verification and sandbox
Fake transports only; `JEV_SPEND_LEDGER` in tmp; mutants run on an export of HEAD in /tmp.

## 15. Acceptance criteria (the Done contract)
- C1 `tests/test_jev_spend_ledger.py` passes, covering: default path absolute and resolved per call; bad paths rejected;
  UTC day with a frozen clock at 15:00 UTC; each choke point asserts from inside the fake transport that an `attempted` row
  already exists; one row per attempt with a 429 retry; settle and error rows; reserve failure => transport call count 0 at
  all four sites with the pinned status string; finish failure after a good reply => reply returned, one post, no retry;
  mirror order (own cap refusal writes no canonical row; canonical failure leaves the legacy row `refused`); cap set to two
  reserves => third call not sent; 16-process concurrent reserve => 16 distinct rows, no lock error; the watcher's exact SQL
  over a ledger written through `client.send`; refusal sidecar line written.
- C2 existing Jev tests pass: `tests/test_jev*.py tests/test_mission_control_jev_shadow.py tests/test_skill_rout*.py
  tests/test_secrets_check_placeholder.py` and `tests/test_jev_constitution*.py` where present.
- C3 `tests/test_jev_spend_census.py` passes at HEAD (it failed at base: saved run).
- C4 every planted mutant fails C1 with an assertion: reserve removed at each of 4 sites; reserve moved after send (client);
  reserve outside the retry loop; settle writes reserve into actual; local date instead of UTC; `spend.reserve` swallows its
  error; path resolved at import; finish raises through; mirror order swapped; cap sum check removed.
- C5 `ruff check` on changed Python files exits 0.
- C6 the real watcher, run by path in dry mode against a tmp canonical ledger plus a mirrored legacy ledger written by this
  code, reports the exact sum with each mirrored call counted once.
- C7 the engineering gate passes on this spec.

## 16. Rollback
Revert this PR and the watcher PR together. The ledger file is additive and may be deleted; the watcher then reports UNKNOWN.

## 17. Crew and loadout
Lead: Opus main thread. Bench (Sonnet): boris, eng-failure, eng-observability, eng-test, eng-concurrency, eng-cost.
Review: Codex, one Tier 2 round. Skills: spm, done-harness, engineering-requirements, pr-release-gate, unslop.

## 18. Handoff seed
Worktree ~/Pi-Dev-Ops/.claude/worktrees/jev-spend-ledger. Then the watcher (skills-library), then Jev review triage.

## 19. Open decisions
None blocking. Until Phill sets `JEV_DAILY_CAP_USD`, spend is unbounded and alert-only: the $20/day line is an alert, not a stop.
