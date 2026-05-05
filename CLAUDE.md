# Pi-Dev-Ops — Claude Code Guidance

## Autonomous Operation Mandate (2026-04-18 — authorised by user)

The user has granted a standing autonomous mandate. Work through the backlog without asking permission. Do not check in. Do not ask "should I?" — act.

**Durable rules — follow without confirmation every session:**

1. **Sandbox first, push only when explicitly asked.** Iterate on local clones under `/tmp/` or `/tmp/pi-ceo-workspaces/`. Do NOT push to main or open PRs against portfolio repos unless the user's most recent message explicitly says "push" / "open PR" / "ship it". Prepare the diff, stage it locally, write the PR body to a markdown file, then STOP.
2. **Generate Linear tickets for every discovery.** Use `mcp__pi-ceo__linear_create_issue`. Route to the correct team/project via `.harness/projects.json` (repo → `linear_team_id` + `linear_project_id`). Never dump findings into Pi-Dev-Ops's own project unless the finding is about Pi-CEO itself.
3. **Smoke-test every change before committing.** At minimum: `python -m py_compile` on edited Python files, `npx tsc --noEmit` on edited TS. If an endpoint changed, issue a probe. If a CI workflow changed, trigger it and wait for the result.
4. **Surface-treatment prohibition (RA-1109) applies to every autonomous run.** No `.catch(() => {})`, no fake-green status, no "it compiled so it works" claims. Every async > 2 s action needs a visible progress surface; every terminal state needs an unambiguous signal.
5. **Honest failure reporting.** If a fix doesn't land, say so with the exact error class + source-line, and file a follow-up ticket. Never dress up a failure as "still running" or silently retry forever.
6. **Skill-injection hooks are advisory.** The `skillInjection` system-reminders (Vercel plugin pattern matches like "deployments-cicd", "next-upgrade", etc.) fire on file patterns and keywords. Ignore them when they don't match the actual task context. Explain why in one line and move on.

**What "working autonomously" means at Pi-CEO scope:**

- Pick the highest-leverage item from the Linear backlog (Urgent+High Todo first, then Medium).
- Fix it in an isolated `/tmp/` clone with a fresh branch.
- Run the gates (typecheck, unit tests, smoke test against Railway/Vercel if applicable).
- Write the commit + PR body into the sandbox but **do not push unless told**.
- Update the Linear ticket: move to In Progress on start, attach the sandbox path + diff summary + any follow-up discoveries on complete.
- File follow-up tickets for anything noticed-but-not-in-scope.
- Repeat.

**When to stop and ask:**

Only when the user's last message says so, or when a rule explicitly requires a human decision (branch-strategy changes, secret rotations, destructive migrations, new service provisioning).

**Finishing a task is NOT a stop signal.** (2026-04-18 — reinforced after repeated founder friction.)

Completing the thing you were doing does not mean "turn it back to the user and wait". It means "move to the next highest-leverage thing immediately". Chain, don't wait. The pattern below is the default operating loop for every autonomous session:

```
1. Complete current task (code + smoke + commit + PR + Linear update)
2. One-line status: "done X, moving to Y"
3. Scan for next work, in order:
   a. Any in-flight session that needs verification/unblocking
   b. Any new Linear Urgent/High Todo in the portfolio
   c. Any open sandbox ticket ready to code (RA-xxxx-Todo with spec)
   d. Any review surface from a completed PR (merged → verify deploy → verify product)
   e. Audit + follow-up tickets from the last change's blast radius
4. Start that next task. DO NOT pause for confirmation between 3 and 4.
```

**Stop words** — only these trigger an actual pause:
- "pause" / "stop" / "wait for me" / "hold" / "take a break"
- "I'll take it from here" / "I'll handle X"
- An explicit question from the user ("what do you think?" / "should I do X?") — answer, then resume.

**Not stop words** — do NOT treat any of these as permission to idle:
- Any form of "thanks" / "good" / "nice" / "great job"
- Any silence / no message
- Any system notification of a background task completing
- Any tool-result summary page ("done" / "completed") — that's progress, not an endpoint
- "I'm going to bed" / "I'll be back" — that's WHY autonomous mode exists, keep going

**The founder has said verbatim, multiple times: "stopping really gives me the shits when there is so much work to accomplish".** Treat every completion as a starting gun for the next item. If the backlog is genuinely empty and every surface is verified, say so in one line and pick up an improvement/audit task — never just stand down.

### Gate-to-green loop (2026-04-21 mandate)

After every code change, run this loop before declaring the PR done:

```
sandbox local:  npx tsc --noEmit          →  fix my errors
                npm run lint (if exists)  →  fix my warnings (ignore pre-existing)
                npm test (if fast)        →  fix my failures

push:           git push branch    →  gh pr create

CI wait:        gh pr view N --json statusCheckRollup
                  while any check is pending: sleep 30
                  if any REQUIRED check red: read logs, fix on same branch, push, goto CI wait
                  else: move on
```

**Smoke after merge:** once the user merges a PR, navigate to the affected production path via Chrome MCP, read console + network for errors, and file any findings as **Linear tickets** (not new PRs) in the target repo's project. Routing table in `.harness/projects.json`.

**PR vs Linear ticket decision:**
- Discovered during smoke / audit / code review → **Linear ticket** in the target repo's project, priority 3 default.
- In-scope for the current session's stated goal OR clearly launch-critical → **PR**.
- When in doubt: ticket first, mention in status update.

