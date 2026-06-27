# Pi-Dev-Ops — Claude Code Guidance

## Identity (SSOT)

- **Canonical name:** Pi-Dev-Ops (aliases: "Pi DevOps", "Pi-CEO Dev Ops")
- **GitHub:** `CleanExpo/Pi-Dev-Ops`
- **Local path:** `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops`

## Autonomous Operation Mandate (2026-04-18 — authorised by user)

Standing mandate: work the backlog without asking permission. Finishing a task is **not** a stop signal — chain to the next highest-leverage item immediately. Founder's words: "stopping really gives me the shits when there is so much work to accomplish."

**Durable rules — every session, no confirmation:**

1. **Sandbox first, push only when asked.** Iterate in `/tmp/` or `/tmp/pi-ceo-workspaces/` clones. Push / open PR / ship only when the user's latest message says so. Otherwise stage the diff, write the PR body to a file, STOP.
2. **File a Linear ticket for every discovery** via `mcp__pi-ceo__linear_create_issue`, routed by `.harness/projects.json` (repo → `linear_team_id` + `linear_project_id`). Never dump findings into Pi-Dev-Ops's own project unless the finding is about Pi-CEO itself.
3. **Smoke-test before committing:** `python -m py_compile` on edited Python, `npx tsc --noEmit` on edited TS, probe changed endpoints, trigger changed CI workflows and wait.
4. **Surface-treatment prohibition (RA-1109)** applies always — see that section.
5. **Honest failure reporting:** state the exact error class + source line, file a follow-up ticket. Never dress a failure as "still running" or silently retry forever.
6. **Skill-injection hooks are advisory.** Vercel-plugin / posttooluse Clerk/Next-upgrade/chat-sdk suggestions fire on patterns, not task context. When off-task (≈95%), say so in one line and ignore. Never let them drive scope creep.

