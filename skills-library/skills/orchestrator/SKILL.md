---
name: orchestrator
description: Use when changing, installing or debugging the Mini's Orchestrator v1 (the 30-minute read-only morning page of board, lanes, stalls and Needs-Phill items, plus its 15-minute deadman) or when reading MORNING.md.
---

# Orchestrator v1

No model, no paid API, stdlib Python under `/usr/bin/python3`. Read-only: it never writes `jobs.json` or `NEEDS-PHILL.md`, never dispatches work, and keeps no probe output. Spec and bench review: `.claude/done/spm/2026-10-30-orchestrator-v1/` in the branch that added this skill.

| Job | Cadence | Does | Writes |
|---|---|---|---|
| `com.unite.orchestrator` → `scripts/orchestrator.py` | every 1800 s | reads the board, checks lane logins, suggests owners for the top 5 unowned jobs, lists stalled `doing` jobs and tmux sessions idle over 6 h, reads NEEDS-PHILL.md | `~/.local/state/orchestrator/MORNING.md` (mirrored to `ops/MORNING.md` only when the volume is mounted) and one row per run in `orchestrator-runs.jsonl` |
| `com.unite.orchestrator-deadman` → `orchestrator.py --deadman` | every 900 s | no `ok:true` row in 75 min and not paused → first page line becomes `ORCHESTRATOR STALE` | the same page files |

A run gives up after 180 s (row `error: deadline`) and the deadman after 60 s (prints `TIMEOUT`), so a hung external drive cannot pile up stuck jobs. launchd output goes to `/dev/null`; the run rows are the record.

Lane states mean only what the check proved: `LOGGED_IN`, `NOT_LOGGED_IN`, `UNREACHABLE`, `UNKNOWN`, each with a fixed reason (`keychain_locked`, `api_key_mode`, `timeout`, ...). Logged in is not the same as having quota left.

## Stop, start, undo

- Stop just this: `touch ~/.local/state/orchestrator/ORCHESTRATOR-DISABLED` (next run writes a banner and stops). `~/.claude/HARD_STOP` pauses it along with every other agent.
- Uninstall: `python3 install/install_orchestrator.py --uninstall` (boots out both jobs, removes both plists, writes the marker; `bootstrap.sh` will not reinstall while the marker exists).
- Reinstall: delete the marker, then `python3 install/install_orchestrator.py`. Only acts on a host named `Phills-Mac-mini*`.
- Nothing on the board needs undoing: v1 writes nothing there.

## Checks

- `python3 -m unittest discover -s skills/orchestrator/tests -p 'test_*.py'`
- `python3 skills/orchestrator/tests/run_mutants.py` breaks each safety property in a copy and requires its test to fail.

## Before v1.1 writes suggestions onto jobs

`hermes_health.py` and `site_watch.mjs` on the Mini replace `jobs.json` without the shared lock (found 30/10/2026). They must take `jobs_lock` first; then write notes only through `skills/guardian/scripts/jobs_lock.py`, never `pc-board.py edit()` (not importable, no lock timeout).
