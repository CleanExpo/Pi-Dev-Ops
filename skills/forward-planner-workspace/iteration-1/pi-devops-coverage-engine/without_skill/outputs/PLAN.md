# Pi-Dev-Ops Coverage Engine — Build Plan

**Goal:** Stop the autonomous loop from reporting "done" when work is actually missing.
**Root cause (verified in code):** termination is per-task and trust-by-reaching-a-line, never project-level and fact-verified.
**Date:** 2026-06-07

---

## 1. The actual failure mode (grounded in the real codebase)

This is not a hypothetical. Three concrete code paths each declare success without proving completeness:

### 1.1 `app/server/tao_judge.py` — the per-task judge
- `judge()` scores **one goal string** against a state snapshot. `done=true` only when `reason="GOAL_MET"` and "tests pass" (`_build_prompt` line 87).
- But "tests pass" is whatever the LLM infers from `state.last_test_output`. The state is built by `tao_loop._quick_pytest()`, which **returns `""` when there is no `tests/` directory** (line 92). An empty test output is not a failure signal — the judge can read "no failures shown" and emit `GOAL_MET`. **A task with zero tests can score done.**
- On any parse failure or SDK error the verdict defaults to `STILL_WORKING` (correct, fail-safe) — so the bug is not false-negative; it is **false-positive completeness**: the judge never sees the *set* of requirements, only one goal.

### 1.2 `app/server/tao_loop.py` — the loop runner
- `run_until_done()` terminates the moment any single judge verdict returns `done`. There is **no notion of "all sub-goals of the original spec are satisfied."** One goal met = loop exits with `reason="GOAL_MET"`.
- `judge_every_n_iters` is a cost control, not a completeness control. The loop has a `LoopCounter` for iters/cost/hard-stop but **no requirement counter.**

### 1.3 `app/server/session_phases.py` — the ship gate (`_phase_push` ~line 1694)
This is the smoking gun. The `gate_checks` row logged on every ship is:
```python
gate_checks={
    "spec_exists":    spec_exists,      # file present, not content-verified
    "plan_exists":    plan_exists,      # file present, not content-verified
    "build_complete": True,             # hardcoded — "reached here only if generate succeeded"
    "tests_passed":   True,             # hardcoded — "reached here only if sandbox succeeded"
    "review_passed":  review_passed,    # LLM score ≥ threshold
}
```
`build_complete` and `tests_passed` are **literal `True` constants** justified by a comment ("reached here only if…"). This is precisely the anti-pattern CLAUDE.md's own verification protocol forbids: *"Reaching the end of a pipeline is NOT verification… the run looked successful — the diff was clean, CI was green, endpoint returned 200, yet the feature was unusable."* The gate records reaching-the-line, not the fact.

### 1.4 The evaluator is subjective, not enumerated
`_phase_evaluate` (line 1015) asks an LLM: *"Does the diff address EVERY requirement in the brief? List any unmet requirements."* This is the closest existing thing to a DoD — but it is:
- **Prose-in, prose-out:** requirements are never extracted into a discrete, addressable list. "List any unmet requirements" produces free text that nothing downstream consumes or gates on.
- **Single-shot and diff-scoped:** it judges one diff, not the cumulative state of the project against the cumulative spec.
- **Score-collapsed:** a brief with 10 requirements where 8 are perfect and 2 are missing can average to a passing COMPLETENESS score. Partial work passes.

**Conclusion:** Pi-Dev-Ops has a *quality* gate (is this diff good?) but no *coverage* gate (is every required thing actually present and proven?). The Coverage Engine supplies the missing axis.

---

## 2. Design principles (so the cure isn't worse than the disease)

1. **Machine-checkable beats LLM-judged.** Every requirement must reduce to a probe that returns a hard boolean: a file exists, an endpoint returns 200, a test name passes, a symbol is defined, a string appears in output. LLM judgement is allowed only to *author* probes, never to *be* the probe.
2. **Coverage is a separate gate from quality.** Do not overload the evaluator. The evaluator answers "is this good?"; the Coverage Engine answers "is all of it here?". Both must pass to ship.
3. **Fail-closed.** Unknown coverage = not done. Any unmapped requirement, any probe that errors, any acceptance criterion without a verifying artifact ⇒ `done=false`. This inverts the current fail-open default in the gate.
4. **No new "reached-here" booleans, ever.** Every boolean in the new system must trace to an executed probe with captured stdout/exit-code evidence.
5. **Idempotent + durable.** Coverage state survives Railway redeploys (write to Supabase, mirror to `.harness/`), and re-running a clean coverage check is a no-op.
6. **Cheap by default.** Probes are deterministic shell/AST/HTTP checks — near-zero LLM cost. LLM is invoked once per spec to *extract* criteria, then cached.

