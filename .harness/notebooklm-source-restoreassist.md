# NotebookLM Source — RestoreAssist
**Prepared:** 2026-04-15 | **Source tickets:** RA-822 | **Status:** Sprint 12 active

---

## 1. What RestoreAssist Is

### Purpose

RestoreAssist is the field-facing SaaS platform for Australian restoration technicians. Its primary deliverable is the National Inspection Report (NIR) — a single standardised inspection and scope-of-work format that eliminates the fragmented, inconsistent reporting that currently costs the Australian restoration industry between $1.125 billion and $2 billion annually in re-inspections, disputes, and processing overhead.

The core user flow: a technician takes moisture readings, humidity, temperature measurements, and timestamped photos in the field. The mobile app validates the data and uploads it. The NIR generation engine interprets the data, applies IICRC standards (S500 / S520 / S700), classifies damage by category and class, determines state-specific building code triggers, evaluates scope items, estimates costs, and produces a professional-grade report. Output formats: PDF (human), JSON (claims system integration), Excel (billing/operations).

Key innovation: a junior technician using RestoreAssist produces the same quality report as an expert. The system interprets; the human measures.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js, TypeScript |
| Backend | Supabase (PostgreSQL) |
| Deployment | Vercel (frontend), TBD backend |
| GitHub repo | CleanExpo/RestoreAssist |
| Production URL | https://restoreassist.app |
| Linear project | RestoreAssist Compliance Platform (RA team) |
| Linear project ID | 3c78358a-b558-4029-b47d-367a65beea7b |
| Linear team ID | a8a52f07-63cf-4ece-9ad2-3e3bd3c15673 |

### Business Model

Subscription SaaS targeting restoration companies, insurance adjusters, and TPA/admin companies.

Pricing model (proposed, not yet validated with customers):
- Starter: ~$99/month, 10 reports/month
- Professional: ~$299/month, unlimited reports
- Enterprise: custom

Year 1 revenue target: $50,000 from 50+ signed companies (Phase 3 launch). Year 2 target: $300,000 from 100+ companies. Year 3: $800,000, 250+ companies, de facto industry standard.

### Phase Roadmap

| Phase | Timeline | Budget | Outcome |
|-------|----------|--------|---------|
| Phase 1 — Foundation | Months 1–3 | $100–120k | Production-ready system, full NIR specification |
| Phase 2 — Pilot | Months 4–7 | $50k | 3–5 pilot companies, 50+ real claims processed |
| Phase 3 — Launch | Months 8–12 | $95k | 50+ companies signed, $50k Year 1 revenue |
| Phase 4+ | Year 2+ | — | 100+ companies, premium API/analytics features |

---

## 2. Current Status and Health

**Charter status:** Active onboarding (pre-build — business model validated, no code written yet as of charter date 2026-04-11)

**Pi-SEO scan date:** 2026-04-12

### Health Pillar Scorecard

| Pillar | Score | Status | Notes |
|--------|-------|--------|-------|
| 1. Security | 60/100 | RED | 2 high findings (hardcoded password pattern in change-password page) |
| 2. Code quality | 100/100 | GREEN | No issues found |
| 3. Dependencies | 100/100 | GREEN | Zero vulnerability findings |
| 4. Deployment health | 100/100 | GREEN | Fully deployed at restoreassist.app |
| 5. Observability | AMBER | Unknown | No heartbeat/error tracking confirmed |
| 6. Documentation | AMBER | Unknown | README, CLAUDE.md, runbooks not yet verified |
| 7. Autonomy-ready | RED | Not yet | No green end-to-end Pi-CEO run on this repo |

### Security Finding Detail

Two high-severity findings flagged in the 2026-04-12 security scan:
- `app/dashboard/change-password/page.tsx` line 69: hardcoded password pattern match
- `app/dashboard/change-password/page.tsx` line 78: hardcoded password pattern match

**Classification note:** These are likely test fixtures or UI password field variable names (`password=` in a change-password form) — the Pi-CEO scanner's regex is matching variable assignments in UI code. Manual classification required before rotating or allowlisting. The charter previously noted 9 hardcoded password findings from an earlier scan (2026-04-10); the April 12 scan shows 2, suggesting some were resolved or the scan scope narrowed.

Pi-SEO portfolio average score: 0/100 across most repos in the dryrun digest. RestoreAssist at 0/100 in the dryrun but individual scan files show higher per-category scores.