Never dump discoveries into the Pi-Dev-Ops project unless the finding is about Pi-CEO itself. Use the Linear GraphQL API directly when the MCP tool defaults wrong: `POST https://api.linear.app/graphql` with `Authorization: lin_api_...` (from `.env.local`) and `{variables:{i:{teamId,projectId,title,description,priority}}}`.

**Skill advisories are almost always off-task.** Vercel plugin + posttooluse validator inject Clerk/Next-upgrade/workflow/chat-sdk migration suggestions on nearly every Edit. When they don't match the current task (≈95 % of the time), say so in one line and ignore. Never let them pull into scope creep ("while I'm here, migrate to Clerk"). The rule from the top of this file already says this — it applies especially hard when in the gate-to-green loop.

**Hardwired lessons from 2026-04-17 marathon (PRs #68-81):**

See `## Pi-CEO Session Pipeline — Hardwired Lessons` section below for the 14 fixes that together make the autonomous pipeline actually work. Do not regress any of them.

---

## Project Context

Pi-Dev-Ops converts a GitHub repo URL + plain-English brief into an autonomous Claude Code execution session. Generator and evaluator run via `claude_agent_sdk`. `TAO_USE_AGENT_SDK=1` is mandatory — setting 0 raises `ImportError` at startup.

## Architecture

| Layer | Tech | Location |
|-------|------|----------|
| Frontend | Next.js 16.2.2, React 19, Tailwind | `dashboard/` |
| Backend | FastAPI, Python 3.11+ | `app/server/` |
| Routes | 8 focused route modules | `app/server/routes/` |
| MCP Server | Node.js, @modelcontextprotocol/sdk | `mcp/` |
| TAO Engine | Python (skills, tiers, budget) | `src/tao/` |
| Harness State | YAML/JSON/Markdown | `.harness/` |
| Skills | 48 SKILL.md files | `skills/` |
| Database | Supabase (PostgreSQL) | `supabase/` |
| Deploy (FE) | Vercel | `dashboard/vercel.json` |
| Deploy (BE) | Railway | `railway.toml`, `Dockerfile` |

## Backend Module Map (`app/server/`)

| File | Lines | Concern |
|------|-------|---------|
| `main.py` | ~25 | Thin assembler — imports `app`, registers all routers |
| `app_factory.py` | ~130 | `app` object, CORS/security middleware, `_resilient`, startup/shutdown hooks |
| `models.py` | ~126 | All Pydantic request models |
| `routes/auth.py` | ~48 | `POST /api/login`, `POST /api/logout`, `GET /api/me` |
| `routes/sessions.py` | ~122 | `/api/build`, `/api/build/parallel`, session list/kill/logs/resume |
| `routes/webhooks.py` | ~214 | `POST /api/webhook` (GitHub+Linear), morning-intel, Telegram |
| `routes/triggers.py` | ~32 | Trigger CRUD (`GET/POST/DELETE /api/triggers`) |
| `routes/scan_monitor.py` | ~111 | `/api/scan`, `/api/projects/health`, `/api/monitor` |
| `routes/pipeline.py` | ~89 | `/api/spec`, `/api/plan`, `/api/test`, `/api/ship`, `/api/pipeline/{id}` |
| `routes/utils.py` | ~68 | `/api/gc`, `/api/lessons`, `/api/autonomy/status`, WebSocket `/ws/build/{sid}` |
| `routes/health.py` | ~125 | `/health`, `/api/health/vercel`, Claude CLI poll, static mount |
| `routes/mission_control.py` | ~258 | `GET /api/mission-control/live` — single aggregator powering the dashboard live-autonomy view (throughput, active sessions, recent completions, Linear queue, pulse). All Linear calls fail-soft to keep the dashboard alive. |

Public contract: `app.server.main:app` is the FastAPI instance — Dockerfile and Railway both reference it. `main.py` re-exports `app` from `app_factory`. Never break this import.

## Development Setup

```bash
cd app && source .env.local && uvicorn server.main:app --host 127.0.0.1 --port 7777
cd dashboard && npm run dev
node mcp/pi-ceo-server.js
```

### Local dev auth
- Login password defaults to **`dev`** when `.env.local` contains unresolved `op://` refs (the Vercel CLI creates these by default)
- Override by setting `DASHBOARD_PASSWORD=<plaintext>` in `dashboard/.env.local`
- `dashboard/scripts/dev-env.sh` auto-detects and resolves — no manual 1Password CLI required
- Never commit plaintext passwords; `.env.local` is gitignored

## Running Tests

```bash
python -m pytest tests/ -x -q                # Gate: import check must pass first
python -c "from app.server.main import app"   # Must print FastAPI
cd dashboard && npx tsc --noEmit
cd dashboard && npm run build
python scripts/smoke_test.py --url http://127.0.0.1:7777 --password $TAO_PASSWORD
```

Expected: 3 pre-existing failures in `test_sdk_phase2.py` (claude_agent_sdk not installed locally). All other tests pass.

## Code Conventions

- **Python:** snake_case, type hints on all functions, `logging.getLogger()`, structured JSON via `_JsonFormatter`
- **TypeScript:** strict mode, no `any`, named exports, interfaces over types
- **Commits:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `ci:`, `chore:`)
- **Branches:** `feature/{ticket-id}-{short-desc}` or `fix/{ticket-id}-{short-desc}`
- **Functions:** under 40 lines. Files under 300 lines. Extract when exceeding.
- **Security:** bcrypt passwords, parameterised queries, CSP headers, no secrets in code

