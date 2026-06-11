# OpenRouter/Kimi model switch — 2026-05-28

Scope: respond to operator instruction to use OpenRouter model `~moonshotai/kimi-latest` after Anthropic API credit failures in Pi-Dev-Ops production logs.

Changes made in Railway production env for service `Pi-Dev-Ops`:
- `TAO_CHEAP_PROVIDER=openrouter`
- `TAO_CHEAP_REMOTE_MODEL=~moonshotai/kimi-latest`
- `TAO_MODEL_EVALUATOR=openrouter:~moonshotai/kimi-latest`
- `TAO_MODEL_GENERATOR=openrouter:~moonshotai/kimi-latest`
- `TAO_MODEL_SENIOR_BRIEF=openrouter:~moonshotai/kimi-latest`
- `TAO_MODEL_PLANNER=openrouter:~moonshotai/kimi-latest`
- `TAO_MODEL_ORCHESTRATOR=openrouter:~moonshotai/kimi-latest`
- `TAO_MODEL_BOARD=openrouter:~moonshotai/kimi-latest`
- `TAO_MODEL_PORTFOLIO_SYNTHESIS=openrouter:~moonshotai/kimi-latest`
- `TAO_MODEL_MARGOT_SYNTHESIS=openrouter:~moonshotai/kimi-latest`
- `TAO_MODEL_MARGOT_TRUTH_CHECK=openrouter:~moonshotai/kimi-latest`
- `TAO_MODEL_REALTIME_LOOKUP=openrouter:~moonshotai/kimi-latest`
- `TAO_MODEL_RESEARCH_REALTIME=openrouter:~moonshotai/kimi-latest`

Notes:
- The actual OpenRouter model ID includes the leading tilde: `~moonshotai/kimi-latest`.
- A direct OpenRouter API probe without the tilde (`moonshotai/kimi-latest`) returned HTTP 400 invalid model ID.
- A direct OpenRouter API probe with the tilde succeeded and OpenRouter resolved it to `moonshotai/kimi-k2.6-20260420`.
- `OPENROUTER_API_KEY` was already present in Railway; value was not printed.
- Setting variables triggered Railway redeploys; final active deployment is healthy.

Verification:
- `railway run` selected provider/model for roles:
  - evaluator/generator/senior_brief/planner/orchestrator/board/portfolio.synthesis/margot.synthesis/margot.truth_check/realtime_lookup/research.realtime all resolve to `openrouter:~moonshotai/kimi-latest` via env role override.
  - monitor/guardian resolve to `openrouter:~moonshotai/kimi-latest` via cheap-tier default.
- Provider-router live smoke call:
  - role `evaluator`
  - selected `openrouter ~moonshotai/kimi-latest`
  - rc `0`
  - err `None`
  - response text `ok`
- Railway deployment health:
  - active deployment `42aa2492-29ae-4061-8aa1-6a48885e25f7`
  - status `SUCCESS`
  - `/health` HTTP 200
  - `/api/health/full` HTTP 200, ok=true
  - `/api/integrations/health` HTTP 200, all_healthy=true

Remaining caveat:
- Some older paths in `session_evaluator.py` still call Anthropic directly for cached evaluator/persona review before falling back. The provider-router roles now point to OpenRouter/Kimi, but a code cleanup may still be needed to remove direct Anthropic-first calls from those legacy paths.
- No secrets printed.
