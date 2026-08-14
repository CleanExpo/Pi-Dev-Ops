# SPM Spec — RA-7216 completion (gap 2 steps 3–6 + gap 4)

| | |
|---|---|
| Created | 14/08/2026 |
| Base | `main` @ `defd963` |
| Status | **Awaiting acceptance** — no build authorised by this document |
| Prior art | audit `24f7767` · acceptance events `d25ff6e` · design `0a74a98` · attribution keys `defd963` |

---

## 1. Task being planned

Finish RA-7216: implement gap 2 steps 3–6 (revert detector, reopen event, CI-failure row, re-point C1) and gap 4 (SDK cost durability), so that **every one of the seven metrics is either measurable or explicitly `needs_data` with a named reason.**

## 2. Current project context

Four RA-7216 changes are already on `main`. What they left behind:

| Shipped | Consequence for this spec |
|---|---|
| `gate_checks.accepted_at` / `accepted_state_type`, written by `record_acceptance()` from the Linear terminal-transition webhook | Metrics 1, 5 and 6 have a real end-point timestamp for the first time |
| `gate_checks.repo_name` / `pr_number` / `head_branch` / `merge_sha` / `merged_at` | A revert can finally be attributed — the keys began accruing at `defd963` |
| C1 returns `needs_data` at every ship rate; C2 reads terminal outcomes with a 5-sample floor | Both are honest but C1 measures nothing yet |
| `record_merge()` + merged-PR webhook branch ordered ahead of both skips | The ordering pattern this spec reuses three more times |

**Nothing reads the attribution keys.** That is the hole this spec closes.

## 3. Problem statement

C1 is the metric RA-7216 names as the rollback trigger for any routing change — *"roll back any route that increases critical defects"*. It currently returns `needs_data` unconditionally, so **no routing proposal can be evaluated, because the measure that would veto it does not exist.** Three of the seven metrics still have no source at all, and metric 7 is biased low because the dominant cost of a build never reaches durable storage.

## 4. Desired outcome

`scripts/zte_v2_score.py --json` reports, for each of the seven metrics, either a real number with its provenance or an explicit `needs_data` naming what is missing — and no metric reports a number it cannot support.

## 5. Scope

### In scope
- Detector A: revert commits on a default branch, attributed via `merge_sha`
- Detector B: reopen after acceptance
- Detector C: default-branch CI failure after merge, diagnostic only
- `outcome_events` table
- C1 re-pointed as `observed_rollback_rate` + `unattributed_reverts` + attribution coverage, per the §9 decision (option b)
- Metrics 3, 5 and 6 surfaced from data that now exists
- Gap 4: one `record_cost()` call so Agent SDK spend reaches `llm_costs`

### Out of scope
- Applying any DDL to production — `supabase/migration.sql` is edited; the founder runs it
- Any routing or model-selection change (ticket guardrail 3)
- The 30-day baseline itself — it accrues in wall-clock time, not in this work
- Backfilling history (ticket guardrail 1 forbids inventing it)

### Explicit non-goals
- Making metric 2 (human correction count) measurable. **It stays `needs_data`** — see §8.
- A dashboard surface for any of this. Data first.

### Assumptions
- `A1` GitHub sends `push` events for the default branch to `/api/webhook` today. *Verified:* `parse_github_event` handles `push` and the route is live.
- `A2` `merge_commit_sha` on a squash-merge is the commit that lands on `main`, so `git revert` of that commit names it. **UNVERIFIED against GitHub docs** — must be confirmed in phase 1 before Detector A is trusted; if false, attribution needs the post-merge `head_commit` instead.

### Constraints
- Fire-and-forget: observability must never raise into the pipeline (module doctrine)
- Detection runs before session creation **and** before the RA-1182 self-modification skip
- No secrets, no destructive operations

## 6. Existing capability review

Do not rebuild:

