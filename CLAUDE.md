# Pi-Dev-Ops — Claude Code Guidance

> **Every fact below was verified against this repo on 2026-08-18 at commit `d124c6af`.**
> Each block names the command that re-derives it. If a command disagrees with the text, the
> command is right and the text is stale — fix the text in the same PR.
> Claims that cannot be re-derived by a command are marked **POLICY** and are decisions, not facts.

## Identity

- **Repo:** `CleanExpo/Pi-Dev-Ops` (`git remote -v`)
- **Canonical checkout:** `/Users/phillmcgurk/Pi-Dev-Ops` — the main worktree (`git worktree list`)
- **Aliases seen in tickets:** "Pi DevOps", "Pi-CEO Dev Ops"

Other directories matching `pi-dev-ops*` on this machine are worktrees, Hermes profile copies, or
scan output. Only the path above has the `origin` remote. Do not edit the others.

## What this repo does

Converts a GitHub repo URL plus a plain-English brief into an autonomous Claude Code session.
Generator and evaluator run through `claude_agent_sdk`. `TAO_USE_AGENT_SDK=0` raises at startup
(`app/server/config.py:291`) — the SDK path is the only supported mode.

| Layer | Tech | Location |
|-------|------|----------|
| Frontend | Next.js `^16.2.3`, React `^19.0.0`, Tailwind `4.1.9` | `dashboard/` |
| Backend | FastAPI, Python `>=3.11` (`pyproject.toml`) | `app/server/` |
| Routes | 8 modules | `app/server/routes/` |
| MCP server | Node, `@modelcontextprotocol/sdk` | `mcp/pi-ceo-server.js` |
| TAO engine | Python | `src/tao/` |
| Harness state | JSONL / JSON | `.harness/` |
| Skills | `SKILL.md` files | `skills/` |
| Database | Supabase (PostgreSQL) | `supabase/migration.sql` |
| Deploy | Vercel (FE) · Railway (BE) | `dashboard/vercel.json`, `railway.toml` |

Shared packages: `packages/brand-config/` (brand-token SSOT) and `packages/ui/` (shadcn New York
primitives, built with `tsup`). Consume via `"@unite-group/ui": "file:../packages/ui"`.

**Public contract:** `app.server.main:app` is the FastAPI instance. The Dockerfile and Railway
both reference it; `main.py` re-exports `app` from `app_factory`. Never break this import.

Re-derive: `python3 -c "import json;d=json.load(open('dashboard/package.json'));print(d['dependencies'])"`

## Setup and gates

Use `.venv/bin/python`. The machine default `python3` is 3.9.6 and **cannot import this repo** —
`config.py:321` uses `str | None`, which needs 3.10+. Commands written as bare `python` fail.

```bash
# Backend
cd app && source .env.local && ../.venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 7777
cd dashboard && npm run dev
node mcp/pi-ceo-server.js

# Gates — run in this order, first failure stops the work
.venv/bin/python -c "from app.server.main import app"   # must print a FastAPI instance
.venv/bin/python -m pytest tests/ -x -q                 # 250 test files
cd dashboard && npx tsc --noEmit && npm run build
bash scripts/handoff-loop.sh                            # full definition-of-done gate
```

### Release-gate receipts — record ONE command, not four

`pr_release_gate.py` re-runs every command recorded in the receipt's `tests` array on each push.
`scripts/handoff-loop.sh` already runs ruff, `pytest tests/` and `pytest swarm/` as its own gates
(`lint-ruff`, `tests-python`, `tests-swarm`) plus 15 more. Recording those three *alongside*
`handoff-loop.sh` runs the 75-second Python suite twice — ~140 s total, which exceeds the
2-minute tool timeout and kills the push mid-gate. Two pushes died this way on 2026-08-18.

Record exactly this, and nothing else:

```
bash scripts/handoff-loop.sh
```

It is strictly stronger than the four-command list (18 gates versus 3) and finishes inside the
timeout. Verify with `wc -l` on the receipt's `tests` array: more than one entry means the next
push will time out.

Local auth: the dashboard password defaults to `dev` when `.env.local` holds unresolved `op://`
refs. Override with `DASHBOARD_PASSWORD` in `dashboard/.env.local`. `.env.local` is gitignored —
never commit a plaintext password.

## Known broken — do not trust the old text on these

Found by direct check on 2026-08-18. Each is real and unfixed; treat as work, not as background.

