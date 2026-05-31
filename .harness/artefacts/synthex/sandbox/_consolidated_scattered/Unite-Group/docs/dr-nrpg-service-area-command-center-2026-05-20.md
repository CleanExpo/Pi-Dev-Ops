# DR/NRPG Service-Area Command Center Packet

Date: 2026-05-20
Status: Active routing packet

## Decision

Disaster Recovery / NRPG is an online-first service-area and contractor-network business. Unite-Group must represent it as a live operating system for demand, contractor coverage, evidence, search performance, and approval gates, not as a storefront-location business.

## Command Center Objects

Unite-Group should track these objects for DR/NRPG:

- client intake
- contractor application
- contractor verification
- service-area coverage
- location/service search page
- GBP/service-area profile
- Search Console opportunity
- review/reputation signal
- budget ledger entry
- KPI snapshot
- approval gate

## Required Board Signals

The Command Center should surface:

- client requests by service and location
- contractor applications awaiting verification
- service areas with demand but weak contractor coverage
- pages ready for evidence/QA/publish
- pages published and awaiting KPI review
- GBP/API blockers
- budget cap usage by contractor and month
- controlled-retreat candidates where a location is not paying off

## Synthex Boundary

Synthex remains the automation and marketing-intelligence layer:

- drafts page updates
- drafts GBP/service-area updates where eligible
- drafts review replies
- identifies Search Console opportunities
- checks budget gates
- records KPI snapshots
- proposes retreat/expand decisions

Unite-Group is the control surface. It should not directly publish, spend, or mutate Google Business Profile data.

## DR/NRPG Boundary

DR/NRPG remains the client/contractor product:

- client intake
- contractor intake
- contractor verification
- directory/profile pages
- service-area pages
- local restoration education

## No-Go Rules

- No fake office locations.
- No storefront assumption.
- No phone-first funnel.
- No keyword-stuffed GBP names.
- No public publishing without evidence, QA, and approval gates.
- No business grant/token reuse across unrelated businesses.

## First Build Slice

- [ ] Add DR/NRPG service-area board view to Command Center planning.
- [ ] Map Synthex `ContractorOnboardedEvent`, budget ledger, and KPI snapshots into Command Center cards.
- [ ] Add a service-area gap lane: demand exists, contractor coverage weak, page needs update, GBP blocked, review gap.
- [ ] Add an approval lane for page/GBP/review-response drafts.
- [ ] Add a "no fake storefront" policy badge to DR/NRPG search work.

## Verification

- Command Center data is read-only until a reviewed mutation route exists.
- Cards link back to DR/NRPG or Synthex source records.
- Every visible search/action recommendation includes source, confidence, risk, and next approval gate.
