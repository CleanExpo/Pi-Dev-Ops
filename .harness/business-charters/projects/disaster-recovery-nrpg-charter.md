# Project Charter — Disaster Recovery / NRPG

**Status:** active onboarding — **highest risk of the three**
**Repos:**
- https://github.com/CleanExpo/Disaster-Recovery (`disaster-recovery` in scan results)
- https://github.com/CleanExpo/DR-NRPG (`dr-nrpg` in scan results)
- https://github.com/CleanExpo/NRPG-Onboarding (`nrpg-onboarding` in scan results)

**Owner:** Phill (Unite Group)
**Pi-CEO agent:** assigned (marathon 2026-04-11)
**Charter last updated:** 2026-04-11
**Baseline scan:** `.harness/scan-results/disaster-recovery/` and `.harness/scan-results/dr-nrpg/` (2026-04-10)

---

## What this project does

"Disaster Recovery - NRPG" spans three related repos that together deliver the National Restoration Practitioners Group (NRPG) platform — a professional-body website, member onboarding system, and the disaster-recovery-facing application that supports restoration practitioners during active incident response. Context clues from the scan results: Next.js + LangChain + Prisma stack, active AI feature work in progress, multiple environments.

This is the highest-risk project in the three-project onboarding because:

1. The raw security finding count is an order of magnitude higher than the other two combined.
2. Dependencies show real, scored npm vulnerabilities — not just pattern-matching noise.
3. Both repos have `Hardcoded secret` and `DB connection string` findings at **high** severity that look like real credentials, not fixtures.
4. `disaster-recovery` alone has 766 high-severity findings, mostly `dangerouslySetInnerHTML` — if even 10% are genuine XSS sinks on user-generated content, this is a publicly-reachable risk.

This charter treats the three repos as one program with a shared security posture. Each repo gets its own ticket stream but the cleanup phases run in parallel.

## Who Pi-CEO is to this project

Same role, but with an additional escalation contract: anything tagged `severity:critical` on either repo fires an immediate Telegram alert and does NOT wait for the next heartbeat cycle.

## Current state — per repo

### Disaster-Recovery
| Pillar | Score / Finding count | Status |
|---|---|---|
| Security | 766 high + 5 medium + 1004 low | **RED** |
| Code quality | 100/100 | GREEN |
| Dependencies | score 8/100, 18 findings (6 high, 10 medium, 2 low) | **RED** |
| Deployment health | 100/100 | GREEN |

### DR-NRPG
| Pillar | Score / Finding count | Status |
|---|---|---|
| Security | 2 critical + 130 high + 128 medium + 3649 info | **RED** |
| Code quality | 100/100 | GREEN |
| Dependencies | 52 findings (4 critical, 21 high, 9 medium, 18 low) | **RED** |
| Deployment health | 100/100 | GREEN |

### NRPG-Onboarding
Scan files present but not yet summarised in this charter pass. Tracked as `NRPG-ONB-000` to complete the audit.

## Security breakdown — why this is urgent

### Disaster-Recovery — the XSS concern
- **762× `dangerouslySetInnerHTML` at high severity.** This is the single most important number in the whole portfolio audit. Three possibilities:
  1. Most are in a shared MDX or CMS-rendered component where the content is trusted server-side — legitimate but needs explicit allowlist entries
  2. Some are on user-generated content without sanitisation — real XSS sinks, must be fixed before any new user onboards
  3. Some are on AI-generated output (LangChain is in the stack) — model output treated as trusted HTML is a classic prompt-injection vector
- Mitigation plan: sample 30 occurrences at random, manually classify them into those three buckets, write the triage plan based on the distribution.
- **978× `console.log in production`** — standard Next.js noise, allowlist strategy same as CCW and RestoreAssist.

### DR-NRPG — the secrets concern
- **2 critical + 60 high `Hardcoded secret` findings** — this is the first place to look when the marathon return briefing said "6 exposed secrets." The real number is much larger.
- **43× `DB connection string`** — database URLs embedded in code. Some are almost certainly Prisma datasource placeholders in schema files, but any real one is an immediate rotation.
- **99× `dangerouslySetInnerHTML (review required)`** — same triage as Disaster-Recovery but at smaller scale.
- **4 critical npm vulnerabilities** — this is the hard blocker. Any critical CVE in a dependency used at runtime is automatic Urgent triage regardless of reachability.