---

## 3. The route, 15 moves ahead

These are sequenced so each move de-risks the next and nothing is a dead end. Moves 1–5 are the MVP that closes the false-positive hole; 6–10 harden and integrate; 11–15 are the second- and third-order consequences most plans miss.

### Move 1 — Define the DoD schema as a first-class artifact
Create `.harness/dod.schema.json` and a Pydantic model `src/tao/schemas/dod.py`. A **Definition of Done** for a session is a list of `AcceptanceCriterion`:
```
AcceptanceCriterion = {
  id: str,                # stable, e.g. "AC-3"
  requirement: str,       # human text, traced from the brief
  probe: Probe,           # the machine check that proves it
  severity: "must"|"should",
  source: str,            # where in the brief/spec this came from
}
Probe = {
  kind: "file_exists"|"test_passes"|"http_200"|"symbol_defined"|
        "grep_present"|"cmd_exit_zero"|"json_path_equals",
  args: {...},            # kind-specific
}
```
**Why first:** every later move references this schema. Land the contract before any consumer. The `must`/`should` split is load-bearing — `should` failures warn but don't block, which prevents the system becoming so strict it can never ship (Move 14's failure-of-the-cure risk).

### Move 2 — Build the probe runner (`src/tao/coverage/probes.py`)
A pure function `run_probe(probe, workspace) -> ProbeResult{passed: bool, evidence: str, error: str|None}`. One handler per `kind`. No LLM. Each handler captures real evidence (the matched line, the HTTP status, the pytest node-id result). **Errors are not passes** — a probe that throws returns `passed=False, error=...`. Unit-test every handler against tmp fixtures, including the "no tests/ dir" case that currently fools the judge.

### Move 3 — Build the DoD extractor (`src/tao/coverage/extract.py`)
One LLM call (evaluator role, sonnet — reuse `model_policy.select_model`) that takes the original brief + spec and emits the `AcceptanceCriterion[]` JSON. JSON-discipline identical to `tao_judge` (`first char {`, parse-fail ⇒ raise, never silently empty). Output is **persisted and reviewed once**, then frozen for the session — so coverage is measured against a stable target, not a moving LLM opinion. This is the only LLM in the hot path and it runs once.

### Move 4 — Build the coverage checker (`src/tao/coverage/check.py`)
`compute_coverage(dod, workspace) -> CoverageReport`:
```
CoverageReport = {
  total: int, must_total: int,
  passed: [ac_id...], failed: [ac_id...], errored: [ac_id...],
  must_satisfied: bool,         # ALL must-criteria passed
  coverage_pct: float,          # passed / total
  evidence: {ac_id: ProbeResult},
}
```
`done = must_satisfied` (fail-closed: any errored/unmapped must ⇒ false). This is the single scalar the loop and gate will consume — analogous to the existing judge's `score`, but **derived from executed probes, not from a model's opinion.**

