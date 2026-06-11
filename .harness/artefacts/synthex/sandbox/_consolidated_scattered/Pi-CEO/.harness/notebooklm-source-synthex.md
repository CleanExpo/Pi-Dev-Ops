# NotebookLM Source — Synthex
**Prepared:** 2026-04-15 | **Source tickets:** RA-823, RA-844 | **Status:** Sprint 12 active

---

## 1. What Synthex Is

### Purpose

Synthex is a social platform product under the CleanExpo GitHub organisation. It is deployed at https://synthex.social. The platform is built on the standard CleanExpo stack (Next.js, TypeScript, Supabase) with significant additional tooling including Prisma ORM, Hono HTTP framework, Storybook, and AI integrations via the Anthropic SDK.

Synthex is one of the three highest-priority entities for Pi-CEO's NotebookLM knowledge base build (alongside RestoreAssist and CleanExpo). It is tracked under its own Linear team: Synthex team (SYN), team ID `b887971b-6761-4260-a111-b94dbb628ebe`, project ID `3125c6e4-b729-48d4-a718-400a2b83ddc5`.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, TypeScript, React |
| ORM | Prisma |
| HTTP framework | Hono (with `@hono/node-server`) |
| Database | Supabase (PostgreSQL) |
| Testing | Storybook, Playwright |
| AI integration | Anthropic SDK (`@anthropic-ai/sdk`) |
| Email | Nodemailer |
| GitHub org | CleanExpo |
| Repo | CleanExpo/Synthex |
| Production URL | https://synthex.social |
| Linear team key | SYN |
| Scan priority | High (scanned every 6 hours by Pi-SEO) |

---

## 2. Current Status and Health

**Overall Pi-SEO health:** Critical — scored 0/100 in the portfolio dryrun digest (2026-04-13). This is driven by the dependency vulnerability count and security posture.

**Pi-SEO scan date:** 2026-04-12

### Health Pillar Scorecard

| Pillar | Score | Status | Notes |
|--------|-------|--------|-------|
| 1. Security | Low (dryrun: 10 critical, 379 high) | RED | Exposed keys in docs/runbooks/scripts found earlier; error leakage fixed (RA-786) |
| 2. Code quality | 85/100 | GREEN | Zero high/critical code quality findings |
| 3. Dependencies | 0/100 | RED | 1 critical, 8 high, multiple medium vulns — see CVE list below |
| 4. Deployment health | 100/100 | GREEN | synthex.social live and reachable |
| 5. Observability | Unknown | AMBER | No confirmed heartbeat or error tracking |
| 6. Documentation | Unknown | AMBER | README/CLAUDE.md/runbooks not confirmed |
| 7. Autonomy-ready | Partial | AMBER | Dep health PR merged (RA-843); full autonomy onboarding not confirmed |

### Sprint 11 Synthex Work Completed

| Ticket | Change | Status |
|--------|--------|--------|
| RA-843 | Dependency health PR for Synthex merged (one of 4 repos) | Done |
| RA-844 | Synthex CVEs reduced from 28 → 22 (6 migrations completed) | Done |
| RA-786 | Synthex error message leakage fixed — 107 API routes patched | Done |

---

## 3. Active Risks and Issues

### Risk 1 (CRITICAL) — Dependency vulnerability backlog: 22 remaining CVEs including critical severity

**Linear ticket:** RA-844 (In Progress / Sprint 12)
**Severity:** Critical
**Description:** As of 2026-04-12, Synthex has 1 critical, 8 high, and multiple medium/low npm vulnerabilities. Sprint 11 addressed 6 migrations (reducing the count from 28 to 22). 22 remain. The most severe are:

**Critical CVEs:**
- `axios` ≤1.14.0: SSRF via NO_PROXY hostname normalisation bypass. Auto-fixable via `npm audit fix`.
- `handlebars` 4.0.0–4.7.8: JavaScript injection via AST type confusion. Auto-fixable.

**High CVEs:**
- `@hono/node-server` ≤1.19.12: Authorization bypass for static paths via encoded slashes in Serve Static Middleware. NOT auto-fixable (requires major version migration).
- `@prisma/config` range affected: prototype pollution via `effect` dependency. NOT auto-fixable.
- `@prisma/dev` ≤0.22.0: chains to `@hono/node-server`. NOT auto-fixable.
- `@xmldom/xmldom` <0.8.12: XML injection via unsafe CDATA serialization. Auto-fixable.
- `basic-ftp` ≤5.2.1: Incomplete CRLF injection protection. Auto-fixable.
- `defu` ≤6.1.4: Prototype pollution via `__proto__`. Auto-fixable.
- `effect` <3.20.0: AsyncLocalStorage context lost under concurrent load. NOT auto-fixable.
- `hono` ≤4.12.11: XSS via ErrorBoundary component. Auto-fixable.
- `lodash` ≤4.17.23: Prototype pollution in `_.unset` and `_.omit`. NOT auto-fixable.
- `next` 16.0.0-beta.0–16.2.2: DoS via Server Components. Auto-fixable.
- `prisma` version range: chains to `@prisma/config`. NOT auto-fixable.
- `picomatch` ≤2.3.1 or 4.0.0–4.0.3: Method injection in POSIX character classes. Auto-fixable.