---

## 3. Active Risks and Issues

### Risk 1 (HIGH) — Hardcoded credential pattern in production UI code

**Linear ticket:** To be created (RA-CLEAN-001 equivalent)
**Severity:** High
**Description:** Two matches of the pattern `(?i)(password|passwd|pwd)\s*=\s*['"][^''` in `app/dashboard/change-password/page.tsx` at lines 69 and 78. If these are literal secret values (not variable names), they represent an exposed credential. Rotation and immediate removal required.
**Mitigation:** Manual code review of lines 69 and 78. If they are variable assignments in a React form component (e.g. `const [password, setPassword] = useState('')`) they are false positives requiring an allowlist entry. If they contain actual credential values, rotate immediately.
**Status:** Open — no ticket confirmed closed.

### Risk 2 (MEDIUM) — NIR platform in pre-build state with no pilot company named

**Linear ticket:** Business charter open question
**Severity:** Medium
**Description:** The RestoreAssist charter identifies several open questions that are preconditions for Phase 1: no pilot restoration company named, no insurer validation conversation logged, technology stack not yet chosen. The 30-day milestone ("at least one pilot company preliminary conversation") has no confirmed completion.
**Mitigation:** Charter flags Pi-SEO should escalate if no pilot company is named by Day 30, no insurer conversation logged by Day 45, and no open question answered by Day 60 where it blocks the next phase.
**Status:** Open — founder input required.

### Risk 3 (MEDIUM) — Autonomy-ready status is RED

**Linear ticket:** RA-CLEAN-030 through RA-CLEAN-032 (planned)
**Severity:** Medium
**Description:** Pi-CEO cannot autonomously work the RestoreAssist backlog until `.claude/settings.json` is configured, the repo is registered in Pi-SEO's monitor-config, and a green end-to-end run is observed. Without this, all RestoreAssist improvement work requires manual intervention.
**Mitigation:** Phase 4 of the RestoreAssist charter covers this — allowlist config, monitor registration, smoke test run. Estimated effort: 1–2 days Pi-CEO work after Phase 1–3 complete.
**Status:** Open — Phase 4 scheduled after security and NIR readiness phases.

### Additional Risks from Charter

- **PII compliance:** RestoreAssist handles insurance-claim-level PII (property addresses, damage photos, homeowner data). Australian Privacy Act 1988 / APPs compliance scope not yet confirmed.
- **dangerouslySetInnerHTML:** Earlier scan found 14 instances. Each requires either DOMPurify wrapping or a documented `// SAFE:` comment. XSS risk if any instance renders user-supplied HTML.
- **Technology stack not yet chosen:** Phase 1 has not confirmed whether the build is React + Node.js SaaS, mobile-native, or PWA. Stack choice affects security posture, testing approach, and deployment topology.

---

## 4. Architecture Overview

### Business Architecture (as designed)

```
Technician on site
    │
    ▼
Mobile App (data capture)
    ├── Moisture readings
    ├── Humidity / temperature
    ├── Timestamped photos
    └── Structured form (dropdowns, validated)
    │
    ▼ upload
Cloud Storage + NIR Generation Engine
    ├── Extract property address → determine state building code
    ├── Apply IICRC S500/S520/S700 standards
    ├── Classify damage (category + class)
    ├── Identify state-specific triggers
    ├── Evaluate scope items
    ├── Estimate costs
    └── Generate verification checklist + audit trail
    │
    ▼
Output pipeline
    ├── PDF → insurance adjusters / restoration companies
    ├── JSON → claims system integration
    └── Excel → billing and operations
```

### Current Technical Architecture

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js (TypeScript), deployed to Vercel |
| Backend / data | Supabase (PostgreSQL + Auth) |
| GitHub org | CleanExpo |
| Repo | CleanExpo/RestoreAssist |
| Scan schedule | Every 6 hours (Pi-SEO) |

### Non-functional Requirements

- **IICRC compliance:** All damage classification and scope items must align with IICRC S500, S520, S700. Non-negotiable for insurance credibility.
- **Data privacy:** Australian Privacy Act 1988 / APPs. GDPR and state-specific rules pending confirmation.
- **One national format:** No per-company customisation in Phase 1. Custom branding is a Phase 4+ feature.
- **ROI proof:** Pilot companies must see $2,000–$5,000 savings per claim within 30 days of go-live.

---

## 5. Key Integrations