### Move 5 — Wire coverage into the ship gate (the actual fix)
In `session_phases._phase_push`, **before** logging the gate row:
- Run `compute_coverage`.
- Replace the hardcoded `"build_complete": True` / `"tests_passed": True` with the *real* probe-derived values.
- Add `"coverage_satisfied": report.must_satisfied` and `"coverage_pct"` to the `gate_checks` payload (extend `supabase/migration.sql` + the new `coverage_reports` table in the SAME PR per CLAUDE.md's observability rule).
- **If `must_satisfied` is False, the session does NOT report COMPLETE.** Set `status="incomplete"`, keep the Linear issue out of "In Review", and emit the failing AC ids + evidence to the stream. This is the line that stops fake-done.
**Why move 5 not move 1:** by now the schema, probes, extractor, and checker all exist and are tested in isolation; wiring is a thin, low-risk call. Wiring first would mean editing the riskiest file (the live ship path) against unbuilt dependencies.

### Move 6 — Wire coverage into the loop's termination (`tao_loop.run_until_done`)
Add an optional `dod: DoD | None` param. When present, the loop's exit condition becomes `judge.done AND coverage.must_satisfied`. The judge keeps deciding *"is this iteration making progress / is this sub-goal met"*; coverage decides *"is the whole spec covered."* Add a new `LoopResult.reason = "COVERAGE_INCOMPLETE"` so a loop that hits MAX_ITERS with the judge happy but coverage failing reports the truthful reason. Feed `report.failed` back as the next iteration's goal hint ("you still owe AC-3, AC-7") — turning the coverage gap into the worker's to-do list. This closes the loop: the system now self-directs toward uncovered requirements instead of declaring victory.

### Move 7 — Make the evaluator emit structured unmet-requirements
Change `_phase_evaluate`'s prompt to output unmet requirements as a JSON list keyed to AC ids (it already asks for them as prose at line 1015 — make it machine-readable). Cross-check the evaluator's claimed-unmet against the probe-derived `report.failed`. **Disagreement is a signal:** if the LLM says "complete" but a probe says an AC failed, trust the probe and log the divergence to `model-policy-violations.jsonl`-style audit. This catches the evaluator over-scoring partial work (the §1.4 bug) without ripping out the existing evaluator.

### Move 8 — Coverage report durability + resume safety
Write `CoverageReport` to Supabase (`coverage_reports` table) and mirror to `.harness/coverage/<session>.json`. On session resume (`_should_skip_phase` pattern), reload the frozen DoD and last report rather than re-extracting — so a Railway redeploy mid-session doesn't re-run the LLM extractor or lose which ACs were already satisfied. Idempotent re-run of `compute_coverage` on an unchanged workspace must produce an identical report (probes are deterministic).

### Move 9 — Probe authoring guardrails (anti-gaming)
Second-order risk: the **generator** could learn to satisfy probes trivially (write an empty test named after the AC; create a stub file to pass `file_exists`). Counter-measures, built now not later:
- Probe `kinds` are biased toward *behaviour* not *presence*: prefer `test_passes` (named node-id must pass) and `http_200`/`cmd_exit_zero` over bare `file_exists`.
- The extractor (Move 3) is instructed to avoid trivially-gameable probes and to attach a `min_assertions`/`non_trivial` hint where a real behaviour is expected.
- A `should`-severity "spot-check" criterion can require the diff for an AC to touch *non-test* code, so "added a test, changed no logic" is visible.
This is the move most plans omit and the one that determines whether the engine actually works in an adversarial autonomous setting.

### Move 10 — CI workflow + smoke test (per CLAUDE.md gates)
Add `tests/test_coverage_*.py` (probes, extractor JSON-discipline, checker fail-closed cases, "no tests dir" regression). Add a `.github/workflows/coverage-engine.yml` running on PRs touching `src/tao/coverage/**`. Extend `scripts/smoke_test.py` to assert a deliberately-incomplete fixture session reports `coverage_satisfied=False` and does **not** reach COMPLETE — i.e. an automated proof that fake-done is now impossible. This is the meta-DoD: the Coverage Engine's own DoD.

### Move 11 — Backfill + portfolio rollout strategy
Coverage gating will, on day one, flip many "complete" sessions to "incomplete" (because old sessions had no DoD). Plan for it: ship behind `TAO_COVERAGE_ENABLED` (shadow mode first, like `TAO_SWARM_SHADOW`), logging what *would* have been blocked without blocking. Read the shadow data for one sprint, tune probe strictness, then flip to enforcing. This prevents a hard cutover from halting the whole autonomous pipeline overnight — the §14 "cure worse than disease" failure.

### Move 12 — Human-facing coverage surface
The dashboard (`dashboard/lib/phases.ts`, phases UI) gets a coverage panel: green/red per AC with evidence on hover, and a top-line `coverage_pct`. This directly serves CLAUDE.md's "Visible-Progress Mandate" — the user can *watch* which requirements are proven vs missing, instead of trusting a "done" label. An incomplete session links to the exact failing ACs.

### Move 13 — Linear integration: coverage gaps become tickets, not silent skips
When a session ships with `should`-failures or hits MAX_ITERS with `must`-failures, auto-open a Linear sub-issue per failing AC in the target repo's project (reuse the existing `save_issue` + `projects.json` routing in `session_linear.py`). The system never *silently* leaves work undone — every gap is either fixed in-loop (Move 6) or surfaced as a tracked, mergeable action (the autonomy mandate's "actionable artifact, not a dead end" rule).