| # | Defect | Evidence |
|---|---|---|
| 1 | `.harness/config.yaml` **does not exist**, yet the prior model-routing table named it as the config location for all six agent roles | `ls .harness/` |
| 2 | ~~`projects.json` repo→project lookup is ambiguous~~ — **RETRACTED, was never a defect.** `CleanExpo/Pi-Dev-Ops` legitimately carries two Linear projects (`pi-dev-ops`, `margot`). All 12 `id` values are unique and both consumers key on `id`, never `repo`. See the routing section | ids 12/12 unique |
| 3 | ~~Four `.claude/skills/*/SKILL.md` missing~~ — **FIXED 2026-08-18.** Added as symlinks to the `.agents/skills/` originals, matching the existing `skybridge` convention. Six routes now resolve | `ls -la .claude/skills/` |
| 4 | `HERMES.md` is **missing**, though it was cited as Launch Crew governance | `ls HERMES.md` |
| 5 | `app/server/routes/webhooks.py` is **1292 lines** against a documented 300-line ceiling; `mission_control.py` 406; `health.py` 302 | `wc -l app/server/routes/*.py` |
| 6 | ~~`Monorepo CI` on `main` red since 2026-08-14~~ — **RETRACTED 2026-08-30.** The claim was two weeks stale when checked: `main` had been green for many consecutive runs, and the most recent failure long predated the date the row named. The workflow's display name is also `CI`, not `Monorepo CI`. CI health rots by the hour — run the command, never trust a pasted verdict here | `gh run list --workflow ci.yml --branch main` |

Do not paste per-file line counts into this document again. They were wrong in every row of the
previous version — one claimed ~214 lines against an actual 1292. Run `wc -l` instead.

## Non-negotiables

**POLICY — Surface-treatment prohibition (RA-1109).** A feature is not shipped until the
user-visible outcome is demonstrable. HTTP 200, clean types, and green lint are not shipping.

Reject on sight: `.catch(() => {})` on a user action; a button that logs `ok` and never updates
the UI; "200 so it works" without an end-to-end click-test on the live deploy; a 3-second toast as
the only feedback for a long action; a label overstating what the action did.

Require: every write action produces an immediate UI state change or a subscribable progress
surface; anything over 2 s gets a live progress surface, not a toast; destructive actions get
confirm plus success/undo or an actionable error; spawn actions get an inline log stream or a link
to watch it. `.github/PULL_REQUEST_TEMPLATE.md` enforces a "Manual verification path".

**POLICY — Model routing (RA-1099).** Opus is reserved for `planner` and `orchestrator`. Every
other role uses Sonnet or Haiku. Enforcement lives in code, not in a config file:

- `app/server/model_policy.py` — `select_model()` downshifts opus→sonnet for non-allowed roles and
  logs to `.harness/model-policy-violations.jsonl`
- `app/server/config.py:193` — `OPUS_ALLOWED_ROLES`, overridable via `TAO_OPUS_ALLOWED_ROLES`
- `app/server/model_policy.py:153` — `assert_model_allowed()`, called at
  `app/server/session_sdk.py:234` so it raises before the wire

Never pass `model="claude-opus-*"` directly. Budget-tier escalation changes retries, threshold and
timeout — never the model. The plan phase runs on Sonnet by intent: Haiku produced 5%-confidence
plans and prose refusals. Do not regress this.

**POLICY — Evidence.** Ground every progress claim in a tool result from this session. Before
writing "done", "fixed", "green" or "verified", point at the output that proves it. Two corollaries
that have both burned this repo:

- A null result is not evidence until you have proven the check can return non-null. Run a positive
  control. Zero findings from a broken query looks exactly like zero findings from a clean system.
- Counting the shape of a thing is not measuring its contents. A permissions audit describing 96
  RLS-off tables says nothing about exposure until you count the rows in them.

## Sandbox and scope

1. **Sandbox first.** Iterate in `/tmp/` or `/tmp/pi-ceo-workspaces/` clones. Push, open a PR, or
   ship only when the current instruction says so. Otherwise stage the diff, write the PR body to a
   file, and stop.
2. **File a Linear ticket for every discovery**, routed by `config/harness/projects.json`. Never
   file findings about another repo into Pi-Dev-Ops's own project.
3. **Smoke-test before committing:** `py_compile` on edited Python, `npx tsc --noEmit` on edited TS,
   probe changed endpoints, trigger changed workflows and wait.
4. **Report failures honestly:** name the error class and source line, then file a follow-up.
   Never dress a failure as "still running" and never retry silently.
5. **Skill-injection hooks are advisory.** They fire on patterns, not task context. When off-task,
   say so in one line and ignore. Never let them drive scope creep.
6. **Finishing the requested task is the stop signal.** Report and hand back. Do not auto-chain
   into the next backlog item or open new scope without a fresh instruction.

Pause immediately for an explicit stop word, or for any decision requiring a human: branch-strategy
change, secret rotation, destructive migration, new service provisioning.

## Command surface

