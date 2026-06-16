# Forward plan: Definition-of-Done + coverage check for Pi-Dev-Ops

Generated: 2026-06-07 · Horizon: 18 moves · Planner: forward-planner

## Framing — why a coverage check, not a better judge

The brief says "stop reporting 'done' when work is actually missing." The naive read is "make the judge stricter." That is the trap. The judge (`app/server/tao_judge.py`) answers a per-*task* question — "did the worker meet *this goal*, and do tests pass?" — and `tao_loop.run_until_done` terminates the moment `judge()` returns `GOAL_MET`. Nothing in that path ever asks "is the *project* finished?" There is no representation of the finished project to ask against. Tightening the judge only makes per-task verdicts crisper; it cannot detect a deliverable that was never a task, because the missing deliverable is invisible to a function that only sees the goal in front of it.

So the win condition is structural: introduce a persisted, machine-checkable **Definition of Done (DoD) per project**, and a **coverage check** that diffs that DoD against observed reality, and gate the loop's terminal "done" on coverage — not just on the per-task judge. This is exactly the seam the forward-planner skill already names: its structured plan's `win_condition[].probe` fields are *designed* to seed this coverage check, and the skill points at a `swarm/gap_detector.py` that does not yet exist. We are building that missing organ.

## Win condition (Definition of Done)
What "complete" means for *this* feature, as checkable conditions. `[auto]` = machine-verifiable; `[human]` = needs judgment.

- [auto] **wc1** — A DoD schema exists and is documented; a project's DoD is a list of `{id, statement, check: auto|human, probe}` items persisted at a known path. Probe: load `.harness/dod/pi-dev-ops.dod.json`, assert it parses and every item has the four fields.
- [auto] **wc2** — A `coverage_check(project_id)` module exists that loads a project's DoD, runs each `auto` probe, and returns a structured report: per-item `present|partial|absent|unknown`, plus an aggregate `coverage_ratio` and an `unmet[]` list. Probe: `pytest tests/test_coverage_check.py` green; calling it on a seeded fixture returns the expected unmet set.
- [auto] **wc3** — Probes are sandboxed and side-effect-free: a probe failure/timeout yields `unknown` for that item and never raises into the caller. Probe: inject a probe that raises and one that hangs; assert report still returns with those items = `unknown`.
- [auto] **wc4** — `tao_loop.run_until_done` no longer terminates `done=True` on `GOAL_MET` alone for project-scoped runs: it additionally requires coverage over a threshold (`TAO_COVERAGE_MIN`, default 1.0 for `auto` items). When the judge says `GOAL_MET` but coverage shows `unmet[]`, the loop reports `COVERAGE_INCOMPLETE`, not `done`. Probe: `pytest tests/test_tao_loop_coverage.py` — judge mocked to `GOAL_MET`, DoD with one unmet auto item → `LoopResult.done is False and reason == "COVERAGE_INCOMPLETE"`.
- [auto] **wc5** — Each `unmet[]` DoD item is filed as a Linear ticket in the correct project/team via `.harness/projects.json` routing, with idempotency so re-runs don't duplicate. Probe: run coverage with 2 unmet items against a mocked Linear client → exactly 2 `save_issue` calls with `project_id=f45212be…`, `team_id=a8a52f07…`; second run with same unmet set → 0 new calls.
- [auto] **wc6** — The forward-planner structured plan is the canonical DoD source: a converter turns `win_condition[]` from a `forward-plan.json` into a project `.dod.json`. Probe: feed this plan's own JSON through the converter; output validates against the DoD schema and item count matches `win_condition` length.
- [auto] **wc7** — Coverage state is observable: every coverage run writes one row to a Supabase `coverage_runs` table (and the `CREATE TABLE IF NOT EXISTS` ships in `supabase/migration.sql`), fire-and-forget. Probe: run coverage with a mocked observability client → one insert with `project_id`, `coverage_ratio`, `unmet_count`; observability failure does not block the run.
- [auto] **wc8** — A CI gate (`coverage-gate` workflow / job) runs the coverage check on `pi-dev-ops`'s own DoD and fails the build if `auto` coverage < threshold, with `concurrency` + fork guard like the codebase-wiki workflow. Probe: workflow file present, parses, and a red fixture run exits non-zero.
- [auto] **wc9** — "Done" reporting at every surface (loop `LoopResult`, session streamer, six-pager, board memos) sources completeness from coverage, not the judge verdict — so no surface can say "done" while `unmet[]` is non-empty. Probe: grep the streamer/six-pager done-emitters; assert they read `coverage.complete`, covered by a test that a non-empty `unmet[]` suppresses any "done"/"completed" emission.
- [human] **wc10** — Any *change* to a project's DoD (adding/removing/weakening a win condition) is surfaced for human approval, never self-authored silently by the loop — honoring launch-charter governance. Verify: a DoD edit PR carries the manifest checklist and a diff of DoD items; reviewer confirms no silent weakening.
- [human] **wc11** — `human`-checked DoD items are never auto-marked satisfied by the coverage engine; they surface as `needs_human_verification` and block the terminal "done" until a human signs off. Verify: a DoD with one `human` item can never reach `complete` via probes alone.
- [auto] **wc12** — Operator runbook exists: how to author a DoD, read a coverage report, interpret `unknown` vs `absent`, and force-stop a stuck coverage gate. Probe: `.harness/runbooks/coverage-check.md` exists and references the kill-switch and the env vars.

