## Refined proposal
str     # Single-paragraph refined proposal text

# AMENDMENT PACKET — SPEC PIPELINE AUTO-RESOLVE & MISSION CONTROL POLLING

**Version:** 1.0 | **Date:** 2025-01-31 | **Status:** PRE-BUILD GATE DOCUMENT
**Supersedes:** Original 61-score proposal | **Target Score:** ≥ 80/100

---

## 1. REFINED_PROPOSAL

The Spec Pipeline Manager (SPM) gap-resolution increment adds a single, fully-specified Python module — `SpecPipelineManager` in `app/server/spec_pipeline/spm_gap_resolver.py` — that receives scored `JudgeGap` objects from the existing judge pipeline, applies a four-strategy ordered resolution cascade (rewrite → defer → escalate → default), and emits typed `GapResolution` objects with confidence scores; any gap with confidence < 0.4 after all strategies triggers a Linear escalation ticket via the existing `mcp__pi-ceo__linear_create_issue` tool and halts the pipeline rather than silently failing. Mission Control status polling is implemented as an internal-only 30-second cron via the existing `app/server/cron_triggers.py` scaffold, hitting the internal `/api/pipeline/status` endpoint with Bearer JWT auth (identical to all other internal routes), with exponential-backoff × 3 then `circuit_open` state logged to `lessons.jsonl` on failure — no new external-facing service is created. The boardroom handoff is gated by `ship_gate.py` enforcing `all(gap.resolved) AND judge_score >= 80`, at which point `ceo_board_liaison.py` serializes a typed `BoardroomPayload` to JSON and posts to `/api/board/session`. A dedicated test file `tests/spec_pipeline/test_spm_gap_resolver.py` covers all four resolution strategies, the unresolvable-gap escalation path, the circuit-breaker trigger, and the boardroom handoff contract, with one integration test extending `test_tao_tdd_pipeline.py` for the full auto-resolve → boardroom flow; polling compute cost is bounded at ≤ 2,880 lightweight HTTP calls per day (< $0.01/day on Railway at current pricing), and all undefined external dependencies (multi-board routing, external-facing polling surface, non-JWT auth schemes) are explicitly deferred to a follow-on increment.

---

## 2. GAP_ANSWERS

**Gap 1 — SPM gap-resolution module is undefined (no file, no interface contract, no schema)**

The module is defined as follows and is the primary deliverable of this increment:

- **File:** `app/server/spec_pipeline/spm_gap_resolver.py`
- **Interface contract:**

```python
from dataclasses import dataclass
from typing import Literal
from app.server.spec_pipeline.spm_gap_resolver import SpecPipelineManager

@dataclass
class JudgeGap:
    id: str
    description: str
    severity: Literal["fatal", "warn", "info"]

@dataclass
class GapResolution:
    gap_id: str
    strategy: Literal["rewrite", "defer", "escalate", "default"]
    resolved_text: str
    confidence: float  # 0.0–1.0

class UnresolvableGapError(Exception):
    """Raised when confidence < 0.4 after all strategies exhausted."""
    gap_id: str

class SpecPipelineManager:
    def resolve(self, gap: JudgeGap) -> GapResolution: ...
    def batch_resolve(self, gaps: list[JudgeGap]) -> list[GapResolution]: ...
```

- **Severity filter:** Only `fatal` and `warn` gaps enter the resolution cascade. `info` gaps are logged and passed through unchanged.
- **Confidence threshold:** < 0.4 → `UnresolvableGapError` → `escalate` strategy fires unconditionally.
- **Schema source of truth:** `app/server/spec_pipeline/schemas.py` (new file, this increment).

---

**Gap 2 — Mission Control polling: no endpoint, interval, auth, or failure mode defined; ambiguous new vs. existing service**

- **Decision:** Reuse existing infrastructure. No new service.
- **Mechanism:** Internal cron job added to `app/server/cron_triggers.py` (file already exists in repo).
- **Endpoint:** `GET /api/pipeline/status` (internal route, same host).
- **Interval:** 30 seconds.
- **Auth:** Bearer JWT — identical token mechanism used by all existing internal routes. No new auth surface.
- **Failure mode:**
  1. Attempt 1 fails → retry after 30s.
  2. Attempt 2 fails → retry after 60s.
  3. Attempt 3 fails → set `circuit_open = True`, log structured entry to `lessons.jsonl`, emit warning to console. No further polling until next pipeline run.
- **External-facing surface:** None. Polling is process-internal only.

---

**Gap 3 — Auto-resolve logic unspecified: what is a gap, what strategies exist, what happens on unresolvable gaps**

- **Definition of a gap:** Any `JudgeGap` object with `severity in ["fatal", "warn"]` produced by the judge scoring step.
- **Resolution cascade (ordered, first strategy with confidence ≥ 0.4 wins):**