| Command | Purpose | Claude Code | Codex | Shared docs |
|---|---|---|---|---|
| `/judge` | Read-only challenge gate — decides *whether to build*. Scores out of 100. Never implements. | **missing** (defect 3) | `.agents/skills/judge/SKILL.md` | `.judge/` |
| `/spm` | Decision-grade spec before implementation. Read-only by default. | **missing** (defect 3) | `.agents/skills/spm/SKILL.md` | `.spm/` |
| `/session-handoff` | Gates the tree via `scripts/handoff-loop.sh`, then writes `docs/session-handoffs/handoff-<ts>.md`. Non-zero exit ⇒ write a BLOCKED handoff naming the failing gate. | **missing** (defect 3) | `.agents/skills/session-handoff/SKILL.md` | `.session-handoff/` |
| `/resume-from-handoff` | Re-runs the same gate, reconciles drift, then resumes. Verification is read-only and mandatory first. | **missing** (defect 3) | `.agents/skills/resume-from-handoff/SKILL.md` | `.resume-from-handoff/` |

`/judge` decides whether to build. `/spm` specifies what to build. `/session-handoff` records what
happened. `/resume-from-handoff` picks it back up. Distinct from `tao-judge`, which scores
loop termination, not whether work should start.

Handoff rules: never claim tests passed unless they ran; never claim something shipped without
commit/push/merge evidence; never claim a process is running without checking; always give the
next agent a first command.

## Conventions

- **Python:** snake_case, type hints on every function, `logging.getLogger()`, structured JSON via
  `_JsonFormatter`.
- **TypeScript:** strict, no `any`, named exports, interfaces over types.
- **Commits:** Conventional Commits. **Branches:** `feature/{ticket}-{desc}` or `fix/{ticket}-{desc}`.
- **Size:** functions under 40 lines, files under 300. Four files already breach this (defect 5) —
  extract when you touch them; do not add to them.
- **Security:** bcrypt passwords, parameterised queries, CSP headers, no secrets in code. Run
  `detect-secrets scan` pre-commit.
- **Content:** no first-person business voice (we/our/I/us/my), no AI filler (delve, tapestry,
  landscape, leverage, robust, seamless, elevate). Every paragraph answers a specific question.

## Operational facts worth keeping

These cost real debugging time. Each is a behaviour of an external system, not a preference.

- **`ANTHROPIC_API_KEY=""`** — the `claude` CLI exports an empty string, which children inherit and
  then fail with 401. Empty is not unset. In Python `os.environ.pop("ANTHROPIC_API_KEY", None)` when
  no explicit key is given. In Next.js `.trim()` it — Vercel appends a trailing newline.
- **`CLAUDE_CODE_OAUTH_TOKEN` fails the Claude lane guard.** `claude setup-token` mints a long-lived
  subscription token for headless use, and it is the right tool on a runner or container. It is a
  refusal on a review host: `scripts/estate/guard_claude_lane.sh:44-51` fails on the variable's
  *presence*, value never read, alongside every other override route — an env-supplied credential
  would make the check self-approving. The lane demands `claude auth status` reporting
  `authMethod == "oauth_token"` **and** `apiProvider == "firstParty"` (`:80-81`), which is an
  interactive `claude login` on the host. Never export it from a shell profile on a machine that
  runs `review_bridge.sh`. `tests/estate/test_bridge_failclosed.sh:52-58` strips it in `clean_env()`
  for the same reason. The guard cannot read plan tier (`:85-90`) — confirm Max via `/status` by eye.
- **`op://` refs** resolve only under `op run --`. `dotenv` reads them literally. Add a Pydantic
  `field_validator(mode="before")` returning `None` for strings starting with `op://`.
- **Rate limiting behind a load balancer** — on Railway/Render/Fly, `request.client.host` is the
  LB's internal IP so per-IP buckets never fill. Trust `X-Forwarded-For` when `_IS_CLOUD`; use
  `request.client.host` locally to avoid spoofing.
- **`asyncio` do-while** — `while True: await sleep(interval)` delays the first run by a full
  interval after restart. Use a short `startup_delay` and log every skipped poll.
- **Cron trigger reset** — `config/harness/cron-triggers.json` `last_fired_at` reverts to committed values on
  Railway redeploy. Use `abs()` in the debounce check and fire overdue triggers within 10 s of boot.
- **Anthropic docs redirects** — `docs.claude.com` → `platform.claude.com`/`code.claude.com`. Any
  `httpx` fetcher needs `follow_redirects=True`.
- **`_sessions` is in-memory.** Persist status to disk after every state change: write to `.tmp`
  then `os.replace()`. Terminal states are GC'd after `TAO_GC_MAX_AGE` seconds
  (`config.py:230`, default `14400` = 4 h).
- **Path traversal** — `_safe_sid()` (`app/server/persistence.py:28`) strips non-alphanumerics from
  session IDs before any file-path use. **Webhook HMAC** — `hmac.compare_digest()` for GitHub and
  Linear signatures. The `pidev/` skip is at `app/server/routes/webhooks.py:187`.
