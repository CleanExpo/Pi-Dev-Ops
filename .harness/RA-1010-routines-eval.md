# RA-1010 — Claude Code Routines Evaluation

**Date:** 2026-04-16  
**Claude Code version evaluated:** 2.1.109  
**Author:** Pi-CEO autonomous research (RA-1010)

---

## Executive Summary

- Routines cover the **scheduled poll** trigger (replaces `autonomy.py`) cleanly — cron syntax, cloud-hosted, Mac-independent.
- **GitHub event** trigger is native to Routines; it can replace the `workflow_run` webhook path without Railway being in the loop.
- **Linear webhook** is the hardest gap: Routines have no inbound HTTP listener that accepts arbitrary third-party webhooks with custom HMAC signatures. The Railway `/api/webhook` endpoint cannot be retired for this trigger type.
- MCP connectors (Linear MCP, pi-ceo MCP) are accessible inside Routines sessions — Linear operations can be done via MCP tools rather than raw GQL.
- Auth to external services (Railway, Supabase, GitHub) requires secrets configured at Routine creation time; no runtime env inheritance from Railway.

---

## Q1 — Trigger Parity

### Trigger 1: GitHub `workflow_run` webhook

**Current path:**  
`GitHub → POST /api/webhook (Railway) → verify HMAC → _handle_workflow_run() → create_session()`

**Routines replacement:**  
Routines support a **GitHub event trigger** natively. A Routine can be wired directly to a repo's `workflow_run` event. No Railway middleman needed. GitHub sends the event payload; the Routine receives it as structured context.

**Gap:** The current handler in `_handle_workflow_run()` checks for CI failures and conditionally creates sessions. That logic would need to be expressed in the Routine's prompt/instructions. Doable, but the conditional branching (e.g. "only trigger if conclusion == 'failure'") must be encoded in the Routine's system prompt rather than Python code. Event filtering is limited compared to code.

**Verdict: Full replacement possible.** Routines is a better path than a Railway HTTP server for this trigger.

---

### Trigger 2: Linear webhook (issue state transitions)

**Current path:**  
`Linear → POST /api/webhook (Railway) → verify Linear-Signature HMAC → parse_linear_event() → create_session()`

**Routines replacement:**  
Routines have **no inbound HTTP listener** that accepts arbitrary third-party webhooks. There is no way to register a Routine as the target URL for a Linear webhook. Routines can be triggered by: (a) schedule, (b) API POST to Anthropic's endpoint, (c) GitHub events.

To bridge this, one of two workarounds applies:
1. **Keep Railway `/api/webhook`** for Linear — it receives the webhook, verifies HMAC, then calls `POST https://api.anthropic.com/v1/routines/{id}/trigger` to fire a Routine instead of calling `create_session()` internally. Railway remains as a thin dispatcher.
2. **Replace with polling** — drop the Linear webhook entirely and use a Routine on a 5-minute cron to replicate `autonomy.py` behaviour. Accepts up to 5-minute latency for issue pickup (same as current polling anyway).

**Verdict: No direct replacement.** The Linear webhook trigger requires Railway or a similar HTTP-capable middleman. Polling via Routine cron is a viable functional equivalent.

---

### Trigger 3: Scheduled `autonomy.py` poll

**Current path:**  
`Railway process → asyncio loop (TAO_AUTONOMY_POLL_INTERVAL=300s) → Linear GQL → create_session()`

**Routines replacement:**  
Direct 1:1 replacement. A Routine on `*/5 * * * *` cron runs without a Mac being awake, without Railway process staying alive, and without the do-while startup-delay bug (see CLAUDE.md — first tick is delayed by a full interval after Railway restart).

The Routine's task: query Linear for Urgent/High Todo issues in project `f45212be-…`, transition matching issues to In Progress, then call `POST /api/build` on Railway (or directly run a Claude session via the Managed Agents API).

**Verdict: Cleanest migration candidate.** Eliminates the Railway long-running process dependency for this concern.

