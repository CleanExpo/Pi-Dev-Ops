# NotebookLM Source — CleanExpo
**Prepared:** 2026-04-15 | **Source tickets:** RA-824 | **Status:** Sprint 12 active

---

## 1. What CleanExpo Is

### Purpose

CleanExpo is the GitHub organisation that owns the primary codebase portfolio managed by Pi-CEO. It is the organisational wrapper for Phill's suite of business software products — spanning restoration industry tooling, disaster recovery platforms, service business operations, and shared infrastructure.

CleanExpo is not itself a single product but a product portfolio organisation. In the Pi-CEO framework, "CleanExpo" as an entity refers to:
1. The GitHub organisation (`CleanExpo` on GitHub) and its 11 monitored repositories
2. The parent business entity behind the CCW (commercial cleaning/workflow), restoration, and disaster recovery verticals
3. The organisational context for decisions that affect multiple repos (shared standards, security baseline, deployment platform choices)

### Key Business Verticals Under CleanExpo

| Vertical | Primary Repo | Platform | Status |
|----------|-------------|---------|--------|
| Pi Dev Ops (AI engineering) | CleanExpo/Pi-Dev-Ops | Railway + Vercel | Production (ZTE 85/100) |
| RestoreAssist (NIR compliance) | CleanExpo/RestoreAssist | Vercel + Supabase | Active onboarding |
| Disaster Recovery (client site) | CleanExpo/Disaster-Recovery | disasterrecovery.com.au | Monitored |
| DR-NRPG (operations platform) | CleanExpo/DR-NRPG | TBD | Active onboarding |
| NRPG Onboarding Framework | CleanExpo/NRPG-Onboarding-Framework | TBD | Monitored |
| Synthex (social platform) | CleanExpo/Synthex | Vercel | CVE remediation active |
| Unite Group (dashboard) | CleanExpo/unite-group | Vercel | Monitored |
| CCW-CRM (CRM/ERP) | CleanExpo/CCW-CRM | TBD | Active onboarding |
| CARSI | CleanExpo/carsi | DigitalOcean | Blocked (ADMIN_PASSWORD) |
| NodeJS Starter V1 | CleanExpo/NodeJS-Starter-V1 | TBD | Low priority |
| Oh My Codex | CleanExpo/oh-my-codex | TBD | Low priority |

### Organisation Context

**Owner:** Phill (sole decision-maker, final approver on all phase gates)
**GitHub org:** CleanExpo
**Total monitored repos:** 11
**Total Linear teams:** 4 (RA, DR, UNI, GP)
**Pi-SEO scan coverage:** All 11 repos, multiple scan types

---

## 2. Current Portfolio Health

**Portfolio health score (Pi-SEO dryrun, 2026-04-13):** 12/100 average
**Total critical findings across portfolio:** 35
**Total high findings across portfolio:** 6,509

### Per-Repo Health Summary (2026-04-13 dryrun)

| Repo | Score | Critical | High | Primary Issues |
|------|-------|----------|------|----------------|
| pi-dev-ops | 0/100 | 3 | 3,510 | deployment_health, security (scanner self-scan false positives) |
| restoreassist | 0/100 | 0 | 52 | security |
| synthex | 0/100 | 10 | 379 | dependencies, security |
| ccw-crm | 0/100 | 2 | 422 | security |
| carsi | 0/100 | 2 | 72 | dependencies, security |
| disaster-recovery | 0/100 | 0 | 1,538 | dependencies, security |
| dr-nrpg | 0/100 | 12 | 434 | dependencies, security |
| nodejs-starter | 0/100 | 0 | 38 | security |
| unite-group | 0/100 | 6 | 43 | dependencies, deployment_health, security |
| oh-my-codex | 37/100 | 0 | 21 | dependencies, security |
| nrpg-onboarding | 100/100 | 0 | 0 | — |

**Note on scoring:** The raw dryrun scores (0/100 for most repos) reflect the Pi-SEO scanner's sensitivity to false positives (e.g., `console.log` in test files, placeholder patterns in documentation). Per-category scan files show higher scores — Pi-Dev-Ops is 85/100 code quality, 100/100 deployment health; RestoreAssist is 100/100 for code quality, dependencies, and deployment health. The dryrun aggregate does not apply the per-project exclusion lists.

### ZTE v2 Score (Pi-Dev-Ops platform health)

