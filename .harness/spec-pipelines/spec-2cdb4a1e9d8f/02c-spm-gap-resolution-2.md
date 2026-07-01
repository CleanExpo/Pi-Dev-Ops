# AMENDMENT PACKET — Machine Spec Pipeline v2
## Round 2 Gap Resolution | Pre-Build Clearance Document

---

## 1. REFINED_PROPOSAL

Machine Spec Pipeline v2 introduces a `GapResolver` class in `prebuild_judge.py` that is invoked by the CEO-Board Liaison within the existing `SPM` stage (not as a separate stage), following the canonical `PIPELINE_STAGES = ("judge", "liaison", "SPM", "boardroom")` tuple enforced by `StageGate` in `spec_pipeline/__init__.py`. Auto-resolve semantics are: `PARTIAL` rows warn-and-continue; `UNSUPPORTED` rows raise `HardBlockError` halting the pipeline; `NOT_CHECKED` rows warn-and-continue with structured log entry `[NOT_CHECKED → WARN_CONTINUE]` (STORM re-fetch is dropped — no phantom dependency). After all rows are processed, `GapResolver.resolve()` raises `ThresholdNotMetError` (a lightweight subclass of `HardBlockError`) if `final_score < 70` or `hard_block_count > 0`; score exactly 70 with zero hard blocks proceeds. Mission Control status is broadcast asynchronously via `PipelineStatusEvent` hooks in `autonomy.py` using the internal async event bus only — no HTTP route, webhook, or external socket is registered this sprint; broadcaster failure logs `WARNING` only and does not mutate `PipelineCheckpoint`, which is the single source of truth for pipeline state. Rollback uses a `PipelineCheckpoint` dataclass with max 2 retries before halting and filing a Linear ticket via `mcp__pi-ceo__linear_create_issue`. Six tests in `tests/test_judge_skill.py` cover: (1) `PARTIAL` row warns without `HardBlockError`; (2) `UNSUPPORTED` row raises `HardBlockError`; (3) out-of-order stage call raises `PipelineOrderError`; (4) broadcaster failure is non-fatal and `PipelineCheckpoint.stage` and `.score` are unchanged; (5) score 65 raises `ThresholdNotMetError` and score exactly 70 passes; (6) retry exhaustion calls `mcp__pi-ceo__linear_create_issue` exactly once with correct `team_id` and `project_id`. Security hardening of the broadcast endpoint is explicitly deferred with a scoped TODO in `autonomy.py` confirming internal-bus-only exposure. Net new LOC is capped at 350 across all modified files.

---

## 2. GAP_ANSWERS

**Gap 1 — Stage name inconsistency (`gap_resolver` vs `SPM`)**
The conflict is resolved by establishing `SPM` as the sole canonical stage key. `PIPELINE_STAGES = ("judge", "liaison", "SPM", "boardroom")` in `spec_pipeline/__init__.py` is unchanged from its existing SUPPORTED evidence. `GapResolver` is a class that executes *inside* the `SPM` stage handler — it is not registered as a stage key anywhere. `StageGate` validates against stage keys only; class names are invisible to it. Every reference in the proposal body that previously said `gap_resolver` as a stage label now reads `SPM`. No runtime conflict is possible.

**Gap 2 — STORM re-fetch for NOT_CHECKED rows (phantom dependency)**
STORM is removed from scope entirely. The repo contains no `STORM` class, module, or import hook, and none will be added in this sprint. `NOT_CHECKED` rows receive identical treatment to `PARTIAL` rows: `GapResolver` emits a structured log entry `[NOT_CHECKED → WARN_CONTINUE]` at `WARNING` level and continues processing. This is semantically correct — a `NOT_CHECKED` row has neither supporting nor refuting evidence and cannot justify a hard block. If STORM integration is required in a future sprint, it will be declared as an explicit new dependency with its own import path, module stub, and evidence row before that proposal reaches the judge.

**Gap 3 — Score threshold ≥70 enforcement location and test coverage**
Enforcement is in `prebuild_judge.py`, method `GapResolver.resolve()`, in the return path after the evidence-row loop completes. The logic is: `if final_score < 70 or hard_block_count > 0: raise ThresholdNotMetError(final_score, hard_block_count)`. `ThresholdNotMetError` is a direct subclass of `HardBlockError` with no additional fields beyond `score` and `block_count`. Test 5 (`test_score_below_threshold_raises_error`) asserts two sub-cases: (a) a mock evidence set that resolves to score 65 raises `ThresholdNotMetError`; (b) a mock evidence set that resolves to exactly score 70 with zero hard blocks does *not* raise and returns a passing `ResolverResult`. Both sub-cases run in the same parameterized test function.