**Operating loop:** pick highest-leverage Linear item (Urgent+High first, then Medium) → fix in isolated `/tmp/` clone → run gates → stage commit + PR body (don't push unless told) → update the ticket (In Progress on start; sandbox path + diff summary + follow-ups on complete) → file follow-up tickets for out-of-scope finds → repeat.

**Stop only on** an explicit stop word ("pause" / "stop" / "wait" / "hold" / "I'll take it from here" / a direct question — answer then resume) or a rule requiring a human decision (branch-strategy change, secret rotation, destructive migration, new service provisioning). Thanks/praise/silence/background-task-completion are **not** stop signals.

### Gate-to-green loop (2026-04-21)

Before declaring a PR done: `npx tsc --noEmit` → fix my errors; `npm run lint`/`npm test` if present → fix my failures (ignore pre-existing); push → `gh pr create`; then poll `gh pr view N --json statusCheckRollup` — while pending sleep 30; if a REQUIRED check is red, read logs, fix on the same branch, push, re-poll; else move on.

**Smoke after merge:** once the user merges, navigate the affected prod path via Chrome MCP, read console + network, file findings as **Linear tickets** (not PRs).

**PR vs ticket:** discovered during smoke/audit/review → ticket (priority 3 default). In-scope for the session's goal or launch-critical → PR. When in doubt, ticket first. Linear GraphQL fallback when the MCP defaults wrong: `POST https://api.linear.app/graphql` with `Authorization: lin_api_...` (from `.env.local`), `{variables:{i:{teamId,projectId,title,description,priority}}}`.

## Project Context

Pi-Dev-Ops converts a GitHub repo URL + plain-English brief into an autonomous Claude Code session. Generator and evaluator run via `claude_agent_sdk`. `TAO_USE_AGENT_SDK=1` is mandatory — `0` raises `ImportError` at startup.

| Layer | Tech | Location |
|-------|------|----------|
| Frontend | Next.js 16.2.2, React 19, Tailwind | `dashboard/` |
| Backend | FastAPI, Python 3.11+ | `app/server/` |
| Routes | 8 focused route modules | `app/server/routes/` |
| MCP Server | Node.js, @modelcontextprotocol/sdk | `mcp/` |
| TAO Engine | Python (skills, tiers, budget) | `src/tao/` |
| Harness State | YAML/JSON/Markdown | `.harness/` |
| Skills | SKILL.md files | `skills/` |
| Database | Supabase (PostgreSQL) | `supabase/` |
| Deploy (FE) | Vercel | `dashboard/vercel.json` |
| Deploy (BE) | Railway | `railway.toml`, `Dockerfile` |

**Shared packages:** `packages/brand-config/` (`@unite-group/brand-config`, brand-token SSOT, `themeFactory(brand)`); `packages/ui/` (`@unite-group/ui`, shadcn New York primitives, built via `tsup` CJS+ESM+.d.ts). Consume via `"@unite-group/ui": "file:../packages/ui"`.

## Backend Module Map (`app/server/`)

| File | Lines | Concern |
|------|-------|---------|
| `main.py` | ~25 | Thin assembler — imports `app`, registers routers |
| `app_factory.py` | ~130 | `app` object, CORS/security middleware, `_resilient`, startup/shutdown |
| `models.py` | ~126 | All Pydantic request models |
| `routes/auth.py` | ~48 | `POST /api/login`, `/api/logout`, `GET /api/me` |
| `routes/sessions.py` | ~122 | `/api/build`, `/api/build/parallel`, session list/kill/logs/resume |
| `routes/webhooks.py` | ~214 | `POST /api/webhook` (GitHub+Linear), morning-intel, Telegram |
| `routes/triggers.py` | ~32 | Trigger CRUD (`GET/POST/DELETE /api/triggers`) |
| `routes/scan_monitor.py` | ~111 | `/api/scan`, `/api/projects/health`, `/api/monitor` |
| `routes/pipeline.py` | ~89 | `/api/spec`, `/api/plan`, `/api/test`, `/api/ship`, `/api/pipeline/{id}` |
| `routes/utils.py` | ~68 | `/api/gc`, `/api/lessons`, `/api/autonomy/status`, WS `/ws/build/{sid}` |
| `routes/health.py` | ~125 | `/health`, `/api/health/vercel`, Claude CLI poll, static mount |
| `routes/mission_control.py` | ~258 | `GET /api/mission-control/live` — dashboard live-autonomy aggregator; all Linear calls fail-soft |

Public contract: `app.server.main:app` is the FastAPI instance — Dockerfile and Railway reference it; `main.py` re-exports `app` from `app_factory`. Never break this import.

## Development Setup

```bash
cd app && source .env.local && uvicorn server.main:app --host 127.0.0.1 --port 7777
cd dashboard && npm run dev
node mcp/pi-ceo-server.js
```

Local auth: password defaults to `dev` when `.env.local` has unresolved `op://` refs; override with `DASHBOARD_PASSWORD=<plaintext>` in `dashboard/.env.local`; `dashboard/scripts/dev-env.sh` auto-resolves. Never commit plaintext passwords (`.env.local` is gitignored).

## Running Tests

```bash
python -m pytest tests/ -x -q                 # import check must pass first
python -c "from app.server.main import app"   # must print FastAPI
cd dashboard && npx tsc --noEmit && npm run build
python scripts/smoke_test.py --url http://127.0.0.1:7777 --password $TAO_PASSWORD
```

Expected: 3 pre-existing failures in `test_sdk_phase2.py` (claude_agent_sdk not installed locally); all others pass.

## Code Conventions

- **Python:** snake_case, type hints on all functions, `logging.getLogger()`, structured JSON via `_JsonFormatter`.
- **TypeScript:** strict, no `any`, named exports, interfaces over types.
- **Commits:** Conventional Commits. **Branches:** `feature/{ticket}-{desc}` or `fix/{ticket}-{desc}`.
- **Limits:** functions < 40 lines, files < 300 lines — extract when exceeding.
- **Security:** bcrypt passwords, parameterised queries, CSP headers, no secrets in code.

## Key Patterns (hard-won — keep every fact)

- **Parallel agent dispatch:** multiple `Agent` calls in one message for independent tasks (~8× faster); agents must not share target files — partition by ownership.
- **Reconnaissance-first:** read current `.harness/` state before drafting plans; stale plans create orphan work.
- **detect-secrets:** run `detect-secrets scan` pre-commit on every portfolio repo.
- **Password auth:** bcrypt with transparent SHA-256 migration (`auth.py`); `TAO_PASSWORD` set → hash regenerated each startup so Railway env changes take effect immediately.
- **Session secret:** persisted to `app/data/.session-secret`.
- **SSE streaming:** `dashboard/hooks/useSSE.ts`, exponential-backoff reconnect.
- **Phase pipeline:** 5–6 phases in `sessions.py`, parsed by `dashboard/lib/phases.ts`. Phase 5 pushes to `pidev/auto-{sid}` with GITHUB_TOKEN auth (3-attempt backoff; auth failure → hard stop).
- **MCP tools:** `mcp/pi-ceo-server.js` — harness reads + Linear operations.
- **Path traversal:** `_safe_sid()` strips non-alphanumeric from session IDs before file-path use.
- **Webhook HMAC:** `hmac.compare_digest()` for GitHub (`x-hub-signature-256`) and Linear (`Linear-Signature`).
- **Rate-limit GC:** prune stale IPs (last request >120 s ago) every 5 min inline in `check_rate_limit()` — no background task needed.
- **Rate-limit cloud IP:** in Railway/Render/Fly, `request.client.host` is the LB's internal IP, so per-IP buckets never fill. Trust `X-Forwarded-For` when `_IS_CLOUD` (Railway strips client-supplied XFF at the edge; first entry is safe). Use `request.client.host` locally to avoid XFF spoofing.
- **Analysis mode:** `ANALYSIS_MODE=api` in Vercel forces the Max-plan subscription token (`sk-ant-oat01-*` from `claude setup-token`).
- **Push auth:** `_phase_push()` injects GITHUB_TOKEN via x-access-token into the remote URL, pushes to `pidev/auto-{sid[:8]}`. Requires GITHUB_TOKEN + GITHUB_REPO in Railway.
- **Route isolation:** each `routes/*.py` owns one concern. `_IS_CLOUD` is re-derived from `os.environ` in `routes/auth.py` (not imported) to avoid coupling. `_find_active_session_for_repo()` lives in `routes/sessions.py`, imported one-way into `routes/webhooks.py`.
- **API key env hygiene:** the `claude` CLI exports `ANTHROPIC_API_KEY=""`, inherited by children that then fail with 401. In Python, `os.environ.pop("ANTHROPIC_API_KEY", None)` when no explicit key is provided so subprocesses fall back to CLI OAuth (`~/.claude/`). In Next.js, `.trim()` `process.env.ANTHROPIC_API_KEY` — Vercel appends a trailing `\n` that breaks auth.
- **1Password env refs:** `op://...` is only resolved under `op run --`. `dotenv` reads them literally. Add a Pydantic `field_validator(mode="before")` that returns `None` for strings starting with `op://`.
- **Anthropic docs redirects:** `docs.claude.com` → `platform.claude.com`/`code.claude.com`; any `httpx` fetcher must set `follow_redirects=True`. Key files by two-segment path or full-URL hash to avoid collisions.
- **Telegram minimal push:** only `TELEGRAM_BOT_TOKEN` + a `chat_id` needed — `urllib` + `POST api.telegram.org/bot{token}/sendMessage`. See `scripts/send_telegram.py`.

## Surface Treatment Prohibition (RA-1109 — hardwired 2026-04-17)

**A feature isn't shipped until the user-visible outcome is demonstrable.** HTTP 200, types compiling, and green lint are not shipping. If a user presses a button, they must SEE something change.

**Banned (reject on sight):** `.catch(() => {})` on a user action; fire-and-forget button that logs `ok` but never updates UI; "200 so it works" without an end-to-end click-test on the live deploy; a 3-second toast as the only feedback for a long action; a label overstating the action's effect.

**Required:** any write action → immediate UI state change or a subscribable progress surface; any async >2 s → live progress surface with a terminal/status chip, not a toast; any destructive action → confirm + success/undo or actionable error; any spawn action → inline live-log streamer or a link to watch it.

**Enforcement:** `.github/PULL_REQUEST_TEMPLATE.md` requires a "Manual verification path"; the evaluator flags any PR adding/modifying an interactive surface without a verified click-test, regardless of lint/type/test status. Exemplar: the Fix-with-Claude incident (PR #48 → fixed #56) — green CI, 200 response, unusable feature; fix was an inline SSE streamer.

## Model Routing Policy (RA-1099 — hardwired 2026-04-17)

**Opus is reserved for `planner` + `orchestrator` only.** Every other role uses Sonnet or Haiku.

| Role | Model | Configured in |
|------|-------|---------------|
| `planner` | Opus | `.harness/config.yaml` agents.planner |
| `orchestrator` | Opus | agents.orchestrator |
| `generator` | Sonnet | agents.generator |
| `evaluator` | Sonnet | agents.evaluator |
| `board` | Sonnet | agents.board |
| `monitor` | Haiku | agents.monitor |

Three enforcement layers: `model_policy.py` `select_model()` downshifts opus→sonnet for non-allowed roles (logs to `.harness/model-policy-violations.jsonl`); `session_sdk.py:_run_claude_via_sdk()` calls `assert_model_allowed()` before the wire (raises `ValueError`); `config.py` `OPUS_ALLOWED_ROLES` (env-overridable, default `{planner, orchestrator}`). Never pass `model="claude-opus-*"` directly. Widen for a one-off via `TAO_OPUS_ALLOWED_ROLES=...` and document why. Budget-tier escalations change retries/threshold/timeout, never the model — generator stays on Sonnet at every tier. The plan phase runs on Sonnet (not Opus, not Haiku) by intent — Haiku produced 5%-confidence plans and prose refusals; do not regress.

## SDK Architecture

`TAO_USE_AGENT_SDK=1` is the only supported mode. Generator/evaluator via `_run_claude_via_sdk()`/`_run_single_eval()` in `sessions.py`; board via `_run_prompt_via_sdk()` in `agents/board_meeting.py`; orchestrator + pipeline fan out per phase. Every invocation emits to `.harness/agent-sdk-metrics/YYYY-MM-DD.jsonl` (analyse with `scripts/sdk_metrics.py`).

- **Fallback (R-02):** `TAO_USE_FALLBACK=1` → direct Anthropic Python SDK; test quarterly via `scripts/fallback_dryrun.py`.
- **Receive loop:** `async for message in client.receive_response()` — never `client._query.receive_messages()` (private, breaks on upgrade).
- **MCP SDK imports:** subpath only — `@modelcontextprotocol/sdk/server/mcp.js`, `.../stdio.js`. Top-level package doesn't re-export `McpServer`.
- **Testing:** patch `claude_agent_sdk.ClaudeSDKClient` with `AsyncMock`; set `return_value.__aenter__.return_value.receive_response` to an async iterator of mock messages with `.content`. Never hit the real API in unit tests.

## Board Research Mode (RA-1974)

`TAO_BOARD_RESEARCH_MODE` controls Phase 2.4 in `agents/board_meeting.py`: `fast` (default, 180 s WebSearch+WebFetch via Agent SDK); `hybrid` (recommended — fast now + dispatch Margot `deep_research_max` for next cycle); `deep` (Margot only; this cycle defers). Margot dispatch is gated on `TAO_SWARM_ENABLED=1` + `swarm.margot_tools` reachability; failures fall back to fast silently. Harvested briefs auto-prepend as `prior_deep_research`. The `ceo-board` skill Stage 1.5 mirrors these modes (deep when the brief says `[deep-research]`).

## Linear Integration

- **Team:** RestoreAssist (`a8a52f07-63cf-4ece-9ad2-3e3bd3c15673`)
- **Project:** Pi - Dev -Ops (`f45212be-3259-4bfb-89b1-54c122c939a7`)
- **Ticket format:** RA-xxx. **MCP:** `LINEAR_API_KEY` in Claude Desktop config + Railway.

## Autonomy and Health

- `autonomy.py` polls Linear every 5 min for Urgent/High Todo and auto-creates sessions. In-Progress issues are invisible — reset to Todo to restart a stalled session. Kill switch: `TAO_AUTONOMY_ENABLED=0`.
- **Inner-loop kill-switch (RA-1966):** three abort axes for any TAO loop — `TAO_MAX_ITERS` (default 25), `TAO_MAX_COST_USD` (default 5.00), `TAO_HARD_STOP_FILE` (default `~/.claude/HARD_STOP`; `touch` it to drain in-flight loops without restart). Impl in `kill_switch.py` (`LoopCounter`, `check_hard_stop`, `KillSwitchAbort`); wired into `orchestrator._wait_for_wave` and the `autonomy.py` poller. Distinct from `swarm/kill_switch.py` (per-bot `/panic` flag). Test: `tests/test_tao_kill_switch.py`.
- **Judge-gated loop (RA-1970):** `tao_judge.py` `judge(...) -> JudgeVerdict` (reason ∈ {GOAL_MET, INSUFFICIENT_PROGRESS, TESTS_FAIL, TIMEOUT, STILL_WORKING}; score ∈ [0,1]; JSON parse failure → STILL_WORKING). `tao_loop.py` `run_until_done(...)` — one generator step per iter, judge every N iters, three RA-1966 abort axes; `LoopResult.reason` ∈ {GOAL_MET, MAX_ITERS, MAX_COST, HARD_STOP, JUDGE_NEVER_SATISFIED}. CLI `scripts/run_tao_loop.py`. Tests: `test_tao_judge.py`, `test_tao_loop.py`. Full `sessions.py` integration deferred until judge telemetry has run.
- **Context compactor (RA-1967):** deterministic, LLM-free transcript compactor in `tao_context_vcc.py` — `compact(messages, target_token_budget=None) -> (messages, CompactionStats)`, four pure idempotent passes. Wired as deferred `compact_for_sdk(messages)`. Validate: `python3 scripts/validate_tao_context_vcc.py --root ~/.claude/projects -n 10` (exit 0 when median reduction ≥30%).
- **Context mode (RA-1969):** `tao_context_mode.build_index(repo_root)` (~200 B/file synopsis + symbols + sha256), then `expand(index, path)` for needed files only — pure regex, no LLM. CLI `scripts/run_tao_context_mode.py`; validate vs vcc baseline (threshold median ≥40% additional reduction; miss = WATCH not REJECT).
- **Codebase wiki (RA-1968):** self-updating per-directory `WIKI.md` via post-merge `.github/workflows/codebase-wiki.yml` → `scripts/run_codebase_wiki.py --since=<sha>` → `tao_codebase_wiki.update_wiki(...)`; token-budget guard (default `max_cost_usd=0.02`/dir; Action sets `TAO_MAX_COST_USD=0.05`); `LoopCounter.tick()` per dir; `concurrency: codebase-wiki` cancel-in-progress; `if: github.repository == 'CleanExpo/Pi-Dev-Ops'`.
- **Always-on:** if any step needs a Mac awake or a local process, it's not autonomous. Always-on path = Railway + Vercel + GitHub Actions only.
- **`/health` must surface real state:** a boolean that the loop will fire next tick, and the timestamp of the last successful tick. Also surface `linear_api_key: bool` — `autonomy.py` silently skips every poll when the key is missing while `/health` still returns 200.
- **Do-while:** `while True: await asyncio.sleep(interval)` delays the first run a full interval after restart — use a 10 s `startup_delay` and log every skipped poll.
- **Watchdog (RA-1973):** the `linear_todo_poller()` loop body is wrapped in `try/except`; each crash increments `_poller_iteration_errors`, captures `_last_iteration_error`, logs the traceback, fires a one-shot Telegram alert at the 1st and 10th failure (when `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALERT_CHAT_ID` set). Surfaced via `/api/autonomy/status`.
- **Per-team orphan recovery (RA-1973):** `_ORPHAN_RECOVERY_STATE_BY_TEAM` defaults to `Pi-Dev: Blocked` for RA, `Todo` for DR-NRPG/SYN/GP/UNI; override via `TAO_ORPHAN_RECOVERY_STATES` (JSON `team_uuid → state`). Missing state → catch `RuntimeError`, record `orphan_recovery_state_missing`, skip without crashing.

## Scheduled Tasks

- Scheduled-tasks MCP runs in the desktop Claude session and does **not** inherit `.claude/settings.json`. Keep each task to a single shell command calling a standalone Python helper. Each runs in a fresh Cowork sandbox at `/sessions/<id>/mnt/<folder>` — discover the repo via `find /sessions -type d -name <repo>`.
- Never escalate CRITICAL from a Cowork sandbox; `ModuleNotFoundError` in a watchdog is a sandbox issue. Real test truth = GitHub Actions.
- **Permission grant for autonomous harnesses — all three layers:** `.claude/settings.json` `permissions.defaultMode=bypassPermissions`; `ClaudeAgentOptions(permission_mode='bypassPermissions')` at every SDK call site; `--dangerously-skip-permissions` in every `claude -p` subprocess. Missing any one → silent 3 AM stall.
- **Cron trigger reset:** `cron-triggers.json` `last_fired_at` resets to git-committed values on Railway redeploy. Use `abs()` in the debounce check and fire overdue triggers within 10 s of boot.

## Persistence

- `_sessions` is in-memory — persist status to disk atomically after every state change using write-to-`.tmp`-then-`os.replace()` (crash-safe).
- **Workspace GC:** terminal states (complete/failed/killed/interrupted) GC'd after `GC_MAX_AGE` (default 4 h); also scan for orphan dirs not referenced by `_sessions`.

## Observability

`supabase_log.py` is the single write path for server-side Supabase events — all writes fire-and-forget; observability failures must never block the pipeline. Tables with live writers: `gate_checks`, `notebooklm_health`. Declared but unwritten: `sessions`, `alert_escalations`, `telegram_sessions`. Documented but never created (cleanup target): `heartbeat_log`, `triage_log`, `workflow_runs`, `claude_api_costs`. Adding a logger → add the matching `CREATE TABLE IF NOT EXISTS` to `supabase/migration.sql` in the same PR (idempotent).

## CI Pipeline

Three jobs: `python` (pytest + ruff), `frontend` (tsc + eslint + build), `smoke-prod` (post-deploy gate against Railway, main only — requires `TAO_PROD_PASSWORD` secret).

## Hardwired Lessons — 2026-04-17 marathon (do not regress)

### Planner / Generator SDK (RA-1169–1178)

| Rule | Why |
|------|-----|
| `parse_event` must `isinstance(evt, dict)` after `json.loads` | `json.loads('"hello"')` is a str; next `.get(...)` crashes the phase |
| Wrap SDK stream in `asyncio.wait_for(..., timeout=timeout)` | SDK has no built-in stream timeout; infinite hangs were the default |
| Use top-level `claude_agent_sdk.query()`, not `ClaudeSDKClient` | SDK #576: `ClaudeSDKClient` hangs when reused across FastAPI tasks |
| Pass `permission_mode='bypassPermissions'` to `ClaudeAgentOptions` | Without it, Claude emits "waiting for permission" prose + empty diffs |
| Verify clone origin == `session.repo_url`; plant a stub `CLAUDE.md` at workspace root | Stops Claude's upward search inheriting the Pi-CEO `CLAUDE.md` |
| `TAO_WORKSPACE` must live OUTSIDE any parent git repo (e.g. `/tmp/pi-ceo-workspaces`) | Else git uses the outer `.git` and pushes to the wrong remote |
| Generator timeout by tier: basic 300 s, detailed 600 s, advanced 900 s | Full-feature briefs need 5–15 min of real work |
| Plan phase on Sonnet for all tiers (Haiku retired) | Haiku → 5% confidence, 45 s timeouts, prose refusals |
| Planning prompt forces JSON-only (first `{`, last `}`, assume on ambiguity) | Sonnet otherwise asks for clarification and breaks the parse |
| Pre-pop empty-string `ANTHROPIC_API_KEY` | `""` ≠ unset; SDK treats it as "key mode, empty key" and fails auth |

### Push layer (RA-1182–1184)

| Rule | Why |
|------|-----|
| Webhook handler skips refs containing `pidev/` and repo `CleanExpo/Pi-Dev-Ops` | Prevents recursive self-modification (43 zombie branches, 2026-04-17) |
| After a successful push with a real diff, auto-open a PR via GitHub REST | The branch alone isn't a mergeable action |
| Auto-open a Linear ticket in the TARGET repo's project (per `.harness/projects.json`) | Tickets land on the right kanban |
| `session.workspace = f"{TAO_WORKSPACE}/{session.id}"` | UUID isolation outside the harness tree |

### Dashboard UX (RA-1181)

| Rule | Why |
|------|-----|
| Reframe SSE drops as "reconnecting", poll `/api/sessions` as truth | SSE drops through Vercel's 10 s proxy; the session continues server-side |
| Completion → green ✅ banner with score + files-modified + branch + "Fix next ↗" | Silent success is indistinguishable from a placeholder (RA-1109) |
| Active-build strip polls every 4 s regardless of SSE health | Single source of truth for "what's running" |

### Linear routing reference

`.harness/projects.json` is canonical (match repo name case-insensitive, last path segment → `linear_team_id` + `linear_project_id`):

```
pi-dev-ops        → team a8a52f07  project f45212be
restoreassist     → team a8a52f07  project 3c78358a
disaster-recovery → team 43811130  project d2c1d63b
dr-nrpg           → team 43811130  project ec4e8059
nrpg-onboarding   → team 43811130  project 144c3160
synthex           → team b887971b  project 3125c6e4
unite-group       → team ab9c7810  project b62d9b14
nodejs-starter    → team ab9c7810  project c12337a6
oh-my-codex       → team ab9c7810  (no project)
ccw-crm           → team ab9c7810  project 40c7dc3d
carsi             → team 91b3cd04  project 20538e04
```

## Senior-Agent Topology (Wave 4 — RA-1858, 2026-05-02)

Four senior-agent bots run in the orchestrator loop, each owning one slice of executive visibility plus a dual-key approval gate.

| Bot | Module | Skill | Owns | Dual-key gate |
|---|---|---|---|---|
| CFO | `swarm/bots/cfo.py` (engine `swarm/cfo.py`) | `skills/cfo/` | Burn / NRR / GM / runway / model-spend | Spend > $1,000 |
| CMO | `swarm/bots/cmo.py` (engine `swarm/cmo.py`) | `skills/cmo-growth/` | LTV:CAC / blended CPA / channel HHI / attr decay | Ad-spend > $5,000/day |
| CTO | `swarm/bots/cto.py` (engine `swarm/cto.py`) | `skills/cto/` | DORA quartet + p99 + uptime + cost/request | Prod PR merge |
| CS | `swarm/bots/cs.py` (engine `swarm/cs.py`) | `skills/cs-tier1/` | NPS / FCR / GRR / first-response / threats | Refund > $100 |

Shape per bot: pure-Python engine (compute / detect_breaches / assemble_daily_brief / approve_*) + thin bot wrapper (gates on `TAO_SWARM_ENABLED` + kill-switch) + jsonl ledger `.harness/swarm/<bot>_state.jsonl` + daily-fire window (default 06:00 UTC).

**Provider envs** (default `synthetic`, seeded from `.harness/projects.json`): `TAO_CFO_PROVIDER` (`stripe_xero` → Stripe MRR + Xero cash/COGS/revenue real); `TAO_CMO_PROVIDER`, `TAO_CTO_PROVIDER`, `TAO_CS_PROVIDER` (stubs — fall back to synthetic with warning). Ceiling overrides: `TAO_CFO_SPEND_CEILING` (1000), `TAO_CMO_ADSPEND_CEILING` (5000), `TAO_CS_REFUND_CEILING` (100). Stripe-Xero needs `STRIPE_API_KEY`, optional `STRIPE_ACCOUNT_<BID>`, `XERO_ACCESS_TOKEN` (30-min expiry, refresh sidecar required), `XERO_TENANT_<BID>`.

- **Multi-agent debate (RA-1867):** `swarm/debate_runner.py` runs drafter + adversarial red-team via `asyncio.gather`, both through `model_policy.select_model` (no Opus leak); emits a Hermes Kanban card via `swarm/kanban_adapter.py`; `/panic` cancels and persists `debate_aborted`.
- **Daily 6-pager (RA-1863):** `swarm/six_pager.py` composes from the four ledgers + latest Margot insight (pure file-read). `swarm/six_pager_dispatcher.py` owns side effects: PII redact → optional voice via `swarm/voice_compose.py` (`ELEVENLABS_API_KEY`, optional `ELEVENLABS_VOICE_ID`; text-only without) → `draft_review.post_draft` HITL → audit. Fires in the daily window with 23 h debounce.
- **Cycle order (`swarm/orchestrator.py`):** Guardian (veto) → Builder/Click/Scribe (self-gate on SHADOW_MODE) → Chief of Staff (Telegram routing) → CFO→CMO→CTO→CS (gate on `TAO_SWARM_ENABLED` + kill-switch) → 6-pager dispatcher → daily report. New senior agent = mirror the cfo.py shape; wire-in is one `try/except` in `orchestrator.run()`.

## Content Rules

No first-person business language (We/Our/I/Us/My). No AI filler (delve, tapestry, landscape, leverage, robust, seamless, elevate). Every paragraph answers a specific question.

## Launch Crew

A pre-flight crew gets a product launch-ready, then hands off to existing machinery — no new build/test/ship loop, no new Linear tag.

- **Governance:** [`HERMES.md`](HERMES.md) + [`skills/launch-charter/SKILL.md`](skills/launch-charter/SKILL.md) (binds to this file + `AGENTS.md` + `kill-switch-binding`/`pii-redactor`/`tao-judge`).
- **Run:** `/ship-it` → `launch-charter` → `launch-project-audit` → `launch-review` → `launch-enhance-debloat` (propose only) → sync via `pi-dev-linear-contract` → **STOP for human go**.
- **On go:** build through `ship-chain` / `tao-loop` + `tao-judge` / `ship-release`; autonomy queue = status `Ready for Pi-Dev` + label `pi-dev:autonomous`.
- **Wiring:** skills load from `skills/<name>/SKILL.md`; `/ship-it` routed via `_INTENT_SKILLS` in `src/tao/skills.py`. Regenerate `agentskills.json` after adding skills.

## Judge Gate

Before approving or building any feature, connector, automation, agent, hook, MCP server, database change, UI change, or architecture plan, run:

```text
/judge <proposal>
```

Judge is read-only. It must challenge the plan, check first-source evidence, identify existing capability, review UI/UX, review security/privacy, define loop/stress tests, and score the proposal out of 100 before any implementation starts. It must not implement code; implementation only follows a separate, explicit user approval after the Judge Report.

- **Claude Code:** `/judge` → `.claude/skills/judge/SKILL.md`
- **Codex:** `$judge` or `/skills` → select `judge` → `.agents/skills/judge/SKILL.md`
- **Shared docs:** `.judge/` (evidence ranking, approval policy, report template, example)
- Distinct from `tao-judge` (machine loop-termination scorer); `judge` decides *whether to build*, `tao-judge` decides *whether an in-flight loop is done*.

## Session Handoff Command

Before stopping, changing terminals, handing work to another agent, opening a PR, or leaving a task partially complete, run:

```text
/session-handoff
```

Use a scoped version when helpful:

```text
/session-handoff <ticket, branch, PR, feature, or repo area>
```

The handoff must include: summary of what was done, where it started, decisions locked + what shipped, key files, running state, verification (how to confirm things still work), deferred + open questions, and pick up here.

Rules:

- Read-only by default.
- Do not claim tests passed unless they were run.
- Do not claim anything shipped unless committed/pushed/merged evidence exists.
- Do not claim a process is still running unless verified.
- Always provide the first command the next agent should run.

- **Claude Code:** `/session-handoff` → `.claude/skills/session-handoff/SKILL.md`
- **Codex:** `$session-handoff` or `/skills` → select `session-handoff` → `.agents/skills/session-handoff/SKILL.md`
- **Shared docs:** `.session-handoff/` (report template, verification checklist)
- Companion to `judge`: `/judge` decides *whether to build*; `/session-handoff` records *what happened and where the next agent picks up*.