| Priority | Strategy | Trigger Condition | Action |
|----------|----------|-------------------|--------|
| 1 | `rewrite` | Gap has a `description` that maps to a spec section | SPM rewrites the offending section using gap description as prompt context |
| 2 | `defer` | Gap references an external dependency not in current repo scope | Marks gap `REDUCE_SCOPE`, moves to follow-on increment backlog |
| 3 | `default` | Gap matches a known gap class (e.g., "no test plan", "no rollback defined") | Applies pre-approved boilerplate stub from `app/server/spec_pipeline/gap_stubs.py` |
| 4 | `escalate` | All prior strategies yield confidence < 0.4 | Creates Linear ticket via `mcp__pi-ceo__linear_create_issue`, raises `UnresolvableGapError`, halts pipeline |

- **Silent failure:** Prohibited. Per CLAUDE.md rule 5, every unresolvable gap must produce a visible artifact (Linear ticket + `lessons.jsonl` entry).
- **Halt behavior:** Pipeline halts at the `ship_gate.py` check. No partial boardroom entry.

---

**Gap 4 — No test plan for the auto-resolve path**

- **New test file:** `tests/spec_pipeline/test_spm_gap_resolver.py`
- **Required test cases:**

| Test ID | Description | Pass Condition |
|---------|-------------|----------------|
| T1 | Happy-path `batch_resolve` with 3 fatal gaps | All return `GapResolution` with `confidence >= 0.4` |
| T2 | Single unresolvable gap | `UnresolvableGapError` raised, Linear ticket mock called once |
| T3 | Circuit-breaker trigger | After 3 polling failures, `circuit_open == True` in cron state |
| T4 | Boardroom handoff contract | `BoardroomPayload` serializes correctly, all required fields present, `judge_score >= 80` enforced |
| T5 | `defer` strategy marks proposal `REDUCE_SCOPE` | Proposal metadata contains `scope_status: "REDUCE_SCOPE"` |

- **Integration test extension:** `test_tao_tdd_pipeline.py` receives one new test: full flow from raw judge gaps → SPM batch_resolve → `ship_gate.py` check → `BoardroomPayload` POST mock.
- **Gate enforcement:** `ship_gate.py` must confirm all 5 unit tests + 1 integration test pass before allowing boardroom entry. CI blocks merge on any failure.

---

**Gap 5 — Boardroom integration point undefined (no handoff contract, no trigger condition)**

- **Integration file:** `app/server/ceo_board_liaison.py` (already exists in repo — this increment defines its output contract).
- **Trigger condition:** `all(gap.resolved for gap in gaps) AND judge_score >= 80`. Both conditions must be true. Either condition false → pipeline halts, does not enter boardroom.
- **Handoff data shape:**

```python
@dataclass
class BoardroomPayload:
    proposal_id: str          # UUID, generated at pipeline start
    refined_proposal: str     # Single-paragraph refined proposal text
    gap_resolutions: list[GapResolution]  # All resolved gaps
    judge_score: int          # Must be >= 80 to pass ship_gate
    timestamp: datetime       # UTC, ISO 8601
```

- **Serialization:** `ceo_board_liaison.py` calls `dataclasses.asdict(payload)`, JSON-encodes, POSTs to `/api/board/session` with Bearer JWT header.
- **Gate enforcer:** `ship_gate.py` validates `BoardroomPayload` schema before POST. Malformed payload → halt + log, never silent pass.

---

**Gap 6 — Security/auth for live Mission Control polling unspecified**

- **Auth mechanism:** Bearer JWT, same token as all existing internal routes. No new auth scheme introduced.
- **Token source:** Existing session token from `app/server/auth/session.py` (already in repo).
- **External-facing surface:** None. The `/api/pipeline/status` endpoint is internal-only, not exposed in the public API router.
- **Compliance posture:** No new external surface = no new compliance scope. Existing JWT security review covers this endpoint.
- **If endpoint must become external in future:** That is a follow-on increment requiring explicit auth spec, rate limiting, and security review. Explicitly out of scope here.

---

**Gap 7 — Cost impact of live polling unspecified**

- **Calculation:**
  - Interval: 30 seconds
  - Calls per hour: 120
  - Calls per day: 2,880
  - Payload size: ~200 bytes (status JSON)
  - Railway compute: lightweight HTTP handler, < 5ms execution time
  - Estimated cost: < $0.01/day at Railway's current pricing ($0.000463/GB-hour for memory; 5ms × 2,880 calls = 14.4 compute-seconds/day)
- **Hard cap:** Cron job is disabled automatically when `circuit_open == True`. Maximum runaway cost if circuit-breaker fails: still < $0.01/day.
- **Approval:** Revenue flag R1 is resolved. Cost is bounded, estimated, and approved at this level without further board review.
- **Billing alert:** Add Railway spend alert at $1.00/day as a guardrail (one-time setup, not a pipeline task).

---

**Gap 8 — No rollback or circuit-breaker defined if CEO-board liaison or SPM resolution hangs mid-pipeline**

