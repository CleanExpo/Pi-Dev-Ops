# SPM Build Slice: Senior Harness provenance in Pi-CEO

**Status:** Judge-approved reduced scope for implementation.
**Decision:** Implement only the non-authorizing `off`/`observe` transport. `enforce` must fail closed until a separately trusted external validator is installed.

## Literal objective

Make the Senior Harness, rather than an LLM, the eventual authority above Pi-CEO execution without allowing Pi-CEO, an API caller, a resumed session, or a worker to mint its own permission.

## Current build slice

Pi-CEO may receive and durably retain a safe correlation projection for an externally issued Harness admission and Unlazy reservation. This slice does not validate, grant, or infer execution authority.

The only request fields are:

- `senior_harness_admission_ref: str | None`
- `senior_harness_reservation: dict | None`

The reservation projection is closed to:

- `schema_version`
- `reservation_ref`
- `task_id`
- `plan_id`
- `node_id`
- `worker_id`
- `worker_context_id`
- `base_sha`
- `node_contract_digest`

Pi-CEO must never accept or persist the signed receipt, MAC, HMAC key, controller state path, full TaskContract, full plan, routing request, `authority`, `reserved`, or caller-controlled enforcement mode.

## Deployment modes

- `off` is the default and preserves legacy execution. It retains no caller-supplied Harness projection.
- `observe` validates the safe projection shape, deep-copies valid correlation metadata, and reports present, missing, or malformed status. It never blocks legacy execution and never labels the projection as authority.
- `enforce` is reserved but unavailable in this slice. Every session creation attempt must fail before in-memory insertion, persistence, or task scheduling. There is no fallback.

The mode is deployment-controlled, never request-controlled.

## Parallel execution boundary

A `/api/build/parallel` request carrying either Harness field is rejected. Pi-CEO must not silently discard an admission reference, and one external reservation cannot be copied to a parent and multiple workers. The Senior Harness must reserve each leaf and submit each single-session build independently.

## Persistence boundary

Carry the safe projection through the request route, `create_session`, `BuildSession`, local JSON save/restore, Supabase checkpoint JSONB, Supabase recovery, and the safe API projection. No database migration is required.

## Judge Report

### Decision and score

**APPROVE BUILD: 100/100 for this reduced observe-only slice.** This score does not approve enforcement or claim the Harness controls Pi-CEO execution yet.

| Category | Score | First-source basis |
|---|---:|---|
| First-source evidence | 25/25 | Current request model, route forwarding, session lifecycle, persistence, recovery, controller, scheduler, and migration were inspected at the exact branch state. |
| Clear user/business problem | 20/20 | The slice makes external Harness provenance measurable without repeating the self-authorizing LLM failure. |
| Reuse of existing capability | 15/15 | Reuses `BuildRequest`, `BuildSession`, local JSON, existing checkpoint JSONB, and external controller/scheduler receipts. |
| Security/privacy safety | 15/15 | Closed safe projection; no secrets, signed receipts, MACs, controller paths, or authority booleans enter the public-read checkpoint. |
| UX clarity | 10/10 | API/session telemetry says `off`, `missing`, `malformed`, or `observed`; none says approved or authorized. |
| Testability | 10/10 | Every write boundary, restore path, pre-side-effect fail-closed path, fan-out rejection, and mutation control is deterministic. |
| Cost/control simplicity | 5/5 | No dependency, schema migration, provider call, model call, or new scheduler. |

### Devil's advocate result

The largest risk is mistaking correlation metadata for permission. The slice prevents that by naming it an observation, omitting all authority fields, making `off` the default, and making unavailable `enforce` fail before any side effect. The second risk is silent provenance loss or reservation reuse across Pi-CEO fan-out; Harness-bearing parallel requests are rejected.

## Acceptance gates

1. Legacy request payloads and every internal legacy caller behave unchanged in `off`.
2. Unknown or secret-like reservation keys are never persisted or returned.
3. `observe` deep-copies valid metadata and records explicit non-authority status.
4. Missing/malformed observation never blocks in `observe` and never becomes an authority claim.
5. `enforce` denies before `_sessions`, disk/Supabase persistence, or `asyncio.create_task` changes.
6. Local JSON and Supabase recovery preserve only the safe projection.
7. Harness-bearing parallel requests fail before parent creation or cloning.
8. Focused route, lifecycle, persistence, checkpoint, recovery, and orchestrator tests pass.
9. Exact branch diff passes lint, whitespace, independent review, and release receipt gates.

## Explicitly deferred

- An external signed lease validator with expiry, replay prevention, exact target/base binding, and independently retained receipt lookup.
- Enforced runtime admission at create, resume, restore, and root fan-out.
- Candidate/result authority after checkout mutation.
- Any production claim that the Senior Harness already controls Pi-CEO execution.
