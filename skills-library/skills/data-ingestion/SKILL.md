---
name: data-ingestion
description: B.U.I.L.D. Inflow orchestration — run the data-capture pipeline as one routine (mine session lake → refresh OKF indexes → sync wiki to Supabase). Use when the user says "/data-ingestion", "run the ingestion routine", "pull in new data", or on the Tue/Fri 09:00 routine. The improvement loop (improve-system) is a separate EOD routine.
---

# data-ingestion

One command that flows new data into the lake. The AM half of the rhythm;
`improve-system` is the EOD half (kept separate so a failure is isolated to the
stage that failed).

## Run

```bash
cd ~/Pi-Dev-Ops && bash scripts/data_ingestion.sh
```

Stages (idempotent, safe to re-run):
1. `sync_claude_sessions.py --since-last` — mine new sessions → `process/sessions/`.
2. `okf-index.py` — refresh OKF indexes so new digests are discoverable.
3. `sync_wiki_to_supabase.py --since-last` — mirror wiki to Supabase.

Logs to `~/.hermes/logs/data-ingestion.log`. Exit non-zero if any stage failed
(the failed stage is named in the log).

## Scheduling

LaunchAgent plists in `~/Pi-Dev-Ops/scripts/launchagents/` — install with
`bash scripts/launchagents/install.sh` AFTER the PR merges and the prod checkout
(`~/Pi-Dev-Ops`) has pulled. data-ingestion: Tue/Fri 09:00 ·
improve-system: Tue/Fri 18:00.

- Spec: `~/Pi-Dev-Ops/docs/specs/2026-06-29-self-improving-system-build.md`.
- Note: `source-ingest` (interactive research capture) is run on demand, not in
  this unattended routine.