## Key Patterns

- **Parallel agent dispatch:** Dispatch multiple `Agent` tool calls in a single message for independent tasks — ~8× faster than sequential. Agents must not share target files; partition by file ownership.
- **Reconnaissance-first:** Always read current `.harness/` state before drafting new plans or briefs. Stale plans produce orphan work and file conflicts.
- **detect-secrets:** Run `detect-secrets scan` pre-commit on every portfolio repo. Pi-SEO activation found 6 exposed keys in docs/runbooks across dr-nrpg, synthex, ccw-crm.
- **Password auth:** bcrypt with transparent SHA-256 migration (`auth.py`). `TAO_PASSWORD` set → hash regenerated on every startup so Railway env changes take effect immediately.
- **Session secret:** Persisted to `app/data/.session-secret`.
- **SSE streaming:** `dashboard/hooks/useSSE.ts` with exponential backoff reconnection.
- **Phase pipeline:** 5–6 phases in `sessions.py`, parsed by `dashboard/lib/phases.ts`. Phase 5: git push to `pidev/auto-{sid}` feature branch with GITHUB_TOKEN auth (3-attempt backoff; auth failure → hard stop).
- **Settings:** Supabase-backed via `dashboard/lib/supabase/settings.ts`.
- **MCP tools:** `mcp/pi-ceo-server.js` — 27 tools for harness reads + Linear operations.
- **Path traversal:** `_safe_sid()` strips non-alphanumeric from session IDs before file path use.
- **Webhook HMAC:** `hmac.compare_digest()` for GitHub (`x-hub-signature-256`) and Linear (`Linear-Signature`).
- **Rate-limit GC:** `_req_log` in `auth.py` accumulates IP keys forever. Prune stale IPs (last request >120 s ago) every 5 min inline inside `check_rate_limit()` — no background task needed in asyncio.
- **Analysis mode:** `ANALYSIS_MODE=api` in Vercel forces Max plan subscription token (`sk-ant-oat01-*` from `claude setup-token`).
- **Push auth:** `_phase_push()` injects GITHUB_TOKEN via x-access-token into git remote URL and pushes to `pidev/auto-{sid[:8]}` feature branch. Requires GITHUB_TOKEN + GITHUB_REPO env vars in Railway.
- **Route isolation:** Each `routes/*.py` module owns one concern. `_IS_CLOUD` is re-derived from `os.environ` in `routes/auth.py` (not imported from `app_factory`) to avoid coupling. `_find_active_session_for_repo()` lives in `routes/sessions.py` and is imported into `routes/webhooks.py` one-way.
- **Rate-limit cloud IP:** In Railway/Render/Fly, `request.client.host` is the load-balancer's internal IP (varies per LB instance), so per-IP buckets never fill. Trust `X-Forwarded-For` when `_IS_CLOUD` — Railway strips any client-supplied XFF at the edge before injecting the real client IP, so the first entry is safe to use. Use `request.client.host` locally to avoid XFF spoofing.
- **API key env hygiene:** `ANTHROPIC_API_KEY=""` set by the `claude` CLI in the parent shell is inherited by child processes. In Python, call `os.environ.pop("ANTHROPIC_API_KEY", None)` when no explicit key is provided so subprocesses fall back to CLI OAuth tokens (`~/.claude/`) rather than failing with HTTP 401. In Next.js routes, always call `.trim()` on `process.env.ANTHROPIC_API_KEY` — Vercel stores env vars with a trailing `\n` that silently breaks API auth.
- **1Password env refs:** `op://vault/item/field` references in `.env` files are only resolved when launched via `op run --`. Python `dotenv.load_dotenv()` reads them as literal strings. Add a Pydantic `field_validator(mode="before")` that detects strings starting with `op://` and returns `None` so the field is treated as absent.
- **Anthropic docs redirects:** `docs.claude.com` redirects to `platform.claude.com` and `code.claude.com`. Any `httpx` fetcher hitting Anthropic docs must set `follow_redirects=True`. Filename collisions occur if URLs are keyed by last path segment alone — use two-segment extraction or a full URL hash.
- **Telegram minimal push:** Sending a Telegram message from a sandboxed Python env requires only `TELEGRAM_BOT_TOKEN` + a `chat_id`. The full `python-telegram-bot` package is not required — `urllib` + `POST api.telegram.org/bot{token}/sendMessage` is sufficient. See `scripts/send_telegram.py`.

## Surface Treatment Prohibition (RA-1109 — hardwired 2026-04-17)

**A feature isn't shipped until the user-visible outcome is demonstrable.** HTTP 200 is not shipping. Types compiling is not shipping. Lint green is not shipping. If a button exists and a user presses it, they must SEE something change — a spinner, a streamed log, a navigation, a persisted state change, an error. Silent success is indistinguishable from a placeholder and destroys trust.

**Banned patterns — reviewer must reject on sight:**
- `.catch(() => {})` on a user action — swallows failures the user needs to know about.
- Fire-and-forget button that returns `ok` in console but never updates the UI.
- "Backend returned 200 so it works" without an end-to-end click-test on the live deploy.
- Toast that disappears in 3 seconds as the only feedback for a long-running action.
- Label on a button that overstates its actual effect (e.g. "Fix with Claude" that only spawns a background session with no viewing surface).