## Roadmap to production-ready

### Phase 0 — Stop the bleeding (week 1, immediate)
- [ ] **DR-SEC-000 (Urgent)** DR-NRPG: identify the 2 critical security findings, file individual tickets, rotate any real credentials
- [ ] **DR-SEC-001 (Urgent)** DR-NRPG: identify the 4 critical npm vulnerabilities, patch or remove dependencies
- [ ] **DR-SEC-002 (Urgent)** Disaster-Recovery + DR-NRPG combined: sample 30 `dangerouslySetInnerHTML` usages across both repos, classify as "safe", "needs wrapper", "XSS risk", report back to founder with distribution and plan
- [ ] **DR-SEC-003 (Urgent)** Both repos: classify all `Hardcoded secret` and `DB connection string` findings, rotate real credentials, allowlist placeholders

### Phase 1 — Dependency hygiene (week 2)
- [ ] **DR-DEP-010** Disaster-Recovery: patch the 6 high npm advisories
- [ ] **DR-DEP-011** DR-NRPG: patch the 21 high npm advisories
- [ ] **DR-DEP-012** Both: medium advisories tracked with 30-day SLA
- [ ] **DR-DEP-013** Both: lock files committed and verified

### Phase 2 — Pattern cleanup (weeks 2-3)
- [ ] **DR-PAT-020** Bulk allowlist pass on `console.log` and `print()` for production code path scoping
- [ ] **DR-PAT-021** Per-line `dangerouslySetInnerHTML` review for the real risks identified in DR-SEC-002
- [ ] **DR-PAT-022** Shared `.pi-seo-ignore` template across the three repos to keep signal-to-noise high

### Phase 3 — Standard compliance (weeks 4-5)
- [ ] **DR-STD-030** Observability audit — includes LangChain call tracing (the AI layer needs its own observability)
- [ ] **DR-STD-031** Documentation audit — README + CLAUDE.md + runbooks per repo
- [ ] **DR-STD-032** `/health` audit — especially any background worker that drives the LangChain pipeline
- [ ] **DR-STD-033** NRPG-Onboarding: full seven-pillar audit pass (tracked as `NRPG-ONB-000` above)

### Phase 4 — Autonomy onboarding (week 6)
- [ ] **DR-AUT-040** Three repos get `.claude/settings.json` allowlists
- [ ] **DR-AUT-041** Three repos registered in Pi-SEO monitor-config
- [ ] **DR-AUT-042** Smoke test Linear tickets for each repo
- [ ] **DR-AUT-043** Charter status → `production-ready` when all three repos pass their smoke tests

## Open questions for Phill — URGENT

1. Are **either** Disaster-Recovery or DR-NRPG currently serving real user traffic? If yes, the XSS sampling has to happen in the next 24 hours, not weeks. Reply: `DR TRAFFIC: yes|no|unsure`
2. Is there a staging environment for both repos where patches can be validated before production? Reply: `DR STAGING: yes|no`
3. The LangChain layer in Disaster-Recovery — what does it process? User-submitted text, uploaded documents, or internal content only? Reply: `DR LANGCHAIN: user|docs|internal`
4. Are the NRPG onboarding flows handling real practitioner PII today, or is the system pre-launch? Reply: `NRPG STATUS: live|pre-launch`

These four answers change the priority ordering in Phase 0. If Disaster-Recovery is live with user traffic and the LangChain layer touches user-submitted text, DR-SEC-002 becomes the single most urgent ticket in the entire portfolio.

## How Pi-CEO will keep you informed

- **Red alert contract (new for this project):** any finding tagged `critical` pushes Telegram immediately via the watchdog, not on the next cycle
- Urgent transitions → Telegram immediately
- Weekly digest (shared across the three repos) on Monday morning
- Real-time push on new criticals in the Pi-SEO hourly dry-run
- No auto-merges, ever
