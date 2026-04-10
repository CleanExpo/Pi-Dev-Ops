# Project Charter — RestoreAssist (CleanExpo/RestoreAssist)

**Status:** active onboarding
**Repo:** https://github.com/CleanExpo/RestoreAssist
**Owner:** Phill (Unite Group)
**Pi-CEO agent:** assigned (marathon 2026-04-11)
**Charter last updated:** 2026-04-11
**Baseline scan:** `.harness/scan-results/restoreassist/2026-04-10-*.json`

---

## What this project does

RestoreAssist is the field-facing application for CleanExpo restoration technicians — the tool they use on site to capture inspection data, photos, damage assessments, and the National Inspection Report (NIR). Context from the `restoreassist-national-inspection-report-nir-initiative` skill: the NIR is a strategic Australian restoration industry initiative, and this app is how technicians generate compliant NIR reports from their phones and tablets.

This charter assumes the mission is to make RestoreAssist ready to support the NIR rollout across the Australian restoration industry without per-deployment hand-holding. That means production-grade reliability, security sound enough to handle insurance-claim-level PII, and a deployment pipeline that doesn't need a human to stand over it.

## Who Pi-CEO is to this project

Same role as CCW: autonomous project manager + delivery rail. Continuously scan, file, execute, PR, notify. Does not touch real inspection data, does not deploy to production unapproved, does not merge its own PRs.

## Current state against the seven pillars

| Pillar | Score / Finding count | Status | Target |
|---|---|---|---|
| 1. Security | 25 high + 6 medium + 402 low | **RED** | 0 critical, 0 high in prod code, mediums triaged |
| 2. Code quality | 100/100 | GREEN | ≥ 80 |
| 3. Dependencies | 100/100 | GREEN | ≥ 80 |
| 4. Deployment health | 100/100 | GREEN | 100 |
| 5. Observability | unknown | AMBER | heartbeat + error tracking |
| 6. Documentation | unknown | AMBER | README + CLAUDE.md + runbooks |
| 7. Autonomy-ready | not yet | RED | one green end-to-end run |

### Security breakdown — smaller than CCW but the same story

- **347× `console.log in production`** — Next.js / React codebase noise. Scope the rule to `app/`, `components/`, and `lib/` only; exclude `scripts/`, `prisma/seed*`, `.do/`, and `docs/`.
- **55× `print() in production (Python)`** — limited Python surface, likely in `tools/` or `scripts/`. Same allowlist approach.
- **14× `dangerouslySetInnerHTML`** — this is the real one. Each instance needs either a `DOMPurify.sanitize()` wrapper or a documented `// SAFE: <reason>` comment and a line-level allowlist. `dangerouslySetInnerHTML` on HTML content that came from a form field is a real XSS risk; `dangerouslySetInnerHTML` on a server-rendered Markdown component is usually fine.
- **9× `Hardcoded password`** — needs manual classification. Most likely test fixtures or seed data, but every one must be checked before it's allowlisted.
- **4× `TODO near sensitive keyword`** — code comments flagging unfinished security-adjacent work. Convert each to a Linear ticket so the TODO actually gets tracked.

### Gaps 2–7

Same caveat as CCW: cannot fully assess without the repo mounted or cloned. Pillars 5, 6, 7 stay AMBER/RED until a deeper pass is possible.

## Roadmap to production-ready

### Phase 1 — Security triage (week 1)
- [ ] **RA-CLEAN-001 (Urgent)** Classify and rotate the 9 hardcoded password findings
- [ ] **RA-CLEAN-002 (High)** Review the 14 `dangerouslySetInnerHTML` findings — for each, either wrap in DOMPurify or add a signed-off `// SAFE:` comment with a variance entry
- [ ] **RA-CLEAN-003 (High)** Review remaining high-severity findings from the other 2 "Hardcoded secret" items
- [ ] **RA-CLEAN-004 (Normal)** Convert the 4 `TODO near sensitive keyword` items to explicit Linear tickets
- [ ] **RA-CLEAN-005 (Normal)** Scope console.log and print() rules to production code paths via `.pi-seo-ignore`

### Phase 2 — NIR readiness (weeks 2-3)
- [ ] **RA-CLEAN-010** Audit the NIR PDF generation pipeline against the `restoreassist-national-inspection-report-nir-initiative` skill requirements
- [ ] **RA-CLEAN-011** Verify PII handling meets Australian privacy standards — at minimum the Privacy Act 1988 / APPs
- [ ] **RA-CLEAN-012** Document the NIR compliance mapping in `docs/compliance/nir.md`

### Phase 3 — Standard compliance (weeks 3-4)
- [ ] **RA-CLEAN-020** Observability audit — structured logs + Sentry/Honeybadger + heartbeat
- [ ] **RA-CLEAN-021** Documentation audit — README, CLAUDE.md, three runbooks
- [ ] **RA-CLEAN-022** `/health` endpoint audit + PDF pipeline health check

### Phase 4 — Autonomy onboarding (week 5)
- [ ] **RA-CLEAN-030** `.claude/settings.json` allowlist for RestoreAssist
- [ ] **RA-CLEAN-031** Register in Pi-SEO monitor-config
- [ ] **RA-CLEAN-032** Smoke test Linear ticket + observed green end-to-end run
- [ ] **RA-CLEAN-033** Mark charter `status: production-ready`

## Open questions for Phill

1. Is RestoreAssist already in production with real NIR reports going out, or still in pre-production?
2. Who is the NIR compliance contact on the CleanExpo side? (important for the compliance-mapping deliverable)
3. Is there an existing PII handling policy for RestoreAssist? If yes, where does it live?
4. What's the target branch cadence for NIR features — weekly, fortnightly, monthly?

## How Pi-CEO will keep you informed

Same contract as CCW: Telegram on Urgent transitions, weekly digest Monday morning, real-time on new critical findings, no auto-merges.
