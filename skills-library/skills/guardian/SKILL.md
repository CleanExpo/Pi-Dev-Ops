---
name: guardian
description: Use when changing, installing or debugging the Mini's site, PR and Jev-spend watchers, the live ~/.claude drift alarm (guardian-watcher, jev-cap-watcher, live_claude_drift, shared jobs_lock) or their installer.
---

# Guardian watchers

No model, no paid API, stdlib Python (runs under `/usr/bin/python3`, the interpreter launchd uses). All three write W-* rows into `/Volumes/Mini Mini 2T Storage/ops/jobs.json` only through `scripts/jobs_lock.py`, which takes the same `fcntl.flock` on `jobs.json.lock` that `pc-board.py` takes.

| Watcher | Cadence | Checks | Writes |
|---|---|---|---|
| `guardian-watcher.py` | launchd, every 900 s | unite-group.in `/`, `/grow`, `/cards`, synthex.social; Stripe buy links on `/grow` and `/cards`; every open PR of CleanExpo/Unite-Group and CleanExpo/Synthex (list from the GitHub CLI, then each PR's checks) | rows `W-SITE-*`, `W-STRIPE-*`, `W-PR-LIST-<repo>`, `W-PR-<repo>-<n>`; heartbeat `ops/.watcher-last-run`; last-good times in `~/.local/state/guardian-watcher.json` |
| `jev-cap-watcher.py` | launchd, every 600 s | today's (UTC) Jev/TypeSafe spend from the canonical `~/.local/state/jev/spend.sqlite` (`JEV_SPEND_LEDGER`) plus the Mission Control ledger (a mirrored row is paired only by its `spend_call_id`, the canonical `call_id` from Pi-Dev-Ops PR #956, and counted once at the larger amount; until #956 lands every mirrored row counts in full, an overcount); both are required and read as SQLite only, and `JEV_WATCH_LEDGERS` is not read (setting it raises UNKNOWN) against the $20 cap (80% and 100%) | rows `W-TYPESAFE-CAP`, `W-TYPESAFE-CAP-UNKNOWN`, `W-ALERT-DELIVERY`; state `~/.local/state/jev-cap-watcher.json` |
| `live_claude_drift.py` | launchd, daily 07:15 (reference plist `com.guardian.live-claude-drift`, MacBook) | the live `~/.claude` checkout (`LIVE_DRIFT_REPO`): fetches origin, then counts commits behind `origin/main`, the committer age of the oldest missing one, and commits ahead. FAIL when behind and that age is over 24 h; UNKNOWN when it is not a git repo or the fetch fails. Also the nightly memory backup's `~/Library/Logs/claude-memory-backup.status` (`OK <ts>` / `FAIL <ts> exit=N <error>`, written by the memory backup script in the Pi-Dev-Ops repo): FAIL when it reads FAIL, an OK older than 36 h, or no file while the `com.phillmcgurk.claude-memory-backup` LaunchAgent is installed; UNKNOWN when unreadable | rows `W-DRIFT-LIVE-CLAUDE-<host>` and `W-MEMORY-BACKUP-<host>`; when `jobs.json` is absent (Mini volume not mounted) a non-OK result is also a macOS notification, and the exit is non-zero (0 OK, 1 FAIL, 2 UNKNOWN) |

## Three states, never two

- **OK**: the check ran and the answer is right. A recovered row is marked done.
- **FAIL**: the check ran and the answer is wrong (HTTP 4xx/5xx, missing buy link, failing PR check).
- **UNKNOWN**: the check could not run (DNS/TLS/connection/timeout, git fetch failed or not a git repo, GitHub CLI missing/non-zero/timeout/unparsable output, a Jev ledger missing/corrupt/locked/missing its column). UNKNOWN never resets a FAIL row to done. In guardian, UNKNOWN older than 30 minutes escalates the row to `check could not run: <reason>`. In jev, spend becomes a lower bound and `W-TYPESAFE-CAP-UNKNOWN` names the failing ledger.

A Jev alert level is recorded as sent only when Telegram confirmed delivery; two failed runs in a row raise `W-ALERT-DELIVERY`.

## Install and test

- `python3 install/install_guardian.py [--dry-run]` copies the scripts and `jobs_lock.py` to `~/.local/bin`, saving any differing file as `<name>.bak-<YYYYMMDD-HHMMSS>`. It never touches launchd; `launchd/*.plist` are reference copies of the loaded agents.
- Tests (offline, temp dirs, stub CLI, local HTTP server): `python3 tests/test_jobs_lock.py`, `test_jev_cap_watcher.py`, `test_guardian_watcher.py`, `test_live_claude_drift.py` (real temp git repos), `test_install_guardian.py`. Each prints `N/M passed` and exits 1 on any failure.
- Env seams for tests: `JEV_WATCH_*`, `GUARDIAN_*` and `LIVE_DRIFT_*` (see each script's docstring).

## Review supersede sweep

Each exact-SHA review round adds a card (claimed by worktree `rv-<stream>-<sha>`) and parks it in `review`; nobody closed the older rounds, so on 01/11/2026 19 of 76 `review` cards were stale evidence. `scripts/review_supersede.py` (dry run by default, `--apply` to write through `jobs_lock`) closes every older `review` card in a stream as `done` with `superseded_by` naming the newest round and the reason in `supersede_note` (an existing `closed_note` is never overwritten). Rounds are ranked only by `created` (`updated` is a mutable edit time and once closed the live round). A stream with a missing, unparseable or naive `created`, a tie for newest or a duplicate card id is left alone, as are single rounds and cards with no `rv-` stream. Tests: `python3 tests/test_review_supersede.py`.


<!-- SOP: seek-latest-before-task -->
## Knowledge publish loop (SOP `seek-latest-before-task`)

The brain-1 ingest -> index -> git publish -> SQL/corpus loop is hard-coded in the vault, not in
a watcher: `2nd Brain/_system/post_ingest.py` in CleanExpo/brain-1, triggered by the vault's
`post-commit` hook (installed by `2nd Brain/_system/install-post-ingest-hook.sh`; where a global
`core.hooksPath` is set it also adds a chain stub there, like the managed `pre-push`). Each run
writes `~/.local/state/brain1-post-ingest/status.json` with the same three-state discipline as
these watchers (PASS / FAIL / UNAVAILABLE, plus BLOCKED for a merge conflict); an UNAVAILABLE
corpus sync is never reported as synced. `live_claude_drift.py` covers the skills side: it
already alarms when the live `~/.claude` falls behind `origin/main`, which is the seek step of the
same SOP. Orchestrator v1 stays read-only and is not a writer for this loop.
<!-- /SOP: seek-latest-before-task -->
