# Pi-CEO Autonomous Rails — V2 Architecture Design

**Status:** draft, for Phill's review
**Date:** 2026-04-12
**Replaces:** the "marathon rails" architecture that failed overnight on 2026-04-11→12
**Author:** Pi-CEO (Sunday morning post-mortem)

---

## Why we need V2

V1 had the right ideas and the wrong topology. The watchdog, the bidirectional Telegram loop, the Pi-SEO dry-runs, the lessons file, the charters — every individual component is sound. The problem is where they run. V1 put them inside Cowork scheduled tasks, which turned "autonomous" into "active only when Phill's Mac is open." The overnight failure was the inevitable consequence of that choice.

V2 fixes the topology. Same components, different homes.

## The one-sentence architecture

**Everything that needs to run 24/7 runs on Railway. Everything that needs to run only when Phill is present runs in Cowork. And there is a single source of truth — a GitHub Actions workflow — for "are the tests actually green."**

## The three environments

### Environment A: Railway (always-on, the real rail)

This is the only place that truly runs 24/7. Costs money. Has predictable package state. Has outbound network. Has secrets. Has git push credentials.

**Runs on Railway:**

1. **Pi-Dev-Ops FastAPI server** — already there. HTTP API for session creation, /health endpoint, the autonomy poller that watches Linear.
2. **Autonomy poller** — the `linear_todo_poller` background coroutine. Fetches Todo Linear issues every 5 minutes (first poll at +10s after startup — the fix from commit e611b1c that's still unpushed), creates sessions, commits, pushes, closes tickets.
3. **Pi-SEO scheduler** — the three cron-trigger entries (high priority scans 4x/day, medium 1x/day, low 1x/day) move out of the Cowork scheduled-tasks MCP and into Pi-Dev-Ops itself as APScheduler jobs. Scan results land in a Railway-attached volume or get pushed to a shared S3 bucket. Not in `.harness/scan-results/` on a sandbox disk that doesn't exist after the sandbox rotates.
4. **Health watchdog** — a simple endpoint `/api/admin/selftest` that runs every 5 minutes inside the Pi-Dev-Ops process itself. Reads its own state, verifies the poller is alive, verifies Linear is reachable, verifies the SDK can round-trip, writes a status row to Postgres (or a redis key if we don't want Postgres yet). If anything fails, it writes to Telegram via an outbound HTTP call.
5. **Telegram outbound** — the existing `send_telegram.py` script becomes a Python module called directly from the FastAPI app. No sandbox, no scheduled task, just an inline function call when the watchdog wants to tell Phill something.
6. **Telegram inbound** — a FastAPI endpoint `/webhook/telegram` that's registered with Telegram's Bot API as a webhook. No polling. Telegram pushes messages to Railway; Railway routes them into a queue the autonomy poller reads. Inbound latency drops from 5 minutes (current polling) to sub-second.

**Does NOT run on Railway:**

- The Agent SDK build sessions themselves. Those are ephemeral Claude processes — each session is spun up in response to a Linear ticket, runs to completion, exits. Railway is just the scheduler that decides when to spin one up.

### Environment B: GitHub Actions (the test-truth rail)

This is the only place we should ever ask "are the tests green?" It has a known, reproducible environment. It runs on every commit, and on a schedule.

**Runs on GH Actions:**

1. **pytest on every push to `main`.** Full suite, real dependencies, Python 3.11 (matching `pyproject.toml`'s `requires-python`). Exit code writes to a status check on the commit. The commit is "green" or "red" based on this, not based on a watchdog running in an unknown sandbox.
2. **pytest on a schedule** — every 30 minutes via `workflow_dispatch` cron. Same suite, same environment. Result goes to a `tests-status.json` file checked into a `status/` branch (or published as a GH Pages JSON endpoint). Railway's watchdog reads this file to know whether tests are green — not by running pytest itself.
3. **Pi-SEO scanner on a schedule** — every 6 hours, scan all 11 repos, write findings to the `status/` branch. This replaces the Cowork dry-run task entirely.
4. **Deploy-on-green** — when pytest passes on `main`, trigger a Railway deploy hook so the autonomy poller always runs the latest verified code.

**Why GH Actions and not Railway for tests:** Railway is production. Production containers shouldn't be running pytest on themselves. And Railway deployments mutate environment in ways that are hard to reason about. GH Actions is clean-slate every time, which is exactly what a test runner wants.

### Environment C: Cowork (ephemeral, human-in-the-loop only)

Cowork keeps running what it's good at: interactive design work with Phill when he's at his desk. It stops trying to be a production rail.

**Runs in Cowork:**

1. **Charter and documentation work.** When Phill opens Cowork and asks for a new charter, a strategic board review, or a markdown report, that happens here. Human-driven, not time-driven.
2. **Idea intake.** The "feature ideas from phone" flow already works — Telegram messages routed to `.harness/ideas-from-phone/`. That's still a valid Cowork flow IF we keep it tied to a human reviewing the ideas later, rather than pretending it's autonomous.
3. **Debugging and post-mortem investigation.** Like right now, when Phill needs to understand what broke. Cowork is the right place for this, because it has the file system, the git history, and the human.

**Does NOT run in Cowork anymore:**

- The watchdog.
- The Pi-SEO cron scans.
- The Telegram inbox poller.
- The Linear sync.
- The heartbeat.
- Anything that's supposed to keep running when Phill is asleep.

All of those move to Environment A (Railway) or Environment B (GH Actions).

## The data flow diagram (in prose, because ASCII art ages badly)

1. A Linear Todo ticket is filed (by Phill or by the autonomy poller itself when it detects a Pi-SEO regression).
2. Railway's autonomy poller (Environment A) sees the ticket within 10 seconds of startup or 5 minutes of ticking (whichever is shorter, per commit e611b1c).
3. The poller transitions the ticket to In Progress, creates a session, and calls the Claude Agent SDK to run the build.
4. The session's working directory is a fresh clone of the target repo, in a Railway volume. When the session ends, the clone is deleted.
5. Session outputs commits, runs tests locally (against a bundled test requirements set, NOT the Cowork sandbox), and pushes via a GitHub fine-grained PAT stored in Railway's secret store.
6. GitHub Actions (Environment B) picks up the push, runs the full suite, writes the status to the `status/` branch.
7. Railway's watchdog reads the `status/` branch every 5 minutes to know whether tests are green. If they're red, the watchdog transitions the ticket back to Todo with a comment explaining the failure, and sends Phill a Telegram message via the inline module.
8. If tests are green, the watchdog merges the session's PR (or leaves it for human review, per the ticket's `auto_merge` label — Phill's choice).
9. Linear ticket closes.
10. Pi-SEO re-scans within the next 6 hours and confirms the regression is gone.

No step in this flow depends on Cowork being open. No step in this flow runs pytest in an unknown environment. No step requires a manual `git push`.

## Component matrix

| Component | V1 location | V2 location | Change type |
|---|---|---|---|
| Linear Todo poller | Railway (broken, 5min bootstrap) | Railway (fixed: 10s bootstrap) | Push the fix |
| Pi-SEO scanner cron | Cowork scheduled-tasks MCP | Railway APScheduler OR GH Actions cron | Move |
| Pytest runner | Cowork scheduled-task sandbox | GH Actions workflow | Move |
| Watchdog | Cowork scheduled-tasks MCP | Railway FastAPI background task | Move |
| Test-green status | "run pytest right now" | Read from `status/` branch | Change source of truth |
| Telegram outbound | Cowork sandbox calls python script | Railway FastAPI calls inline module | Move |
| Telegram inbound | Cowork polling getUpdates every 5min | Railway webhook, Telegram pushes | Architecture change |
| Lessons file | `.harness/lessons.jsonl` in sandbox | Pushed to main branch on every entry | Persistence change |
| Charters and docs | `.harness/business-charters/` in sandbox | Committed to main branch | Persistence change |
| Scan results | `.harness/scan-results/` in sandbox | Railway volume OR `status/` branch | Move |

## The three things that will take real work

Everything else in the matrix is a file move or a function call. These three are actual engineering:

### 1. Railway APScheduler for Pi-SEO cron

Add `apscheduler>=3.10` to `pyproject.toml`. On FastAPI startup, create a `BackgroundScheduler` and register the six cron entries from `.harness/cron-triggers.json`. Each entry calls into the existing `run_monitor_cycle` function, which already exists as an MCP tool. One-to-two days of work.

### 2. GitHub Actions workflow + status branch

Write `.github/workflows/pytest.yml` and `.github/workflows/pi-seo-scan.yml`. Each workflow writes results to a `status` orphan branch that Railway can pull. Two to three days, most of which is getting the status-branch-write pattern right. Use something like `actions/github-script` or a pre-built "commit a file to a branch" action.

### 3. Railway-native git push from a build session

The session needs to push to `origin/main`. Options:
- **Fine-grained GitHub PAT** in Railway secret store, limited to content-write on specific repos. Simple but tokens expire.
- **GitHub App** with repo content write permission. More setup but doesn't expire and gives per-repo granularity.
- **Deploy key** per repo. Good if we only need one-way push. Painful if multiple repos.

Recommendation: start with a PAT for Pi-Dev-Ops only, prove the flow, then move to a GitHub App when we onboard CCW, RestoreAssist, and DR-NRPG. Three to five days of work including the security review of the PAT's blast radius.

## Migration plan (concrete steps, not hand-waving)

### Day 1 — Today (Sunday 2026-04-12)
- [ ] Phill: run the one-line `git push origin main` that's been waiting since Saturday. This is the ONLY thing that unblocks everything else.
- [ ] Phill: set `LINEAR_API_KEY` in Railway env vars so the poller actually has a key to use once e611b1c deploys.
- [ ] Phill: restart the Railway container (Railway does this automatically on deploy, but a manual restart after the env var change makes it clean).
- [ ] Verify: hit `/health` and confirm `autonomy.armed == true` and `linear_key == true`.
- [ ] Verify: watch the poller log — poll #1 should fire within 10 seconds. Poll #2 should be 5 minutes later.

This alone gets us 40% of the way to working autonomy, using ONLY what's already committed.

### Day 2-3 — Cowork rails teardown
- [ ] Disable every Cowork scheduled task EXCEPT the telegram-inbox poller (keep that one until webhooks are live).
- [ ] Add a status field to every heartbeat that says which environment it came from.
- [ ] Gate `_check_tests` in `marathon_watchdog.py` so it runs `pytest --collect-only` instead of the full suite — that proves the import chain works without needing runtime deps.

### Week 1 — GH Actions + status branch
- [ ] Write `.github/workflows/pytest.yml`.
- [ ] Write `.github/workflows/pi-seo-scan.yml` that drives the scanner and writes to the `status/` branch.
- [ ] Add a `read_status_branch` helper to the Railway watchdog.

### Week 2 — Railway APScheduler
- [ ] Add `apscheduler` dep, register the cron entries, verify they fire on a Railway-hosted container.
- [ ] Remove the Cowork `marathon-pi-seo-dryrun-hourly` task.
- [ ] Retire `.harness/scan-results/` as a sandbox path — scans now write to a Railway volume OR the `status/` branch.

### Week 3 — Autonomous git push from Railway
- [ ] Create a fine-grained PAT for Pi-Dev-Ops repo content write.
- [ ] Store in Railway secrets as `GITHUB_PUSH_TOKEN`.
- [ ] Add `git push` to the build session cleanup.
- [ ] Run an end-to-end test with a low-risk ticket.

### Week 4 — Onboard CCW, RestoreAssist, DR-NRPG
- [ ] Move from PAT to GitHub App.
- [ ] Add per-repo config to Pi-Dev-Ops (`REPO_CONFIGS` dict with one entry per target repo).
- [ ] Re-run the charters' Phase 1 security cleanup autonomously.

## Budget and effort

Rough estimate for the full V2 migration, assuming Pi-CEO does most of the work autonomously and Phill does the infra approvals:

- Day 1: 1 hour Phill + 0 Pi-CEO (just pushes + env var)
- Days 2-3: 4 hours Pi-CEO, 30 min Phill review
- Week 1: 2 days Pi-CEO (GH Actions), 1 hour Phill (secret setup)
- Week 2: 1.5 days Pi-CEO (APScheduler)
- Week 3: 2 days Pi-CEO (git push from Railway), 2 hours Phill (PAT security review)
- Week 4: 3 days Pi-CEO per target repo

Total: ~3-4 weeks of Pi-CEO wall-clock with ~6 hours of founder involvement. By end of week 3, overnight autonomy is real. By end of week 4, it's real across all three business projects.

## How V2 prevents the V1 failure mode

The V1 failure was: rails stop when the Mac sleeps, watchdog cries wolf about an environment issue, commits sit unpushed, Railway runs stale code, nothing gets built, Phill wakes up disappointed.

V2 prevents every link in that chain:

- Rails don't stop when the Mac sleeps (they're on Railway).
- Watchdog doesn't cry wolf because test truth comes from GH Actions, not from a sandbox.
- Commits don't sit unpushed because the build session has push credentials.
- Railway runs fresh code because GH Actions triggers a deploy on every green `main`.
- Something gets built because the whole flow is closed-loop.

## Open questions for Phill

1. **GH Actions or Railway-native cron for the scanner?** Railway cron is cheaper and colocated. GH Actions is more transparent and version-controlled. I lean GH Actions for the transparency but it's a preference call.
2. **PAT or GitHub App for the autonomous push?** PAT is faster to set up. GitHub App is better long-term. Want to start with PAT to prove the loop and upgrade later?
3. **What's your appetite for a Postgres on Railway?** Several V2 components (status history, lessons persistence, session metadata) want real database semantics. A single hobby-tier Postgres is ~$5/month. Happy to avoid it if you'd prefer sticking to filesystem + S3.
4. **Who has write access to the `status` branch?** If it's automated, it's simpler. If it's protected, we need a bot account with a PAT limited to that branch. Preference?

None of these block the Day 1 unblock step (`git push origin main` + `LINEAR_API_KEY`). Answer them whenever you've got ten quiet minutes.
