# Margot Project Portfolio Index

Date: 2026-05-23 07:33 AEST
Project: Unite-Group
Owner: Margot
Scope: Existing repo/docs/code evidence only. External Linear/Supabase live status is not asserted unless present in local docs or code.

## Purpose

This index is the Senior Project Manager portfolio surface for Margot. It turns the repo's current CRM, command-center, client, marketing, integration, and AI work into a single management view with status, blockers, next actions, evidence, and $2B strategy leverage.

Read-first inputs:

- `docs/margot/SENIOR-PROJECT-MANAGER-OPERATING-MODEL.md`
- `docs/margot/crm-operating-model.md`
- `docs/margot/crm-schema-inventory.md`
- `docs/plans/2026-05-23-margot-multi-day-crm-build-plan.md`
- `src/components/command-center/business-360/business-360-data.ts`
- `src/lib/empire/read-portfolio-summary.ts`
- `src/lib/empire/read-business-360.ts`
- `src/lib/empire/list-nexus-clients.ts`

## Source-of-truth rule

- Linear/GitHub/Vercel/Stripe/Supabase providers remain authoritative for their own live state.
- This document is a repo-local portfolio control index, not proof of external production state.
- Static Business 360 seed data is marked as seed evidence unless a local reader points to live Supabase mirrors.
- Unknowns are explicit and must become tasks, not assumptions.

## Portfolio rows

