# Unite Group Nexus — Full System Audit (2026-06-11)

Source mandate: Plaud recording 2026-06-10 "Bridging the Execution Gap" (`brain/plaud/2026-06-10-06-11-bridging-the-execution-gap-in-an-ai-driven-business-ecosystem-a-systemic-overhaul-mandate.md`).

Surfaces audited: local Hermes/launchd/cron automation, GitHub CI (10 CleanExpo repos), Vercel (11 production projects, team unite-group), Railway (20 projects).

## Executive summary

The deploy layer is healthy — **zero errored production deployments on Vercel**, and 9 of 10 repos have green CI. The breakage is concentrated in the **automation layer**: more than half of all Hermes cron jobs were bulk-paused on 10 June and never resumed, Telegram delivery is locked in a permanent conflict loop, and two Railway backends (Plaud processor DB, Telegram bot) are dead. This matches the recorded complaint exactly: jobs "run" but results never arrive.

## Findings by severity

### Urgent

1. **Telegram delivery broken — duplicate bot instance.** The Hermes gateway loops on `Conflict: terminated by other getUpdates request` every ~27s, all day (`~/.hermes/logs/gateway.error.log`). Something else polls the same bot token. Suspects: a stale remote session or one of the 13 auto-named Railway projects. Railway `pi-ceo-telegram-bot` has service `telegram-bot` FAILED since 2026-04-19 and `piceo-telegram-bot` never deployed. Fix: locate/kill the duplicate poller or rotate the bot token.
2. **19 of 36 Hermes cron jobs paused since 2026-06-10 14:40 ("noisy pause").** Includes the 6-hour `security-alerts` job (the "six-hour cron" from the recording), `prod-blockers`, `unite-ecosystem-health-v2`, `synthex-pipeline`, `media-ingest`, all `daily-ops-*`, three Nexus discovery jobs, Nexus Build Sweep, Margot Orchestrator (hermes copy). Evidence: `~/.hermes/cron/jobs.json` vs `jobs.before-noisy-pause-20260610-1440.json`. Fix: triage the list, selectively resume.

### High

3. **plaud-processor Railway Postgres CRASHED since 2026-05-30.** The Plaud webhook/expert-router backend has no working database.
4. **Two monitors dead on model error since 2026-06-04.** `plaud-itr-monitor` and `duncan-discovery-monitor-v2` died with `gpt-5.5-pro model is not supported when using Codex with a ChatGPT account`, then were paused. plaud-itr-monitor left 1,744 output files. Fix: point at a supported model, resume.
5. **CCW-CRM is the only repo with red CI.** (a) `rollback.yml` fails at workflow-parse stage (zero jobs spawn, 2026-06-10); (b) weekly `deepsec` scan failing since 2026-06-08 — open PR #197 claims the fix; (c) PRs #151/#152/#153 (CI-unblock fixes) rotting 30–32 days.

### Medium

6. **Discord platform dead since 2026-05-24** (`failed to reconnect`, `~/.hermes/gateway_state.json`) — deliveries to Discord vanish silently.
7. **"Runs but does nothing" jobs.** `Linear → Margot today queue watcher`: 1,335 consecutive empty outputs. `Pilot V1 scheduler`: perpetual `off_hours`/`no_suggestion`, even in business hours. Both healthy as processes, mis-wired as systems.
8. **ATO repo PR pileup**: 5 near-duplicate "audit: Pi CEO full analysis" PRs (#19–23) opened in hours on 2026-06-10, plus #8 rotting since 2026-05-14.
9. **Railway sprawl**: 13 auto-named projects (`determined-playfulness`, `joyful-hope`, …) plus legacy SaaS projects (AI Guided SaaS, Zenith ×2, Local_Lift) of unknown cost/status.

### Low

10. **CARSI stagnant** — no dev since 2026-06-02, two PRs >14 days old.
11. **`~/.hermes/state.db` is 3.04 GB** + 2,388 session dirs — needs prune/vacuum.
12. **morning-fetch is fetch-only by design** — `git fetch` for 11 repos daily, but nothing consumes the result. Design gap, not a failure.

## Healthy

- Vercel: all 11 production projects READY; busiest (pi-dev-ops) deploying multiple times/hour.
- GitHub CI green: Unite-Hub, Unite-Group, RestoreAssist, DR-NRPG, Synthex, ATO, CARSI (scheduled), Pi-Dev-Ops.
- Railway Pi-Dev-Ops backend: SUCCESS, deployed 2026-06-10.
- Hermes gateway stable since 10 Jun; self-update current (v0.16.0); budget monitor under threshold; Margot orchestrator (launchd) ticking; Plaud ingest pulling (09:52 today).

## Linear tickets filed

See the "System Audit 2026-06-11" parent ticket in the Pi-Dev-Ops project; per-product tickets filed to Synthex, CCW CRM, Unite-Group, CARSI projects. Mandate backlog items from the recording filed alongside.
