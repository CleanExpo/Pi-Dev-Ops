# Executive Summary

Functional but fragile. The core loop (clone → claude -p → WebSocket stream → push) works end-to-end. The Next.js dashboard (Vercel) runs 8 structured analysis phases with SSE streaming and pushes .harness/ artefacts to a PR branch. The FastAPI backend handles auth, sessions, and subprocess management with solid security headers and HMAC tokens. However, the system sits at ZTE Level 1 (Leverage Score 35/60 — Assisted band, one point below Autonomous). Five leverage points score 2/5: Error Recovery, Session Continuity, Quality Gating, Trigger Automation, and Knowledge Retention. The src/tao/agents/__init__.py engine is an empty stub — all intelligence delegates to the CLI subprocess. Session state is in-memory only (lost on restart). No evaluator tier runs post-build. The _req_log rate-limit dict has an unbounded memory leak. No workspace garbage collection. The .harness/lessons.jsonl agent-expert knowledge base is missing.

## Strengths
- Zero API cost architecture: shells out to claude CLI inside Claude Max subscription — $0/token regardless of session length.
- Clean security posture: HMAC-signed tokens, HttpOnly cookies, CSP headers, timing-safe password comparison, rate limiting — all implemented correctly in app/server/auth.py.
- Dual-mode execution: ANALYSIS_MODE env var switches between CLI (Max plan) and SDK (API key) without code changes — smart escape hatch.
- 23 well-defined skills across 4 layers give the system a coherent methodology vocabulary that is already embedded in phase prompts and MCP tools.
- MCP server (mcp/pi-ceo-server.js) provides first-class Claude Desktop integration — board notes, sprint plans, and ZTE scores available via natural language in Cowork.
- Live SSE streaming dashboard with phase tracker, result cards, and actions panel gives real-time visibility that most agentic tools lack.
- scripts/analyze.sh provides a zero-dependency CLI fallback — full 8-phase analysis without the browser UI.

## Weaknesses
- In-memory sessions (app/server/sessions.py _sessions dict): any backend restart wipes all active and historical session state — no persistence layer exists.
- src/tao/agents/__init__.py is empty: the Python orchestration engine is scaffolding only — no multi-tier fan-out, no evaluator pass, no skill injection at runtime.
- Rate-limit memory leak: _req_log in app/server/auth.py appends IP timestamps forever with no eviction — leaks unboundedly under load.
- No workspace garbage collection: app/workspaces/ accumulates every cloned repo indefinitely — disk exhaustion risk on long-running instances.
- No evaluator tier in the build flow: claude output is never graded before the push step — Quality Gating scores 2/5.
- .harness/lessons.jsonl missing: the agent-expert Act-Learn-Reuse cycle cannot activate — Knowledge Retention scores 2/5.
- SESSION_SECRET regenerates on restart if not set via env — invalidates all active sessions silently.
- dashboard/.env.example only documents NEXT_PUBLIC_API_URL — ANALYSIS_MODE, ANTHROPIC_API_KEY, GITHUB_TOKEN, TELEGRAM_BOT_TOKEN are absent, making first-time setup error-prone.
- ceo-mode skill is missing from the tao-skills master index (skills/tao-skills/SKILL.md lists only 21 skills, not 23).

## Next Actions
1. Implement session persistence: write _sessions to .harness/sessions.json on every state change, load on startup in app/server/sessions.py.
2. Fix rate-limit memory leak: add asyncio background task in app/server/auth.py to evict IPs not seen in >5 minutes from _req_log.
3. Add workspace GC: on session status='complete' or 'failed', schedule shutil.rmtree of session.workspace after 24h TTL.
4. Seed .harness/lessons.jsonl with lessons extracted from this analysis run, and wire app/server/sessions.py to inject top-5 relevant lessons into every build brief.
5. Add evaluator tier post-build: after claude -p completes in run_build(), spawn a second claude -p eval pass using tier-evaluator dimensions. Gate git push on evaluator PASS.
6. Implement POST /api/webhook with GitHub/Linear signature verification, event-to-ADW mapping, and automatic session creation.
7. Update dashboard/.env.example to document all required env vars (ANALYSIS_MODE, ANTHROPIC_API_KEY, GITHUB_TOKEN, TELEGRAM_BOT_TOKEN) and add them to CLAUDE.md onboarding steps.
