# Pi CEO Analysis — Pi-Dev-Ops

Branch: `pidev/analysis-20260407`
Date: 2026-04-07

## Tech Stack
Python 3.11+, FastAPI, Uvicorn, WebSockets, Next.js 16, React 19, TypeScript, Tailwind CSS, Claude Max (Opus 4.6 / Sonnet 4.6 / Haiku 4.5), @anthropic-ai/sdk, @octokit/rest, Node.js 20, Docker

## Quality Scores
| Dimension | Score |
|-----------|-------|
| Completeness | 7/10 |
| Correctness | 6/10 |
| Code Quality | 5/10 |
| Documentation | 7/10 |

## ZTE Maturity
Level 2 — Score: 36/60

## Sprint Plan
### Sprint 1: Stability & Persistence Foundation (5d)
- [S] Session persistence: write _sessions to .harness/sessions.json on state change, load on startup
- [S] Rate-limit memory fix: background task evicts IPs not seen in >5min from _req_log in auth.py
- [S] Workspace GC: schedule shutil.rmtree after 24h TTL on session complete/failed in sessions.py
- [S] Fix af variable scope bug in sessions.py run_build() summary block (af referenced before assignment)
- [S] Seed .harness/lessons.jsonl with first agent-expert entries from this analysis run
- [S] Pin SESSION_SECRET to env var with startup warning if auto-generated (prevents session invalidation on restart)

### Sprint 2: Quality Gating & Evaluator Tier (5d)
- [M] Add evaluator tier: second claude -p eval pass post-build using tier-evaluator skill (4 dimensions)
- [M] Structured brief intake form: classify intent (feature/bug/chore/spike/hotfix) before /api/build
- [S] Route classified brief to corresponding ADW template from agent-workflow skill
- [M] Implement src/tao/skills.py skill loader: parse SKILL.md frontmatter, expose registry for prompt injection
- [S] Emit structured pass/fail event over WebSocket after evaluator tier completes

### Sprint 3: Trigger Automation & Webhook Layer (5d)
- [M] POST /api/webhook: accept HMAC-signed GitHub webhook, parse push/PR events, auto-create build session
- [M] PITER intent classifier: map webhook event type to ADW template (feature/bugfix/chore)
- [M] Linear webhook support: parse issue created/updated events → brief generation
- [S] Cron trigger: scheduled analysis runs via POST /api/build with stored repo config
- [S] Add /api/capabilities endpoint (self-describing API per agentic-layer skill)

### Sprint 4: Knowledge Retention & ZTE Level 2 (5d)
- [M] agent-expert Act-Learn-Reuse: extract lessons after each build, append to .harness/lessons.jsonl
- [M] Inject top-5 relevant lessons into claude -p spec prompt at build start
- [S] Record leverage-audit.md baseline score per repo in .harness/ after each run
- [S] MCP server: add get_zte_score tool to read leverage-audit.md score trend over time
- [S] Auto-update .harness/handoff.md with session outcome, next recommended action, ZTE delta
- [S] ZTE Level 2 gate: validate webhooks + auto-brief working before declaring L2 promotion

### Sprint 5: Multi-Session Orchestration & TAO Engine (7d)
- [L] Implement src/tao/agents/__init__.py: TierAgent base class, dispatch to claude subprocess per tier
- [L] Fan-out orchestration: decompose brief into N parallel worker sessions via tier-orchestrator pattern
- [M] Session tree persistence: replace flat _sessions dict with parent→child tree for orchestrator→specialist→worker
- [M] Merge results via Opus evaluator after parallel worker fan-out completes
- [M] Context-compressor integration: truncate/extract/summarize at tier boundaries before passing to child
- [S] BudgetTracker integration: enforce token_budget_pct per tier from 3-tier-webapp.yaml template