**Medium CVEs:**
- `@anthropic-ai/sdk` 0.79.0–0.80.0: Memory Tool Path Validation sandbox escape to sibling directories.
- `@chevrotain/cst-dts-gen`, `@chevrotain/gast`, `chevrotain`: chains from `@mrleebo/prisma-ast`.
- `@mrleebo/prisma-ast` 0.4.2–0.13.1: chains to chevrotain.
- `brace-expansion` ≤1.1.12 etc.: process hang and memory exhaustion.
- `nodemailer` ≤8.0.4: SMTP command injection via unsanitised `envelope.size`.
- `yaml` 2.0.0–2.8.2: stack overflow via deeply nested YAML. Auto-fixable.

**Low CVEs:** `@storybook/nextjs`, `browserify-sign`, `create-ecdh`, `crypto-browserify`, `elliptic`, `node-polyfill-webpack-plugin` — cryptographic primitive risks, mostly transitive.

**Mitigation:** Sprint 12 target is Synthex health 56 → 80+. The non-auto-fixable CVEs (hono, prisma, effect, lodash) require major version migrations. The board set this as a 3-week sprint target (15 Apr → 6 May 2026).

### Risk 2 (HIGH) — Exposed API keys in docs/runbooks/scripts (pre-Sprint 11)

**Linear ticket:** Flagged in 2026-04-12 board minutes
**Severity:** High
**Description:** Pi-SEO scan found exposed keys across dr-nrpg, synthex, ccw-crm in `docs/runbooks` and `scripts/` directories. A `detect-secrets` pre-commit hook deployment was recommended as the fix.
**Mitigation:** RA-843 dep health PR included some remediation. Full `detect-secrets` hook deployment across all portfolio repos is a recommended follow-on action from the board meeting.
**Status:** Partially resolved — confirm via next Pi-SEO security scan.

### Risk 3 (MEDIUM) — Error message leakage in 107 API routes (resolved in Sprint 11, needs verification)

**Linear ticket:** RA-786 (Done)
**Severity:** Medium (historical — resolved)
**Description:** 107 API routes were leaking internal error messages to clients. Fix was pushed in Sprint 11 (RA-786). Risk remains that verification of the fix across all 107 routes was not independently confirmed in a fresh scan.
**Mitigation:** Run a fresh Pi-SEO security scan post-Sprint 11. Check that error handling in API routes no longer surfaces stack traces or internal messages to 4xx/5xx responses.
**Status:** Marked Done in Linear — awaiting scan confirmation.

### Additional Risk Context from Board Meetings

From the 2026-04-12 board minutes: "Pre-commit `detect-secrets` hook deployment. Pi-SEO scan found 6 exposed keys across dr-nrpg, synthex, ccw-crm in docs/runbooks and scripts/. Adding the hook to all portfolio repos before Pi-SEO full activation prevents the scanner from surfacing the same findings repeatedly."

From the sprint plan: Synthex health target for Sprint 12 is 56 → 80+. The current dryrun score of 0/100 reflects the unpatched CVE load. Once the 22 remaining CVEs are resolved, the dependency score should recover significantly.

---

## 4. Architecture Overview

### System Architecture

```
Browser / Mobile
    │
    ▼
Next.js 16 Frontend (TypeScript)
    ├── React 19 components
    ├── Storybook (component library)
    └── Playwright (E2E tests)
    │
    ▼
Hono HTTP Layer (@hono/node-server)
    ├── API routing
    ├── Static file serving (NOTE: ≤1.19.12 has auth bypass vuln)
    └── ErrorBoundary (NOTE: ≤4.12.11 has XSS vuln)
    │
    ▼
Supabase (PostgreSQL)
    ├── Prisma ORM (data access layer)
    └── Auth (user sessions)
    │
    ▼
External Integrations
    ├── Anthropic SDK (AI features)
    └── Nodemailer (email delivery)
```

### Deployment Topology

| Component | Platform | URL |
|-----------|---------|-----|
| Frontend | Vercel (inferred from CleanExpo standard) | https://synthex.social |
| Database | Supabase cloud | Managed |
| CI | GitHub Actions (inferred) | CleanExpo/Synthex |

### Key Dependency Graph (CVE-relevant)

The major CVE chains in Synthex all trace back to a few packages:

1. **Prisma ecosystem chain:** `prisma` → `@prisma/config` → `effect` → `@hono/node-server` / `@prisma/dev`
2. **Chevrotain chain:** `@mrleebo/prisma-ast` → `chevrotain` → `@chevrotain/cst-dts-gen` / `@chevrotain/gast`
3. **Storybook chain:** `@storybook/nextjs` → `node-polyfill-webpack-plugin` → `crypto-browserify` → `browserify-sign` / `elliptic`
4. **Direct high-risk packages:** `axios`, `handlebars`, `lodash`, `hono`, `next`, `basic-ftp`, `defu`

Resolving the Prisma ecosystem chain will close the largest cluster of interrelated CVEs.

---

## 5. Key Integrations