**Gap 4 — Security deferral on Mission Control broadcast endpoint**
Confirmed: `PipelineStatusEvent` in `autonomy.py` publishes exclusively to the internal async event bus. No route file in `app/server/routes/` imports or references `PipelineStatusEvent` in this sprint. The TODO marker reads exactly: `# TODO(security-sprint): harden if/when PipelineStatusEvent is exposed externally — currently internal bus only, no network exposure this sprint`. This is a documentation-level deferral, not a live risk. The assertion is mechanically verifiable (see Verification section).

**Gap 5 — Broadcaster failure state consistency**
`PipelineCheckpoint` is the authoritative state store. The event bus is fire-and-forget: `autonomy.py` wraps the broadcast call in `try/except Exception` and on any exception logs `WARNING: broadcaster failure — pipeline state unaffected` without touching `PipelineCheckpoint`. Downstream consumers (boardroom stage, Linear ticket filer) are documented in `ARCHITECTURE.md` addendum to read exclusively from `PipelineCheckpoint`, never from bus state. Test 4 is extended to assert that after a simulated broadcaster exception, `PipelineCheckpoint.stage` equals its pre-broadcast value and `PipelineCheckpoint.score` equals its pre-broadcast value — proving no state mutation occurred.

**Gap 6 — PipelineCheckpoint retry exhaustion → Linear ticket path has no test**
Test 6 (`test_retry_exhaustion_files_linear_ticket`) is added. It mocks `mcp__pi-ceo__linear_create_issue`, constructs a `PipelineCheckpoint` with `max_retries=2`, forces two consecutive `RetryableError` raises from a mock `GapResolver.resolve()`, and asserts: (a) `mcp__pi-ceo__linear_create_issue` is called exactly once; (b) the call includes `team_id` and `project_id` sourced from `.harness/projects.json`; (c) the pipeline raises `HardBlockError` after ticket filing rather than silently exiting. The `.harness/projects.json` path is read via a fixture so the test is not hardcoded to a specific project ID.

**Gap 7 — Complexity budget / RA-1109 compliance**
Net new LOC is capped at 350. Per-file breakdown:

| File | Net New LOC | Purpose |
|---|---|---|
| `prebuild_judge.py` | ~120 | `GapResolver`, `ThresholdNotMetError`, `ResolverResult` |
| `spec_pipeline/__init__.py` | ~30 | `StageGate` order enforcement, `PipelineOrderError` |
| `autonomy.py` | ~50 | `PipelineStatusEvent`, broadcaster try/except, TODO marker |
| `models/checkpoint.py` | ~40 | `PipelineCheckpoint` dataclass, retry counter |
| `tests/test_judge_skill.py` | ~110 | Six tests + fixtures |
| **Total** | **~350** | |

STORM removal eliminates approximately 40 lines of speculative code that would otherwise have been needed. Every new class has at least one directly exercising test. No scaffolding is added without a corresponding tested function. RA-1109 compliance is confirmed: no surface-treatment stubs, no placeholder classes, no TODO-body methods shipped to build.

---

## 3. SCOPE_LOCK

### Files and Modules IN SCOPE

```
prebuild_judge.py
    - class GapResolver
    - class ThresholdNotMetError(HardBlockError)
    - class ResolverResult
    - class HardBlockError (if not already present; otherwise import)

spec_pipeline/__init__.py
    - PIPELINE_STAGES tuple (read-only reconciliation, no new logic)
    - class StageGate (add PipelineOrderError raise on out-of-order call)
    - class PipelineOrderError

autonomy.py
    - class PipelineStatusEvent
    - broadcaster try/except wrapper
    - TODO(security-sprint) marker

models/checkpoint.py  [NEW FILE]
    - dataclass PipelineCheckpoint
      fields: stage, score, retry_count, max_retries, last_error
    - retry exhaustion logic → mcp__pi-ceo__linear_create_issue call

tests/test_judge_skill.py
    - test_partial_row_warns_no_hard_block
    - test_unsupported_row_raises_hard_block_error
    - test_out_of_order_stage_raises_pipeline_order_error
    - test_broadcaster_failure_nonfatal_checkpoint_unchanged
    - test_score_below_threshold_raises_error (parameterized: 65 fails, 70 passes)
    - test_retry_exhaustion_files_linear_ticket

.harness/projects.json  [READ-ONLY — fixture source for team_id/project_id]
ARCHITECTURE.md  [ADDENDUM — one paragraph documenting PipelineCheckpoint as state authority]
```

