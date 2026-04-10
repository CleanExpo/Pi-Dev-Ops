# Pi-CEO Standard — what "production-ready" means in this portfolio

**Owner:** Phill (Unite Group)
**Maintained by:** Pi-CEO autonomous rails
**Last updated:** 2026-04-11
**Applies to:** every repo Pi-SEO monitors (`ccw-crm`, `restoreassist`, `disaster-recovery`, `dr-nrpg`, `nrpg-onboarding`, `carsi`, `synthex`, `unite-group`, `nodejs-starter`, `oh-my-codex`, `pi-dev-ops`)

---

## Purpose

Every project in the portfolio gets measured against the same bar. The bar is deliberately boring — most of it is plumbing that should be in place before anyone writes a single new feature. When Phill says "get this project on track for production," this document is what "on track" means. No interpretation, no vibes.

The standard is enforced by Pi-SEO scans (already running 4x/day) and by the marathon watchdog (running every 30 minutes). A project that scores below a category threshold goes onto the work queue automatically. A project that's green across all seven pillars is production-ready by definition.

## The seven pillars

### 1. Security — no hardcoded secrets, no dangerous patterns

**Measured by:** `security` scan type, thresholds per severity level.

**Targets:**
- Zero `critical` findings.
- Zero `high` findings in production code paths (tests and docs get a grace period).
- Low findings tracked but not blocking. `console.log` in a `.md` runbook is fine. `console.log` inside a React component shipped to users is not.
- `dangerouslySetInnerHTML` requires a signed-off `// SAFE: <reason>` comment on the line above OR a DOMPurify wrapper. Raw usage is a high-severity finding.
- Any AWS key pattern (`AKIA`), OpenAI key (`sk-`), Linear key (`lin_api_`), or Anthropic key (`sk-ant-`) in committed code is an automatic **urgent** Linear issue.

**Exit criteria:** latest `security.json` reports 0 high, 0 critical. Any `high` that remains must have an open Linear ticket with `Blocked` label and a documented exception in `.harness/security-exceptions.md`.

### 2. Code quality — score ≥ 80

**Measured by:** `code_quality` scan type.

**Targets:**
- Score ≥ 80/100 in the latest scan.
- Linter passes clean (`next lint`, `ruff`, `eslint` — whichever the project uses).
- Tests run and pass in CI. Tests exist for the critical business paths — the definition of "critical" lives in each project's charter.

**Exit criteria:** latest `code_quality.json` score ≥ 80, CI is green on `main`, test file count ≥ 10% of source file count.

### 3. Dependencies — score ≥ 80, no medium+ vulns

**Measured by:** `dependencies` scan type.

**Targets:**
- Score ≥ 80/100.
- Zero `high` or `critical` npm/pip advisories.
- `medium` advisories tracked in Linear with a 30-day SLA.
- No packages > 12 months out of date on a major version.
- Lock files committed. `package-lock.json` or `pnpm-lock.yaml` or `poetry.lock` — one of them, always.

**Exit criteria:** latest `dependencies.json` score ≥ 80, zero high/critical, no stale mediums past SLA.

### 4. Deployment health — runnable end-to-end

**Measured by:** `deployment_health` scan type + a human smoke test.

**Targets:**
- Score 100/100 on the Pi-SEO scan.
- `Dockerfile`, `railway.toml`, or equivalent in place.
- Environment variables documented in `.env.example` (committed) with no real values.
- A `/health` endpoint that reports truth, not just "process is alive." For any project with background workers, `/health` must include an `armed` boolean per worker and a `seconds_since_last_tick` counter. See Pi-Dev-Ops `main.py` for the reference implementation.
- Rollback procedure documented in a one-page runbook at `docs/runbooks/rollback.md`.

**Exit criteria:** score = 100, `/health` returns a payload that distinguishes "process up" from "work is happening", runbook committed.

### 5. Observability — you can tell when it's broken from your phone

**Measured by:** human audit + scheduled tasks.

**Targets:**
- Structured logs (JSON lines preferred) to stdout. No `print()` for log output. Python projects use `logging` with a `StructuredFormatter`, Node projects use `pino` or `winston`.
- Error tracking connected — Sentry, Honeybadger, or equivalent. DSN in Railway env vars, not committed.
- A Telegram or Slack channel that receives the output of a marathon-watchdog-equivalent for the project. For CCW/RestoreAssist/NRPG the initial target is to reuse the Pi-CEO Telegram bot (`@piceoagent_bot`) with per-project message prefixes.
- A one-line metric Pi-CEO can pull into the cross-portfolio dashboard (e.g. "CCW: 12 active tickets, API p95 320ms, last deploy 4h ago").

