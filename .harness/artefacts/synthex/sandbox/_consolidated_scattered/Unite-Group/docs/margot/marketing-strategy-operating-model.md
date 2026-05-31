# Margot Marketing Strategy Operating Model

Date: 2026-05-23 07:33 AEST
Project: Unite-Group
Owner: Margot
Scope: Existing repo/docs/code evidence only. No campaigns are launched and no client-facing messages are sent by this doc lane.

## Purpose

Marketing strategy is a CRM-connected growth function. Margot should connect ICP, offers, SEO/content, campaigns, lead capture, follow-up tasks, client memory, and performance learning into the same operating loop used for clients and projects.

Primary inputs:

- `docs/margot/SENIOR-PROJECT-MANAGER-OPERATING-MODEL.md`
- `docs/margot/crm-operating-model.md`
- `docs/margot/crm-schema-inventory.md`
- `src/app/api/marketing/leads/route.ts`
- `supabase/migrations/20260523100000_crm_leads.sql`
- `docs/dr-nrpg-service-area-command-center-2026-05-20.md`
- `docs/margot/MARGOT-COMMAND-CENTER.md`

## Marketing-to-CRM loop

```text
Market signal / content idea / campaign result
  -> identify business/client/campaign/source
  -> attach ICP/offer/content/channel context
  -> create or update lead/contact/opportunity/task/activity
  -> decide follow-up: auto, draft, ask Phill, block, never
  -> verify evidence and source labels
  -> update client 2nd Brain and project portfolio
  -> surface in command center / morning report
```

## Canonical marketing fields

Until formal tables exist, these are the fields Margot should preserve in docs, lead records, tasks, or future CRM objects:

```yaml
strategy_identity:
  business_slug:
  client_slug:
  campaign_slug:
  source_doc:
audience:
  icp:
  buyer_roles:
  geography:
  pain_points:
  urgency_triggers:
offer:
  offer_name:
  value_proposition:
  offer_ladder_stage: awareness|lead_magnet|consult|proposal|retainer|upsell|renewal|unknown
  proof_assets:
content:
  topic:
  search_intent:
  target_keywords:
  content_type: landing_page|service_page|blog|email|ad|social|proof_video|proposal|unknown
  status: idea|briefed|drafted|approved|published|measured|retired
campaign:
  channel:
  start_date:
  owner:
  budget_or_effort:
  approval_gate:
conversion:
  primary_cta:
  form_or_route:
  crm_follow_up_rule:
  lead_source:
performance:
  traffic:
  leads:
  qualified_leads:
  conversion_rate:
  revenue_attribution:
  confidence:
learning:
  observed_signal:
  next_test:
  retired_assumptions:
```

## Lead follow-up rules

Current local evidence:

- Public marketing submissions enter through `src/app/api/marketing/leads/route.ts`.
- Local migration `supabase/migrations/20260523100000_crm_leads.sql` defines `crm_leads` with `source`, `status`, `interests`, `referral_source`, `marketing_consent`, `assigned_owner`, match/conversion fields, and privacy-sensitive IP/user-agent fields.
- SendGrid is a side integration, not the CRM source of truth.

Safe default follow-up:

1. Persist the lead in CRM first where migration is applied.
2. Attach source/campaign/referral/interests if present.
3. Do not treat SendGrid subscription as proof of CRM capture.
4. Create a qualification recommendation, not auto-conversion, until Board rules exist.
5. Create a follow-up task when lead quality or urgency is high enough under approved criteria.
6. Surface new/qualified/blocked leads in the morning report.
7. If identity matches an existing client/business, require strong-key verification before linking.

## Marketing outputs as CRM activities/tasks

Marketing work should become durable CRM objects:

| Marketing output | CRM/memory object | Required evidence |
| --- | --- | --- |
| Website lead | `crm_leads` row | route response, lead id, source, consent status |
| Content brief | task + artifact | business/client identity, audience, offer, approval gate |
| Service/location page recommendation | task or approval | source signal, confidence, risk, no-go policy |
| Campaign launch plan | project/task | owner, channel, budget/effort, approval status |
| Client-facing copy | draft artifact only until approved | client identity, source docs, human approval before send |
| SEO/content performance signal | activity/event or digest row | provider/source, date, metric, confidence |
| Learning from performance | 2nd Brain update | what changed, why, next test |

## Context separation rules

Keep these contexts separated unless strong identity evidence says otherwise:

- CCW CRM / UNI-2053 product category work.
- RestoreAssist / Brand OS / UNI-2054 command-center and content-index recovery.
- Synthex automation/marketing-intelligence layer.
- DR/NRPG service-area and contractor-network command-center work.
- CARSI course/content work.
- Home Loan Essentials / Duncan / Dimitri ITR platform.

No cross-client copy reuse without checking:

1. client/business identity;
2. source license/confidentiality;
3. brand voice;
4. approval status;
5. whether sensitive data appears in the draft.

## Approval boundaries

Margot may auto-create or update local marketing docs, internal briefs, and mock-tested helpers.

Margot must draft first or ask before:

- sending emails/messages to leads or clients;
- publishing pages/posts/ads;
- changing budgets;
- mutating Google Business Profile, Search Console, Vercel env, or production systems;
- merging lead/client identities;
- using client-sensitive data in marketing material;
- defining permanent pipeline/conversion rules.

## DR/NRPG marketing model from existing packet

`docs/dr-nrpg-service-area-command-center-2026-05-20.md` defines a useful template:

- represent DR/NRPG as online-first service-area/contractor-network, not storefront-location;
- surface demand, contractor coverage, pages needing evidence/QA/publish, GBP/API blockers, budget cap usage, review/reputation signal;
- Synthex drafts updates/replies and proposes decisions;
- Unite-Group remains the control surface and does not directly publish, spend, or mutate GBP without approvals;
- no fake locations, no phone-first assumption, no keyword-stuffed GBP names, no unapproved public publishing.

Apply that pattern to other marketing lanes: source signal, draft/recommend, approval gate, verified publish/measure loop.

## Digest questions

Every morning marketing digest should answer:

```text
What new leads arrived?
Which source/campaign did they come from?
Which leads need Phill's attention?
Which content/campaign tasks moved?
Which approvals are blocked?
Which performance signals changed strategy?
Which client/business context is missing or ambiguous?
```

## Immediate next implementation steps

1. Add CRM lead list/query visibility so marketing intake is visible in the command center.
2. Add deterministic lead qualification recommendations with reasons.
3. Add campaign/source fields to future lead/task/activity surfaces where not already present.
4. Create per-business strategy profiles using the Client 2nd Brain model.
5. Keep all client-facing marketing drafts approval-gated.