- **Recursive self-modification guard** — the webhook handler skips refs containing `pidev/` when
  the repo is `CleanExpo/Pi-Dev-Ops`. Removing this produced 43 zombie branches on 2026-04-17.
- **Workspace isolation** — `TAO_WORKSPACE` must live outside any parent git repo (e.g.
  `/tmp/pi-ceo-workspaces`), or git uses the outer `.git` and pushes to the wrong remote. Plant a
  stub `CLAUDE.md` at the workspace root so Claude's upward search cannot inherit this file.

## Observability

`app/server/supabase_log.py` is the single write path for server-side Supabase events. All writes
are fire-and-forget — observability failures must never block the pipeline.

Adding a logger means adding the matching idempotent `CREATE TABLE IF NOT EXISTS` to
`supabase/migration.sql` in the same PR. Re-derive the current table set with:

```bash
grep -oiE 'create table (if not exists )?[a-z_."]+' supabase/migration.sql | sort -u
```

Do not maintain a hand-written table list here. The previous version carried one that disagreed
with the migration file in both directions.

## Autonomy and kill switches

`app/server/autonomy.py` polls Linear for Urgent/High Todo issues and creates sessions, every
`TAO_AUTONOMY_POLL_INTERVAL` seconds (`autonomy.py:803`, default `300` = 5 min). In-Progress issues
are invisible to it — reset to Todo to restart a stalled session.

Three abort axes apply to every TAO loop (`app/server/kill_switch.py`):

| Axis | Env | Default |
|---|---|---|
| Iterations | `TAO_MAX_ITERS` | 25 |
| Cost | `TAO_MAX_COST_USD` | 5.00 |
| Hard stop | `TAO_HARD_STOP_FILE` | `~/.claude/HARD_STOP` — `touch` it to drain in-flight loops without a restart |

Master switch: `TAO_AUTONOMY_ENABLED=0`. Distinct from `swarm/kill_switch.py`, which is a per-bot
`/panic` flag.

`/health` must surface real state: whether the loop will fire next tick, the timestamp of the last
successful tick, and `linear_api_key: bool` — without the key `autonomy.py` skips every poll while
`/health` still returns 200.

**Always-on means Railway + Vercel + GitHub Actions only.** If a step needs a Mac awake or a local
process, it is not autonomous.

## Linear routing

`config/harness/projects.json` is canonical. **Route on `id`, never on `repo`.** `id` is unique
across all 12 entries; `repo` is not — `CleanExpo/Pi-Dev-Ops` deliberately carries two Linear
projects (`pi-dev-ops` and `margot`), so a repo-keyed lookup would silently pick one. This is
already how the code works, and it is correct:

- `mcp/pi-ceo-server.js:313` — `resolveProjectRouting()` matches `p.id === project_key`
- `app/server/autonomy.py:82` — the poller iterates every entry, so both projects get polled

The previous version of this file described the lookup as repo-keyed. It never was.

Primary team/project for this repo: team `a8a52f07-63cf-4ece-9ad2-3e3bd3c15673`, project
`f45212be-3259-4bfb-89b1-54c122c939a7`. Ticket format `RA-xxx`.

Re-derive the full table:

```bash
python3 -c "import json;[print(f\"{p['id']:<22}{p['repo']:<38}{p.get('linear_project_id')}\") for p in json.load(open('config/harness/projects.json'))['projects']]"
```

**PR versus ticket:** discovered during smoke, audit or review → ticket. In scope for the session's
stated goal, or launch-critical → PR. When in doubt, ticket.

## Sub-agent doctrine

Keep one warm, named specialist per domain per session and resume it for follow-ups rather than
re-spawning. The main thread coordinates; noisy collection (grep sweeps, bulk reads, web fan-out)
goes to throwaway children that return distilled verdicts. Standing specialists here:
`backend-pi-fastapi`, `ops-railway-pi`. Names freeze at spawn and must still be accurate at
resume #8. A domain change means a fresh agent, always.

## Keeping this file honest

This document was rewritten on 2026-08-18 after an audit found twelve false claims in it, including
a wrong canonical path, a table of twelve file line-counts where eleven were wrong, and four
documented command routes pointing at files that do not exist. The failure mode was accumulation:
each session appended without re-checking what was already there.

Rules that prevent the recurrence:

1. **No fact without a re-derivation command.** If it cannot be checked by a command, mark it POLICY.
2. **No copied measurements.** Line counts, table lists and version numbers rot within days. Name
   the command instead of pasting its output.
3. **Delete on contradiction.** If a check disagrees with this file, fix the file in that same PR.
   Leaving both is how the whisper stack forms.
4. **Append only after reading.** New sections must be checked against existing ones for duplication.
