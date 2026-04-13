# AGENTS.md — Pi-Dev-Ops Boundary Matrix

Defines what an autonomous agent (Claude Code, Pi-CEO generator, board meeting agent) may
freely modify, must proceed with care on, or must never touch without explicit human approval.

Three tiers apply in every build session. When directories conflict, the more specific
scope wins (e.g., `app/server/config.py` → ⚠️ overrides the default ✅ for `app/server/`).

---

## Root Boundary Matrix

| Tier | Meaning |
|------|---------|
| ✅ | Modify freely — safe to add, edit, delete without extra review |
| ⚠️ | Modify with care — changes need rationale in PR description + evaluator score ≥ 8 |
| 🚫 | Do not modify — requires explicit human approval before touching |

---

## Directory Map

### ✅ Safe to modify freely

| Path | What it is |
|------|-----------|
| `app/server/agents/` | Board meeting, scout, plan discovery, feedback loop agents |
| `app/server/session_evaluator.py` | Evaluator runners — safe to tune thresholds |
| `app/server/session_phases.py` | Build phase pipeline — add/remove phases, tune prompts |
| `app/server/brief.py` | Brief parser and complexity classifier |
| `app/server/lessons.py` | Lessons JSONL reader/writer |
| `app/server/budget.py` | Budget-to-params mapping |
| `app/server/triage.py` | Pi-SEO triage logic |
| `app/server/vercel_monitor.py` | Vercel deployment monitor |
| `app/server/scanner.py` | Repo scanner |
| `dashboard/app/api/analyze/` | Analysis API route |
| `dashboard/app/api/chat/` | Chat API route |
| `dashboard/app/api/capabilities/` | Capabilities route |
| `dashboard/app/api/pi-ceo/` | Pi-CEO MCP bridge routes |
| `dashboard/components/` | React UI components |
| `dashboard/lib/` | Shared TypeScript utilities (except `supabase/`) |
| `mcp/pi-ceo-server.js` | MCP tool definitions — add tools, update tool descriptions |
| `skills/` | SKILL.md files — add skills, update guidance |
| `scripts/` | Developer utilities |
| `tests/` | Test files |
| `.harness/` | Harness state files (YAML, JSONL, Markdown docs) |

---

### ⚠️ Modify with care

These files affect runtime behaviour, auth flows, or external integrations. Changes require
a clear rationale in the PR body. Evaluator score must be ≥ 8/10 before auto-shipping.

| Path | Risk | What to check |
|------|------|---------------|
| `app/server/main.py` | FastAPI routes + startup hooks | Verify `/health`, `/sessions`, `/webhook/*` still respond |
| `app/server/sessions.py` | Session lifecycle facade | Run full pytest suite; zero import regressions |
| `app/server/session_model.py` | `BuildSession` dataclass | Field additions need `persistence.py` migration |
| `app/server/session_sdk.py` | SDK runner + metrics | Confirm `.harness/agent-sdk-metrics/` still writes |
| `app/server/session_linear.py` | Linear GraphQL sync | Verify state transitions on mock issue |
| `app/server/orchestrator.py` | Multi-session fan-out | Confirm concurrency limits enforced |
| `app/server/pipeline.py` | Sequential build pipeline | Check phase order + timeout propagation |
| `app/server/autonomy.py` | Linear poll loop | Must not break `/health` autonomy boolean |
| `app/server/cron.py` | Cron trigger handlers | Verify watchdog intervals unchanged |
| `app/server/autopr.py` | Auto PR creation | Confirm branch naming and push target |
| `app/server/gc.py` | Session garbage collection | Verify TTL logic preserved |
| `app/server/persistence.py` | Disk session save/restore | Keep atomic write-then-replace pattern |
| `app/server/supabase_log.py` | Fire-and-forget Supabase writes | All writes must remain non-blocking |
| `dashboard/app/api/sessions/` | Session management API | Validate SSE stream compatibility |
| `dashboard/app/api/settings/` | Supabase-backed settings | Keep backward-compatible response shapes |
| `dashboard/app/api/auth/` | JWT auth flow | Do not change cookie names or expiry defaults |
| `dashboard/app/api/webhook/` | Inbound webhook handlers | Verify HMAC signatures still checked |
| `dashboard/app/api/cron/` | Scheduled job routes | Keep Vercel cron header validation |
| `dashboard/lib/supabase/` | Supabase client factory | Schema changes need migration + type regen |
| `supabase/migrations/` | Database migrations | New migration per schema change; never edit existing |
| `.github/workflows/` | CI pipeline | Changes must not remove any of the three jobs |
| `railway.toml` | Railway deploy config | Never remove health check path |
| `Dockerfile` | Container build | Keep `TAO_USE_AGENT_SDK=1` ENV |

---

### 🚫 Do not modify without explicit human approval

| Path | Why |
|------|-----|
| `app/server/config.py` | Auth, secrets loading, bcrypt password hash — wrong change = locked out |
| `app/server/auth.py` | Login/session verification — any bug = full auth bypass |
| `app/data/.password-hash` | Live bcrypt hash — overwrite = locked out |
| `app/data/.session-secret` | JWT signing key — rotate only via deliberate Railway redeploy |
| `.env*` / `*.env` | Secrets — never read or write env files |
| `dashboard/middleware.ts` | Next.js auth middleware — protects every dashboard route |
| `dashboard/app/api/actions/` | Irreversible server actions (kill session, delete data) |
| `supabase/seed.sql` | Production seed data |

---

## Directory-Scoped Overrides

### `app/server/` override

```
✅ Default for all files in app/server/
⚠️ Override for: main.py, sessions.py, session_model.py, session_sdk.py,
                  session_linear.py, orchestrator.py, pipeline.py, autonomy.py,
                  cron.py, autopr.py, gc.py, persistence.py, supabase_log.py
🚫 Override for: config.py, auth.py
```

Run `python -m pytest tests/ -x -q` before committing any change to `app/server/`.

### `dashboard/app/api/` override

```
✅ Default for: analyze/, chat/, capabilities/, pi-ceo/
⚠️ Override for: sessions/, settings/, webhook/, cron/
🚫 Override for: auth/, actions/
```

Run `npx tsc --noEmit && npm run build` before committing any change to `dashboard/`.

---

## Autonomy Behaviour Rules

1. **Never auto-ship a 🚫-tier change.** If a brief requires touching a 🚫 file, stop the
   session, post a Telegram alert, and move the Linear issue to "Blocked".

2. **⚠️-tier changes must pass the evaluator at ≥ 8/10** before `_phase_push()` fires.
   If the score is < 8, retry up to `max_retries` times, then escalate to Telegram.

3. **File count ceiling.** The default scope contract (`max_files_modified: 5`) applies
   to all auto-triggered sessions. Violations trigger a Telegram alert + scope gate.

4. **Test gate.** `run_cmd(["python", "-m", "pytest", "tests/", "-x", "-q"])` must exit 0
   before any push. If tests fail after generation, classify the failure and attempt one
   targeted repair before escalating.

5. **No credentials in generated code.** Any snippet containing `sk-`, `lin_api_`,
   `SUPABASE_`, `postgres://`, or `Bearer ` (token patterns) must be rejected by the
   evaluator with a mandatory flag comment.

---

## Source

Patterns adapted from Codex four-file task memory (PROMPT/PLAN/IMPLEMENT/STATUS.md),
Kimi K2 minimal tool set philosophy (6 orthogonal tools > 20 overlapping), and
DeepSeek R1 structured reasoning seeding.

Last updated: 2026-04-14 (RA-935)
