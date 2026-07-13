# RestoreAssist video opportunity roadmap — 2026-06-24

## Current inventory signals

- RestoreAssist app registry currently has 68 registered video slugs in `components/setup/video-registry.ts`.
- The Learn page currently surfaces 54 of those slugs.
- Registered but not surfaced in Learn page: `help-*` videos, `remotion-byok`, `remotion-report-export-pdf`, `remotion-setup-wizard-full`, `remotion-sign-in`, `remotion-sign-up`, `remotion-why-restoreassist`, `remotion-linkedin-short-1`, `remotion-linkedin-short-2`.
- Dashboard/app surface scan found many additional high-value product areas not yet represented as focused videos: claims analysis, reports completeness, authority forms, field capture, contents manifest, insurer profiles, WHS, contractor profile/equipment/certifications, integrations health/sync errors, storage health, video analytics, and admin workflows.
- New generated Pi-Dev-Ops video packets this session:
  - `ra-facebook-proof-sells-20260624`
  - `ra-facebook-walkthrough-20260624`
  - `ra-client-facing-why-restoreassist-20260624`

## Production principles

1. In-app videos should solve a user’s next action in under 90 seconds.
2. Marketing videos should sell a business outcome, not a feature list.
3. Client-facing videos should make RestoreAssist feel like a trust standard the restorer uses, not software the client has to learn.
4. Every video should have a direct placement target before production: Learn page, How To dropdown, help article, onboarding, dashboard empty state, pricing page, sales/social, or client portal.
5. Prefer short social cuts after a longer master is approved.

## Recommended next production batch

### Batch A — highest-impact app walkthroughs

| Priority | Video | Placement | Audience | Purpose | Suggested duration | Status |
|---:|---|---|---|---|---:|---|
| A1 | First 5 minutes in RestoreAssist | Learn page / onboarding / dashboard empty state | New restorer users | Show dashboard → first inspection → evidence → report path | 60–75s | ready_to_script |
| A2 | Create a water-damage inspection from scratch | Inspections help / Learn page | Technicians/restorers | Show a job being opened and structured correctly | 60–75s | ready_to_script |
| A3 | Report completeness check | Reports help / report edit empty state | Restorers/admins | Show missing fields before client/assessor handover | 45–60s | ready_to_script |
| A4 | Share a report with a client or assessor | Client portal / reports share page | Restorers/admins | Explain safe sharing, access, versions, next step | 45–60s | ready_to_script |
| A5 | Mobile field capture workflow | Mobile/field dashboard / inspections capture | Field technicians | Show phone/tablet evidence capture and close-out | 45–60s | ready_to_script |

### Batch B — trust/compliance videos

| Priority | Video | Placement | Audience | Purpose | Suggested duration | Status |
|---:|---|---|---|---|---:|---|
| B1 | Evidence chain and audit trail | Compliance / reports / client portal | Restorers, assessors, clients | Explain why evidence is credible and traceable | 45–60s | ready_to_script |
| B2 | IICRC S500/S520/S700 citation discipline | Compliance help | Restorers/assessors | Show standards references and edition discipline | 60–90s | ready_to_script |
| B3 | WHS checklist walkthrough | WHS dashboard/help | Restorers/admins | Show site safety/documentation readiness | 45–60s | needs_app_surface_check |
| B4 | Authority forms and sign-off | Report authority forms / client portal | Restorers/clients | Explain client authority flow and sign-off | 45–60s | ready_to_script |
| B5 | Version history and report audit | Reports version history | Restorers/admins/assessors | Show confidence in edits and final reports | 45–60s | ready_to_script |

### Batch C — operational/admin videos