### Explicit Non-Goals (Out of Scope This Sprint)

- **STORM integration** — no `STORM` class, module, import, or hook of any kind
- **External exposure of `PipelineStatusEvent`** — no HTTP route, webhook, WebSocket, or external socket
- **Security hardening of broadcast endpoint** — deferred to security sprint with scoped TODO
- **Modification of existing judge scoring logic** — `GapResolver` consumes judge output; it does not alter the judge
- **Changes to boardroom stage logic** — boardroom reads from `PipelineCheckpoint`; its internals are untouched
- **New Linear project or team configuration** — `team_id`/`project_id` are read from existing `.harness/projects.json`
- **Dashboard or UI changes** — `PipelineStatusEvent` is internal bus only
- **Any file not listed in the IN SCOPE section above**

---

## 4. VERIFICATION

| Gap | Verification Method | Pass Condition |
|---|---|---|
| **Gap 1** — Stage name reconciled | CI: `grep -r "gap_resolver" spec_pipeline/` returns zero matches; `grep "PIPELINE_STAGES" spec_pipeline/__init__.py` returns tuple containing `"SPM"` | Zero grep hits on `gap_resolver` as stage key; `"SPM"` present in tuple |
| **Gap 2** — STORM removed | CI: `grep -r "STORM\|storm_fetch\|re_fetch" . --include="*.py"` returns zero matches | Zero grep hits |
| **Gap 3** — Threshold enforcement location | CI: `pytest tests/test_judge_skill.py::test_score_below_threshold_raises_error -v` passes both parameterized sub-cases (score=65 raises, score=70 passes) | Green test, both sub-cases |
| **Gap 4** — No external route for PipelineStatusEvent | CI: `grep -r "PipelineStatusEvent" app/server/routes/` returns zero matches | Zero grep hits |
| **Gap 5** — Broadcaster failure does not mutate checkpoint | CI: `pytest tests/test_judge_skill.py::test_broadcaster_failure_nonfatal_checkpoint_unchanged -v`; asserts `checkpoint.stage` and `checkpoint.score` pre/post broadcaster exception are equal | Green test, both field assertions pass |
| **Gap 6** — Retry exhaustion files Linear ticket | CI: `pytest tests/test_judge_skill.py::test_retry_exhaustion_files_linear_ticket -v`; mock asserts `mcp__pi-ceo__linear_create_issue` called exactly once with `team_id` and `project_id` from fixture | Green test, mock call count == 1, correct args |
| **Gap 7** — LOC budget ≤350 | CI: `git diff --stat main | grep "insertions"` after PR; manual: `wc -l` on each in-scope file delta | Net insertions ≤ 350 across all in-scope files |
| **All gaps** — Full test suite | CI: `pytest tests/test_judge_skill.py -v` — all 6 tests green, zero skips | 6/6 pass, 0 skip, 0 error |
| **RA-1109** — No surface-treatment stubs | Manual review gate: PR reviewer confirms zero `pass`-body methods, zero TODO-body functions in shipped code | Reviewer sign-off in PR description |

**CI Entry Point:**
```bash
pytest tests/test_judge_skill.py -v --tb=short
grep -r "gap_resolver" spec_pipeline/ && exit 1 || echo "PASS: no gap_resolver stage key"
grep -r "STORM\|storm_fetch" . --include="*.py" && exit 1 || echo "PASS: no STORM dependency"
grep -r "PipelineStatusEvent" app/server/routes/ && exit 1 || echo "PASS: no external route"
git diff --stat main | awk '/insertions/ {if ($4 > 350) exit 1}' && echo "PASS: LOC within budget"
```

---

## 5. GOAL_COMMAND

```
GOAL_COMMAND: /goal prebuild_judge.py GapResolver implemented and all 6 tests in tests/test_judge_skill.py pass green in CI, PIPELINE_STAGES tuple confirmed as ("judge","liaison","SPM","boardroom") with zero grep hits for "gap_resolver" as a stage key, STORM dependency confirmed absent, PipelineStatusEvent confirmed absent from all route files, net new LOC ≤350 confirmed by diff stat, and PR reviewer has signed off on RA-1109 compliance — pipeline is cleared to proceed to boardroom stage.
```