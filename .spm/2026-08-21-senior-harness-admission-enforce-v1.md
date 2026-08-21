# SPM Build Slice: Senior Harness admission enforcement v1

**Status:** Judge-approved for implementation.
**Predecessor:** `2026-08-21-senior-harness-pi-ceo-observe-slice.md`

## Objective

Install a parent-owned, short-lived, single-use authority above Pi-CEO so an LLM, API caller, Pi-CEO worker, resumed session, or internal fan-out cannot mint or reuse its own execution permission.

## Authority split

- The external Senior Harness owns parent reservation, child derivation, release, and revocation.
- Pi-CEO owns only public-key verification, exact target comparison, atomic child consumption, and active-lease assertion.
- One child lease binds one Unlazy leaf to one worker context and one Pi-CEO session.
- Pi-CEO never imports issuer operations or receives the private signing key.
- `/api/build/parallel` remains denied in `enforce`; the external Harness derives one child per leaf and submits individual `/api/build` requests.

## Signed target

The Ed25519 claim binds the source kind, source ID and immutable source version; normalized repository; exact objective and scope digests; plan, node, reservation, worker and worker-context identities; base SHA; node-contract digest; audience; issue and expiry times; signer key ID; and a claim digest.

Normalization is deterministic:

- Repository HTTPS/SSH forms lose credentials, query, fragment, trailing slash and `.git`; host and owner/repository are lowercased.
- Objective uses Unicode NFC and LF newlines without lowercasing or collapsing internal whitespace.
- Scope recursively normalizes strings, sorts keys, rejects non-finite numbers and unsupported values, and uses compact canonical JSON.

Linear admissions bind `source_version` to authoritative `updatedAt`. The parent authority refreshes it immediately before consume; a mismatch is stale. A resume after expiry requires a newly derived child.

## Durable authority store

Add private `senior_harness_admissions` storage with parent/child lineage, signed immutable target fields, `reserved|consumed|released|revoked|expired` terminal state, TTL, audience, claim digest, signer key ID, consumption session, and terminal timestamps/reason.

Narrow database functions atomically reserve a parent, derive a child, consume a child, release, revoke, and assert active. One conditional update is the single-use consume boundary. Zero returned rows is denial. Revoking a parent revokes every active descendant. Released, revoked, expired, or consumed records never reactivate.

## Pi-CEO enforcement points

1. Preallocate the session ID, validate and atomically consume the child before `_sessions`, persistence, or scheduling.
2. Assert the consumed binding as the literal first operation of `run_build`, before logs, source sync, clone, provider, or model work.
3. Restore/recovery requires a fresh derived child when the prior lease is no longer active; no persisted correlation field counts as authority.
4. Root `fan_out` remains denied before parent insertion, clone, or Opus decomposition.
5. Remove the consumer credential from any Agent SDK subprocess environment.

## Judge Report

### Decision and score

**APPROVE BUILD: 100/100 for enforce v1.** Production enablement remains evidence-gated after implementation, independent review, database replay, and exact deployment configuration.

| Category | Score | First-source basis |
|---|---:|---|
| First-source evidence | 25/25 | Exact current Pi-CEO ingress, session, resume, fan-out, persistence, Supabase, Linear, Mesh, Nexus approval, scheduler and control-plane code inspected. Local PostgreSQL 15 is accepting connections for real atomicity tests. |
| Clear user/business problem | 20/20 | Prevents the LLM/runtime from self-authorizing and closes the repeated drift/spin failure at the execution boundary. |
| Reuse of existing capability | 15/15 | Reuses the observation transport, Unlazy leaf reservation bindings, existing Supabase migration pattern, local PostgreSQL, and installed Ed25519 library; does not overload Mesh/Nexus semantics. |
| Security/privacy safety | 15/15 | Private issuer key, public consumer keys, private table, closed audience, TTL, one-time consume, immutable claim, replay denial, revocation, and no signed claim in public checkpoints. |
| UX clarity | 10/10 | `off`, `observe`, and `enforce` stay deployment-controlled; denial differentiates missing, stale, invalid, consumed, revoked, and unavailable authority without claiming model judgment. |
| Testability | 10/10 | Credential-free mutation tests plus real concurrent PostgreSQL consume/revoke/replay tests; side-effect sentinels at every ingress. |
| Cost/control simplicity | 5/5 | One declared existing dependency, one private table, narrow functions, no second scheduler, no provider/model call in authority decisions. |

### Existing capability decision

Linear dual-signal remains a source of external intent but is not authority. Mesh contributes only its atomic-reservation pattern. Nexus contributes only state-machine lessons. Neither is reused as the admission record because runners can self-claim/auto-approve and neither binds immutable scope plus one-time audience.

### Bloat deletion test

- No generic policy engine.
- No Pi-CEO issuer API.
- No internal authoritative fan-out.
- No duplicate request transport.
- No HMAC reuse across scheduler, controller, and admission domains.
- No new model, provider, UI, or runtime dependency beyond explicit `cryptography` declaration.

## Acceptance gates

1. Signature or any bound-field mutation fails; unknown/revoked key IDs fail.
2. Two concurrent consumes yield exactly one winner in real PostgreSQL.
3. Parent revoke invalidates active children; released/expired/consumed leases cannot replay.
4. A lease cannot cross worker, session, repository, objective, scope, source version, base SHA, node, reservation, or audience.
5. Denial precedes `_sessions`, disk/Supabase writes, clone, provider/model calls, output logs, or task scheduling.
6. `off` and `observe` remain backward compatible.
7. `enforce` parallel requests fail before parent creation, clone, or decomposition.
8. Migration applies idempotently in the disposable local PostgreSQL sandbox and SQL security/atomicity tests pass.
9. `cryptography` becomes a direct pinned project dependency.
10. Focused and full repository suites, lint, whitespace, mutation controls, independent exact-SHA review, and release receipt pass.

## Production boundary

Implementation and local tests do not enable production `enforce`. Enablement additionally requires provisioned issuer/consumer identities, private signing key outside Pi-CEO, public key ring, private database grants, Linear authoritative refresh, revocation path, and a live smoke proving one accepted child and one replay denial.