**Exit criteria:** one scheduled task per project writes a heartbeat to the shared channel at least hourly, and the `.harness/monitor-digests/` for that project has at least 7 consecutive days of data.

### 6. Documentation — enough for a human to pick it up cold

**Measured by:** human audit against a checklist.

**Targets:**
- `README.md` explains: what it does (2 paragraphs), who it's for, how to run it locally, how to deploy, where the production URL is, who to call when it breaks.
- `CLAUDE.md` at the repo root tells future Claude agents the house rules — stack, style, forbidden patterns, how to run tests, where to file issues.
- `docs/runbooks/` has at minimum: `incident-response.md`, `rollback.md`, `data-migration.md` (even if it says "not applicable yet").
- `docs/architecture.md` has a one-page system diagram. A Mermaid flowchart is enough — this is not an excuse to build a Visio empire.

**Exit criteria:** the README answers the six questions above, `CLAUDE.md` exists and is non-empty, the three runbooks exist.

### 7. Autonomy-ready — Pi-CEO can actually work on this repo

**Measured by:** a green run of the Pi-CEO build pipeline against a test Linear ticket.

**Targets:**
- The project has a Linear team configured and its team ID is on the repo's `.harness/pi-ceo.json` config file.
- `.claude/settings.json` exists with `defaultMode: bypassPermissions` and an allowlist covering the tools this project needs. Mirror the Pi-Dev-Ops `.claude/settings.json` and prune what's not needed.
- Repo has a `CLAUDE.md` that tells the agent where to run tests, what constitutes a definition of done, what the house style is.
- The repo is registered in Pi-SEO's monitor list (`.harness/monitor-config.json`).
- An end-to-end dry run: create a low-risk Linear ticket (e.g. "add a blank line at the end of README.md"), label it with the team, watch the Pi-CEO poller pick it up, build a session, open a PR, close the ticket.

**Exit criteria:** a successful Pi-CEO session on this repo has been observed in `.harness/autonomy.log` in the last 30 days.

---

## How a project moves through the standard

1. **Audit** — Pi-SEO scan produces the baseline JSON files. A human (or an agent) reads them against the seven pillars and writes a charter at `.harness/business-charters/projects/<slug>-charter.md`. The charter records today's score on each pillar and the target score.
2. **Backlog** — every gap in the charter becomes a Linear issue. Gaps tagged `security:high` or `security:critical` become Urgent. Everything else defaults to Normal with a 30-day SLA.
3. **Execute** — the Pi-CEO poller works the backlog in priority order. Each session closes one ticket, opens a PR, runs the tests, and updates the charter with the new score.
4. **Certify** — when all seven pillars are green, the charter is marked `status: production-ready` and the project graduates from "active onboarding" to "steady-state monitoring."
5. **Maintain** — the daily Pi-SEO scans keep the project honest. Any regression that drops a pillar below its threshold files a new Linear issue automatically.

## Non-goals

This standard does NOT prescribe:

- What language or framework a project uses. Go, Python, TypeScript, Rust — all acceptable. The standard measures outcomes, not technology choices.
- What a feature roadmap should contain. That's each project's own business concern.
- What "done" looks like for any specific feature. Definition of Done is a project-level decision — the standard only covers the plumbing everyone agrees on.
- Code style beyond what the project's own linter enforces. No opinion wars over tabs vs spaces or import ordering.

## Variance capture

When a project genuinely cannot meet a pillar — e.g. a legacy project where `dangerouslySetInnerHTML` has a good reason to exist — the variance goes into `.harness/standard-variances.md` with three fields: which pillar, why, and when the variance expires. No open-ended variances. Every one has a review date.

---

## First application

The three projects being onboarded in the 2026-04-11 marathon are:

| Project | Initial Pi-SEO score | Primary gap |
|---------|---|---|
| CCW (CleanExpo/CCW-CRM) | 3/4 pillars green (security partial) | 6374 low-severity security findings — pattern cleanup |
| RestoreAssist (CleanExpo/RestoreAssist) | 3/4 pillars green (security partial) | 433 low-severity security findings — same pattern |
| Disaster Recovery - NRPG (CleanExpo/DR-NRPG + Disaster-Recovery) | 2/4 pillars green | Medium npm vulnerabilities in @langchain/* + high-severity `dangerouslySetInnerHTML` |

Each gets its own charter in this directory. The charters are the source of truth for the work ahead.