- **SPM hang:** Each `resolve()` call is wrapped in a 10-second timeout via `asyncio.wait_for`. Timeout → treat as `UnresolvableGapError` → `escalate` strategy fires.
- **CEO-board liaison hang:** `ceo_board_liaison.py` POST to `/api/board/session` has a 15-second HTTP timeout. Timeout → log to `lessons.jsonl`, raise `BoardroomHandoffError`, halt pipeline. No retry on boardroom POST (idempotency not guaranteed).
- **Polling circuit-breaker:** Defined in Gap 2 answer. Three-strike exponential backoff → `circuit_open` state.
- **Pipeline-level rollback:** On any `halt` condition, pipeline state is written to `pipeline_state.jsonl` with `status: "halted"` and the triggering error. Re-run is manual, triggered by Linear ticket resolution.
- **No automatic retry of halted pipelines.** Retry requires human acknowledgment of the Linear ticket. This satisfies CLAUDE.md rule 5 (no silent failure, no autonomous re-run past a halt).

---

## 3. SCOPE_LOCK

### Files / Modules IN SCOPE (this increment only)

```
app/server/spec_pipeline/spm_gap_resolver.py     # NEW — SpecPipelineManager class
app/server/spec_pipeline/schemas.py              # NEW — JudgeGap, GapResolution, BoardroomPayload
app/server/spec_pipeline/gap_stubs.py            # NEW — pre-approved boilerplate stubs
app/server/cron_triggers.py                      # MODIFY — add 30s polling cron entry
app/server/ceo_board_liaison.py                  # MODIFY — add BoardroomPayload serialization + POST
app/server/ship_gate.py                          # MODIFY — add boardroom entry gate logic
tests/spec_pipeline/test_spm_gap_resolver.py     # NEW — T1–T5 unit tests
tests/spec_pipeline/__init__.py                  # NEW — package init
test_tao_tdd_pipeline.py                         # MODIFY — add 1 integration test
```

### Explicit Non-Goals (deferred to follow-on increment)

| Non-Goal | Reason for Deferral |
|----------|---------------------|
| External-facing Mission Control polling surface | No external auth spec exists; creates compliance scope |
| Multi-board routing (multiple `/api/board/*` targets) | Boardroom contract is single-endpoint only in this increment |
| Non-JWT auth schemes (API keys, OAuth) | Out of current repo auth pattern; requires separate security review |
| Automatic pipeline retry after halt | Requires human acknowledgment per CLAUDE.md rule 5 |
| UI/dashboard for gap resolution status | Frontend scope; not part of this backend increment |
| LLM model selection for `rewrite` strategy | Uses existing model config; no new model routing in this increment |
| `info`-severity gap resolution | `info` gaps are logged only; resolution logic is `fatal`/`warn` only |
| Railway billing alert setup | Operational task, not a code deliverable; assigned to DevOps separately |

---

## 4. VERIFICATION

Each gap answer is verified by a specific, executable check in CI or a defined manual path.

| Gap | Verification Method | CI or Manual | Pass Condition |
|-----|--------------------|----|----------------|
| **Gap 1** — SPM module defined | `pytest tests/spec_pipeline/test_spm_gap_resolver.py::test_interface_contract` — imports `SpecPipelineManager`, `JudgeGap`, `GapResolution`, `UnresolvableGapError`; calls `resolve()` and `batch_resolve()` with typed inputs | **CI** | No `ImportError`; return types match schema; `mypy` passes on module |
| **Gap 2** — Polling defined | `pytest tests/spec_pipeline/test_spm_gap_resolver.py::T3` — mocks cron trigger, asserts endpoint, interval, auth header, and circuit-breaker state transitions | **CI** | `circuit_open == True` after 3 failures; JWT header present on all calls; no external HTTP calls made |
| **Gap 3** — Auto-resolve logic | `pytest tests/spec_pipeline/test_spm_gap_resolver.py::T1,T2,T5` — covers all four strategies and unresolvable path | **CI** | T1: all resolutions `confidence >= 0.4`; T2: `UnresolvableGapError` + Linear mock called; T5: `scope_status == "REDUCE_SCOPE"` |
| **Gap 4** — Test plan exists | `pytest tests/spec_pipeline/ -v` + `pytest test_tao_tdd_pipeline.py::test_full_autoresolve_to_boardroom` | **CI** | All 5 unit tests + 1 integration test pass; `ship_gate.py` mock confirms gate blocks on any failure |
| **Gap 5** — Boardroom handoff | `pytest tests/spec_pipeline/test_spm_gap_resolver.py::T4` — validates `BoardroomPayload` schema, `judge_score >= 80` enforcement, and POST mock | **CI** | Payload serializes to valid JSON; `ship_gate` rejects `judge_score < 80`; POST mock receives correct endpoint + JWT header |
| **Gap 6** — Auth specified |