---

## Q2 — MCP Access

Routines execute inside a Claude Code session environment. MCP connectors configured for the account are available to that session.

**Linear MCP (`LINEAR_API_KEY`):** Available. The Routine can call `mcp__linear__list_issues`, `mcp__linear__update_issue`, etc. directly — no raw GQL needed. This removes the `_gql()` helper dependency from `autonomy.py`.

**pi-ceo MCP server (`mcp/pi-ceo-server.js`):** The pi-ceo MCP server is a Node.js process that runs locally (Mac or Railway). It is **not** a cloud-hosted MCP connector; it is not reachable from a Routine by default. The 21 tools it exposes (harness reads, Linear operations, build triggers) would need to be either:
- Exposed via a public HTTPS endpoint (e.g. Railway or a dedicated tunnel), or
- Replaced by direct Linear MCP + Railway API calls from within the Routine.

**Verdict:** Linear MCP works natively. Pi-ceo MCP requires Railway-hosted exposure or tool-level replacement.

---

## Q3 — Session Creation

A Routine can create a build session via two paths:

**Path A — Direct Managed Agents API:**  
The Routine itself *is* a managed agent session. It can execute the same 5-phase pipeline that `_run_claude_via_sdk()` runs today. No call to Railway `/api/build` needed. The Routine's instructions become the build brief; the session output is streamed/stored by Anthropic.

Limitation: session state (`.harness/build-logs/`, in-memory `_sessions` dict, Supabase `workflow_runs` rows) would not be written unless the Routine explicitly calls Railway or Supabase endpoints.

**Path B — Call Railway `/api/build`:**  
The Routine makes a `POST /api/build` HTTP call to the Railway backend with the repo URL and brief. Railway handles the full pipeline as today. The Routine is purely a trigger — it does the Linear query and HTTP dispatch, nothing else.

Path B preserves all existing observability (Supabase logs, WebSocket streaming, harness state, `/health` metrics). Path A is cleaner but loses dashboard visibility unless the Routine emits structured output to Supabase directly.

**Verdict: Path B recommended for initial migration** — lowest risk, preserves all existing observability. Path A is a future state once Routines have stable observability integration.

---

## Q4 — Auth

Routines authenticate to external services via **secrets set at Routine creation time** in the Claude Code configuration UI or API. These are equivalent to env vars but scoped to the Routine.

Secrets needed for the scheduled-poll Routine:
- `LINEAR_API_KEY` — Linear GQL / MCP auth
- `TAO_PASSWORD` — Railway `/api/build` basic auth
- `RAILWAY_BACKEND_URL` — e.g. `https://pi-dev-ops.up.railway.app`
- `SUPABASE_SERVICE_ROLE_KEY` (optional, if the Routine writes directly to Supabase)

**ANTHROPIC_API_KEY note (from memory):** The Claude CLI sets `ANTHROPIC_API_KEY=""` in the shell. This does not affect Routines — Routines run in Anthropic's cloud and use the account's authenticated session, not a local env var. No source `.env.local` workaround needed.

Secrets are not inherited from Railway env — they must be set independently per Routine. Keeping them in sync when Railway secrets rotate is an operational risk (see Risk Register).

---

## Q5 — Limitations vs Current Approach

| Capability | Railway + autonomy.py | Routines |
|---|---|---|
| Inbound arbitrary webhook (Linear HMAC) | Yes | No |
| Cron scheduling | Yes (asyncio loop) | Yes (native, cloud-hosted) |
| GitHub event trigger | Via webhook receiver | Native |
| WebSocket streaming to dashboard | Yes | No (stateless HTTP) |
| Harness file writes (`.harness/`) | Yes (local filesystem) | No (no persistent filesystem) |
| In-memory session dedup (`_sessions` dict) | Yes | No |
| Supabase observability writes | Yes | Only via HTTP call |
| Dashboard `/api/autonomy/status` | Yes | No (unless Routine writes status to Supabase) |
| Kill switch (`TAO_AUTONOMY_ENABLED=0`) | Railway env var, instant | Requires disabling/deleting the Routine |
| First-tick delay bug | Yes (do-while pattern) | No — cron fires on schedule |
| Mac dependency | Yes (if running locally) | No |
| Session result streaming | Yes (SSE + WebSocket) | No — Routine output is opaque unless Path B used |