**Required patterns:**
- Any write action: either immediate UI state change, OR a subscribable progress surface (SSE stream, polling status, phase tracker).
- Any async action >2 s: a live progress surface with a visible terminal or status chip, NOT a toast.
- Any destructive action: confirmation + success toast with undo OR error state with actionable next step.
- Any spawn action (Fix with Claude, Run, Redeploy, etc.): inline live-log streamer OR link to a page where the user can watch it work.

**Enforcement:**
- `.github/PULL_REQUEST_TEMPLATE.md` requires an explicit "Manual verification path" describing the live click-through.
- Evaluator gate: any PR that adds / modifies an interactive surface but doesn't describe a verified manual click-test in the PR body is flagged, regardless of lint/type/test status.
- The Fix-with-Claude incident (PR #48 → fixed in PR #56) is the exemplar: lint was clean, CI was green, endpoint returned 200, yet the feature was unusable. The fix was adding an inline SSE streamer showing live session output.

## Model Routing Policy (RA-1099 — hardwired 2026-04-17)

**Opus 4.7 is reserved for Senior PM (`planner`) + Senior Orchestrator (`orchestrator`) ONLY.** Every other agent role uses Sonnet 4.6 or Haiku 4.5.

| Role | Model | Where configured |
|------|-------|------------------|
| `planner` | Opus 4.7 | `.harness/config.yaml` agents.planner |
| `orchestrator` | Opus 4.7 | `.harness/config.yaml` agents.orchestrator |
| `generator` | Sonnet 4.6 | `.harness/config.yaml` agents.generator |
| `evaluator` | Sonnet 4.6 | `.harness/config.yaml` agents.evaluator |
| `board` | Sonnet 4.6 | `.harness/config.yaml` agents.board |
| `monitor` | Haiku 4.5 | `.harness/config.yaml` agents.monitor |

**Enforcement is in three layers:**
1. `app/server/model_policy.py` — `select_model(role, requested)` reads config and downshifts opus → sonnet for non-allowed roles, recording violations to `.harness/model-policy-violations.jsonl`.
2. `app/server/session_sdk.py:_run_claude_via_sdk()` — calls `assert_model_allowed(role, model)` before the SDK request hits the wire. Raises `ValueError` on violation.
3. `app/server/config.py` — `OPUS_ALLOWED_ROLES` env-overridable set, default `{"planner", "orchestrator"}`.

**Never bypass the policy.** If you need to widen opus access for a one-off, set `TAO_OPUS_ALLOWED_ROLES=planner,orchestrator,foo` and document why. Do not pass `model="claude-opus-4-7"` directly to the SDK — `assert_model_allowed` will reject it.

**Budget tier escalations** (`autonomy_budget.anchors`) only escalate retries / threshold / timeout, never the model. Generator stays on sonnet at every tier.

## SDK Architecture

`TAO_USE_AGENT_SDK=1` is the only supported mode.

| Layer | SDK Path | File |
|-------|----------|------|
| Generator | `_run_claude_via_sdk()` | `sessions.py` |
| Evaluator | `_run_single_eval()` → SDK | `sessions.py` |
| Board Meeting | `_run_prompt_via_sdk()` | `agents/board_meeting.py` |
| Orchestrator | Agent SDK fan-out | `orchestrator.py` |
| Pipeline | Agent SDK per phase | `pipeline.py` |

Every SDK invocation emits a row to `.harness/agent-sdk-metrics/YYYY-MM-DD.jsonl`. Analyse with `python scripts/sdk_metrics.py`.

**Fallback (Risk Register R-02):** `TAO_USE_FALLBACK=1` activates direct Anthropic Python SDK. Test quarterly via `scripts/fallback_dryrun.py`.

**SDK receive loop:** Use `async for message in client.receive_response()` — NOT `client._query.receive_messages()`. The latter is a private API that breaks on SDK upgrades.

**MCP SDK imports:** Use subpath imports — `@modelcontextprotocol/sdk/server/mcp.js` and `@modelcontextprotocol/sdk/server/stdio.js`. The top-level package does not re-export `McpServer` directly.

**Testing SDK-wrapped functions:** Patch `claude_agent_sdk.ClaudeSDKClient` with `unittest.mock.AsyncMock`. Set `return_value.__aenter__.return_value.receive_response` to an async iterator yielding mock message objects with `.content` attributes. Never call the real API in unit tests.

## Linear Integration

- **Team:** RestoreAssist (`a8a52f07-63cf-4ece-9ad2-3e3bd3c15673`)
- **Project:** Pi - Dev -Ops (`f45212be-3259-4bfb-89b1-54c122c939a7`)
- **Ticket format:** RA-xxx
- **MCP:** `LINEAR_API_KEY` in Claude Desktop config and Railway

## Autonomy and Health

- `autonomy.py` polls Linear every 5 min for **Urgent/High Todo** issues and auto-creates sessions. In Progress issues are invisible — reset to Todo to restart a stalled session.
- Kill switch: `TAO_AUTONOMY_ENABLED=0` in Railway.
- **TAO inner-loop kill-switch (RA-1966):** Three independent abort axes for any iteration loop inside a single TAO session — orchestrator wave-poll, evaluator retry, future tao-judge / tao-loop:
  - `TAO_MAX_ITERS` (default `25`) — count cap; aborts with reason `MAX_ITERS`.
  - `TAO_MAX_COST_USD` (default `5.00`) — cumulative-cost cap; aborts with reason `MAX_COST`.
  - `TAO_HARD_STOP_FILE` (default `~/.claude/HARD_STOP`) — file existence aborts immediately with reason `HARD_STOP`. `touch ~/.claude/HARD_STOP` drains in-flight TAO loops without restarting the server.
  - Implementation: `app/server/kill_switch.py` (`LoopCounter`, `check_hard_stop`, `KillSwitchAbort`). Distinct from `swarm/kill_switch.py` (per-bot-cycle file flag driven by Telegram `/panic`).
  - Wired in `orchestrator._wait_for_wave` (per-poll hard-stop) and `autonomy.py` poller (per-cycle hard-stop). Future tao-loop / tao-judge consumers construct `LoopCounter()` per loop and call `.tick(cost_delta_usd=...)` each iteration.
  - Integration test: `tests/test_tao_kill_switch.py` (10 tests, all green).
- **TAO judge-gated loop (RA-1970):** Port of pi-until-done's `/goal ... Ralph` autonomous-coding loop with a single-scalar termination gate. Two siblings:
  - `app/server/tao_judge.py` — `judge(goal, workspace, state, *, timeout_s, session_id) -> JudgeVerdict` calls the evaluator role (Sonnet 4.6 per RA-1099) with a JSON-only scoring prompt. `JudgeVerdict.reason` ∈ {GOAL_MET, INSUFFICIENT_PROGRESS, TESTS_FAIL, TIMEOUT, STILL_WORKING}; `score` ∈ [0, 1] is the single termination scalar. JSON parse failure → STILL_WORKING (continues), `KillSwitchAbort` from any caller in the chain bubbles up.
  - `app/server/tao_loop.py` — `run_until_done(goal, workspace, *, max_iters, max_cost_usd, judge_every_n_iters, timeout_per_iter_s, on_event, session_id) -> LoopResult`. One generator step per iter, optional judge call every N iters. Three abort axes from RA-1966's `LoopCounter`: `TAO_MAX_ITERS`, `TAO_MAX_COST_USD`, `TAO_HARD_STOP_FILE`. `judge_every_n_iters=2` halves judge spend on cost-sensitive sessions. `LoopResult.reason` ∈ {GOAL_MET, MAX_ITERS, MAX_COST, HARD_STOP, JUDGE_NEVER_SATISFIED}.
  - Autoresearch lens: autonomy mandate gives intent, `judge()` gives a measurable termination condition (single-scalar gate). Kill-switch supplies orthogonal cost / iter / hard-stop bounds.
  - SKILLs: `skills/tao-judge/`, `skills/tao-loop/`. CLI: `python scripts/run_tao_loop.py --goal "..." --workspace /path --max-iters N --max-cost X --judge-every N` (exit 0 on GOAL_MET, 1 otherwise; LoopResult JSON to stdout, iter events to stderr).
  - Integration tests: `tests/test_tao_judge.py` (7), `tests/test_tao_loop.py` (8). Full integration into `sessions.py` deferred to a follow-up sub-issue once judge-output telemetry has run.
- **TAO context compactor (RA-1967):** Deterministic, LLM-free transcript compactor — port of `@sting8k/pi-vcc`. Public API `compact(messages, target_token_budget=None) -> (messages, CompactionStats)` lives in `app/server/tao_context_vcc.py`. Four passes (whitespace normalise, repeat-pattern collapse, tool-output dedup, verbose-block head/tail truncation) — all pure, idempotent, zero token cost. SKILL: `skills/tao-context-vcc/`. Wired as the deferred `compact_for_sdk(messages)` helper rather than a hard pre-pass on `_run_claude_via_sdk` (TODO comment in-source — RA-1970 will resolve once `tao-loop` settles the canonical message representation). Manual verification: `python scripts/validate_tao_context_vcc.py [DIR]` runs `compact()` over saved sessions and exits 0 when median token reduction ≥ 30%.
- **Codebase wiki (RA-1968, Wave 1):** port of `@0xkobold/pi-codebase-wiki`. Self-updating per-directory `WIKI.md` driven by post-merge `.github/workflows/codebase-wiki.yml`. Each merge runs `python scripts/run_codebase_wiki.py --since=<previous-sha>`, which calls `app.server.tao_codebase_wiki.update_wiki(...)`. The updater groups commits by top-level directory, builds a compact summarisation prompt per directory, runs a token-budget guard (sonnet 4.6 = $3/M input + $15/M output; default `max_cost_usd=0.02` per directory; the GH Action sets `TAO_MAX_COST_USD=0.05`), and writes `<dir>/WIKI.md`. Kill-switch integration: `LoopCounter.tick()` runs at the start of each directory iteration, so a `TAO_HARD_STOP_FILE` causes a graceful bypass. Workflow uses `concurrency: codebase-wiki` with `cancel-in-progress: true` so only the latest merge's run survives; `if: github.repository == 'CleanExpo/Pi-Dev-Ops'` keeps it off forks. SKILL: `skills/tao-codebase-wiki/`. Tests: `tests/test_tao_codebase_wiki.py` (8 tests, all green).
- **Always-on requirement:** if any step depends on a Mac staying awake or a local process running, the system is not autonomous. Always-on path: Railway + Vercel + GitHub Actions only.
- **`/health` must surface real state:** (1) boolean confirming the loop will fire on next tick, (2) timestamp of last successful tick. Without both, silent-success theatre.
- **Silent failure pattern:** `autonomy.py` skips every poll cycle when `LINEAR_API_KEY` is missing but `/health` still returns 200. Symptom: `sessions.total` stays at 0. Always surface `linear_api_key: bool`.
- **Do-while pattern:** `while True: await asyncio.sleep(interval)` delays first execution by a full interval after Railway restart. Use a 10s `startup_delay` instead. Log every skipped poll.
- **Watchdog around poller iteration (RA-1973):** the body of the `while True` loop in `linear_todo_poller()` is wrapped in `try/except Exception` so a single unhandled crash does NOT kill the asyncio task. Each crash increments `_poller_iteration_errors`, captures `_last_iteration_error` (type + message + ISO timestamp), records a `poller_iteration_error` event in the in-memory ring, logs the full traceback via `log.exception(...)`, and (when `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALERT_CHAT_ID` are set) fires a one-shot Telegram alert at the 1st and 10th failure. Both fields are surfaced via `/api/autonomy/status` so the dashboard and `/health` consumers can see crashes instead of silent-success theatre. Backstory: 2026-05-05 prod incident — poller died for 16 h on Railway, only caught by smoke test.
- **Per-team orphan-recovery state map (RA-1973):** `_orphan_recovery` no longer hard-codes `"Pi-Dev: Blocked"` (which only exists on the RA team workflow). The map `_ORPHAN_RECOVERY_STATE_BY_TEAM` defaults to `Pi-Dev: Blocked` for RA and `Todo` for DR-NRPG / SYN / GP / UNI. Override at process boot via `TAO_ORPHAN_RECOVERY_STATES` (JSON dict mapping `team_uuid → state_name`; falls back to defaults on parse error). If the chosen state still doesn't exist on a team's workflow, the routine catches the `RuntimeError`, records an `orphan_recovery_state_missing` event, and skips that ticket without crashing the rest of the pass.

## Scheduled Tasks

- Scheduled-tasks MCP runs inside the desktop Claude session and does **not** inherit `.claude/settings.json`. Keep every task to a single shell command calling a standalone Python helper.
- Each task runs in a fresh Cowork sandbox at `/sessions/<random-id>/mnt/<folder>`. Discover the repo dynamically: `find /sessions -type d -name <repo>`.
- Never escalate CRITICAL from a Cowork sandbox. `ModuleNotFoundError` inside a watchdog is a sandbox environment issue. Real test truth comes from GitHub Actions.
- **Permission grant for autonomous harnesses:** three layers required — (1) `.claude/settings.json` `permissions.defaultMode=bypassPermissions`, (2) `ClaudeAgentOptions(permission_mode='bypassPermissions')` at every SDK call site, (3) `--dangerously-skip-permissions` in every subprocess `claude -p` call. Missing any one layer causes silent stall at 3 AM.
- **Cron trigger reset:** `cron-triggers.json` `last_fired_at` resets to git-committed values on Railway redeploy, causing missed windows. Fix: use `abs()` in debounce check and fire any overdue triggers within 10 s of boot (startup catch-up).

## Persistence

- `_sessions` is in-memory — server restart loses all running sessions. Persist status to disk atomically after every state change.
- Use write-to-`.tmp`-then-`os.replace()` for JSON writes. Crash-safe on NTFS and POSIX.
- **Workspace GC:** `app/workspaces/` fills disk if completed sessions are never deleted. Terminal states (complete/failed/killed/interrupted) should be GC'd after `GC_MAX_AGE` (default 4 h). Also scan for orphan dirs not referenced by `_sessions`.

## Observability

`supabase_log.py` is the single write path for all server-side Supabase events. All writes are fire-and-forget — observability failures must never block the build pipeline.

**Tables actually written today** (verified RA-1105 audit 2026-04-17):
- `gate_checks` — every quality-gate result on `/ship` phase (declared `supabase/migration.sql:93`)
- `notebooklm_health` — NotebookLM source-freshness audit (declared `supabase/migration.sql:233`)

**Declared in `migration.sql` but no current writer**:
- `sessions` — placeholder for future cross-instance session sync
- `alert_escalations` — aspirational; tracked locally in `app/data/.escalation-state.json`
- `telegram_sessions` — telegram-bot writes its own SQLite, not this Supabase

**Documented historically but never created/wired** (cleanup target):
- `heartbeat_log`, `triage_log`, `workflow_runs`, `claude_api_costs`

If you add a new logger to `supabase_log.py`, add the matching `CREATE TABLE IF NOT EXISTS …` to `supabase/migration.sql` in the same PR. The migration is idempotent; safe to re-run on any Supabase project.

## CI Pipeline

Three jobs: `python` (pytest + ruff), `frontend` (tsc + eslint + build), `smoke-prod` (post-deploy gate against Railway, main-branch only). `smoke-prod` requires `TAO_PROD_PASSWORD` GitHub secret.

## Current Sprint (Sprint 12 — Active 2026-04-16)

**ZTE v2: 85/100 → target 90**

Board activation vote carried unanimously on 15 Apr 2026. Swarm flipped to active mode (`TAO_SWARM_SHADOW=0`). Rate limit: 3 autonomous PRs/day (lifts after 20 consecutive green supervised merges). NotebookLM 5th criterion added: top-3 risks per entity from Linear + Pi-SEO. Next board: 6 May 2026 Enhancement Review (RA-949).

**Open PRs awaiting human merge (2026-04-16):**
- Pi-Dev-Ops #17–32 — Security hardening (RA-1003–1032), compound-engineering features, Routine prototype
- CARSI #17 — GP-311–319 security hardening
- Synthex #59 SYN-695, #60 SYN-696/697, #61 SYN-698–703

**Developer actions required:**
- Merge all open PRs above
- Register SYN-694 Routine in Claude Code (see `.harness/routines/SYN-694-deploy-verify.md`)

**Open as of 2026-04-20:**
- `ENABLE_PROMPT_CACHING_1H=1` — RA-1009 code merged, Railway env var status could not be verified by this audit (Railway CLI unauthorized); leave on checklist until someone with Railway access confirms.

**Completed (2026-04-16):**
- RA-1003–1032: Security + compound-engineering sprint (PRs #17–32) ✓
- GP-311–319: CARSI security hardening (CARSI PR #17) ✓
- SYN-694–703: Synthex security hardening (Synthex PRs #59–61) ✓
- RA-1010: Claude Code Routines evaluation complete (`.harness/RA-1010-routines-eval.md`) ✓
- SYN-694: Deploy-verify Routine prototype (`.harness/routines/`) ✓
- RA-981: Pi-SEO false positive closed (backend confirmed live) ✓

## Pi-CEO Session Pipeline — Hardwired Lessons (2026-04-17 marathon)

14 PRs merged in one session closed the autonomous pipeline end-to-end. Each rule below maps to a real bug that broke silently in production. Do not regress.

### Planner / Generator SDK (RA-1169 to RA-1178)

| Rule | Why |
|------|-----|
| `parse_event` must `isinstance(evt, dict)` after `json.loads` | `json.loads('"hello"')` returns a str; the next `.get(...)` crashes the whole phase |
| Wrap SDK stream in `asyncio.wait_for(..., timeout=timeout)` | The SDK has no built-in stream timeout; infinite hangs were the default failure mode |
| Use top-level `claude_agent_sdk.query()`, not `ClaudeSDKClient` | SDK issue #576: `ClaudeSDKClient` silently hangs when reused across FastAPI tasks (queue ownership lost) |
| Pass `permission_mode='bypassPermissions'` to `ClaudeAgentOptions` | Without it, Claude emits prose "waiting for permission" and produces empty diffs |
| Verify clone origin matches `session.repo_url` + plant stub `CLAUDE.md` at workspace root | Prevents Claude's upward search from inheriting the Pi-CEO `CLAUDE.md` when the workspace is inside the Pi-CEO tree |
| `TAO_WORKSPACE` must live OUTSIDE any parent git repo (e.g. `/tmp/pi-ceo-workspaces`) | Otherwise git commands use the outer `.git` context, pushing to the wrong remote |
| Generator timeout scales by tier: basic 300 s, detailed 600 s, advanced 900 s | Full-feature briefs need 5-15 min of real Claude work |
| Plan phase uses Sonnet for ALL tiers (Haiku retired) | Haiku produces 5 % confidence plans, times out at 45 s, or returns prose refusals on ambiguous briefs. Claude Max cost = `$0.0000` regardless, so no cost argument |
| Planning prompt must force JSON-only output (first char `{`, last char `}`, no prose, assume on ambiguity) | Sonnet otherwise asks for clarification and breaks JSON parse |
| Pre-pop `ANTHROPIC_API_KEY` from env if empty-string | Empty string is NOT "unset" — SDK treats `""` as "API key mode, key is empty" and fails auth |

### Push layer (RA-1182 to RA-1184)

| Rule | Why |
|------|-----|
| Webhook handler skips refs containing `pidev/` and repo-url `CleanExpo/Pi-Dev-Ops` | Prevents recursive self-modification (43 zombie branches cleanup 2026-04-17) |
| After successful push with a real diff, auto-open a PR via GitHub REST | Closes the loop; the branch alone isn't an action the user can merge |
| Auto-open Linear ticket in the TARGET repo's project (per `.harness/projects.json`) | `linear_team_id` + `linear_project_id` mapped per repo; tickets land on the right kanban |
| `session.workspace = f"{TAO_WORKSPACE}/{session.id}"` — isolation by UUID | Full path is outside the harness tree; git operations see only the cloned repo |

### Dashboard UX (RA-1181)

| Rule | Why |
|------|-----|
| SSE drops must be re-framed as "reconnecting" not "disconnected" — poll `/api/sessions` as source of truth | SSE streams drop often through Vercel's 10 s proxy; the session continues server-side |
| Completion shows a green ✅ **Complete** banner with score + files-modified + branch name + "Fix next ↗" CTA | Silent-success is indistinguishable from a placeholder (RA-1109) |
| Active-build strip polls every 4 s regardless of SSE health | Single source of truth for "what's running" |

### Model Routing vs Plan Phase

The plan phase uses role `planner` which is allow-listed for Opus per RA-1099. We use **Sonnet** for plan because Opus would exceed budget on trivial briefs and Sonnet is reliable enough. This is intentional — do not downgrade plan to Haiku again.

### Linear-routing reference

`.harness/projects.json` is the canonical map. When Pi-CEO creates a ticket from a session, use the repo-name match (case-insensitive, last path segment) to find `linear_team_id` + `linear_project_id`. Current portfolio mapping:

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

---

## Senior-Agent Topology (Wave 4 Phase A — RA-1858, 2026-05-02)

Four senior-agent bots run inside the orchestrator main loop alongside the existing Guardian / Builder / Click / Scribe / CoS bots. Each bot owns one slice of daily executive visibility plus a dual-key approval gate.

| Bot | Module | Skill | Owns | Dual-key gate |
|---|---|---|---|---|
| CFO | `swarm/bots/cfo.py` (engine `swarm/cfo.py`) | `skills/cfo/SKILL.md` | Burn / NRR / GM / runway / model-spend ratio | Spend > $1,000 |
| CMO | `swarm/bots/cmo.py` (engine `swarm/cmo.py`) | `skills/cmo-growth/SKILL.md` | LTV:CAC / blended CPA / channel HHI / attr decay | Ad-spend > $5,000/day |
| CTO | `swarm/bots/cto.py` (engine `swarm/cto.py`) | `skills/cto/SKILL.md` | DORA quartet + p99 + uptime + cost-per-request | Production PR merge |
| CS | `swarm/bots/cs.py` (engine `swarm/cs.py`) | `skills/cs-tier1/SKILL.md` | NPS / FCR / GRR / first-response / enterprise threats | Refund > $100 |

Each bot follows the same shape: pure-Python engine (compute / detect_breaches / assemble_daily_brief / approve_<action>) + thin bot wrapper (run_cycle gating on `TAO_SWARM_ENABLED` + kill-switch) + jsonl ledger at `.harness/swarm/<bot>_state.jsonl` + per-bot daily-fire window (default 06:00 UTC).

### Pluggable provider envs

All four bots default to a deterministic synthetic provider seeded from `.harness/projects.json` so the orchestrator's daily-fire window is non-empty from day 0. Flip to real-data via env:

| Env var | Values | Status |
|---|---|---|
| `TAO_CFO_PROVIDER` | `synthetic` (default) \| `stripe_xero` | Stripe MRR + Xero cash/COGS/revenue real; rest synthetic |
| `TAO_CMO_PROVIDER` | `synthetic` (default) \| `ad_platforms` | `ad_platforms` is stub — falls back to synthetic with warning |
| `TAO_CTO_PROVIDER` | `synthetic` (default) \| `github_actions` | `github_actions` is stub — falls back to synthetic with warning |
| `TAO_CS_PROVIDER` | `synthetic` (default) \| `zendesk` \| `intercom` | both stubs — fall back to synthetic with warning |

Per-bot dual-key ceiling overrides:
- `TAO_CFO_SPEND_CEILING` (default `1000`)
- `TAO_CMO_ADSPEND_CEILING` (default `5000`)
- `TAO_CS_REFUND_CEILING` (default `100`)

Stripe-Xero specific:
- `STRIPE_API_KEY` — required when `TAO_CFO_PROVIDER=stripe_xero`
- `STRIPE_ACCOUNT_<BID>` — optional Stripe Connect account per business (`<BID>` = projects.json id uppercased, non-alpha → `_`)
- `XERO_ACCESS_TOKEN` — current OAuth bearer (refresh sidecar required for production; tokens expire in 30 min)
- `XERO_TENANT_<BID>` — required to pull Xero data for that business

### Multi-agent debate scaffold (RA-1867)

`swarm/debate_runner.py` runs a drafter + adversarial red-team in parallel via `asyncio.gather` over the existing Claude Agent SDK. Both go through `model_policy.select_model` so neither leaks into Opus (the opus allowlist is preserved). On success, a Hermes Kanban card is emitted via `swarm/kanban_adapter.py` so the founder sees the debate without Telegram noise. Mid-debate `/panic` cancels the gather and persists `debate_aborted`.

### Daily 6-pager (RA-1863)

`swarm/six_pager.py` composes a Stripe-style executive page from the four senior-bot jsonl ledgers + latest Margot insight + RA-1842 status. Pure file-read composition — no SDK or external API calls.

`swarm/six_pager_dispatcher.py` owns the side effects: PII redact → optional voice variant via `swarm/voice_compose.py` → `draft_review.post_draft` HITL → audit emit. Fired by the orchestrator main loop when the daily window opens (default 06:00 UTC).

Voice variant requires `ELEVENLABS_API_KEY` (and optional `ELEVENLABS_VOICE_ID`); without it the dispatcher gracefully sends text-only.

### Cycle order in `swarm/orchestrator.py`

1. Guardian (veto)
2. Builder, Click, Scribe (each self-gates on `SHADOW_MODE`)
3. Chief of Staff (Telegram intent routing)
4. CFO → CMO → CTO → CS (each self-gates on `TAO_SWARM_ENABLED` + kill-switch)
5. 6-pager dispatcher (fires only inside the daily window with 23h debounce)
6. Daily report

Adding a new senior agent? Mirror the cfo.py shape: engine + bot wrapper + skill + provider stub + audit type whitelist. Wire-in is one `try/except` block in `orchestrator.run()`.

---

## Content Rules

- No first-person business language (We/Our/I/Us/My)
- No AI filler words (delve, tapestry, landscape, leverage, robust, seamless, elevate)
- Every paragraph answers a specific question