## Board state

**Internal (read from the repo, 2026-06-07):**
- `app/server/tao_judge.py` — per-task evaluator. `judge()` returns `JudgeVerdict{done, reason∈{GOAL_MET,…}, score, next_action_hint}`. `done` is true ONLY when `reason=='GOAL_MET'` and tests pass. It scores *one goal*; it has no concept of a project DoD.
- `app/server/tao_loop.py` — `run_until_done()` loops worker steps; calls `judge()` every N iters; **breaks with `reason="GOAL_MET", done=True` the instant `verdict.done`** (line ~196). That is the exact false-completion seam. Other terminal reasons are kill-switch axes (MAX_ITERS/MAX_COST/HARD_STOP) and `JUDGE_NEVER_SATISFIED`. There is no coverage/project-completeness branch.
- `.harness/projects.json` — registry. `pi-dev-ops` → `linear_project_id f45212be-3259-4bfb-89b1-54c122c939a7`, `linear_team_id a8a52f07-63cf-4ece-9ad2-3e3bd3c15673`, team key `RA`. This is the routing table the coverage check must reuse for ticketing.
- `.harness/business-charters/` exists (e.g. `restoreassist-charter.md`, `projects/`) — prose charters that are the natural *first draft* source of DoD statements, but they are not machine-checkable today.
- **`swarm/gap_detector.py` does NOT exist** (the forward-planner SKILL references it as the consumer of the structured plan). No `coverage`-named module, no DoD store, no `coverage_runs` table. This feature is net-new plumbing, not a refactor.
- `supabase/migration.sql` is the single place to add `CREATE TABLE IF NOT EXISTS` (idempotent) per the project's observability convention. `app/server/observability.py` is the single fire-and-forget write path.
- CLAUDE.md hardwired lessons that constrain the design: silent success == silent failure (observability mandatory); "done" must describe a *verified* manifestation; subprocess/SDK failures must surface, not swallow (but probes specifically must degrade to `unknown`, see red-team); CI workflows need `concurrency` + fork guard + repo-owner check.

**External (best-practice grounding, current as of knowledge cutoff Jan 2026):**
- This is the classic **acceptance-criteria / executable-specification** pattern (Fit/Cucumber lineage): completion is defined by externally-stored checkable criteria, not by the implementer's self-assessment. The robust versions separate *spec* (DoD) from *checker* (probes) from *reporter* (coverage) — the same three-layer split the templates reference (spec → checker → reporter).
- LLM-as-judge literature's known failure mode is exactly self-grading optimism; the mitigation is an *independent, ground-truth-anchored* check. A probe that hits the real surface (route returns 2xx, table has columns, test passes) is that ground truth; the judge is not.
- Idempotent ticket filing (dedupe by a stable key, e.g. `dod_item_id`) is standard for any detector that runs on a schedule, to avoid the "100 duplicate tickets" failure the gap_detector would otherwise cause.

## The gap (win condition − current state)

| Win-condition item | Status | Notes |
|---|---|---|
| wc1 DoD schema + persisted store | absent | No `.harness/dod/`, no schema. Charters are prose only. |
| wc2 `coverage_check()` module | absent | No coverage module exists. |
| wc3 sandboxed, side-effect-free probes | absent | No probe runner. |
| wc4 loop gated on coverage | absent | Loop breaks on `GOAL_MET` alone (tao_loop.py ~L196). |
| wc5 unmet → idempotent Linear tickets | absent | `swarm/gap_detector.py` referenced but missing. |
| wc6 forward-plan → DoD converter | partial | `forward-plan.json` schema exists; no converter to `.dod.json`. |
| wc7 `coverage_runs` observability | absent | Table not declared; observability.py write path exists. |
| wc8 CI coverage gate | absent | No workflow; pattern exists (codebase-wiki). |
| wc9 done-reporting sources coverage | absent | Streamer/six-pager read judge/loop reason today. |
| wc10 DoD change → human approval | absent | No governance hook on DoD edits. |
| wc11 human items never auto-passed | absent | No `auto|human` distinction enforced anywhere. |
| wc12 operator runbook | absent | No coverage runbook. |