---

## Q6 — Recommended Migration Path

### Migrate first: Scheduled Linear poll (`autonomy.py` replacement)

**Why:** Highest risk/reward ratio. `autonomy.py` has known failure modes (first-tick delay, silent skip when `LINEAR_API_KEY` missing). A Routine cron eliminates both. No change to Railway API surface; the Routine just calls `POST /api/build`.

**Implementation steps:**

1. Create a Routine in Claude Code with cron `*/5 * * * *`.
2. Set secrets: `LINEAR_API_KEY`, `TAO_PASSWORD`, `RAILWAY_BACKEND_URL`.
3. Routine instructions (system prompt):
   ```
   Query Linear project f45212be-3259-4bfb-89b1-54c122c939a7 for all Urgent or High priority issues in Todo state. For each:
   1. Transition to In Progress via Linear MCP.
   2. POST {"repo_url": "<from issue>", "brief": "<from issue title + body>"} to $RAILWAY_BACKEND_URL/api/build with Authorization: Basic base64(admin:$TAO_PASSWORD).
   3. Log the session_id returned.
   Stop after processing 3 issues (rate limit parity).
   ```
4. Set `TAO_AUTONOMY_ENABLED=0` in Railway to disable `autonomy.py`.
5. Verify via Linear issue state transitions and Railway session logs for 48h.
6. Remove `autonomy.py` startup hook from `app_factory.py` only after 48h clean run.

**Migrate second: GitHub `workflow_run` trigger**

Replace the Railway webhook receiver for GitHub events with a native Routine GitHub trigger. The Routine calls `POST /api/build` when CI fails. Keep Railway for HMAC verification of the Linear webhook.

**Do not migrate: Linear webhook trigger**

Keep Railway `/api/webhook` for Linear. No Routines equivalent for inbound HMAC-verified webhooks from third-party services.

---

## Risk Register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | Secret drift — LINEAR_API_KEY rotated in Railway but not in Routine | Medium | High — silent poll failures | Add secret rotation checklist to RAILWAY_ENV.md; alert on Routine 401 errors |
| R-02 | Harness file writes lost — Routine has no filesystem | High | Medium — `.harness/autonomy.jsonl` no longer updated | Routine writes status row to Supabase `heartbeat_log` instead |
| R-03 | Dashboard `/api/autonomy/status` returns stale data | High | Low — cosmetic | Surface Supabase `heartbeat_log` in status endpoint instead of in-memory state |
| R-04 | Session dedup broken — `_sessions` in-memory dict not checked | Medium | Medium — duplicate builds | Routine queries Railway `/api/sessions` before triggering; skip if active session exists for repo |
| R-05 | Routine kill switch slower — no single env var toggle | Low | Low | Document Routine disable procedure in RAILWAY_ENV.md |
| R-06 | pi-ceo MCP tools unavailable in Routine context | Medium | Medium — 21 tools not accessible | Expose pi-ceo MCP server via Railway HTTPS; or replace with direct Linear MCP + HTTP calls |
| R-07 | Routine execution time limit — long-running builds timeout | High | High — 5-phase pipeline takes 5-15min | Use Path B (Routine as dispatcher only); Railway owns pipeline execution |
| R-08 | Linear webhook loses HMAC verification if moved to Routine | N/A | N/A | Do not migrate Linear webhook to Routines |
| R-09 | Cost increase — Managed Agents API billed per Routine execution | Low | Low — 288 daily cron ticks cheap | Monitor via `/api/health/vercel` Claude API cost tracking |
