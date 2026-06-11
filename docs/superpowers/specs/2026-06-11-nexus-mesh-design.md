# Nexus Mesh — 3-Machine Agentic Fleet + Mission Control

**Status:** design + foundation build (2026-06-11)
**Source mandate:** Plaud recording 2026-06-10 ("Bridging the Execution Gap") + owner directive 2026-06-11 — "three computers working agentically together in the background with a visual in the Unite-Group Mission Control Panel."
**Linear epic:** RA-6474 (Pi-Dev-Ops). Realises UNI-2133 (Mission Station).

## The one-sentence architecture

**Git is the work bus, Supabase is the nervous system, the dashboard is the eyes.** Every machine auto-ships every agent turn (autogit) so they collaborate through shared GitHub history; every machine heartbeats its live state to Supabase; the Authority-Site Mission Control Panel renders the fleet in real time.

## Why this shape (grounded in recon, 2026-06-11)

- There is **no existing mesh** — the "Hermes Empire ↔ Laptop Agent Bridge" Linear project was scoped and abandoned (0 issues). Greenfield.
- **Two nodes are live now**: `phills-macbook-pro` + `unite-mac-mini` (both macOS, online, 13 ms LAN). `phill-desktop` (Windows) is the third when powered. Build + test a 2-node mesh immediately; Windows joins via the same bootstrap.
- **autogit** (davidondrej/autogit, MIT, zero-dep Node CLI) already supports the exact runtimes installed here — Claude Code 2.1.172 and Codex 0.138.0 — with a parallel-agent busy-marker model and worktree isolation. It is the work-bus keystone. We do **not** fork it; we install the published package and add a Hermes adapter in *our* mesh layer (autogit's own Hermes adapter is an owner-gated roadmap item in their repo).
- The Authority-Site dashboard (`~/Unite-Group`, Next 16 / App Router / shadcn / recharts+visx / framer-motion) already has a `command-center` route with a `readAgentTopology()` reader and Supabase access — the Mission Control Panel is a new route here, not a new app. A Supabase **broadcast** live pattern already exists in Unite-Hub (`advisory:*` channels) to copy for `mission:*`.
- Shared backend: Supabase project **Pi CEO** (`zbryrmxmgfmslqzizsto`). The dashboard reaches fleet data through the always-on Pi-CEO Railway API it already consumes (`PI_CEO_API_URL`), so no service-role key is spread to machines.

## The three planes

### 1. Work plane — Git (autogit)
- autogit installed + `autogit setup` on every machine → Claude Code `Stop`, Codex `Stop`, and (our) Hermes `agent_end` hooks all run `autogit ship` (stage → secrets-scan → commit → push).
- **Branch policy (critical):** every portfolio repo is `pr_required_for_prod`. Mesh agents NEVER auto-push to `main`. The mesh runner always works on `mesh/<machine>/<ticket>` branches; autogit pushes the current branch; production stays PR-gated. CI gates are the merge authority, exactly as today.
- Parallel safety is autogit-native: busy markers defer shipping until the last agent in a repo finishes; worktrees give true per-agent isolation. The mesh runner uses a worktree per claimed ticket.

### 2. Nervous plane — Supabase (`zbryrmxmgfmslqzizsto`)
New tables (migration `mesh/schema/0001_nexus_mesh.sql`, idempotent `CREATE TABLE IF NOT EXISTS`):
- `mesh_machines` — one row per node: host, os, tailnet_ip, status (online/idle/working/offline), cpu_pct, mem_pct, load, agent_runtimes (jsonb), version, last_seen. Heartbeat upserts every 20 s; a row older than 60 s renders as offline.
- `mesh_agents` — live agent sessions: machine, runtime (claude/codex/hermes), session_id, repo, branch, current_task, state (idle/working/shipping/error), started_at, last_ship_at.
- `mesh_ships` — the git activity feed: machine, repo, branch, sha, subject, files_changed, shipped_at. Appended by an autogit post-ship hook.
- `mesh_work_claims` — atomic task assignment: linear_id (unique-while-open), machine, state (claimed/working/done/released), claimed_at, released_at. The unique partial index on open claims is what stops two machines grabbing the same ticket.

### 3. Eyes/command plane — Authority-Site Mission Control Panel
- New route `src/app/[locale]/mission-control/page.tsx` (Server Component, `force-dynamic`).
- Reads `GET /api/mesh/fleet` on Pi-CEO Railway (machines + agents + recent ships + open claims) — same plumbing as the existing Empire dashboard.
- Live layer: Supabase broadcast `mission:fleet` (port Unite-Hub's `advisory:*` pattern) with a 10 s poll fallback.
- Renders: 3 machine cards (alive/idle/working, CPU/mem, current repo·branch·task), a live ship feed, the work-claim board, per-project progress. 3D + voice are explicitly phase 2 (greenfield — no three.js in repo yet; voice can reuse the Hermes SSE primitive).

## Coordination loop (how they "work together on same and different projects")

1. **Dispatcher** (runs in the always-on Pi-CEO Railway server, new `app/server/routes/mesh.py`): watches Linear for issues labelled `mesh:auto` + status `Ready for Pi-Dev`. For each, it writes a `mesh_work_claims` row to the least-loaded **online** machine (load read from `mesh_machines`). The unique open-claim index guarantees single assignment.
2. **Mesh runner** (`mesh/runner.py`, one per machine, launched by the heartbeat daemon): polls its own open claims, and for each — creates a worktree on a `mesh/<machine>/<ticket>` branch, runs the local agent (claude/codex) with the ticket as the prompt, lets autogit ship each turn, updates the claim + Linear ticket on completion, removes the worktree.
3. Different machines pull different tickets (parallel projects); two machines can also split sub-tickets of one epic (same project, different branches) — git + CI reconcile at merge.

Cost routing honours the mandate (RA-6470): the runner uses paid Max plans by default; OpenRouter only for explicitly-tagged sub-agent tickets.

## Build phases

- **P0 (this turn) — foundation, verifiable on the live node:** autogit installed+setup+ship-tested; mesh schema applied to Supabase; heartbeat daemon publishing a real row for `phills-macbook-pro`; Hermes ship adapter; `mesh-bootstrap.sh` one-command join; dashboard route scaffolded against the real endpoint contract.
- **P1 — activate the fleet:** run `mesh-bootstrap.sh` on `unite-mac-mini` (reachable) and `phill-desktop` (when powered); merge the Pi-CEO `/api/mesh/*` endpoints PR; merge + sandbox-deploy the Mission Control route. Result: live 2–3 node view.
- **P2 — autonomy + polish:** dispatcher auto-assignment from Linear; 3D fleet view + voice summaries (UNI-2133); per-project progress rollups.

## Safety & boundaries
- autogit is opt-in per repo (`autogit on`); never touches a repo without it. Secrets scan blocks key/`.env`/JWT pushes. `autogit undo` reverses any bad ship (remote + local).
- Mesh agents are branch-only; `main` is PR+CI gated for every product repo. No mesh path writes to production `main` automatically.
- Heartbeat carries no secrets; machines hold only `PI_CEO_API_KEY`, never the Supabase service-role key.
- Kill switch: the existing Pi-CEO `/api/swarm/kill` + `~/.claude/HARD_STOP` drain pattern extends to the mesh runner (runner checks the same flag each cycle).