| Priority | Video | Placement | Audience | Purpose | Suggested duration | Status |
|---:|---|---|---|---|---:|---|
| C1 | Storage health and disconnected-state recovery | Settings storage / workspace health | Admins | Show why storage matters and how to resolve gaps | 45–60s | ready_to_script |
| C2 | Integration health and sync errors | Integrations health/sync errors | Admins | Show accounting/service sync troubleshooting | 60–75s | ready_to_script |
| C3 | Team roles and technician licence verification | Team help / onboarding | Admins | Show invite, role, licence check | 45–60s | existing_but_can_upgrade |
| C4 | Admin video analytics | Admin video analytics page | Admins/trainers | Show training progress and watched status | 45–60s | ready_to_script |
| C5 | Contractor profile, equipment, certifications | Contractor profile pages | Contractors/admins | Make business profile credible and complete | 60–75s | ready_to_script |

### Batch D — marketing masters

| Priority | Video | Placement | Audience | Purpose | Suggested duration | Status |
|---:|---|---|---|---|---:|---|
| D1 | Choose a restorer who can show the proof | Facebook/client-facing/social | Homeowners/property managers | Client-facing trust-builder | 30–45s | derivative_from_generated |
| D2 | Why restorers should use RestoreAssist over scattered tools | Website/social/sales | Restoration business owners | Competitive positioning | 60–75s | generated_master_exists |
| D3 | The report sells the job | Facebook/LinkedIn | Restoration business owners | Proof-led sales angle without naming source idea | 30–45s | generated_master_exists |
| D4 | Assessor confidence | LinkedIn/sales | Insurance assessors | Show easier review/approval logic | 45–60s | ready_to_script |
| D5 | Property manager confidence | Facebook/LinkedIn | Property managers | Show less chasing, clearer handover | 45–60s | ready_to_script |
| D6 | Before/after workflow comparison | Website/social | Restorers/admins | Generic/scattered process vs RestoreAssist | 45–60s | ready_to_script |
| D7 | ROI: fewer re-explanations and cleaner handovers | Sales/pricing | Business owners | Translate workflow into time/trust value | 60–75s | ready_to_script |
| D8 | One job record | Homepage hero / social | All prospects | Simple memorable platform promise | 30–45s | ready_to_script |

### Batch E — short-form cutdowns

Create short 15–30s variants from each approved long-form video:

| Source | Cutdown ideas | Placement |
|---|---|---|
| `ra-client-facing-why-restoreassist-20260624` | Client proof, ask your restorer, clear report | Facebook/Reels |
| `ra-facebook-walkthrough-20260624` | Dashboard → report in 20s, evidence chain in 20s | Facebook/LinkedIn |
| `ra-facebook-proof-sells-20260624` | Report sells job, proof before pitch | Facebook/LinkedIn |
| Future A1 first 5 minutes | New-user onboarding hook, first inspection hook | Onboarding/social |
| Future A3 completeness check | Find missing info before handover | Help/social |

## Suggested immediate execution order

1. Produce A1 — First 5 minutes in RestoreAssist.
2. Produce A2 — Create a water-damage inspection from scratch.
3. Produce A3 — Report completeness check.
4. Produce D1 — 30s client-facing short from current client-facing master.
5. Produce D3 — 30s proof-led sales cutdown from current proof-sells master.

Reason: this gives RestoreAssist one onboarding master, two product-action videos, and two social/marketing assets without waiting for new app code.

## Registry / app integration follow-up

- Consider adding new generated videos into the app registry after final approval:
  - `remotion-client-facing-why-restoreassist`
  - `remotion-facebook-proof-sells`
  - `remotion-facebook-walkthrough`
- Consider surfacing currently registered but hidden videos on Learn page where still relevant:
  - `remotion-why-restoreassist`
  - `remotion-report-export-pdf`
  - `remotion-setup-wizard-full`
  - `remotion-byok`
- Keep `help-*` videos in MDX context unless they are also useful in the Learn grid.

## Next video packet template

For each selected video:

```json
{
  "brand": "ra",
  "channel": "facebook|website|learn|help|onboarding|sales",
  "audience": "who this is for",
  "goal": "one outcome this video must cause",
  "cta": "one next action",
  "durationSec": 45,
  "placement": "exact app page or marketing channel",
  "scenes": [
    "hook",
    "pain/context",
    "workflow/proof",
    "benefit",
    "cta"
  ]
}
```
