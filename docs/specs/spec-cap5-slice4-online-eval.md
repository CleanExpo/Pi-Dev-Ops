# SPM Spec — Cap 5 Slice 4: Online Eval, Smallest Safe Version (RA-7014 follow-on)

**Status:** awaiting founder acceptance · **Appetite:** 3 days (grill-locked) · **Date:** 2026-07-08

## 1. Task being planned
Capture real production `feedback_loop` classifier calls as eval candidates, and give the
founder a human-gated CLI that promotes them — as synthetic paraphrases only — into the
blocking `evals/golden/` suite.

## 2. Current project context
Prove-It gate slices 1–3 shipped and blocking (PRs #525–#527, #539). ADR-006 closed 2026-07-08:
Langfuse DROPPED, slice 4 redefined in-repo. Judge Report 73/100 → grill
(`Grills/08b-prove-it-gate-online-eval.md`) resolved all founder-level branches. Baseline:
0.944 full-set / 0.917 dev-split (PR #535); DSPy no-lift (PR #536). `llm_costs` telemetry
live as of today.

## 3. Problem statement
The golden set is 100% synthetic. Real Linear-thread distribution (client phrasing, thread
shapes, edge cases) is never sampled, so drift against real traffic is invisible until a
founder notices misclassified outcomes. No capture path exists: `feedback_loop.py` logs
outcome/provider/model but never the input thread (verified `feedback_loop.py:159–180`).

## 4. Desired outcome
Real prod cases flow into a founder review queue; accepted cases join `evals/golden/` as
synthetic equivalents; any future regression on real-world-derived cases fails the existing
blocking CI gate. Zero client-derived text ever enters git.

## 5. Scope and non-goals
**In:** capture hook (flag-off default) in `_classify_with_claude`; `eval_candidates`
Supabase table + local JSONL fallback; promotion CLI; golden-suite append path; tests.
**Non-goals (grill NO-GOs):** auto-labeling; auto-commit; CI changes; alert/diagnostics
machinery; Linear auto-file; any agent beyond `feedback_loop`; any eval platform; raw
prod-trace storage; self-healing anything.

## 6. Existing capability review (reuse, don't rebuild)
- `swarm/pii_redactor.py::redact(payload, context=, strictness=) -> Result` (RA-1839).
- `evals/judge.py::judge_binary_cli(candidate, rubric, model="sonnet") -> Verdict` — ambient CLI auth, fail-closed.
- `app/server/supabase_log.py::_insert(table, row) -> bool` — fire-and-forget, never blocks the pipeline.
- Golden pattern: `evals/golden/*.yaml` + loader/parametrized test (5 suites, blocking CI).
- Env-flag convention: `TAO_*=1`, default OFF (`TAO_SWARM_ENABLED` precedent).
- DDL precedent: `margot_conversations` (durable prod-write/Mac-read, service_only RLS).

## 7. Specialist board review (condensed)
**Architect:** grill's "local gitignored JSONL" fails on Railway — ephemeral disk, unreachable
from the founder's Mac. Amend storage to Supabase `eval_candidates` (RA-1905 precedent);
local JSONL fallback keeps dev usable offline. Capture must be fire-and-forget AFTER the
classification returns — zero latency and zero new failure modes on the fail-soft path.
**Security:** redact BEFORE any write (`strictness="high"`); raw thread never persisted
anywhere. Supabase already holds client-derived text under service_only RLS
(margot_conversations), so posture is unchanged. Git safety is enforced structurally
(synthetic paraphrase at promotion), not by redactor precision.
**UX (RA-1109):** the CLI must show queue position, candidate text, judge suggestion, and
drafted paraphrase in one screen; accept/edit/reject/skip single-keystroke; empty queue
says so explicitly.
**QA:** every path unit-testable with injected fakes; no provider or Supabase needed in CI.
**Devil's advocate:** judge was calibrated on intent_router, not threads — so suggestions
render as ADVISORY with the calibration caveat printed in the CLI header until a
feedback_loop calibration pass exists (grill rabbit hole, non-blocking).

## 8. Judge challenge
Prior score 73/100 with three gaps: appetite (now grill-DECIDED, 3d), privacy bar (now
structurally moot — NO-GO on client text in git; synthetic paraphrase is the only promotion
path), labeling loop (now grill-DECIDED — judge-suggests/human-decides). The storage gap
found in this spec (Railway ephemeral disk) is resolved in-spec with an existing pattern.
**Score: 100/100 — APPROVE BUILD** for exactly this smallest safe version. Anything beyond
§5's "In" list voids the approval. Build still requires separate founder acceptance of this
spec (spm hard rule).

## 9. Proposed solution
1. **Capture** (`app/server/agents/feedback_loop.py`, ~15 lines + helper): when
   `TAO_EVAL_SAMPLING=1` and a sampling check passes (`TAO_EVAL_SAMPLE_RATE`, default 0.2),
   after a successful classification, fire-and-forget:
   `redact(thread, context="eval_capture", strictness="high")` → row
   `{pipeline_id, thread_redacted, state, days_since, predicted_category, predicted_label,
   confidence, provider, model, captured_at}` → `supabase_log.insert_eval_candidate(row)`;
   fallback append to `.harness/eval-candidates/candidates.jsonl` when Supabase unset.
   Never raises (mirror `_log_sprinkle_event`).
2. **DDL:** `eval_candidates` table appended to canonical `supabase/migration.sql`
   (BIGSERIAL id, fields above, `status TEXT DEFAULT 'pending'` for
   pending/promoted/rejected, service_only RLS) — same PR, per the observability rule.
3. **Promotion CLI** (`scripts/review_eval_candidates.py`): pulls `status=pending` rows
   (Supabase; `--local` reads the JSONL), for each shows candidate + judge suggestion
   (`judge_binary_cli`, advisory header) + LLM-drafted synthetic paraphrase; founder
   accepts (writes paraphrase + founder label to `evals/golden/feedback_loop.yaml`, marks
   row promoted), edits, rejects (marks rejected, writes nothing), or skips. Only this
   human-accept path writes dataset files.
4. **Golden suite:** `evals/test_feedback_loop_golden.py` — loads the yaml, runs the
   keyword-tier assertions code-checkably; grows as cases are promoted. Starts with 2 seed
   cases synthesized from the existing 36-case experiment set so CI exercises the loader
   from day one.
5. **Gitignore:** add `.harness/eval-candidates/`.

## 10. UX requirements
One-screen review; single-keystroke actions; explicit empty state ("queue empty — capture
flag is {ON|OFF} in prod"); accept prints the exact yaml block written; totals on exit.

## 11. Technical requirements
Python 3.11, type hints, files <300 lines, functions <40; capture helper pure enough to
unit-test with injected redactor/inserter; no new dependencies; CLI runs via `uv run`.

## 12. Security / privacy requirements
Raw thread text exists only in memory; redacted-only at rest (Supabase service_only / local
gitignored); synthetic-only in git — a test asserts no `eval_candidates`-sourced string is
written by any non-CLI path, and the CLI test asserts the yaml write contains the paraphrase,
never `thread_redacted`. Flag default OFF; enabling in Railway is a founder env change.

## 13. Verification plan
`uv run pytest tests/test_eval_capture.py tests/test_review_cli.py -q` (fakes; no network);
`uv run pytest evals -q` (suite still green, new loader included); `uv run ruff check`;
pglast parse of migration.sql; manual: run CLI against 3 synthetic candidates seeded into
the local JSONL, promote 1, reject 1, skip 1, verify yaml + statuses.

## 14. Loop / stress testing
PII-seeded fixtures (emails, phones, names) must never appear in any written artifact
(capture test asserts on the fake inserter's received rows); capture under Supabase-down
(inserter returns False) must not raise or slow the classifier (timed test); sampling rate
0/1 boundary tests; CLI against empty/malformed rows.

## 15. Acceptance criteria (all mandatory)
1. Flag OFF (default): zero behavioural change; capture code unreachable (test).
2. Flag ON: successful classification → exactly one redacted candidate row; classifier
   latency/result unchanged; failures never propagate (tests).
3. No code path except CLI human-accept writes to `evals/golden/` (test + grep audit).
4. Git contains synthetic text only (CLI write-path test asserts paraphrase-not-source).
5. `uv run pytest evals -q` and full local gates green.
6. DDL in canonical migration.sql, pglast-clean, service_only RLS.
7. RA-1109: CLI meets §10 (manual click-test in PR's Manual verification path).

## 16. Goal command
`/goal Implement docs/specs/spec-cap5-slice4-online-eval.md — all 7 acceptance criteria
green via the §13 commands, on branch feature/ra7014-online-eval-slice4, PR with Manual
verification path, no scope beyond spec §5.`

## 17. Implementation sequence
(1) DDL + gitignore + capture helper with tests → (2) wire flag-gated capture into
feedback_loop + latency test → (3) promotion CLI + tests + 2 seed golden cases + loader
test → (4) run §13, PR, gate green. Rabbit holes to carry in the PR body: redactor eval on
real threads before flipping the flag ON in Railway; feedback_loop judge calibration pass
before dropping the ADVISORY header.

## 18. Session-handoff seed
Cap 5 slice 4 specced (this file) after judge 73/100 → grill 08b (all branches resolved)
→ spm 100/100 APPROVE BUILD. Storage amended grill→spec: Supabase eval_candidates (Railway
ephemeral disk), fallback local JSONL. Build not started; awaiting founder spec acceptance.
First command: read this spec, then run §16's /goal.

## 19. Final recommendation
Build it in the next 3-day window exactly as scoped. The design makes the privacy NO-GO
structural rather than procedural, reuses five existing components, and its only genuinely
new surface (the CLI) is founder-facing and click-testable. Reject any mid-build urge to
add alerting, more agents, or auto-anything — that evidence-gathering is what the promoted
cases themselves are for.