| Integration | Purpose | Status |
|-------------|---------|--------|
| Supabase | Database, auth, storage | Active (deployed) |
| Vercel | Frontend hosting | Active (restoreassist.app live) |
| Pi-SEO | Autonomous security and health scanning | Active (scanning 4x/day) |
| Pi-CEO (Pi-Dev-Ops) | Autonomous backlog execution via Linear | Onboarding (Phase 4 not yet complete) |
| Linear (RA team) | Issue tracking, sprint management | Active |
| Telegram (@piceoagent_bot) | Escalation alerts | Planned (same contract as CCW) |
| IICRC Standards API / data | Damage classification, scope evaluation | Not yet integrated (Phase 1 spec work) |
| Claims system JSON integration | Insurance company data exchange | Phase 2+ scope |
| PDF generation library | NIR report output | TBD (Phase 1 engineering decision) |

---

## 6. Pi-CEO Relationship to RestoreAssist

Pi-CEO acts as autonomous project manager and delivery rail for RestoreAssist. The contract:
- Continuously scan → file Linear tickets → execute sessions → open PRs → notify via Telegram
- Does NOT touch real inspection or insurance data
- Does NOT deploy to production without human approval
- Does NOT merge its own PRs
- Escalates via Telegram for Urgent transitions, sends weekly digest Monday morning

The Pi-CEO pipeline runs on the Pi-Dev-Ops platform (FastAPI + Railway backend, Next.js + Vercel frontend). Pi-Dev-Ops's autonomy poller watches Linear for Urgent/High Todo issues and auto-creates build sessions.

---

## 7. Sprint Context (Sprint 12, April 2026)

**Linear ticket:** RA-822 — NotebookLM KB build for RestoreAssist (5 criteria, incl. top-3 risks)
**Status:** In Review

The board added a 5th criterion to RA-822 on 2026-04-15: top 3 open risks per entity must be surfaced from Linear + Pi-SEO. This document fulfils that criterion.

Adjacent tickets:
- RA-823: NotebookLM KB for Synthex
- RA-824: NotebookLM KB for CleanExpo
- RA-821: Entity ranking — RestoreAssist/Synthex/CleanExpo selected as top-3 priority notebooks

Board decision (2026-04-15 activation vote): swarm active mode enabled, 3 autonomous PRs/day rate limit. RestoreAssist is unblocked for autonomous work (the carsi ADMIN_PASSWORD blocker does not affect this repo).

---

## 8. Non-negotiable Constraints

1. The founder (Phill) does not write code. All technical decisions must be expressible as business requirements.
2. IICRC standards compliance is mandatory for industry credibility.
3. One national format — no per-company customisation in Phase 1.
4. Phase 2 must prove ROI, not just validate the concept. $2,000–$5,000 savings per claim within 30 days of go-live.
5. Network effect must be demonstrable by end of Phase 2 — insurance companies must demand NIR, not tolerate it.

---

## 9. Open Questions (Founder Input Required)

1. Which restoration companies become pilots?
2. Which insurance companies have early validation conversations underway?
3. Technology stack: React + Node.js SaaS, mobile-native, or PWA?
4. Regulatory scope beyond IICRC — building codes, TPA certifications, insurance regulations?
5. Pricing sensitivity — validated with restoration companies?
6. Data ownership and custody — technician's company, property owner, or insurance company?
7. Go-to-market sequence — restoration companies first or pre-commit an insurer first?
8. Competitive map — existing platforms attempting to standardise restoration reporting?

---

## 10. Source References

- `/Pi-Dev-Ops/.harness/business-charters/restoreassist-charter.md` — business model, roadmap, constraints
- `/Pi-Dev-Ops/.harness/business-charters/projects/restoreassist-charter.md` — Pi-CEO standard pillar scorecard
- `/Pi-Dev-Ops/.harness/scan-results/restoreassist/2026-04-12-*.json` — security (60/100), code quality (100/100), dependencies (100/100), deployment (100/100)
- `/Pi-Dev-Ops/.harness/projects.json` — repo registration, Linear IDs
- `/Pi-Dev-Ops/.harness/sprint_plan.md` — RA-822, Sprint 12 context
- `/Pi-Dev-Ops/.harness/board-meetings/2026-04-15-activation-vote.md` — board conditions, swarm activation
- `/Pi-Dev-Ops/CLAUDE.md` — Pi-Dev-Ops architecture and Linear integration details