Every item is absent or partial — this is genuinely new infrastructure. The DoD/coverage organ is the thing the system was missing that *let* it report false completion.

## The spine — 18 moves

Ordered current-state → win condition, respecting real dependencies. Each move is one verifiable deliverable.

1. **DoD schema + spec doc** — *Deliverable:* `.harness/dod/schema.json` + a short spec defining a DoD item `{id, statement, check, probe}` and the file convention `.harness/dod/<project>.dod.json`. *Verify:* schema parses; a hand-written `pi-dev-ops.dod.json` validates against it. *Unlocks:* 2,6. *Requires:* nothing (greenfield). *Satisfies:* wc1.
2. **Probe descriptor model + registry** — *Deliverable:* a typed probe descriptor (kind: `http_2xx`, `pytest`, `file_exists`, `sql_columns`, `grep`, `shell`) and a dispatch registry mapping kind→runner. *Verify:* unit test instantiates each kind; unknown kind → explicit error at load, not at run. *Unlocks:* 3. *Requires:* move 1. *Satisfies:* wc1.
3. **Sandboxed probe runner** — *Deliverable:* `run_probe(descriptor) -> {result: present|partial|absent|unknown, detail}` with per-probe timeout, exception isolation, no writes. *Verify:* test that a raising probe and a hanging probe both yield `unknown`; a passing/failing probe yields `present`/`absent`. *Unlocks:* 4. *Requires:* move 2. *Satisfies:* wc3.
4. **`coverage_check(project_id)` aggregator** — *Deliverable:* `swarm/gap_detector.py::coverage_check` loads the DoD, runs each `auto` probe via the runner, returns `CoverageReport{items[], coverage_ratio, unmet[], human_pending[]}`. *Verify:* `pytest tests/test_coverage_check.py` on a fixture DoD returns the expected `unmet`/`human_pending` partition. *Unlocks:* 5,7,9,11. *Requires:* move 3. *Satisfies:* wc2.
5. **`human` vs `auto` enforcement** — *Deliverable:* coverage never marks a `human` item satisfied via probe; such items land in `human_pending[]` and count against completeness. *Verify:* DoD with one `human` item can never reach `complete=true` from probes alone (test). *Unlocks:* 13. *Requires:* move 4. *Satisfies:* wc11.
6. **forward-plan → DoD converter** — *Deliverable:* `win_condition[]` (with `probe`) from a `forward-plan.json` → `<project>.dod.json`. *Verify:* feed this plan's JSON through it; output validates (move 1 schema) and item count == win_condition length. *Unlocks:* 14. *Requires:* move 1. *Satisfies:* wc6.
7. **`coverage_runs` table + migration** — *Deliverable:* `CREATE TABLE IF NOT EXISTS coverage_runs (...)` in `supabase/migration.sql`; writer in `observability.py`. *Verify:* migration re-runs idempotently; mocked client gets one insert per coverage run. *Unlocks:* 8,12. *Requires:* move 4. *Satisfies:* wc7.
8. **Fire-and-forget observability wiring** — *Deliverable:* `coverage_check` emits a `coverage_runs` event through the existing fire-and-forget path; observability failure never blocks the run. *Verify:* inject a failing observability client → coverage still returns; one attempted insert logged. *Unlocks:* 9. *Requires:* move 7. *Satisfies:* wc7.
9. **Loop terminal-gate on coverage** — *Deliverable:* in `tao_loop.run_until_done`, when `verdict.done` for a project-scoped run, call `coverage_check`; only set `done=True` if `coverage_ratio >= TAO_COVERAGE_MIN` AND `unmet[]` empty; else `reason="COVERAGE_INCOMPLETE"`, keep looping (or stop with that reason at iter cap). *Verify:* `tests/test_tao_loop_coverage.py` — judge mocked `GOAL_MET`, one unmet auto item → `done is False, reason=="COVERAGE_INCOMPLETE"`. *Unlocks:* 10,15. *Requires:* moves 4,8. *Satisfies:* wc4.
10. **`LoopResult` carries coverage** — *Deliverable:* `LoopResult` gains `coverage: CoverageReport | None` + `unmet_ids`. *Verify:* result object exposes unmet ids in the gated test. *Unlocks:* 11,16. *Requires:* move 9. *Satisfies:* wc4,wc9.
11. **Idempotent Linear ticketing for `unmet[]`** — *Deliverable:* `gap_detector` files each `unmet` item as a Linear issue routed via `projects.json` (`pi-dev-ops`→ project `f45212be…`, team `a8a52f07…`), keyed by `dod_item_id` for dedupe. *Verify:* 2 unmet → 2 `save_issue` calls with correct ids; re-run same set → 0 new. *Unlocks:* 12. *Requires:* moves 4,10. *Satisfies:* wc5.
12. **Routing fallback + unknown-project handling** — *Deliverable:* when a project has null `linear_project_id` (e.g. `oh-my-codex`) file at team level; when project_id absent from registry, raise a clear config error (don't silently drop). *Verify:* test both branches. *Unlocks:* 17. *Requires:* move 11. *Satisfies:* wc5.
13. **Done-reporting reads coverage at every surface** — *Deliverable:* loop streamer, six-pager, and board "done" emitters read `coverage.complete` instead of judge reason; non-empty `unmet[]` suppresses any "done"/"completed" text. *Verify:* test that an incomplete coverage report suppresses the done emission in each emitter. *Unlocks:* 18. *Requires:* moves 5,10. *Satisfies:* wc9.
14. **Seed `pi-dev-ops` DoD from this plan** — *Deliverable:* run the converter (move 6) on this very `forward-plan.json` to produce `.harness/dod/pi-dev-ops.dod.json` — the system's first real DoD, dogfooded. *Verify:* `coverage_check("pi-dev-ops")` runs end-to-end and returns a report. *Unlocks:* 15. *Requires:* moves 6,4. *Satisfies:* wc6,wc1.
15. **CI `coverage-gate` workflow** — *Deliverable:* `.github/workflows/coverage-gate.yml` runs `coverage_check("pi-dev-ops")`, fails build if `auto` coverage < threshold; `concurrency: coverage-gate`, `cancel-in-progress`, fork guard (`repository == 'CleanExpo/Pi-Dev-Ops'`). *Verify:* workflow parses; red fixture exits non-zero. *Unlocks:* 16. *Requires:* moves 4,14. *Satisfies:* wc8.
16. **DoD-change governance gate** — *Deliverable:* a check (pre-commit / CI) that flags any diff to `.harness/dod/*.dod.json` and requires the PR manifest checklist + human approval; the loop is forbidden from editing DoD files (path guard). *Verify:* a simulated loop write to a `.dod.json` is rejected; a human PR with the checklist passes. *Unlocks:* 18. *Requires:* move 14. *Satisfies:* wc10.
17. **Probe-failure alerting / drift** — *Deliverable:* sustained `unknown` (probe broken, not feature absent) is distinguished from `absent` in the report and surfaces as a separate alert so a broken probe can't masquerade as "feature missing" or, worse, silently pass. *Verify:* test that `unknown` items are reported in their own bucket and trigger an alert path, not a "done". *Unlocks:* 18. *Requires:* moves 3,11. *Satisfies:* wc3,wc9.
18. **Operator runbook + end-to-end dogfood proof** — *Deliverable:* `.harness/runbooks/coverage-check.md` (authoring DoD, reading reports, `unknown` vs `absent`, force-stopping the gate via kill-switch); plus an end-to-end proof run on `pi-dev-ops` DoD showing it goes from `unmet>0` to `complete` as moves land. *Verify:* runbook exists and references kill-switch + env vars; e2e proof captured. *Requires:* moves 13,15,16,17. *Satisfies:* wc12,wc9.

## Branch points

- **After move 4 — probe execution location:** *Decider:* are probes safe to run in-process inside the loop's workspace, or must they run in an isolated subprocess/sandbox? If *in-process acceptable* (probes are read-only, fast) → continue spine. If *isolation required* (probes hit network / shell) → insert 4a "subprocess probe harness with resource limits" before move 9. Re-converges at move 9. Decider: security review of the probe kinds enumerated in move 2.
- **After move 11 — Linear ticket strategy:** *Decider:* one ticket per unmet DoD item, or one rolled-up "coverage gap" ticket per run? If *per-item* (default, finer routing) → spine. If *rolled-up* (avoids ticket spam when DoD is large) → 11b "aggregate unmet into a single checklist issue, dedupe by run hash", re-converge at move 12. Decider: Phill / ticket-volume tolerance after first live run.
- **After move 9 — loop behavior on `COVERAGE_INCOMPLETE`:** *Decider:* does the loop keep iterating to try to close the gap, or stop-and-report for human/next-cycle? If *keep iterating* → feed `unmet[]` as the next worker goal (needs move 10's unmet_ids). If *stop-and-report* → terminal `COVERAGE_INCOMPLETE`, tickets filed (move 11), next autonomous cycle picks them up. Re-converges at move 13. Decider: autonomy-budget policy; default stop-and-report to respect the 3-PR/day rate limit.

## Risk horizon

- **Probe brittleness — a broken probe reads as `absent`, the loop "fixes" a non-problem or never reports done.** → move 3 isolates failures to `unknown` (not `absent`); move 17 alerts on sustained `unknown` so broken probes are visible, not silently dispositive.
- **Coverage gate becomes a hang vector** (a probe hits a dead Railway endpoint and blocks the loop). → per-probe timeout (move 3) + the existing HARD_STOP kill-switch (referenced in runbook move 18); coverage runs are bounded, never unbounded.
- **Ticket spam** — large DoD with many unmet items floods Linear. → idempotent dedupe (move 11) + the rolled-up branch (11b) + the existing 3-PR/day autonomy rate limit caps action volume regardless.
- **Loop never reaches `done` because a `human` item can't auto-pass** (deadlock). → that's intended (wc11) but must be *legible*: move 13 reports `human_pending[]` distinctly so a human knows the loop is waiting on them, not stuck.
- **DoD self-authoring** — the loop weakens its own DoD to make coverage pass (Goodhart). → move 16 path-guards `.dod.json` against loop writes and requires human-approved diffs (wc10); this is the single most important guardrail.
- **Migration drift** — `coverage_runs` declared but never written, or written to a table that doesn't exist. → move 7 ships `CREATE TABLE IF NOT EXISTS` in the same change as the writer (project convention); move 8 tests the write path.
- **Threshold misconfiguration** — `TAO_COVERAGE_MIN` set below 1.0 silently re-admits false completion for auto items. → default 1.0 for auto items; move 18 runbook documents the knob and its danger.

## Red-team findings (pulled forward)

Walking the spine to "done" and assuming it lied:

- **The judge still fires first.** Even with coverage gating, `judge()` returns `GOAL_MET` and *something* must consult coverage before honoring it. If only `tao_loop` is patched, any *other* caller of `judge()` (board_meeting, tdd_pipeline, feedback_loop — all import judge per grep) can still report false done. → Widened wc9 + move 13 to make *every* done-emitting surface source completeness from coverage, and added an audit (grep) probe so a new uncovered emitter is caught.
- **`human` items create a silent deadlock.** A DoD that's "complete except one human sign-off" looks identical to "stuck" unless reported distinctly. → wc11 + move 5 + move 13's `human_pending[]` surfacing. Inserted as first-class, not afterthought.
- **Goodhart on the DoD itself.** The loop's incentive is to make coverage pass; the cheapest path is to delete a win condition. → wc10 + move 16 governance path-guard. This is the move-16 surprise that would otherwise sink the whole mechanism — a coverage gate the system can edit is no gate.
- **`unknown` ≠ `absent` ≠ `present`.** A two-state (done/not) report collapses "probe broke" into "feature missing," producing either false alarms or false done. → three-state report (move 3,4) + drift alert (move 17).
- **Observability table declared-but-no-writer** is a named recurring bug in CLAUDE.md. → moves 7+8 ship table and writer together, with a write-path test.
- **The verification-gap check on our own win conditions:** every `wc*` here is satisfied by at least one move (validated below). wc10/wc11 (`human`) are satisfied by *governance/enforcement* moves, not by probes — correctly, since they're human-judged.
- **First-run bootstrap:** the very first DoD must come from somewhere trustworthy. → move 14 dogfoods this plan's own JSON as `pi-dev-ops`'s DoD, so the coverage engine's first real subject is itself — the strongest possible proof it works.

## Immediate next move

**Move 1 — DoD schema + spec doc.** It's first because everything downstream is typed against it: the probe model (move 2), the converter (move 6), and the seeded DoD (move 14) all reference the DoD item shape. It's pure greenfield (no dependencies), cheap, and it forces the one decision that shapes the whole feature — *what is a checkable "done" item* — before any code is written against an unstable contract. Ship the schema, hand-write `pi-dev-ops.dod.json` to pressure-test it, then build the probe runner against a fixed target.

---

## Validation output

```
$ python skills/forward-planner/scripts/validate_plan.py forward-plan.json
plan: pi-dev-ops — Build a per-project Definition-of-Done plus a coverage check
  moves: 18 | branch points: 3 | win conditions: 12
VALID
```

Clean pass, no warnings: 18 moves (≥15 horizon), no dependency cycles, no dangling refs, all 12 win conditions satisfied by at least one move, and all 18 moves carry Linear routing.