The ZTE (Zero Touch Engineering) v2 score measures the Pi-Dev-Ops platform itself — the engine that services the CleanExpo portfolio. As of 2026-04-15:

| Section | Score | Max | Notes |
|---------|-------|-----|-------|
| ZTE v1 (capabilities) | 73 | 75 | Near-complete capability set |
| C1 Deployment success | 1 | 5 | No deployment data yet |
| C2 Output acceptance | 1 | 5 | session-outcomes.jsonl not yet written |
| C3 Mean time to value | 1 | 5 | No shipped sessions with push_timestamp yet |
| C4 Security posture | 4 | 5 | Portfolio avg 67, 11 repos scanned |
| C5 Knowledge velocity | 5 | 5 | 7.7 lessons/week, eval avg 9.0/10 |
| **Total v2** | **85** | **100** | Band: Zero Touch |

Sprint 12 target: 85 → 90.

---

## 3. Active Risks and Issues

### Risk 1 (CRITICAL / OPS VETO) — carsi ADMIN_PASSWORD not set in DigitalOcean

**Linear ticket:** RA-950
**Severity:** Urgent
**Description:** The swarm (Pi-CEO's autonomous PR generation system) is blocked from firing on the carsi repository scope until the `ADMIN_PASSWORD` environment variable is set in DigitalOcean App Platform for the carsi service. Without this, any Pi-CEO session targeting carsi will fail at authentication.
**Impact:** Full swarm activation is conditionally blocked by this single item. Pi-Dev-Ops and RestoreAssist are unblocked; carsi scope is not.
**Action required:** Owner (Phill) must set `ADMIN_PASSWORD` in DigitalOcean App Platform for carsi.
**Status:** Open — developer action required. RA-950 in Sprint 12 backlog.

### Risk 2 (HIGH) — Portfolio dependency health: 22 Synthex CVEs, major migrations pending

**Linear ticket:** RA-844
**Severity:** High (multiple repos)
**Description:** The portfolio-wide dependency health is poor. Sprint 11 merged dep health PRs for carsi, DR-NRPG, Synthex, and unite-group (RA-843). Synthex still has 22 CVEs including 1 critical and 8 high. Disaster-recovery has 1,538 high findings from dependency and security scans. DR-NRPG has 12 critical findings. These represent active exploitable vulnerabilities in production systems.
**Mitigation:** Sprint 12 targets Synthex 56 → 80+. Disaster-recovery and DR-NRPG are tracked under the DR Linear team.
**Status:** Active — ongoing remediation sprint.

### Risk 3 (HIGH) — 4 open PRs awaiting human merge; swarm blocked until merged

**Linear tickets:** RA-948 (PR #11), PR #12, PR #13, PR #14
**Severity:** High
**Description:** Four pull requests are open and awaiting human review/merge:
- PR #11 (RA-948): First autonomous PR — swarm_enabled/swarm_shadow in /health
- PR #12: Swarm active mode + bots
- PR #13: Dashboard redesign (Zinc/Geist/sidebar)
- PR #14: RA-837/847 CI webhook + docs synthesis

Until these are merged, the swarm cannot run in active mode on Railway (requires `TAO_SWARM_SHADOW=0` in Railway env, which comes from PR #12), and the CI webhook handler (RA-847) is not live.
**Action required:** Human review and merge of PRs #11–#14.
**Status:** Pending human review.

### Additional Portfolio Risks

**Silent failure in Pi-SEO scanning:** The scanner's `cron-triggers.json` `last_fired_at` resets on Railway redeploy, and a bogus-future-timestamp debounce bug can suppress scheduled scans after every deploy. This means Pi-SEO may not be scanning as frequently as configured without visible indication.

**test suite confidence gap:** ZTE C2 (output acceptance) and C3 (mean time to value) are both at 1/5 because `session-outcomes.jsonl` is not yet being written by live sessions. The system cannot prove autonomous work quality without this data flowing.

**Power dependency (Mac Mini):** The swarm has a Mac Mini node. No UPS (uninterruptible power supply) is in place. The board approved a UPS purchase (≤AUD $500) on 2026-04-15. Until purchased and installed, a power interruption takes down the Mac Mini swarm node.

---

## 4. CleanExpo GitHub Organisation Structure

### Linear Teams and Projects

| Team | Key | Repos Covered |
|------|-----|---------------|
| RestoreAssist | RA | pi-dev-ops, restoreassist, synthex (RA team owns Pi-Dev-Ops Linear project) |
| Disaster Recovery | DR | disaster-recovery, dr-nrpg, nrpg-onboarding |
| Unite Group | UNI | unite-group, ccw-crm, nodejs-starter, oh-my-codex |
| GP (carsi) | GP | carsi |

The RA team ID `a8a52f07-63cf-4ece-9ad2-3e3bd3c15673` is the primary team for Pi-Dev-Ops operations. Linear ticket format: `RA-xxx`.

### Repository Quick Reference

| Repo | Stack | Deployment | Scan Priority |
|------|-------|-----------|---------------|
| Pi-Dev-Ops | FastAPI, Next.js, Python, TypeScript | Railway + Vercel | High (*/6 * * * *) |
| RestoreAssist | Next.js, TypeScript, Supabase | Vercel | High (0 */6 * * *) |
| Disaster-Recovery | Next.js, TypeScript | disasterrecovery.com.au | High (0 */6 * * *) |
| DR-NRPG | Next.js, TypeScript, Supabase | TBD | Medium (0 0 * * *) |
| NRPG-Onboarding-Framework | Next.js, TypeScript | TBD | Medium (0 0 * * *) |
| Synthex | Next.js, TypeScript, Supabase | synthex.social | High (0 */6 * * *) |
| unite-group | Next.js, TypeScript, Supabase, Claude AI | dashboard-unite-group.vercel.app | High (0 */6 * * *) |
| CCW-CRM | Next.js, FastAPI, TypeScript, Python, Supabase | TBD | High (0 */6 * * *) |
| carsi | unknown | DigitalOcean | Medium (0 0 * * *) |
| NodeJS-Starter-V1 | Next.js, FastAPI, PostgreSQL, TypeScript | TBD | Low (0 0 * * 1) |
| oh-my-codex | Python | TBD | Low (0 0 * * 1) |

---

## 5. Pi-CEO Standard — Production-Ready Definition

Every CleanExpo repo is measured against the Pi-CEO Standard ("what production-ready means in this portfolio"). The seven pillars:

### Pillar 1: Security — no hardcoded secrets, no dangerous patterns

Target: zero critical, zero high in production code. `dangerouslySetInnerHTML` requires DOMPurify or a signed-off `// SAFE:` comment. Any AWS/OpenAI/Linear/Anthropic key in committed code triggers an automatic Urgent Linear issue.

Exit criteria: latest `security.json` shows 0 high, 0 critical. Any remaining high needs an open ticket with `Blocked` label.

### Pillar 2: Code quality — score ≥ 80

Target: score ≥ 80/100, linter passes clean, tests run and pass in CI, test file count ≥ 10% of source file count.

### Pillar 3: Dependencies — score ≥ 80, no medium+ vulns

Target: zero high/critical npm/pip advisories, medium advisories tracked with 30-day SLA, no packages > 12 months out of date on a major version, lock files committed.

### Pillar 4: Deployment health — runnable end-to-end

Target: score 100/100, Dockerfile/railway.toml in place, `.env.example` committed, `/health` endpoint reports truth (armed boolean + seconds_since_last_tick for background workers), rollback runbook at `docs/runbooks/rollback.md`.

### Pillar 5: Observability — visible when broken from phone

Target: structured JSON logs to stdout, error tracking connected (Sentry/Honeybadger), Telegram or Slack channel for alerts, one-line metric available for cross-portfolio dashboard.

### Pillar 6: Documentation — enough for a cold start

Target: README answers what it does, who it's for, how to run locally, how to deploy, production URL, who to contact when broken. CLAUDE.md at repo root. Three runbooks: incident-response, rollback, data-migration. `docs/architecture.md` with system diagram.

### Pillar 7: Autonomy-ready — Pi-CEO can work on this repo

Target: Linear team configured and in `.harness/pi-ceo.json`, `.claude/settings.json` with `defaultMode: bypassPermissions`, repo registered in Pi-SEO monitor list, successful end-to-end Pi-CEO session observed in last 30 days.

---

## 6. Architecture: How Pi-CEO Serves the Portfolio

### Pi-Dev-Ops Platform Architecture

```
Linear Todo ticket
    │
    ▼ (every 5 min, first poll at +10s after restart)
autonomy.py poller
    │
    ▼
sessions.py — build session creation
    │
    ├── Phase 1: git clone (3-attempt backoff)
    ├── Phase 2: workspace analysis
    ├── Phase 3: Claude availability check
    ├── Phase 3.5: sandbox verification
    ├── Phase 4: Claude Agent SDK generator
    ├── Phase 4.5: confidence-weighted evaluator (blocking gate, threshold 8/10)
    └── Phase 5: git push to feature branch (3-attempt backoff)
    │
    ▼
lessons.jsonl — auto-learns from evaluator scores
    │
    ▼
Pi-SEO re-scan → Linear triage → board meeting (9 personas)
```

### Deployment Topology for Pi-Dev-Ops

| Component | Platform | URL/Location |
|-----------|---------|-------------|
| Backend (FastAPI) | Railway | https://pi-dev-ops-production.up.railway.app |
| Frontend (Next.js) | Vercel | https://dashboard-unite-group.vercel.app |
| MCP Server | Node.js local | `mcp/pi-ceo-server.js` |
| Database | Supabase | PostgreSQL (6 tables) |
| CI | GitHub Actions | 3 jobs: python, frontend, smoke-prod |

### Key Environment Variables (Railway)

| Variable | Purpose |
|----------|---------|
| `TAO_USE_AGENT_SDK=1` | Mandatory — Agent SDK mode |
| `TAO_PASSWORD` | Auth for build API |
| `LINEAR_API_KEY` | Enables Linear triage and autonomy poller |
| `GITHUB_TOKEN` | Push to feature branches |
| `GITHUB_REPO` | Target repo for push |
| `TAO_AUTONOMY_ENABLED` | Kill switch (set 0 to stop poller) |
| `TAO_SWARM_SHADOW=0` | Activates swarm (was shadow mode) |
| `TAO_USE_AGENT_SDK_CANARY_RATE=0.5` | Phase B canary (pending Railway set) |
| `ADMIN_PASSWORD` (carsi) | Required in DigitalOcean before carsi scope works |

---

## 7. Business Context

### Pi-CEO as Founder OS

The strategic framing from the 2026-04-13 CEO memo: Pi-CEO is a "Founder OS" — an intelligent business operating system for a non-technical founder. The design intent is that Phill makes only strategic decisions; all execution (code, deployment, testing, monitoring, triage) is autonomous.

Current state: execution capability is high (ZTE 85/100, 98 features shipped, 33 skills loaded, 21 MCP tools). The gap is in proving the loop works — ZTE C2 and C3 are at 1/5 because live session data is not flowing yet.

### Business Velocity Index (BVI)

Introduced in Cycle 24 as the primary metric, replacing ZTE score as the lead number on board reports.

Components:
1. CRITICAL alert resolution speed — time from alert raised to resolved
2. Portfolio health improvement — projects showing positive delta cycle-over-cycle
3. Features delivered to real users — MARATHON completions shipped to clients

Cycle 23 baseline: CRITICALs resolved = 0, portfolio projects improved = 0, MARATHON completions = 0.

### MARATHON (Autonomous Multi-Session Runs)

MARATHON-4 (RA-588) was the first 6-hour autonomous self-maintenance run. Completed in Sprint 11. Establishes the pattern for unattended overnight execution.

### Board Personas (9 active)

The CEO Board operates with 9 personas that deliberate on strategic decisions:
- ORACLE, CONTRARIAN, STRATEGIST, OPS, MARATHON (confirmed from board meeting records)

Board meeting schedule: automated, runs at 0/6/12/18 AEST. Next scheduled: 6 May 2026 (Enhancement Review, RA-949).

---

## 8. Current Sprint Summary (Sprint 12, Active 2026-04-15)

**Theme:** Swarm Activation + ZTE v2 85 → 90 + NotebookLM KB Build

### Immediate Merge Queue (Human Action Required)

| PR | Ticket | Title | Status |
|----|--------|-------|--------|
| #11 | RA-948 | First autonomous PR — swarm_enabled/swarm_shadow in /health | Pending |
| #12 | — | Swarm active mode + bots | Pending |
| #13 | — | Dashboard redesign | Pending |
| #14 | RA-837/847 | CI webhook + docs synthesis | Pending |

### Active Sprint Items

| Ticket | Priority | Title | Status |
|--------|----------|-------|--------|
| RA-822 | High | NotebookLM KB — RestoreAssist | In Review |
| RA-823 | High | NotebookLM KB — Synthex | In Review |
| RA-824 | High | NotebookLM KB — CleanExpo | In Review |
| RA-838 | High | SDK Canary Phase B (TAO_USE_AGENT_SDK_CANARY_RATE=0.5 in Railway) | Railway action needed |
| RA-886 | High | Branch protection — CI required before merge | In Review |
| RA-950 | Urgent | OB-4: carsi ADMIN_PASSWORD in DigitalOcean | Developer action |
| RA-830 | Medium | Google Cloud Next '26 (22-24 Apr) — capture AI/NotebookLM delta | Todo |

### Sprint 12 Targets by Track

| Track | Target |
|-------|--------|
| NotebookLM KBs | RA-822/823/824 complete |
| Dashboard live | PR #13 merged + Vercel deploy |
| CI webhook | PR #14 merged + workflow_run events on all repos |
| Swarm active | PR #12 merged + Railway TAO_SWARM_SHADOW=0 |
| Synthex health | 56 → 80+ |
| ZTE v2 | 85 → 90 |

---

## 9. Key Integrations Across Portfolio

| Integration | Scope | Purpose |
|-------------|-------|---------|
| Supabase | Pi-Dev-Ops + most repos | Database, auth, 6 observability tables in Pi-Dev-Ops |
| Vercel | Pi-Dev-Ops, RestoreAssist, Synthex, unite-group | Frontend hosting |
| Railway | Pi-Dev-Ops | Backend hosting, always-on autonomy poller |
| DigitalOcean | carsi | Hosting (ADMIN_PASSWORD required) |
| Linear | All repos | Issue tracking, sprint management, auto-triage |
| GitHub Actions | Pi-Dev-Ops (and planned all repos) | CI — pytest, tsc, smoke-prod |
| Telegram (@piceoagent_bot) | Portfolio-wide | Alerts, bidirectional Founder OS interface |
| Anthropic SDK (Claude Agent SDK) | Pi-Dev-Ops engine | Generator, evaluator, board meetings |
| Pi-SEO scanner | All 11 repos | Security, code quality, dependencies, deployment health |
| NotebookLM | 3 primary entities | Knowledge base for AI-assisted Q&A |
| n8n (planned) | Per-entity | RSS → Google Doc → NotebookLM refresh workflow |
| Prisma | Synthex, CCW-CRM | ORM |
| Storybook | Synthex | Component library |

---

## 10. Observability Tables (Pi-Dev-Ops / Supabase)

Pi-Dev-Ops writes to 6 Supabase tables. All writes are fire-and-forget — observability failures must never block the build pipeline.

| Table | Purpose |
|-------|---------|
| `gate_checks` | Per-session evaluator gate results |
| `alert_escalations` | Escalations surfaced to Telegram/Linear |
| `heartbeat_log` | Periodic liveness records from the autonomy poller |
| `triage_log` | Pi-SEO triage decisions — findings → Linear ticket mapping |
| `workflow_runs` | Build session lifecycle events |
| `claude_api_costs` | Per-session token costs from Anthropic SDK |

---

## 11. Source References

- `/Pi-Dev-Ops/CLAUDE.md` — architecture, routes, patterns, Sprint 12 context
- `/Pi-Dev-Ops/.harness/projects.json` — full portfolio repo registry
- `/Pi-Dev-Ops/.harness/executive-summary.md` — cumulative metrics, sprint history
- `/Pi-Dev-Ops/.harness/sprint_plan.md` — Sprint 12 active items, merge queue
- `/Pi-Dev-Ops/.harness/zte-v2-score.json` — ZTE v2 score breakdown
- `/Pi-Dev-Ops/.harness/ARCHITECTURE-V2.md` — V2 topology (Railway + GH Actions + Cowork)
- `/Pi-Dev-Ops/.harness/business-charters/PI-CEO-STANDARD.md` — 7-pillar production standard
- `/Pi-Dev-Ops/.harness/board-meetings/2026-04-15-activation-vote.md` — swarm activation conditions
- `/Pi-Dev-Ops/.harness/board-meetings/2026-04-13-ceo-memo-board-minutes.md` — BVI definition, restructure decision
- `/Pi-Dev-Ops/.harness/monitor-digests/dryrun-2026-04-13-2123.md` — per-repo health scores
- `/Pi-Dev-Ops/.harness/notebooklm-registry.json` — entity KB registration
