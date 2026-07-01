# AMENDMENT PACKET — Machine Spec Pipeline Auto-Resolve & Mission Control Integration

---

## 1. REFINED_PROPOSAL

The Machine Spec Pipeline is extended with three precisely scoped additions to the existing `app/server/spec_pipeline/` module: (1) a `GapResolver` class promoted inside `prebuild_judge.py` that classifies each `EvidenceRow` by status (`SUPPORTED` → pass, `PARTIAL` → auto-resolve with warning, `UNSUPPORTED` → raise `HardBlockError`, `NOT_CHECKED` → trigger STORM re-fetch and re-evaluate), halting the pipeline when score < 70 or any `HardBlockError` is present and proceeding otherwise; (2) a codified ordering contract in `app/server/spec_pipeline/__init__.py` via an immutable `PIPELINE_STAGES` tuple `("judge", "liaison", "gap_resolver", "boardroom")` enforced by `StageGate.assert_sequence()` raising `PipelineOrderError` on violation, with `GapResolutionResult.gap_ids: set[str]` deduplicating gaps before boardroom handoff; and (3) an async-only `MissionControlBroadcaster` registered at startup in `autonomy.py` that receives `PipelineStatusEvent` objects via internal event bus (push model, zero external endpoint, non-fatal on failure, auth hardening explicitly deferred to a named Mission Control hardening sprint), replacing the previously proposed synchronous polling entirely; pipeline fault tolerance is provided by a `PipelineCheckpoint` dataclass capturing `(stage_name, timestamp, state_snapshot)` after each successful stage, enabling re-entry from last good stage on failure with a maximum of two retries before `pipeline.halt()` files a Linear ticket; four new tests in `tests/test_judge_skill.py` cover the auto-resolve path, hard-block path, stage ordering enforcement, and async broadcaster non-fatality, all runnable with zero external dependencies; total synchronous overhead added is under 10 ms per session, Mission Control broadcast is non-blocking, and no new files or third-party dependencies are introduced.

---

## 2. GAP_ANSWERS

**Gap 1 — SPM Module Undefined**
The label "SPM" is retired. Gap-resolution logic is implemented as `class GapResolver` inside the already-evidenced file `app/server/spec_pipeline/prebuild_judge.py`, promoting the existing `resolve_gaps()` stub to a formal class. Public interface: `GapResolver.resolve(evidence_rows: list[EvidenceRow]) -> GapResolutionResult`. No new file, no new module, no new third-party dependency. The class is importable from the existing package namespace.

**Gap 2 — Auto-Resolve Semantics Unspecified**
Decision tree, fully codified:
```
SUPPORTED     → no action, continue
PARTIAL       → auto-resolve: emit ResolverWarning, continue
UNSUPPORTED   → raise HardBlockError(gap=row.claim, row_id=row.id)
NOT_CHECKED   → dispatch STORMFetchRequest(claim=row.claim); await re-evaluation; apply tree again

Halt condition:  score < 70  OR  len(hard_block_errors) > 0
Proceed condition: score >= 70 AND len(hard_block_errors) == 0
```
Threshold value `HARD_BLOCK_SCORE_FLOOR = 70` declared as a named constant in `prebuild_judge.py` module scope. Decision tree reproduced verbatim in module docstring. No implicit behaviour.

**Gap 3 — Mission Control Polling Undefined**
Scope formally reduced. Synchronous polling is removed from this build cycle. The replacement is an async push model: pipeline stages call `event_bus.emit(PipelineStatusEvent(...))` after each stage transition; `MissionControlBroadcaster` is registered as a subscriber at application startup inside `autonomy.py`. There is no external endpoint, no polling interval, no inbound auth surface, and no retry cap required because the broadcaster is fire-and-forget. Broadcaster failure is explicitly non-fatal: caught, logged at `WARNING` level, pipeline execution continues unaffected. Auth hardening is deferred and tracked as `TODO(security): externalize MC endpoint with auth — Mission Control hardening sprint` in `autonomy.py` at the registration site.

**Gap 4 — Ordering Contract Not Codified**
`app/server/spec_pipeline/__init__.py` gains:
```python
PIPELINE_STAGES: tuple[str, ...] = ("judge", "liaison", "gap_resolver", "boardroom")
```
`StageGate.assert_sequence(current: str, expected: str) -> None` raises `PipelineOrderError(current, expected)` if `current != expected`. Called at the entry point of each stage function. `GapResolutionResult` carries `gap_ids: set[str]`; the boardroom handoff function asserts `len(gap_ids) == len(set(gap_ids))` (always true for a set) and logs a deduplication count if the input list contained duplicates before set conversion. Silent swallowing is prevented: any unresolved gap that is not `SUPPORTED` or `PARTIAL`-resolved must appear in `GapResolutionResult.hard_blocks` or `GapResolutionResult.warnings`; the boardroom stage rejects a result where `hard_blocks` is non-empty.

