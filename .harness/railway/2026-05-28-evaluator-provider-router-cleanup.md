# Evaluator provider-router cleanup — 2026-05-28

Scope: remove legacy Anthropic-first evaluator/persona calls after production model switch to OpenRouter `~moonshotai/kimi-latest`.

Files changed:
- `app/server/session_evaluator.py`
- `tests/test_model_policy_evaluator.py`

Code cleanup:
- Removed direct `_run_claude_via_sdk` import/use from `session_evaluator.py` evaluator paths.
- Reworked `_run_single_eval(...)` to call `provider_router.run_via_provider(role="evaluator")`.
- Reworked `_run_eval_with_cache(...)` to keep its backward-compatible name but route through `run_via_provider(role="evaluator")` instead of direct Anthropic Messages API/prompt-cache calls.
- Reworked persona review calls to use `run_via_provider(role="evaluator", task_class="persona-...")` instead of `anthropic.AsyncAnthropic`.
- Removed API-key-gated Anthropic skip behavior from persona review; configured provider decides availability now.
- Updated evaluator module comments/docstrings to reflect provider-routed behavior.

Test coverage added/updated:
- `_run_single_eval` uses provider router with role `evaluator` and task class `single-sonnet`.
- `_run_parallel_eval` calls provider router twice and does not call the Anthropic SDK directly.
- `_run_parallel_eval_cached` calls provider router for `cached-sonnet` and `cached-haiku`.
- `_run_persona_review` calls provider router once per persona with task classes:
  - `persona-correctness`
  - `persona-testing`
  - `persona-scope`
  - `persona-standards`

Verification:
- `uv run --frozen --with pytest --with pytest-asyncio python -m pytest tests/test_model_policy_evaluator.py -q`
  - `4 passed`
- `uv run --frozen --with pytest --with pytest-asyncio python -m pytest tests/test_model_policy_evaluator.py tests/test_provider_router.py tests/test_budget_tracker.py tests/test_budget_tracker_wired.py -q`
  - `64 passed`
- `python3 -m compileall -q app/server/session_evaluator.py`
  - `compile_ok`
- `uv run --frozen --with ruff ruff check app/server/session_evaluator.py tests/test_model_policy_evaluator.py`
  - `All checks passed!`
- `git diff --check`
  - clean
- Search in `app/server/session_evaluator.py` found no remaining direct Anthropic SDK call markers:
  - `anthropic`
  - `Anthropic`
  - `_run_claude_via_sdk`
  - `AsyncAnthropic`
  - `messages.create(`
  - `count_tokens`

Deployment note:
- This is a local code cleanup. It has not been committed, pushed, or deployed yet.