| Exists | Reuse |
|---|---|
| `_patch` / `_insert` / `_select` in `supabase_log.py` | All new writers |
| `_handle_workflow_run` (RA-847) — already detects CI failure on the default branch | Detector C adds a row; it does not add detection |
| `parse_linear_event` `issue_started` branch | Detector B rides this, no new event type |
| `record_merge` / `record_acceptance` shape | Copy exactly — `is.null` guard, log line, bool return |
| `_C2_MIN_SAMPLE` floor pattern | C1's coverage floor |

## 7. Specialist board review

**T0 / inline. No bench was convened.** Subagent dispatch is disabled for this session, which pins the tier per the skill's operator-override clause. Per the skill's hard line — *"Never role-play a board you didn't convene"* — no seat verdicts, confidences or divergence numbers are reported, because none were produced. The §8 challenge is therefore run inline against the judge rubric, not derived from a devils-advocate seat.

`board_version`: n/a (T0). Axis scores not computed: `references/leveling.md` was not read, and inventing scores would be the same defect as simulating seats.

## 8. Judge challenge

Inline rubric. Five substantive objections, each resolved in the design or accepted as a stated limit:

1. **"Detector B cannot tell 'no row' from 'already accepted'."** Correct, and fatal to the obvious implementation — inferring a reopen from a PATCH that matched nothing conflates *this issue was already accepted* with *Pi-CEO never shipped this issue*. **Resolved by redesign:** a reopen is a transition **to** `started` on an issue whose row already has `accepted_at`. That is an explicit `_select`, not an inference, and it needs no `Prefer: return=representation` change at all. The design doc's suggestion is superseded and this spec says so.
2. **"`outcome_events` grows unbounded."** True. Bounded in practice — one row per revert/reopen/CI-failure, order hundreds per year. Accepted; no retention policy, and none invented.
3. **"A revert of a revert double-counts."** Real. Handled: if the target SHA is itself a recorded `revert` event, the new row is `re_land`, not `revert`, and `re_land` is excluded from C1's numerator.
4. **"CI-failure-on-main has too many false positives to be a metric."** Agreed — that is exactly why it is `kind='ci_fail_on_main'` in the events table and **never enters any score**. Diagnostic only, same status the ticket assigns PR and token counts.
5. **"Metric 2 still cannot be measured, so the goal's 'all seven' is not met."** Half true, and the honest answer is that metric 2 is met by the *second* limb: explicitly `needs_data` with a named reason — no commit-authorship attribution exists for post-merge edits. Making it measurable needs a per-commit author feed nobody has asked for. Recorded as a limit, not smuggled in as a number.

**Score: 96/100.** Not 100, and therefore **not a build authorisation under the skill's hard line.** The four missing points are assumption `A2` (unverified, and Detector A's attribution rests on it) plus the T0 bench, which the rubric treats as reduced assurance for a change touching the webhook ingress. **Ceiling reported honestly rather than inflated.** Phase 1 verifies `A2`; if it holds, the spec is at 100 for phases 2+ and the founder's acceptance of this document is what authorises the build.

## 9. Proposed solution

### System flow
```
push to default branch ──► revert parser ──► match merge_sha ──► outcome_events(revert|re_land)
                                             └─ no match ─────► outcome_events(gate_check_id NULL)
Linear issue → started ──► row has accepted_at? ──► yes ─────► outcome_events(reopen)
workflow_run failed on default branch ─────────────────────► outcome_events(ci_fail_on_main)
Agent SDK invocation completes ────────────────────────────► record_cost() ──► llm_costs
```

### Data flow
`outcome_events` is append-only; nothing updates a row after insert. C1 reads it joined to `gate_checks` on `merge_sha`.

### Failure flow
Every writer is fire-and-forget. A Supabase outage loses events; it never fails a build or a webhook. Lost events depress `attribution coverage`, which is surfaced — the degradation is visible rather than silent.

### Rollback path
`git revert` per phase. DDL is additive and idempotent; reverting code leaves unused tables/columns, and nothing else reads them.

## 10. UX requirements