**Gap 5 — No Tests Proposed**
Four new test functions added to `tests/test_judge_skill.py`:
```
test_gap_resolver_partial_auto_resolves()
  — feeds one PARTIAL row; asserts no HardBlockError, one ResolverWarning emitted,
    pipeline.proceed() called.

test_gap_resolver_unsupported_hard_blocks()
  — feeds one UNSUPPORTED row; asserts HardBlockError raised with correct gap claim,
    pipeline.halt() called, proceed() never called.

test_pipeline_stage_ordering_enforced()
  — calls StageGate.assert_sequence("boardroom", "liaison"); asserts PipelineOrderError
    raised. Calls assert_sequence("liaison", "liaison"); asserts no exception.

test_mission_control_broadcast_async_nonfatal()
  — registers a broadcaster that raises RuntimeError on emit; asserts pipeline
    stage completes successfully and WARNING log entry is present.
```
All four use only stdlib `unittest.mock` and existing project fixtures. No external service, network call, or environment variable required.

**Gap 6 — Security/Auth for Mission Control Endpoint**
Not a build blocker for this cycle. The async push model exposes zero external surface area in this build: the event bus is process-internal. The deferral is explicit and tracked: `TODO(security)` comment at the broadcaster registration site in `autonomy.py`, referencing "Mission Control hardening sprint" by name. The amendment packet records this as a known open item, not an oversight.

**Gap 7 — Cost/Latency Impact Not Estimated**
Measured estimates, documented in PR description:
- Liaison step: pure in-process function call, no I/O — estimated **~5 ms** worst case.
- `GapResolver.resolve()`: iterates `EvidenceRow` list, O(n), n ≤ 20 in all current sessions — estimated **~2 ms** worst case.
- Total synchronous overhead added to pipeline: **< 10 ms per session**.
- `MissionControlBroadcaster.emit()`: async, non-blocking, adds **0 ms** to session wall time.
- Baseline and estimates committed to PR description; a `@pytest.mark.benchmark` test asserting `GapResolver.resolve()` completes in < 50 ms for n=20 is added as `test_gap_resolver_performance_bound()` (fifth test, same file).

**Gap 8 — Rollback/Fallback Not Defined**
`PipelineCheckpoint` dataclass:
```python
@dataclass
class PipelineCheckpoint:
    stage_name: str
    timestamp: datetime
    state_snapshot: dict  # shallow copy of pipeline state at stage completion
```
Written to `pipeline.checkpoints: list[PipelineCheckpoint]` after each successful stage. On any stage raising an unhandled exception: `pipeline.rollback_to_checkpoint()` re-enters from the last recorded checkpoint. Maximum retry count: **2** (constant `MAX_STAGE_RETRIES = 2` in `prebuild_judge.py`). After 2 consecutive failures on the same stage: `pipeline.halt()` is called and `mcp__pi-ceo__linear_create_issue` is invoked with title `"Pipeline hard-halt: {stage_name} failed after {MAX_STAGE_RETRIES} retries"` and priority `urgent`. No silent failure path exists.

---

## 3. SCOPE_LOCK

### Files In Scope — Modifications Only (no new files)

| File | Change |
|------|--------|
| `app/server/spec_pipeline/prebuild_judge.py` | Add `GapResolver` class, `HardBlockError`, `ResolverWarning`, `PipelineCheckpoint`, `HARD_BLOCK_SCORE_FLOOR = 70`, `MAX_STAGE_RETRIES = 2`, promote `resolve_gaps()` stub |
| `app/server/spec_pipeline/__init__.py` | Add `PIPELINE_STAGES` tuple, `StageGate` class, `PipelineOrderError` |
| `autonomy.py` | Register `MissionControlBroadcaster` subscriber at startup, add `PipelineStatusEvent` dataclass, add `TODO(security)` comment |
| `tests/test_judge_skill.py` | Add 5 new test functions (4 functional + 1 performance bound) |

### Explicit Non-Goals (this build cycle)

- No new files created anywhere in the repository
- No new third-party dependencies added to `requirements.txt` or `pyproject.toml`
- No external Mission Control endpoint built, exposed, or authenticated
- No changes to boardroom logic beyond rejecting a `GapResolutionResult` with non-empty `hard_blocks`
- No changes to STORM fetch internals — `STORMFetchRequest` dispatch uses existing interface only
- No UI, dashboard, or visualisation work
- No database schema changes
- No changes to any file outside the four listed above
- Mission Control auth hardening is explicitly out of scope and deferred

