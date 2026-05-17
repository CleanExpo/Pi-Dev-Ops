# ADR 002: Tenant identification — slug column + BrandConfig-driven config + RLS via current_setting + CI/CD guardrail

**Date:** 2026-05-15
**Status:** Accepted

## Context

The Pilot bot is internal-only in v1 but architected for v2 productization into a Unite-Group client offering (per the `[[agency-tinder-game-design-2026-05-15]]` spec drafted earlier today). Q1's `fingerprint` resolution already gestured at tenant-scoped behaviour (semantic-dedup ON for Phill's own brand, OFF by default for client tenants). The grill needed an explicit answer for HOW tenancy is identified before downstream config (dedup flag, pillar overrides, audit-log scoping) can land.

Three shapes were on the table:
- **A — `tenant_id` UUID column + RLS** (standard multi-tenant SaaS pattern).
- **B — Per-tenant Supabase project** (hard isolation, heaviest infra).
- **C — `tenant_slug` column derived from the existing `BrandConfig` infrastructure** (reuses `Synthex/packages/brand-config/src/brands/{slug}.ts`).

A direct context signal: `[[portfolio-health-snapshot-2026-05-14]]` surfaced that Margot's own `unite-group-ops` Supabase had RLS disabled on all 6 `margot_*` tables for 17 days. This decision is the remediation pattern for the broader portfolio.

## Decision

**Shape C.** Single Supabase project. `tenant_slug` (VARCHAR) on every Pilot table, derived from BrandConfig filename. RLS isolates via `tenant_slug = current_setting('app.current_tenant_slug')`. Per-tenant Pilot config (semantic_dedup_enabled, pillar overrides, cadence) lives in a new `pilotConfig` field inside the BrandConfig TypeScript file.

**Type-level separation of `tenant` and `brand`:**
```ts
export interface TenantConfig {
  tenant_slug: string;
  billing_tier: 'pro' | 'enterprise';
  brands: Record<string, BrandConfig>; // 1:N future-proofed
}
export interface BrandConfig {
  brand_slug: string;
  pilotConfig: {
    semantic_dedup_enabled: boolean;
    // + future tenant-scoped Pilot flags
  };
  // ... existing brand assets (voice, colors, logos)
}
```

V1 enforces `Object.keys(brands).length === 1 && tenant_slug === brand_slug`. The envelope exists today so v2 can lift the constraint without a schema refactor.

**Two non-negotiable guardrails:**

1. **CI/CD RLS check** — GitHub Action (pgTAP or equivalent) running against a shadow Postgres on every PR. Asserts RLS is enabled on every `pilot_*` table AND `SELECT * FROM pilot_suggestions` returns 0 rows without `app.current_tenant_slug` set. Build fails on either condition. Direct remediation for the Margot audit finding.
2. **Type-safe tenant/brand separation** — the `TenantConfig` envelope is mandatory even when tenant ≡ brand. Conflating them in types locks out the agency-client expansion.

## Consequences

**Easier:**
- Reuses existing BrandConfig infrastructure → zero new auth surface, single Supabase project.
- TypeScript autocompletion across the swarm for tenant config.
- Per-tenant config changes are PR-reviewable diffs against the BrandConfig file (not opaque DB-row edits).
- CI/CD guardrail closes the Margot RLS leak class permanently — not "we'll be careful," but "build fails if you regress."

**Harder:**
- Schema migration: every `pilot_*` table gets `tenant_slug` NOT NULL + RLS policy + index. Migration is reversible (drop the column + policy) but downstream consumers reading without a tenant context will break loudly — that's the point.
- RLS policies need session-level `SET app.current_tenant_slug` on every connection. Connection-pool middleware must propagate it. Forgotten `SET` = empty query result (correct + safe but easy to debug-confuse if undocumented).
- Adding a new tenant requires a new BrandConfig file PR — slower than a DB-row insert, but exactly the "PR-reviewable" guarantee that buys safety.

**Now hard to undo:**
- Once tenant_slug becomes the load-bearing FK across all Pilot tables, moving to UUID would require a re-key migration on every table.
- Once RLS uses `current_setting('app.current_tenant_slug')`, every consumer (Telegram dispatcher, Margot integration, cron jobs) must adopt the session-variable pattern. Reverting to "open table, filter in app code" would surface every bypass.

## Alternatives considered

- **Shape A — `tenant_id` UUID column + RLS:** rejected. Adds a layer of indirection (UUID ↔ slug ↔ BrandConfig file lookup) that doesn't buy anything in v1 and slows debugging. Future migration to UUID is possible if v2 needs strict opacity, but YAGNI for v1.
- **Shape B — Per-tenant Supabase project:** rejected for v1. Heaviest infra (~1h provisioning per new client), N auth surfaces, N migration paths, N connection strings to manage. Re-evaluate at v3 if a client demands hard-isolation as a compliance requirement.

## Implementation path (deferred to `superpowers:writing-plans`)

Plan-time concerns, NOT glossary-time. The plan agent receives this ADR as a locked input and authors:

1. Schema migration — add `tenant_slug` NOT NULL to every `pilot_*` table, backfill any existing rows with `phill`, add RLS policy + index.
2. Connection-pool middleware — set `app.current_tenant_slug` on every checked-out connection from `BrandConfig.tenant_slug`.
3. BrandConfig TypeScript refactor — wrap existing `BrandConfig` exports in the new `TenantConfig` envelope; add `pilotConfig` field with `semantic_dedup_enabled` default.
4. CI/CD guardrail GitHub Action — pgTAP or custom script asserting RLS state.
5. Consumer updates — every `pilot_*` table reader sets the tenant context before query.

Per `[[feedback-substrate-change-discipline]]`: shadow-run RLS policies against current production for ≥50 dispatches before cutover. Per `[[feedback-tight-code]]`: the CI/CD guardrail script ≤80 lines.

## Cross-refs

- `[[context.md#tenant]]` · `[[context.md#brand]]` · `[[context.md#fingerprint]]` (tenant-scoped config flag)
- `[[adrs/001-pillar-canonicalisation]]` — companion decision (the canonicaliser may eventually need per-tenant pillar overrides — that becomes a `pilotConfig.pillar_overrides` field then)
- `[[portfolio-health-snapshot-2026-05-14]]` — the Margot RLS audit finding this decision permanently remediates
- `[[agency-bot-design-2026-05-14]]` — Pilot v1 internal spec
- `[[agency-tinder-game-design-2026-05-15]]` — v2 productized spec (this decision unblocks it)
- `[[remotion-brand-codify]]` — existing BrandConfig infrastructure being extended
- `[[feedback-substrate-change-discipline]]` · `[[feedback-tight-code]]` · `[[feedback-secrets-handling]]` · `[[feedback-quality-over-quantity]]`