| Project / lane | Business/client | Current repo evidence | Status from local evidence | Next 3 actions | Blockers / unknowns | $2B leverage |
| --- | --- | --- | --- | --- | --- | --- |
| Margot CRM command spine | Unite-Group internal operating system | `docs/margot/crm-operating-model.md`, `docs/margot/crm-schema-inventory.md`, `supabase/migrations/20260523100000_crm_leads.sql`, `src/app/api/marketing/leads/route.ts`, `tests/integration/api/marketing-leads.test.ts` | Active local build. Lead persistence is implemented locally and awaits normal sandbox/promotion flow before production use. | 1. Build lead list/query API. 2. Add lead qualification helper. 3. Draft guarded lead-to-client conversion. | Production migration not applied by this lane. Pipeline stages and auto-conversion rules require Board judgment. | High: creates the CRM operating loop for revenue, client, task, and digest intelligence. |
| Margot voice command center | Unite-Group / Phill cockpit | `src/components/command-center/voice/MargotVoicePanel.tsx`, `src/app/api/pi-ceo/margot-voice/signed-url/route.ts`, `src/app/api/pi-ceo/margot-voice/task/route.ts`, voice tests under `tests/integration/api/` and `tests/unit/` | Active and tested in prior focused runs. Route/table schemas for `tasks` and `voice_command_sessions` are route/test-inferred because local migrations were not found. | 1. Keep regression tests green. 2. Add command-center reader for voice-created tasks. 3. Decide approval table vs task subtype. | Missing local migrations for voice/session/task tables. External ElevenLabs/CRM env status is not verified here. | High: converts operator speech into durable CRM work and approval queues. |
| CRM schema/source-of-truth inventory | Unite-Group CRM data layer | `docs/margot/crm-schema-inventory.md` | Completed local documentation lane; records table inventory, integration mirrors, gaps, and source-of-truth rules. | 1. Keep updated when endpoints/tables change. 2. Add timeline/event taxonomy. 3. Capture provenance for `pi_ceo_health_snapshots`, `tasks`, and `voice_command_sessions`. | Live production schema may contain objects not represented in local migrations. | High: reduces data drift and enables safe agentic CRM expansion. |
| Business 360 / portfolio summary | Portfolio businesses: Synthex, RestoreAssist, DR-NRPG, CARSI, CCW CRM, Disaster Recovery | `src/components/command-center/business-360/business-360-data.ts`, `src/lib/empire/read-business-360.ts`, `src/lib/empire/read-portfolio-summary.ts` | Seeded visual portfolio exists; server readers can overlay `pi_ceo_health_snapshots` and `businesses` data when available. | 1. Map each portfolio row to canonical `businesses.slug`/`pi_ceo_key`. 2. Surface stale/missing health snapshots. 3. Link projects to Linear mirror rows where available. | Current live values are unknown in this doc-only lane. `pi_ceo_health_snapshots` migration/provenance not found in schema inventory. | High: executive visibility across the operating company. |
| RestoreAssist content index / command center recovery | RestoreAssist / Brand OS | `docs/margot/MARGOT-COMMAND-CENTER.md`, `docs/margot/mac-mini-recovery-status.md`, `docs/margot/linear-uni-2054-overnight-update.md` | Active but recovery blocked locally. Local reconstruction is present; original Mac Mini artifacts are not recovered. | 1. Recover approved Mac Mini artifacts when authenticated SMB/SSH/export is available. 2. Compare recovered originals against reconstructed docs. 3. Update UNI-2054 draft locally before any external post. | No authenticated Mac Mini share; SSH unavailable; original `RESTOREASSIST-CONTENT-INDEX.md` missing locally. | Medium/high: restores operating memory and content packs for a live business lane. |
| DR/NRPG service-area command center | DR/NRPG / Disaster Recovery | `docs/dr-nrpg-service-area-command-center-2026-05-20.md`, Business 360 seed rows for `dr-nrpg` and `disaster-recovery` | Strategy packet exists. It defines online-first service-area objects, Board signals, Synthex boundary, and no-go rules. | 1. Map service-area objects into command-center cards. 2. Add approval lane for page/GBP/review drafts. 3. Link contractor/KPI/budget records when source tables/routes are verified. | Source records for contractor events, budget ledger, Search Console, and GBP blockers are not verified in this lane. | High: direct demand generation, coverage optimization, and controlled-retreat intelligence. |
| CCW CRM / product category work | CCW CRM | Business 360 seed row `ccw-crm`; `docs/margot/MARGOT-COMMAND-CENTER.md` lists `UNI-2053` as queued/blocked | Queued/blocked from local docs. | 1. Obtain first CCW product category topic. 2. Keep CCW context separate from RestoreAssist/Synthex/DR-NRPG/CARSI. 3. Draft copy only after client identity/topic is clear. | Topic missing; live Linear status not checked here. | Medium: client marketing/content execution once unblocked. |
| Duncan / Dimitri ITR platform | Home Loan Essentials / Duncan Perkins | `docs/sows/duncan-itr-platform-sow-2026-05-14.md`, Business 360 seed note `Unite-Group: CCW + Duncan` | Draft SOW exists and awaits Phill to fill AUD amounts before send. | 1. Fill commercial amounts and rate card fields. 2. Confirm ACL number/name decision details. 3. Convert approved SOW to client-ready send package only after human review. | Commercial values and client-send approval are unknown; client-facing send requires explicit approval. | High: revenue/client leverage and repeatable AI-software delivery model. |
| Integration mirror mesh | Portfolio/infrastructure | `docs/margot/crm-schema-inventory.md`, `supabase/migrations/20260513000200_integration_schema.sql`, `docs/integrations/README.md` | Local schema exists for GitHub, Vercel, Railway, DigitalOcean, Supabase, 1Password names-only, Linear, Stripe, and Composio mirrors. | 1. Define stale-sync thresholds. 2. Link mirrors to clients/businesses/projects. 3. Surface risks in daily digest. | Live sync freshness not verified here. Secret values must never be stored. | High: turns disconnected tools into operational intelligence. |
| Marketing lead intake | Unite-Group growth / public website | `src/app/api/marketing/leads/route.ts`, `tests/integration/api/marketing-leads.test.ts`, `crm_leads` migration | Local persistence path and tests exist from prior lane. | 1. Add list/query visibility. 2. Add qualification recommendations. 3. Attach leads to campaign/source and follow-up rules. | Production migration/application status unknown; privacy retention for IP/user-agent still needs decision. | High: converts demand into CRM work and pipeline learning. |
| AI enhancement pipeline | Unite-Group operating system | `docs/margot/ai-enhancement-pipeline.md` after this lane; Senior PM model defines watch/triage/sandbox/evaluate/adopt flow | Initial operating model created in this doc lane. | 1. Start local-only evaluation register. 2. Score candidate improvements by CRM/2nd Brain value. 3. Add adoption/retirement evidence to progress logs. | No live AI vendor/tool evaluation is performed by this lane. | High: compounds automation, retrieval, QA, and operational leverage. |

## Portfolio health policy

For each row Margot should maintain:

- owner: person/system accountable for next action;
- source identity: `business_slug`, `client_slug`, Linear project ID, GitHub repo, Vercel project, or explicit unknown;
- status: active, queued, blocked, parked, shipped, or unknown;
- next 3 actions: specific, verifiable, and safe;
- blockers: access, identity, business judgment, production approval, external dependency;
- evidence: file path, route, migration, test, Linear context, or provider mirror;
- $2B leverage: revenue, operating, data, client, or strategic leverage.

## Digest fields

Daily/morning report rows should include:

```text
Project:
Status:
Last verified evidence:
New movement since yesterday:
Decisions needed:
Blocked by:
Next safe action:
```

## Immediate next tasks

1. Link this index from `docs/margot/MARGOT-COMMAND-CENTER.md` and `docs/margot/morning-report.md`.
2. Use this file as the local portfolio row source until a Supabase-backed project portfolio reader exists.
3. Do not invent live project status; mark unknowns and create follow-up tasks.
