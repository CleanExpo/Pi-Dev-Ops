# Evaluator provider-router cleanup shipped — 2026-05-28

Repository: CleanExpo/Pi-Dev-Ops

PR:
- URL: https://github.com/CleanExpo/Pi-Dev-Ops/pull/302
- State: MERGED
- Merge commit: 585bb3ebb2fc485971d936bcee626d00646ba70f
- Branch: refactor/evaluator-provider-router-cleanup

Commit:
- a6e968da5d1c1efcc9667357b64ebb869420e7c5 — refactor: route evaluator through provider router

Included files:
- app/server/session_evaluator.py
- tests/test_model_policy_evaluator.py

PR checks:
- Python (pytest + ruff): SUCCESS
- Validate .claude/DESIGN.md: SUCCESS
- Pi CEO API smoke test (28 checks): SUCCESS
- Frontend (tsc + eslint + build): SUCCESS
- Secrets exposure scan: SUCCESS
- CodeRabbit: SUCCESS
- Railway PR deployment: SUCCESS
- Vercel pi-dev-ops: SUCCESS
- Vercel archive dashboard: SUCCESS
- Vercel pi-dev-ops-sandbox: FAILURE, known/non-production project-config status context

Production deployment:
- Railway latest deployment: 37d15e4b-04fc-4588-a7da-e1dcf146abbe
- Railway status: SUCCESS
- Production URL: https://pi-dev-ops-production.up.railway.app
- Live /api/health/full deploy_sha: 5069326f9961ffcdcf4376beef9bf73f05637a38
  - This is origin/main after the PR merge plus an automatic docs(wiki) refresh commit.

Production health verification:
- /health: HTTP 200, {"status":"ok"}
- /api/health/full: HTTP 200, ok=true
- /api/integrations/health: HTTP 200, all_healthy=true

Runtime model routing verification via Railway env:
- evaluator -> openrouter ~moonshotai/kimi-latest env_role_override
- generator -> openrouter ~moonshotai/kimi-latest env_role_override
- planner -> openrouter ~moonshotai/kimi-latest env_role_override
- orchestrator -> openrouter ~moonshotai/kimi-latest env_role_override
- margot.synthesis -> openrouter ~moonshotai/kimi-latest env_role_override
- realtime_lookup -> openrouter ~moonshotai/kimi-latest env_role_override

Log sample after deploy:
- OpenRouter request observed with HTTP 200.
- No new Anthropic credit-balance line observed in the filtered post-deploy log sample.
- Existing Ollama fallback warning remains non-fatal.

Local state note:
- main fast-forwarded to origin/main.
- Untracked local directories/files remain unrelated and were not committed.
