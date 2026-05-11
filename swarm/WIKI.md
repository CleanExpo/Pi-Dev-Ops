# swarm — Wiki

_Last updated: 2026-05-11T11:08:31Z (commits c94c72a..f379782)_

## Recent changes
- f379782 — Merge pull request #212 from CleanExpo/feat/sprinkle-pulse-gemma4-2026-05-11

## Operator knobs

### `TAO_SWARM_MAX_DAILY_PRS` — Builder daily PR cap (RA-3019)

Max autonomous PRs the Builder may open per UTC day.

- **Default:** `3`
- **Source:** `swarm/config.py:MAX_AUTONOMOUS_PRS_PER_DAY`
- **Enforced cap:** `swarm/config.py:effective_max_daily_prs()` — auto-clamps to `SAFE_FALLBACK_MAX_DAILY_PRS=3` regardless of env override until `.harness/swarm/green_merge_counter.json` shows `consecutive_green >= 20`. Once the threshold is met, the env override applies fully.
- **Inspect live state:** `GET /api/swarm/status` returns `pr_quota: {used, limit, env_override, date, clamped}`.
- **Adjust:** `scripts/raise_pr_cap.sh <N>` sets the env var on Railway and redeploys. Add `--dry-run` to preview, `--show` to query the current value.
- **Recommended progression (post-threshold):** `3 → 5 → 8 → 12`, holding each rung until evaluator-pass-rate sustains for ≥7d.
- **Why the auto-clamp:** any single revert or red CI after merge resets `consecutive_green` to `0`, automatically returning the cap to `3` on the next cycle. Removes the need for a human to remember to lower it after a bad merge.

Not logged in · Please run /login
