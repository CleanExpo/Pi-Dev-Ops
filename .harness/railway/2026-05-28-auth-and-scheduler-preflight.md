# Railway auth and scheduler preflight — 2026-05-28

Scope: resume Pi-CEO Railway/Pilot scheduler lane after Railway authorization.

Verified live Railway access:
- `railway whoami`: authenticated as Phillip McGurk.
- `railway status`: project `Pi-Dev-Ops`, environment `production`, service `Pi-Dev-Ops`, status `Online`.
- Region: Southeast Asia.
- Current deployment: `4b373ec7-925e-49de-93e9-11336427b6db`, status `SUCCESS`, deployed 2026-05-27 18:33 +10:00.
- Public URL: `https://pi-dev-ops-production.up.railway.app`.
- Public `/health`: HTTP 200 `{status:"ok"}`.
- `/api/health/full`: HTTP 200, `ok=true`, deploy SHA `5483a3bb948749c87114527ea5b733524530582f`, uptime about 58k seconds at check time.
- `/api/integrations/health`: HTTP 200, `all_healthy=true`; Linear key ok, GitHub token ok, Linear poll live.
- Authenticated `/api/triggers`: HTTP 200 via session-token header generated from Railway `TAO_SESSION_SECRET` without printing secret values.

Environment/key presence, values not printed:
- `ANTHROPIC_API_KEY`: present.
- `GITHUB_TOKEN`: present.
- `LINEAR_API_KEY`: present and Linear GraphQL sample succeeded.
- `VERCEL_TOKEN`: present.
- `TAO_PASSWORD`: present.
- `TAO_SESSION_SECRET`: present.
- `TAO_AUTONOMY_ENABLED`: present.
- `TAO_SWARM_ENABLED`: present.
- `TAO_SWARM_SHADOW`: present.
- `TAO_USE_AGENT_SDK`: present.
- `PI_SEO_ACTIVE=0`, so Pi-SEO scan/monitor jobs are configured but production scan execution is paused by env gate.

Scheduler/autonomy observations:
- Autonomy poller is running and armed; recent logs show polls #179 through #191.
- Linear pulse is live: `/api/integrations/health` reported `last_poll_age_s=132` with threshold 600.
- Cron trigger set has 27 triggers.
- Scan/monitor triggers continue to tick, but skip work because `PI_SEO_ACTIVE=0`.
- `discovery-restoreassist` is intentionally disabled.
- Weekly/monthly/quarterly stale-looking triggers are mostly schedule-shaped, not necessarily broken.

Confirmed blocker:
- `plan-discovery-daily-0300` is enabled and has `last_fired_at=null`.
- Local code has no dispatcher branch for `type="plan_discovery"` in `app/server/cron_triggers.py`.
- Read-only reproduction: calling `_fire_trigger({type:"plan_discovery"})` returns `ValueError: unknown trigger type 'plan_discovery'`.
- Existing repo script `scripts/disable-plan-discovery-2026-05-11.py` documents this exact historical footgun: disable the trigger until a real `_fire_plan_discovery_trigger` handler exists.
- Production currently has the trigger enabled, so it will remain a silent/recurring scheduler defect unless either disabled again or a real handler is implemented.

Other observed risks from logs:
- Anthropic API calls currently fail with `Credit balance is too low`; eval-cache and personas fall back but this blocks/weakens LLM-backed autonomous work.
- Ollama local fallback attempts fail with connection refused in Railway; currently logged as warnings.
- Supabase insert for `gate_checks` failed HTTP 400 once; logged non-fatal.
- `record_episode` failed once with `expected string or bytes-like object, got 'dict'`; logged non-fatal.

Verification commands:
- `railway whoami` — PASS.
- `railway status` — PASS.
- `railway deployment list` — PASS; latest deployment SUCCESS.
- public `/health` — PASS HTTP 200.
- `/api/health/full` — PASS HTTP 200.
- `/api/integrations/health` — PASS HTTP 200.
- authenticated `/api/triggers` — PASS HTTP 200.
- Linear GraphQL sample via `railway run` — PASS, 20 open issue sample returned.
- `uv run --frozen --with pytest --with pytest-asyncio python -m pytest tests/test_cron_store.py tests/test_cron_catchup_ra2016.py tests/test_cron_watchdogs_ra1981.py tests/test_watchdog_health_full.py -q` — PASS, 29 tests.
- `git diff --check` — PASS.

Safety boundaries observed:
- No Railway env variables changed.
- No deployment/restart triggered.
- No production DB writes/migrations.
- No GitHub push/PR/merge.
- No secrets printed.
- One local generated ignored `.session-secret` from a local import probe was removed immediately.

Approval gates / recommended next actions:
1. Disable `plan-discovery-daily-0300` in production until a real handler exists. This is a production scheduler state mutation, so it needs explicit approval.
2. Decide whether `PI_SEO_ACTIVE` should stay `0` or be changed to `1`. Changing it is a production env mutation/restart and needs explicit approval.
3. Refill/fix Anthropic billing or switch the live provider path if autonomous LLM work must proceed; billing actions need operator action/approval.
4. If desired, implement a proper `plan_discovery` handler locally with TDD, then review before deploy.