### Move 14 — Calibration + escape hatch (preventing over-strictness)
A DoD that's too strict never ships; too loose reproduces the original bug. Build calibration in:
- `must` vs `should` split is the primary dial; default new ACs to `should` until proven stable.
- A `coverage_waiver` mechanism: a human (or the board) can mark a specific AC waived-with-reason, recorded durably. Waivers are auditable and expire. This is the pressure-relief valve so a single un-probeable requirement can't permanently jam the pipeline.
- Track false-block rate (sessions blocked by coverage that a human then waives) as a health metric; if it climbs, the extractor is over-generating ACs.

### Move 15 — Close the meta-loop: coverage feeds the judge's own training signal
Long-horizon move. The divergence log from Move 7 (judge/evaluator said done, probe said not) is the dataset for *improving the judge*. Periodically summarize the cases where the per-task judge was over-optimistic and inject that as a system-note into `tao_judge._build_prompt` ("past over-scoring patterns: X"). The Coverage Engine thus becomes the ground-truth that keeps the cheap per-task judge honest over time — turning a one-off gate into a self-correcting completeness system. This is the difference between patching one bug and building an institution that resists the whole *class* of fake-done bugs.

---

## 4. File-level work breakdown

| Move | New/changed file | Type |
|------|------------------|------|
| 1 | `src/tao/schemas/dod.py`, `.harness/dod.schema.json` | new |
| 2 | `src/tao/coverage/probes.py` | new |
| 3 | `src/tao/coverage/extract.py` | new |
| 4 | `src/tao/coverage/check.py` | new |
| 5 | `app/server/session_phases.py` (`_phase_push`), `supabase/migration.sql` | edit |
| 6 | `app/server/tao_loop.py` | edit |
| 7 | `app/server/session_phases.py` (`_phase_evaluate`) | edit |
| 8 | `app/server/coverage_store.py`, `supabase/migration.sql` | new/edit |
| 9 | `src/tao/coverage/extract.py` (probe-authoring rules) | edit |
| 10 | `tests/test_coverage_*.py`, `.github/workflows/coverage-engine.yml`, `scripts/smoke_test.py` | new/edit |
| 11 | `app/server/config.py` (`TAO_COVERAGE_ENABLED`/shadow) | edit |
| 12 | `dashboard/lib/phases.ts`, coverage UI component | edit/new |
| 13 | `app/server/session_linear.py` | edit |
| 14 | `src/tao/coverage/waiver.py`, calibration metrics | new |
| 15 | `app/server/tao_judge.py` (system-note injection) | edit |

---

## 5. Definition of Done for THIS plan (eat our own dog food)

The Coverage Engine is itself done only when:
1. A fixture session with a known-missing requirement reports `coverage_satisfied=False` and **cannot** reach `status=complete` (proven by `smoke_test.py`, Move 10).
2. The `gate_checks` row contains zero hardcoded `True` booleans — every value traces to a probe (grep `session_phases.py` for `: True` in the gate dict returns nothing).
3. The "no tests/ dir" regression test passes — the original judge-fooling case is closed.
4. Shadow mode (Move 11) has run one sprint with a measured false-block rate before enforcement flips on.

Each of these is itself a machine-checkable probe — the plan satisfies its own schema.

---

## 6. Sequencing rationale (why this order survives contact)

- **MVP = Moves 1–5.** After Move 5 the false-positive hole in the *ship gate* is closed even if nothing else lands. Everything before it is a dependency; nothing before it is wasted.
- **Moves 6–7** extend the same fact-based gate into the loop and evaluator — the other two trust-by-reaching-a-line sites — so all three §1 bugs are covered, not just the ship gate.
- **Moves 8–10** make it durable, ungameable, and self-testing (the hardening most plans skip and then regret).
- **Moves 11–14** handle the rollout and the over-correction risk — the system-level consequences of suddenly enforcing truth on a pipeline that previously didn't.
- **Move 15** converts the gate into a learning loop, so this is the last time this class of bug needs a dedicated fix.

The throughline: replace *"I reached the end, therefore done"* with *"every required thing has executed evidence, therefore done — and where it doesn't, here is the exact gap as a tracked action."*
