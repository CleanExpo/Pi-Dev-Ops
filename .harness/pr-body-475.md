## Summary

- **UNI-2236 phase 2 (schema):** Replace incompatible `tenant_id` `social_posts` migration with additive columns (`metadata`, `eeat_score`, `geo_score`) on the unite-group table. Bridge now writes `founder_id` from `TAO_FOUNDER_USER_ID` / `FOUNDER_USER_ID` so Unite-Hub `social-publisher` cron can drain rows.
- **RA-6890:** Login password field gets `id`/`name`/`autoComplete`; settings + build form fields named; hero wordmark hidden in login mode (fixes double-render bleed); ActionsPanel labels bumped 8–9px → 10px.
- **RA-6889 tail:** `ResultCards`, `Toast`, `progress` use brand tokens / CSS vars.

## Context

Unite-Group (`apps/web`) already ships `/api/cron/social-publisher` and `/api/cron/content-engine`. The gap was Pi-CEO inserting rows with `tenant_id` instead of `founder_id`, invisible to the publisher filter.

## Ops (before first live bridge run)

1. Apply `supabase/migrations/20260702100000_marketing_bridge.sql` to shared Supabase
2. Set `TAO_FOUNDER_USER_ID` on Railway (same UUID as Unite-Hub `FOUNDER_USER_ID`)
3. `python scripts/run_marketing_bridge.py`

## Test plan

- [x] `python -m pytest tests/test_marketing_skill_bridge.py -q`
- [x] `cd dashboard && npx tsc --noEmit`
- [ ] Apply migration + run bridge with founder env set → row visible to social-publisher query
- [ ] Login page: no faded duplicate wordmark when entering password
- [ ] DevTools: form fields report id/name on login + settings