| Integration | Purpose | Status |
|-------------|---------|--------|
| Supabase | Database, auth | Active |
| Vercel | Frontend hosting | Active (synthex.social live) |
| Prisma | ORM for database access | Active (version range has CVEs) |
| Hono | HTTP server/routing | Active (version has auth bypass CVE) |
| Anthropic SDK | AI features | Active (version range has sandbox escape CVE) |
| Nodemailer | Email delivery | Active (version has SMTP injection CVE) |
| Storybook | Component development | Active (version has transitive crypto vulns) |
| Playwright | E2E testing | Active |
| Pi-SEO | Security and health scanning | Active (scanning 4x/day) |
| Pi-CEO (Pi-Dev-Ops) | Autonomous backlog execution | Active (RA-843 dep PR merged) |
| Linear (SYN team) | Issue tracking | Active |
| @piceoagent_bot (Telegram) | Alerts | Shared with portfolio (planned) |

---

## 6. CVE Remediation Roadmap

### Already Completed (Sprint 11)

6 CVE migrations done (RA-844). Specific packages not itemised in available records but count reduced from 28 to 22.

### Remaining Work (Sprint 12 target: 56 → 80+)

Auto-fixable (run `npm audit fix --force` carefully):
- `axios`: upgrade to ≥1.14.1
- `handlebars`: upgrade to ≥4.7.9
- `@xmldom/xmldom`: upgrade to ≥0.8.12
- `basic-ftp`: upgrade to ≥5.2.2
- `defu`: upgrade to ≥6.1.5
- `hono`: upgrade to ≥4.12.12
- `next`: upgrade (coordinate with Next.js 16 compatibility)
- `picomatch`: upgrade
- `brace-expansion`: upgrade
- `yaml`: upgrade to ≥2.8.3

Requires major version migration (manual work):
- `@hono/node-server`: upgrade beyond 1.19.12 (review breaking changes)
- `@prisma/config` and `prisma`: follow Prisma upgrade guide
- `effect`: upgrade to ≥3.20.0 (review Effect library breaking changes)
- `lodash`: upgrade to ≥4.17.24 or replace with individual function imports

### Pi-CEO Standard Exit Criteria for Dependencies

- Score ≥ 80/100 on the `dependencies.json` scan
- Zero high or critical npm advisories
- Medium advisories tracked in Linear with 30-day SLA
- No packages > 12 months out of date on a major version

---

## 7. Sprint and Board Context

### Sprint 12 Targets for Synthex (15 Apr → 6 May 2026)

| Target | Current | Goal |
|--------|---------|------|
| Health score | 56/100 (estimated) | 80+ |
| CVE count | 22 remaining | 0 high/critical |
| Board review | 6 May 2026 | Synthex health progress reported |

### Historical Sprint Work

**Sprint 11 (completed 2026-04-14):**
- RA-843: Dep health PR for Synthex merged (one of 4 repos in the batch: carsi/DR-NRPG/Synthex/unite-group)
- RA-844: 6 CVE migrations complete, count 28 → 22
- RA-786: Error message leakage — 107 API routes patched

**Sprint 10:**
- RA-786 planned and executed — Synthex error leakage fix was a Sprint 10 target

---

## 8. Pi-CEO Monitoring Configuration

From `.harness/projects.json`:

```json
{
  "id": "synthex",
  "repo": "CleanExpo/Synthex",
  "linear_project_id": "3125c6e4-b729-48d4-a718-400a2b83ddc5",
  "linear_team_id": "b887971b-6761-4260-a111-b94dbb628ebe",
  "linear_team_key": "SYN",
  "stack": ["Next.js", "TypeScript", "Supabase"],
  "deployments": { "frontend": "https://synthex.social" },
  "scan_priority": "high",
  "scan_schedule": "0 */6 * * *"
}
```

Pi-SEO scans Synthex every 6 hours. Scan types: security, code_quality, dependencies, deployment_health, linear_hygiene.

---

## 9. Source References

- `/Pi-Dev-Ops/.harness/scan-results/synthex/2026-04-12-dependencies.json` — full CVE list, health_score: 0
- `/Pi-Dev-Ops/.harness/scan-results/synthex/2026-04-12-code_quality.json` — health_score: 85
- `/Pi-Dev-Ops/.harness/scan-results/synthex/2026-04-12-deployment_health.json` — health_score: 100
- `/Pi-Dev-Ops/.harness/scan-results/synthex/2026-04-12-security.json` — security findings (large file)
- `/Pi-Dev-Ops/.harness/projects.json` — repo registration, Linear IDs
- `/Pi-Dev-Ops/.harness/sprint_plan.md` — RA-843, RA-844, Sprint 11 and 12 context
- `/Pi-Dev-Ops/.harness/board-meetings/2026-04-12-board-minutes.md` — detect-secrets recommendation
- `/Pi-Dev-Ops/.harness/board-meetings/2026-04-15-activation-vote.md` — Sprint 12 Synthex health target
- `/Pi-Dev-Ops/.harness/executive-summary.md` — ZTE context, sprint history
- `/Pi-Dev-Ops/.harness/business-charters/PI-CEO-STANDARD.md` — production-ready seven pillars
