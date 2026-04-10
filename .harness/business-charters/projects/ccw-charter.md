# Project Charter — CCW (CleanExpo/CCW-CRM)

**Status:** active onboarding
**Repo:** https://github.com/CleanExpo/CCW-CRM
**Owner:** Phill (Unite Group)
**Pi-CEO agent:** assigned (marathon 2026-04-11)
**Charter last updated:** 2026-04-11
**Baseline scan:** `.harness/scan-results/ccw-crm/2026-04-10-*.json`

---

## What this project does

CCW (Contents Claims Workflow) is the CRM that CleanExpo uses to manage insurance claims work — customer records, job tickets, photos, reports, and the handoff between field technicians and the office. This charter assumes the mission is to take the current CRM from "works for the team" to "ready to handle a production workload across multiple CleanExpo branches without a founder babysitting it."

## Who Pi-CEO is to this project

Pi-CEO is the autonomous project manager + delivery rail. Its role on CCW is:

1. Keep the repo continuously scanned against the Pi-CEO Standard (see `PI-CEO-STANDARD.md`).
2. File every regression as a Linear issue the moment it appears.
3. Work the backlog in priority order — Urgent first, then High, then Normal — via the build pipeline.
4. Push a PR for every completed session so a human can review before merge.
5. Send Phill a Telegram update on any critical finding, any successful production deploy, and any blocked ticket that needs a founder decision.

Pi-CEO does NOT: make product decisions, touch real customer data, deploy to production without approval, or merge its own PRs.

## Current state against the seven pillars

Numbers below are from the 2026-04-10 Pi-SEO scan. The picture is worse than the earlier portfolio summary suggested — the real finding count is much higher than the initial "6 critical + 6 high" figure.

| Pillar | Score / Finding count | Status | Target |
|---|---|---|---|
| 1. Security | 1 critical + 196 high + 113 medium + 6064 low | **RED** | 0 critical, 0 high, all mediums triaged |
| 2. Code quality | 100/100 | GREEN | ≥ 80 |
| 3. Dependencies | 100/100 | GREEN | ≥ 80 |
| 4. Deployment health | 100/100 | GREEN | 100 |
| 5. Observability | unknown, not yet audited | AMBER | per-project heartbeat + error tracking |
| 6. Documentation | README + CLAUDE.md state unknown | AMBER | README answers the six questions + CLAUDE.md present |
| 7. Autonomy-ready | not yet — no Pi-CEO session observed on this repo | RED | one green end-to-end run in autonomy.log |

### Security breakdown — what's actually in those 6374 findings

- **5583× `print() in production (Python)`** — nearly all of this is noise from Python scripts, migrations, and dev tooling. The rule is overtuned for this codebase. Action: introduce a `.pi-seo-ignore` file that scopes the Python print() rule to `app/` and `services/` only, excluding `scripts/`, `migrations/`, `tests/`, and `tools/`.
- **481× `console.log in production`** — same triage approach but narrower scope. Real production React/Next code should never log to console; everything else can be allowlisted.
- **100× `Hardcoded secret` + 37× `Hardcoded password`** — these are the real risk. Could be real credentials or could be placeholder strings in fixtures and seed files. Needs a manual review per finding. Plan: dump the 137 affected lines, classify as "real secret" / "placeholder" / "test fixture" / "example in docs", then rotate any reals and allowlist the rest.
- **57× `Binding to 0.0.0.0`** — standard Docker/containerised service pattern. Not a real finding. Goes into `.harness/standard-variances.md` as a project-wide variance with a documented reason.
- **1× critical** — needs human eyes on the specific file and line immediately. This is the first ticket filed.

### Gaps 2–7

Cannot be assessed properly without the repo being mounted in the Cowork sandbox. The workspace folder currently contains only Pi-Dev-Ops and Pi-SEO — CCW isn't mounted here. The charter will be updated once the repo is either mounted or the remote is cloned into `.harness/tmp-clones/ccw-crm` for a deeper pass.

## Roadmap to production-ready

### Phase 1 — Security triage (weeks 1-2)
- [ ] **CCW-001 (Urgent)** Identify and resolve the 1 critical finding
- [ ] **CCW-002 (Urgent)** Classify and rotate or allowlist the 137 hardcoded secret/password findings
- [ ] **CCW-003 (High)** Review the 196 high-severity findings, rotate any remaining real secrets, file a variance for any intentional ones
- [ ] **CCW-004 (High)** Write `.pi-seo-ignore` rules to scope print() and console.log checks to production code paths only
- [ ] **CCW-005 (Normal)** Rescan and verify the finding count drops to the targets above

### Phase 2 — Standard compliance (weeks 3-4)
- [ ] **CCW-010** Audit observability — structured logs, error tracking, heartbeat
- [ ] **CCW-011** Audit documentation — README answers the six questions, CLAUDE.md present
- [ ] **CCW-012** Audit `/health` endpoint — does it report background worker state truthfully?
- [ ] **CCW-013** Commit `docs/runbooks/incident-response.md`, `rollback.md`, `data-migration.md`

### Phase 3 — Autonomy onboarding (week 5)
- [ ] **CCW-020** Copy `.claude/settings.json` allowlist pattern from Pi-Dev-Ops, prune to what CCW needs
- [ ] **CCW-021** Register CCW in `.harness/monitor-config.json` for Pi-SEO scans
- [ ] **CCW-022** Create a low-risk smoke test Linear ticket and watch Pi-CEO execute it end-to-end
- [ ] **CCW-023** Mark charter `status: production-ready` once the smoke test is green

## Open questions for Phill

1. Are any of the 137 "hardcoded secret" findings known to be real production credentials? If yes, which ones need rotating first?
2. Is CCW deployed today? If yes, where, and what's the current user count?
3. Who are the CleanExpo branch leads who need visibility into CCW's status? (relevant for the observability channel)
4. What's the most critical CCW workflow that must not regress during cleanup? (defines the "critical business path" test coverage target for pillar 2)

## How Pi-CEO will keep you informed

- Telegram message on any Urgent ticket created, transitioned, or closed
- Weekly Monday morning digest: charter delta + top 3 findings + next 3 actions
- Real-time push on any NEW critical security finding in the Pi-SEO hourly dry-run
- Never auto-merges. PRs land for human review.
