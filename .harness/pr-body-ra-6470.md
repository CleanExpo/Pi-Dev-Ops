## Summary

- Add RA-6470 phase-1 OpenRouter enforcement to `swarm/model_router.py`: `TAO_OPENROUTER_ENFORCE` (default off) and `TAO_OPENROUTER_ALLOWED_ROLES` (default remedial/sub-agent roles).
- `get_client(tier, role=…)` strips OpenRouter from provider ladders when enforce is on and the role is not allowlisted; `generator` and `evaluator` are blocked by default.
- Fleet optimizer recommendations log at debug when `role` is passed; `scripts/fleet_value_dryrun.py --json` unchanged (utilisation JSON verified).
- No Hermes config changes.

## Test plan

- [x] `python -m pytest tests/swarm/test_model_router.py -q` — 27 passed
- [x] `python scripts/fleet_value_dryrun.py --json` — emits `dry_run`, `utilization`, `routing_table`
- [x] `python -m py_compile swarm/model_router.py`
- [ ] With `TAO_OPENROUTER_ENFORCE=1`, confirm generator session uses Anthropic-only ladder (manual smoke when wired to session_sdk)

## Env (opt-in only)

| Var | Default | Effect |
|-----|---------|--------|
| `TAO_OPENROUTER_ENFORCE` | off | When `1`/`true`/`yes`, restrict OpenRouter to allowlisted roles |
| `TAO_OPENROUTER_ALLOWED_ROLES` | `margot.casual,research,sub_agent,remedial` | Comma-separated roles permitted OpenRouter when enforce is on |