No UI. The only human-facing surface is `zte_v2_score.py`'s card, which must print C1 as **two numbers plus coverage on separate lines** — never one blended figure. RA-1109 does not bite: nothing here is an interactive surface.

## 11. Technical requirements

```sql
CREATE TABLE IF NOT EXISTS outcome_events (
  id            BIGSERIAL   PRIMARY KEY,
  kind          TEXT        NOT NULL,   -- revert | re_land | reopen | ci_fail_on_main
  gate_check_id BIGINT,                 -- NULL = unattributable, recorded not dropped
  repo_name     TEXT        NOT NULL,
  merge_sha     TEXT,
  event_sha     TEXT,
  occurred_at   TIMESTAMPTZ NOT NULL,
  detected_by   TEXT        NOT NULL,
  raw_ref       TEXT
);
CREATE INDEX IF NOT EXISTS outcome_events_kind_time_idx ON outcome_events (kind, occurred_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS outcome_events_dedupe_idx
  ON outcome_events (kind, event_sha) WHERE event_sha IS NOT NULL;
```
The unique index makes redelivered webhooks idempotent — GitHub redelivers freely.

Revert parse: `^Revert "` on the subject, plus `This reverts commit ([0-9a-f]{7,40})` in the body. Match the captured SHA against `merge_sha` by prefix (`like.<sha>%`) so short SHAs resolve.

C1 output contract:
```
observed_rollback_rate : reverts_attributed / merged_rows_in_window   (or needs_data)
unattributed_reverts   : count
attribution_coverage   : attributed / (attributed + unattributed)
```
`needs_data` when coverage < 0.5 **or** attributed reverts < 5. Thresholds are starting values, documented as un-derived, retunable.

## 12. Security and privacy requirements

- No new secrets, no new external calls; all inputs arrive on the already-HMAC-verified webhook
- Commit messages are attacker-influenceable on public repos: the SHA is matched by regex against `[0-9a-f]{7,40}` and never interpolated raw into a filter beyond that character class
- **Pre-existing weakness to fix while here:** `record_merge` / `record_acceptance` interpolate `repo_name` and issue id into PostgREST filters unescaped. Not injection (values come from signed webhooks) but fragile against `&`/`=`. Add `urllib.parse.quote` on filter values.

## 13. Verification plan

**Static:** `python -m py_compile` on every edited module; `ruff` clean; `json.load` on `smoke-surfaces.json`.

**Unit:** synthetic payloads for — revert with full SHA · revert with short SHA · revert-of-revert → `re_land` · `Revert "` on a non-default branch (must not fire) · a message merely containing the word "revert" (must not fire) · reopen on an accepted issue · `issue_started` on a never-accepted issue (must not fire) · unattributable revert writes `gate_check_id IS NULL` · duplicate delivery inserts once.

**Integration:** route-level — a revert push does **not** create a build session; detection precedes both skips; a merge on Pi-Dev-Ops itself is still recorded.

**Scorer:** C1 emits three values; degrades to `needs_data` below either floor; `re_land` excluded from the numerator; open rows excluded from the denominator.

**Cannot be verified locally:** FastAPI, pytest, bcrypt and `claude_agent_sdk` are absent from the authoring container. Route-level and SDK tests execute first in CI. Each such test is labelled in-file, and a source-order structural guard backs the ordering invariant — the pattern that caught a real defect on #641.

**Sandbox policy:** no production Supabase is touched. DDL is written to `migration.sql` and left unapplied. Isolation: the feature branch plus CI; prod untouched.

## 14. Loop and stress testing

- 1,000 synthetic push events through the revert parser — assert zero false positives against ordinary commit messages drawn from this repo's own `git log`
- Duplicate-delivery storm: same event ×20 → exactly one row (unique index)
- Empty-window: no events at all → every metric `needs_data`, no division by zero
- Coverage-collapse: 3 attributed vs 40 unattributed → C1 must report `needs_data`, **not** a healthy-looking rate