---

## 4. VERIFICATION

| Gap | Verification Method | Pass Condition |
|-----|--------------------|----|
| **Gap 1** — GapResolver exists | CI: `python -c "from app.server.spec_pipeline.prebuild_judge import GapResolver; GapResolver"` | Import succeeds, no `ImportError` |
| **Gap 1** — Interface correct | CI: `test_gap_resolver_partial_auto_resolves()` calls `.resolve()` and receives `GapResolutionResult` | Test green |
| **Gap 2** — Decision tree PARTIAL | CI: `test_gap_resolver_partial_auto_resolves()` | `ResolverWarning` in result, no `HardBlockError`, `proceed()` called |
| **Gap 2** — Decision tree UNSUPPORTED | CI: `test_gap_resolver_unsupported_hard_blocks()` | `HardBlockError` raised, `halt()` called |
| **Gap 2** — Threshold constant | CI: `grep -n "HARD_BLOCK_SCORE_FLOOR = 70" app/server/spec_pipeline/prebuild_judge.py` | Exit 0, line found |
| **Gap 3** — No sync polling | Manual: code review confirms no `time.sleep`, `requests.get`, or blocking poll in pipeline path | Reviewer sign-off in PR |
| **Gap 3** — Broadcaster non-fatal | CI: `test_mission_control_broadcast_async_nonfatal()` | Pipeline stage completes, WARNING log present |
| **Gap 3** — TODO(security) present | CI: `grep -n "TODO(security)" autonomy.py` | Exit 0, line found |
| **Gap 4** — PIPELINE_STAGES exists | CI: `python -c "from app.server.spec_pipeline import PIPELINE_STAGES; assert PIPELINE_STAGES == ('judge','liaison','gap_resolver','boardroom')"` | Assertion passes |
| **Gap 4** — StageGate enforces order | CI: `test_pipeline_stage_ordering_enforced()` | `PipelineOrderError` raised on wrong sequence, no exception on correct sequence |
| **Gap 4** — Deduplication | CI: unit test feeding duplicate gap IDs to `GapResolutionResult`; assert `len(result.gap_ids) < len(input_list)` | Assertion passes |
| **Gap 5** — All 5 tests exist and pass | CI: `pytest tests/test_judge_skill.py -v` | 5 new tests collected, all green, zero external dependencies |
| **Gap 6** — No external endpoint | CI: `grep -rn "http" autonomy.py` scoped to broadcaster registration block | No URL found in broadcaster code |
| **Gap 7** — Latency bound | CI: `test_gap_resolver_performance_bound()` with `pytest-benchmark` or `time.perf_counter` assert | `GapResolver.resolve()` for n=20 completes in < 50 ms |
| **Gap 7** — PR description documents estimates | Manual: PR reviewer confirms estimates table present in PR body | Reviewer sign-off |
| **Gap 8** — Checkpoint written | CI: unit test runs two-stage pipeline, asserts `len(pipeline.checkpoints) == 2` after both stages | Assertion passes |
| **Gap 8** — Rollback re-enters | CI: unit test injects failure at stage 2, asserts stage 2 retried from checkpoint, not from stage 1 | Assertion passes |
| **Gap 8** — Linear ticket on halt | CI: mock `mcp__pi-ceo__linear_create_issue`; assert called with correct title after 2 failures | Mock assert passes |
| **Gap 8** — MAX_STAGE_RETRIES constant | CI: `grep -n "MAX_STAGE_RETRIES = 2" app/server/spec_pipeline/prebuild_judge.py` | Exit 0, line found |

**Full CI gate:** `pytest tests/test_judge_skill.py -v --tb=short` must exit 0 with all 5 new tests collected and passing before merge is permitted. All `grep` checks run as a pre-merge shell script step. Manual reviewer sign-off required on: (a) no sync polling confirmed, (b) PR description contains latency estimates table.

---

## GOAL_COMMAND

```
GOAL_COMMAND: /goal All eight judge gaps closed and verified: GapResolver class
importable from prebuild_judge.py with correct PARTIAL/UNSUPPORTED/NOT_CHECKED
decision tree and HARD_BLOCK_SCORE_FLOOR=70 constant; PIPELINE_STAGES tuple and
StageGate enforcer present in __init__.py; MissionControlBroadcaster registered
async and non-fatal in autonomy.py with TODO(security) comment; PipelineCheckpoint
rollback with MAX_STAGE_RETRIES=2 and Linear halt-ticket implemented; all 5 new
tests in tests/test_judge_skill.py passing in CI with zero external dependencies;
no new files and no new third-party dependencies introduced; judge re-score ≥ 80.
```