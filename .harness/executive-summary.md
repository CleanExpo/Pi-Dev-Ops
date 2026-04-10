# Executive Summary

The system is operationally mature at ZTE 60/60 (Zero Touch band, all 12 leverage points at 5/5) as of Sprint 6 (2026-04-08). The FastAPI backend (app/server/) runs a 5-phase pipeline: clone → analyze → generate → evaluate → push, with 3-attempt exponential backoff on clone and push, a blocking evaluator gate (threshold 8/10, max 2 retries with critique injection), and phase-level checkpoints supporting session resume. The Next.js dashboard is live on Vercel (dashboard-unite-group.vercel.app); the backend is deployed on Railway (pi-dev-ops-production.up.railway.app). 23 skills across 5 layers are loaded and injected into briefs via PITER intent classification and ADW templates. GitHub and Linear webhooks, cron triggers, fan-out parallelism (POST /api/build/parallel), and an MCP server (v3.0.0, 11 tools) are all operational. The CI smoke test suite runs 28 checks on every push to main. Primary gap: CLAUDE.md is a near-empty stub (template placeholder text only), meaning future Claude sessions start with degraded context; this is the highest-leverage unfixed issue.

## Strengths
- ZTE 60/60 achieved — all 12 leverage points at maximum; system is genuinely autonomous from trigger to GitHub push
- Zero marginal cost — claude -p subprocess delegates all inference to Claude Max subscription, no per-token API charges
- Closed-loop evaluator with critique injection (app/server/sessions.py:~310) — retries are meaningfully differentiated, not blind repeats
- Auto-learn from evaluator: low-scoring dimensions auto-appended to lessons.jsonl and injected into future briefs (_parse_evaluator_dimensions, sessions.py:~230)
- Robust error recovery: 3-attempt clone backoff, 2-attempt generator retry, 3-attempt push backoff with auth-error hard-stop (sessions.py:~380-430)
- Phase checkpoints + session resume (POST /api/sessions/{sid}/resume) — interrupted sessions skip already-completed phases
- Strong security posture: HMAC-signed HttpOnly cookies, timing-safe comparisons, path traversal protection (_safe_sid), CSP headers, rate limiting with inline GC
- 28-check CI smoke test (.github/workflows/smoke_test.yml) validates all subsystems on every push to main
- Fan-out parallelism (POST /api/build/parallel) with opus-tier escalation on worker failure (orchestrator.py)
- MCP server v3.0.0 with 11 tools gives Claude Desktop direct read/write access to all harness state

## Weaknesses
- CLAUDE.md is an empty stub (placeholder template text only) — every future Claude session starts blind; this is the single highest-leverage unfixed gap (file: CLAUDE.md, all sections are unfilled templates)
- BudgetTracker.record() accumulates tokens but has no cost_usd() method — token spend is tracked but never converted to dollars despite token-budgeter/SKILL.md having current pricing
- src/tao/agents/__init__.py contains only a stub despite the SPRINT_4_COMPLETION.md claiming AgentDispatcher was implemented — the spec.md still marks it as ✅ Complete (RA-482) but the deployed file via _deploy.py writes it as empty
- dashboard/.env.example exposes TAO_PASSWORD in plaintext ('your-tao-password'); READY_TO_DEPLOY.md exposes live GITHUB_TOKEN, LINEAR_API_KEY, and TAO_PASSWORD values in committed markdown files
- Harness spec.md and feature_list.json reflect Sprint 3/4 state; board minutes show drift vs actual codebase — cross-session context degrades over time without a refresh trigger
- Single-worker Uvicorn (--workers 1 in Dockerfile CMD) means a long-running build blocks the event loop; concurrent sessions share one process with no isolation
- hooks-system skill: only PreToolUse and PostToolUse are wired; Stop and SubagentStop hooks are documented but not implemented

## Next Actions
1. Rotate GITHUB_TOKEN and LINEAR_API_KEY immediately — values are committed in READY_TO_DEPLOY.md (lines 43-44); delete or redact that file; regenerate both tokens
2. Populate CLAUDE.md with actual project context: architecture summary, file map (key paths from spec.md Section 7), dev setup commands, code conventions, smoke test invocation
3. Add cron trigger restore to on_startup() in app/server/main.py: call list_triggers() and re-register enabled triggers so Railway restarts don't silently drop scheduled builds
4. Move session persistence and lessons to Railway Volume or Supabase — update config.py LOG_DIR and LESSONS_FILE to point to mounted volume path
5. Add cost_usd() method to BudgetTracker (src/tao/budget/tracker.py) using pricing from token-budgeter/SKILL.md; expose spend in WebSocket stream and /api/sessions response
6. Implement ZTE self-improvement loop: scheduled agent (cron trigger, daily) reads lessons.jsonl, identifies recurring failure patterns across evaluator dimensions, and proposes targeted CLAUDE.md or skill file updates