## 15. Acceptance criteria

1. `outcome_events` exists in `migration.sql`, unapplied, additive, idempotent
2. Detector A records attributed and unattributable reverts; `re_land` distinguished
3. Detector B records a reopen via explicit lookup, never by PATCH inference
4. Detector C records CI failures and they enter no score
5. C1 reports rate + unattributed + coverage, with both floors, never blended
6. Metrics 3, 5, 6 report real numbers; metric 2 reports `needs_data` with its reason
7. Agent SDK spend reaches `llm_costs`
8. Every new detector runs before session creation and before the self-modification skip
9. Full suite green in CI; each phase's mutation controls shown failing alone
10. No routing change; no DDL applied; no secrets

## 16. Goal command

`/goal` has no `SKILL.md` in this repo — `CLAUDE.md` documents it but only `.spm/goal-template.md` exists. The command below follows that template and is recorded for the human, not dispatched:

```text
/goal Implement the accepted SPM spec .spm/RA-7216-completion.md. Completion condition: outcome_events DDL present and unapplied; Detectors A, B and C implemented and ordered ahead of session creation and the RA-1182 skip; C1 emits observed_rollback_rate + unattributed_reverts + attribution_coverage with both floors; metrics 3/5/6 report real values and metric 2 reports needs_data with a named reason; Agent SDK spend reaches llm_costs; `python -m pytest tests/ -x -q` green in CI and every phase's mutation controls shown failing alone; no routing change, no DDL applied to prod, no secrets added. Stop and produce /session-handoff if blocked by assumption A2 failing, missing Supabase credentials, or any request to apply DDL to production.
```

## 17. Implementation sequence

Phased; do not advance while a phase is `failed`.

| Phase | Content | State | Validation |
|---|---|---|---|
| 1 | Verify assumption **A2** (squash `merge_commit_sha` == commit landing on default branch) against GitHub docs + this repo's own merge history | idle | A2 confirmed, or spec amended in place |
| 2 | `outcome_events` DDL + `record_outcome_event()` + filter-escaping fix (§12) | idle | py_compile, ruff, unit tests |
| 3 | Detector A + ordering + self-mod carve-out | idle | unit + route + source-order tests; mutation controls |
| 4 | Detector B (reopen via explicit lookup) | idle | unit tests; mutation control |
| 5 | Detector C (diagnostic row) | idle | unit test asserting it enters no score |
| 6 | C1 re-point + metrics 3/5/6 + metric 2 `needs_data` | idle | scorer tests incl. coverage-collapse |
| 7 | Gap 4 — `record_cost()` in the SDK result path | idle | unit test that the SDK path calls it |

Phases 2–6 are one PR (they are one coherent change and splitting leaves a detector with no table). Phase 7 is a separate PR — it is independent and touches a different subsystem.

## 18. Session-handoff seed

Base `defd963`; branch `claude/linear-task-continuation-9x7azb` off latest `main`. Local gates run via `python /tmp/mp.py <testfile>` (minimal runner; no pytest here). Known-absent deps: fastapi, pytest, bcrypt, claude_agent_sdk, pydantic, starlette. `.harness/` does not exist in this checkout. Prior evidence: #641's route tests failed first in CI on `asyncio.get_event_loop()` — use `asyncio.run()`.

## 19. Final recommendation

**APPROVE BUILD at 96/100, conditional on phase 1.** The ceiling is reported honestly rather than inflated to clear the skill's 100/100 bar: assumption A2 is unverified and Detector A's attribution depends on it, and the bench was T0. Phase 1 exists to close A2 before any detector is written. If A2 fails, phases 3+ are amended in place — not silently continued.

The single highest-risk item is not any detector but **C1's coverage floor**: without it, a rate computed over three attributed reverts while forty went unattributed reads as reassurance when it is the opposite. That floor is criterion 5 and non-negotiable.

---

SPM spec complete. Next safe action: accept or amend this spec — no code may be written until it is accepted.
