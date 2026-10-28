# SPM Spec — every Jev spend call carries a unique call id (RA-8116 follow-up)

## 1. Task being planned

Give every Jev spend call a unique, never-reused call id, written into the machine spend ledger and copied into the
two legacy ledgers that mirror it, so the Guardian `jev-cap-watcher` matches a mirrored row to its machine row by that
id. This closes the parked P1 on skills-library `fix/RA-8116-jev-watcher-canonical` (round 4 on 6f067bfe).

Founder ask (28/10/2026): "merged, keep going with the watcher". Standing Jev authority; $20/day cap unchanged.

## 2. Current project context

- Repo: CleanExpo/Pi-Dev-Ops, worktree `.claude/worktrees/jev-spend-ledger`, branch `fix/RA-8116-spend-call-id`
  from origin/main c195d3e0 (PR #955 merged). Clean tree (donectl status: dirty_count 0).
- Second repo: CleanExpo/skills-library, worktree `/Users/phill-mac/.claude-worktrees/jev-watcher-canonical`,
  branch `fix/RA-8116-jev-watcher-canonical`, head 6f067bfe, base b1c328b1, not pushed. Main has since merged
  PR #142 (Mission Control ledger added to the watcher's default `LEDGERS`), so the branch must rebase.
- Files inspected (origin/main): `jev_platform/spend.py` (SCHEMA, `_connect`, `reserve`, `finish`),
  `scripts/jev_shadow_support.py` (`_caller`, `_ensure_spend_id`), `scripts/mission_control_jev_shadow.py`
  (`reserve_call` lines ~160-190, `finish_call`), `jev_platform/client.py:258`, `evals/jev_constitution/harness.py:137`;
  watcher `skills/guardian/scripts/jev-cap-watcher.py` `spent_today()` on 6f067bfe.
- Known behaviour: `spend.reserve()` returns the integer row id. The shadow/skill-router path (one function,
  `mission_control_jev_shadow.reserve_call`, ledger chosen by `_caller`) stores that integer in its own
  `calls.spend_id`. The watcher skips a legacy row when today's machine ledger has the same id AND the same amount.
- North Star: `docs/governance/NEXUS-NORTH-STAR.md` revision not read (the Done gate blocked the read-only git
  command before a contract existed). Fit: UNVERIFIED. Promise served: the founder's $20/day Jev cap is enforced on
  true spend (truthful delivery: an alarm that cannot be silenced by a counting bug).
- Unknowns: how and when `~/relint/pdo` on the Mini is updated after a merge (the watcher's default REPO path).

## 3. Problem statement

- User: Phill, via the Guardian cap alert (Telegram + board row) at 50/80/100% of $20/day.
- Pain: an integer row id is reused after the machine ledger is reset (file deleted or moved). A new machine row
  id=1 $12 and an older mirrored legacy row spend_id=1 $12 look like one call; the watcher reports $12 against a
  true $24, and no cap alert fires.
- Current workaround: none. The watcher change is parked; the installed watcher still reads `~/relint/pdo` ledgers
  only (W-TYPESAFE-CAP-UNKNOWN open).
- Business impact: a cap that can under-report is not a cap.
- Technical impact: id + amount is not a call identity. Four review rounds patched the matching rule; the fix
  belongs in the data, not the rule.
- Why now: #955 (the machine ledger) is merged, which was the stated precondition.

## 4. Desired outcome

A mirrored legacy row is skipped only when today's machine ledger holds a row with the SAME unique call id. Every
other legacy row counts. A ledger reset can never make two different calls look like one.

Hard-day case: the machine ledger is unreadable, reset mid-day, or still old-schema while legacy rows already carry
ids. Each case must over-count (alert early) or report UNKNOWN, never a quiet under-count. A reset loses the
spend of calls nothing mirrors (client.send, the eval harness, triage); no ledger can restore it, so the watcher
reports the day UNKNOWN with a lower bound. Signs of a reset (engineering bench, boris and eng-test): a mirrored
call id with no machine row on any day, fewer machine rows today than the last run saw, or a newer oldest machine
row. Residual: a reset AND a refill to the same row count between two watcher runs, with no mirrored call that
day and an unchanged oldest row, is not detectable; recorded in engineering.md.

This change makes the alert truthful. It does not make the cap survive a reset: `JEV_DAILY_CAP_USD`, where set,
sums only the current machine-ledger file, so a reset re-opens the day's allowance (eng-cost; follow-up ticket).

Decision card:
- Impact: the cap alert becomes trustworthy across resets.
- Evidence: round-4 Codex repro (canonical id=1 $12, legacy spend_id=1 $12 -> 12 reported, true 24).
- Unknowns: double counting of mirrored rows written by a writer checkout still on old code. It lasts until every
  writer checkout on the Mini is updated, not one day (eng-failure, boris), so section 17 makes that a precondition
  of installing the watcher.
- Options: (a) keep patching the id+amount rule — rejected after 4 rounds; (b) unique id in the data — chosen.
- Dissent: a uuid column is a schema change on a live local ledger; mitigated by an in-place `ALTER TABLE ADD COLUMN`
  that never rewrites or drops rows.
- Owner: Mini lead (Pi-Dev-Ops Jev lane). Authority: Phill merges both PRs. Next check: watcher run on the Mini
  after both installs.

## 5. Scope

### In scope
- `jev_platform/spend.py`: `calls.call_id TEXT` (uuid4 hex) with a unique index; existing ledgers gain the column
  in place; new `reserve_call(caller, usd) -> tuple[int, str]`; `reserve()` keeps its `-> int` contract.
- `scripts/jev_shadow_support.py` / `scripts/mission_control_jev_shadow.py`: legacy ledgers gain
  `spend_call_id TEXT`; `reserve_call` stores the machine row's call id there alongside `spend_id`.
- skills-library watcher: rebase onto main; match on call id; count every legacy row without a matching id.
- Tests in both repos, mutants, and the real-watcher seam check.

### Out of scope
- Changing the cap value, alert thresholds, Telegram text, or the 10am Brisbane reset.
- Back-filling ids into rows written before this change.
- Installing on the Mini (`install_guardian.py`, `~/relint/pdo` update) — after Phill merges.

### Explicit non-goals
- `finish()` keeps its positional signature; `call_id` is a new keyword. (Superseded by the bench: client.py, the
  eval harness and triage now call `reserve_call` and settle by call id, so a reset mid-call cannot overwrite a
  different call's amount.)
- No Supabase or remote schema.
- Not in this change, ticketed: the cap surviving a reset; per-kind refusal reporting (cap_reached informational,
  settle_failed and settle_missing named); a watcher heartbeat; RA-8120 (refusal line with a non-string `at`).

### Assumptions
- Machine and legacy rows are stamped with the same UTC day (both use UTC today).
- The watcher's DAY is the same UTC day (true on 6f067bfe; re-checked in the watcher tests).

### Constraints
- Tier 2 (internal tooling): local checks, GitHub green on the exact head, one independent review round per repo.
- File and function length ratchets (`.github/scripts/file_length_lint.py`, `function_length_lint.py`) after `git add`.

## 6. Existing capability review

| Capability | Location/source | Reusable? | Notes |
|---|---|---:|---|
| In-place column add | `jev_shadow_support._ensure_spend_id` | Yes | same PRAGMA + ALTER pattern for both new columns |
| Machine ledger connect | `spend._connect` | Yes | add the column + index here, once, for every caller |
| Seam check (real watcher on real ledgers) | `.claude/done/work/w_bb8895505d6c/seam.py` | Yes | extend with the reset case |
| Mutant runner | `.claude/done/work/w_bb8895505d6c/mutants.py` | Yes | copy, new anchors |
| Watcher mutants/suites | `~/.cache/review-briefs/watcher_mutants_r4.py`, `watcher_suites.sh` | Yes | new anchors for call-id rule |

## 7. Specialist board review

| Role | Finding | Risk | Recommendation |
|---|---|---|---|
| Product Manager | Fixes the one thing the alert exists for: true spend | Low | Ship both halves; watcher tolerates either order |
| Software Architect | Identity belongs in the data; `reserve()` contract unchanged keeps two callers untouched | Low | `reserve_call` returns both; `reserve` delegates |
| UX/UI Reviewer | No UI; the alert text is unchanged | None | Keep messages identical |
| Security Reviewer | uuid4 is not a secret; no new network or key path; ALTER never drops data | Low | Unique index tolerates NULLs on old rows (SQLite allows many NULLs) |
| QA/Test Lead | Old-schema ledger, reset, missing id, mixed day must each be tested and mutated | Medium | Tests listed in section 13; each guarded by a mutant |
| Devil's Advocate | Upgrade day double-counts old mirrored rows -> possible early alert | Low | Accept: over-count is the safe direction and ends at day roll; documented |

## 8. Judge challenge

| Category | Score | Notes |
|---|---:|---|
| First-source evidence | 25/25 | code read on origin/main and 6f067bfe; P1 repro from round-4 report |
| Clear user/business problem | 20/20 | cap can under-report after a reset |
| Reuse of existing capability | 15/15 | existing ALTER pattern, seam and mutant runners |
| Security/privacy safety | 15/15 | no secrets, no network, additive schema |
| UX clarity | 10/10 | alert unchanged |
| Testability | 10/10 | every rule has a planted failing case |
| Cost/control simplicity | 5/5 | no paid calls; tests use fakes |

Total 100. Decision: APPROVE BUILD. (North Star fit UNVERIFIED does not lower a mandatory criterion; recorded in 2.)

## 9. Proposed solution

- System flow: `reserve_call` -> `spend.reserve_call(caller, charge)` -> machine row (id, call_id uuid4 hex) ->
  legacy row `UPDATE calls SET spend_id=?, spend_call_id=? WHERE id=?`.
- Watcher flow: read the machine ledger first; if it has `call_id`, twins = set of today's call ids. For each
  legacy ledger: skip a row only if it has `spend_call_id` and that id is in twins; count everything else.
  If the machine ledger has no `call_id` column (old code), twins is empty and every legacy row counts.
  The machine ledger's sum and call ids come from one SELECT (eng-concurrency): two reads let a call landing
  between them be skipped in the legacy ledger and missing from the total.
- Settle flow: `spend.finish(row, ..., call_id=)` updates `WHERE id=? AND call_id=?`; a settle matching no row
  returns False and writes `settle_missing` beside the ledger (eng-data).
- Failure flow: machine ledger unreadable -> already reported in `bad` (UNKNOWN), unchanged. A reset (section 4)
  -> UNKNOWN for the rest of the UTC day.
- Rollback: revert either PR. Columns are additive; old code ignores them. Reverting only Pi-Dev-Ops while the
  new watcher stays installed over-counts every mirrored call (safe direction, noisy). Restore the watcher from
  `~/.local/bin/jev-cap-watcher.py.bak-*` or reinstall, then run the post-install check (section 17).

## 10. UX requirements

No user surface changes. Alert text, thresholds and board rows identical. Confidence signal: the cap alert reflects
true spend across resets.

## 11. Technical requirements

- Files: `jev_platform/spend.py`, `scripts/jev_shadow_support.py`, `scripts/mission_control_jev_shadow.py`,
  `tests/test_jev_spend_ledger.py`, `tests/test_mission_control_jev_shadow.py` (or a new focused test file);
  skills-library `skills/guardian/scripts/jev-cap-watcher.py`, its tests, `SKILL.md`.
- Schema: local SQLite only, additive columns + one unique index.
- Backward compatibility: `reserve()` still returns int; old ledgers upgraded in place on next connect.

## 12. Security and privacy requirements

No auth, secret, PII or external-service change. The call id is random, carries no data. Ledger files stay local.

## 13. Verification plan

- Pi-Dev-Ops tests (pytest, `.venv/bin/python`, clean env): new rows carry a unique 32-hex call id; an old-schema
  ledger gains the column without losing rows; `reserve()` still returns int; the mirrored legacy row stores the
  same call id as its machine row; after deleting the machine ledger, the next call id differs from the mirrored one.
- Existing suites: the C2 list from w_bb8895505d6c plus the census test.
- Watcher tests: reset case (same int id and amount, different call ids) counts both = 24; same call id counts once;
  legacy row with no call id counts; machine ledger without `call_id` column counts every legacy row.
- Seam: real watcher over ledgers written by the real code, including a reset, reports the exact true sum.
- Mutants: each rule above reverted -> a named test fails.
- ruff + size gates on changed files.

## 14. Loop testing and stress testing

Normal, reset, old schema, mixed schema, missing id, duplicate mirror write, unreadable machine ledger (UNKNOWN),
two calls same amount same int id across reset. Retry: `reserve_call` is called once per attempt; uuid uniqueness
enforced by the index.

## 15. Acceptance criteria

- [ ] C1 new spend-ledger and shadow tests pass (section 13 list).
- [ ] C2 existing Jev/shadow/skill-routing suites pass.
- [ ] C3 every planted mutant killed.
- [ ] C4 ruff passes on changed Python files.
- [ ] C5 the watcher at the reviewed skills-library commit reports the exact sum before a reset, and after a reset
  reports the machine ledger UNKNOWN with the lower bound that excludes only the lost unmirrored call (eng-test:
  the earlier oracle passed on a total 1,000 tokens short). Control: the earlier watcher fails it.

## 16. Goal command

```text
/goal Implement the accepted SPM spec for the Jev spend call id. Completion condition: C1-C5 PROVEN by donectl verify at the final head in both repos, each PR green on GitHub with its release receipt. Required proof: donectl verify output, PR_RELEASE_GATE_PASS lines, GitHub check results. Constraints: no unrelated files changed; no secrets added; no destructive operations; stop and produce /session-handoff if blocked.
```

## 17. Implementation sequence

1. Pi-Dev-Ops: spend.py column + `reserve_call`; shadow mirror; tests; mutants; seam. Review, gate, PR.
2. skills-library: rebase onto main; call-id matching; tests; mutants. Review, gate, PR.
3. After Phill merges both, in this order (eng-release, eng-failure, boris):
   a. Record `git rev-parse HEAD` of every Jev writer checkout on the Mini: `~/Pi-Dev-Ops`, `~/relint/pdo`,
      `/Volumes/Mini Mini 2T Storage/code/pdo-jev-runner`, plus any found by `launchctl list | grep -i jev`.
   b. Update each to the merged commit (a descendant of this PR's head) and restart any process running it.
      The watcher is not installed until every one is, because a checkout left on c195d3e0 is double-counted every
      day and one left before #955 writes spend the watcher no longer reads.
   c. Back up `~/.local/bin/jev-cap-watcher.py`, then run `install_guardian.py`.
   d. Post-install check, first run against the current install so it is seen to fail: the installed watcher's
      sha256 equals the merged file's, and the newest line of `~/Library/Logs/jev-cap-watcher.log` carries
      `machine_call_id`, `orphan_links` and `reset`.

## 18. Session handoff seed

RA-8116 call-id follow-up. Pi-Dev-Ops branch fix/RA-8116-spend-call-id; skills-library branch
fix/RA-8116-jev-watcher-canonical (rebased). Parked P1 closed by matching on call id. Next after merge: Mini install.

## 19. Final recommendation

Proceed to implementation.

SPM spec complete. Next safe action: lock the Done contract with C1-C5 and build step 1 in Pi-Dev-Ops.
