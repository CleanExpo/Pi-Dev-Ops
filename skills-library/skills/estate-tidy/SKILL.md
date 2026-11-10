---
name: estate-tidy
description: The 2-hourly settle, handoff and cleanup pass on the MacBook, Mac Mini and PC. Use when reading or changing the tidy schedule, when a tidy report (ops-board/systems/tidy-*.json) shows LOST, STALLED or errors, when the PC queue looks paused, or when someone asks why a worktree, process or temp file was or was not removed.
---

# estate-tidy

Phill's ask (26/10/2026): let the system settle for a few minutes every 2 hours, hand off and resume long-running sessions, and clean up, so data stays clear and clean. **Orchestrate it all, never lose anything, and continue after the cleanup.**

**The one rule:** nothing is deleted unless it is safely on GitHub or otherwise backed up. When unsure, the pass reports and leaves the thing alone.

Files: `estate_tidy.py` (stdlib, Python 3.9+), `install/install_estate_tidy.py` (idempotent; run by hand on each machine, `bootstrap.sh` does not call it yet). Regression tests: `tests/test_estate_tidy.py` (CI runs it).

## Schedule (staggered so the machines never pause together)

| Machine | Runner | When |
|---|---|---|
| MacBook | launchd `com.unite.estate-tidy` | every 2 h at :00 |
| Mac Mini | launchd `com.unite.estate-tidy` | every 2 h at :20 |
| Mac Mini | launchd `com.unite.estate-tidy-relay` | every 5 min: pulls the PC report, pushes the ledger to the PC, raises LOST/STALLED lines |
| PC (WSL, root) | systemd `estate-tidy.timer` | every 2 h at :40; runs a root-owned copy in `/usr/local/lib/estate-tidy/` |

Install or update: `python3 ~/.claude/skills/estate-tidy/install/install_estate_tidy.py [--sessions on|dry|off]` (the PC needs root). `--check` exits 0 only if the installed schedule matches. The sessions mode is remembered in the state folder and must be exactly `off`, `dry` or `on`. The installer replaces a plist, unit or root script copy only when it already carries the exact line the installer writes (the plist `Label`, the unit `Description`, the script's first docstring line); a symlink or any other file at that path is refused.

## One pass, in order

0. **Ledger snapshot and check (before).** Copy `IN-FLIGHT.md` (Mini `session-handoffs/`) to the state folder, then check each row this machine owns.
1. **Session handoffs (`--sessions on`).** Only Claude sessions running inside a tmux pane are candidates (found via `~/.claude/sessions/<pid>.json`). A session is IDLE only if its status file says idle for over 5 minutes, no `esc to interrupt` is on screen, no question is on screen, and the prompt is empty. Anything else is "skipped, busy" and caught next pass. Never killed, never interrupted. Interactive windows outside tmux (including the MacBook lead) are never touched.
   For each idle session: `/session-handoff` writing to `session-handoffs/tidy-handoffs/handoff-<machine>-<session>-<ts>.md`; when the file exists and the session is idle again, `/clear`, then `/resume-from-handoff <path> After reconciliation, continue the standing goal and every open row you own in IN-FLIGHT.md; re-arm your /loop or wakeup if you had one. Do not stop to ask.` The pass then reads the resumed session's own transcript (`~/.claude/projects/*/<new session id>.jsonl`): `/clear` is proven by the new session id, "read the handoff" by a tool call naming the handoff file, and the verdict by MATCH / MINOR DRIFT / MATERIAL DRIFT / CANNOT RESUME or a plain-words match ("matched the handoff", "resumed cleanly"). It waits up to 30 minutes; a session still busy at that point is PENDING, never STALLED. MATERIAL DRIFT, CANNOT RESUME, or no verdict while idle goes to NEEDS-PHILL.md. If the handoff never finishes, the session is NOT cleared.
2. **Settle window.** PC: write `/mnt/d/pc-handoff/queue/PAUSE` (`pid=`, `expires=`), wait 5 minutes, record any job that still started. The flag is removed in a `finally` block and on SIGTERM/SIGINT/SIGHUP, and `pcqueue.service` is kicked so the next job starts at once. If the pass is SIGKILLed, `pcqueue` itself treats a PAUSE whose writer pid is dead or whose expiry passed as stale, removes it and carries on. A PAUSE file with no `pid=` line is a manual pause and is always honoured. Macs: a 5 minute quiet wait.
3. **Worktrees** (Unite-Group, Synthex, CARSI, RestoreAssist/ra-main, Pi-Dev-Ops, `~/.claude`, PC `ug-main`, `synthex-main`). After `git fetch --prune`, a worktree is removed with plain `git worktree remove` (no `--force`) only if ALL hold: fetch worked; not locked; not named (path or branch) in `IN-FLIGHT.md` (an unreadable ledger protects everything); clean including untracked files; no ignored files except rebuildable ones (`node_modules`, `.next`, caches; an `.env` keeps it); no running process has its cwd inside; no git activity for 24 h; and its head is an ancestor of origin main, or its branch is deleted on GitHub (or its PR merged) with the head contained in a remote branch. Everything else is listed as kept with the reason. Then `git worktree prune`. No branch is ever deleted.
4. **Orphan processes.** Killed only if owned by the agent user, parent PID 1, older than 3 h, not a launchd job or systemd service or pcjob unit, not claude/codex/cursor-agent/tmux/ssh/Ops Board, and one of: `next dev`/`next-server`, vitest, headless Playwright/Chromium, or a node dev server (vite, webpack, nodemon...) listening on a high port, or a throwaway one-off: `python -m http.server`, or a python/node/bun/deno script whose file sits in a temp folder (`/tmp`, `/private/tmp`, `/var/folders`; `$TMPDIR` is not trusted; inline `-c`/`-e` code is not one). A temp-folder script that is listening on a port is never killed: it is listed as left for a person (`python -m http.server` is still stopped). Stopping sends INT, then TERM after 10 s, then KILL after 5 s, so Python `finally` blocks run. Every kill rule matches whole argv words or path parts, never a substring of the command line (`/opt/prod/invite-api` is not `vite`). A plain `node server.js` is left alone and listed as unsure. A throwaway one-off that is NOT orphaned is also stopped when it is over 12 h old and descends from a remote bridge that never reaps what it starts (`REMOTE_BRIDGES`, today `desktop-commander`); the bridge itself is never touched. Every kill logs pid, command and age. (1/11/2026: agent lanes driven through Desktop Commander had left up to 20 preview servers and test scripts running for up to 45 h.)
5. **Disk.** `docker volume prune -f` (no `--all`), `docker image prune -f`, `npm cache verify`, `pnpm store prune`, Playwright browser folders not referenced by any live install link and older than 7 days. Temp files: regular files older than 24 h in the system TMPDIR (and the Mini `hot/tmp`), older than 48 h in `/tmp/claude-*`; names containing evidence, report, receipt, bundle, review, handoff, session-handoffs or pc-bundles are never touched. Free space (`df`) is recorded before and after; never quote `du`.
5b. **Fleet versions (all machines, read-only).** Runs `~/.local/share/fleet-sync/fleet-sync --check --self --json` and records the result under `fleet` in the tidy JSON (`GREEN`, `DRIFT` with the differing items, `BLOCKED` when only items waiting on Phill remain, or `UNPROVEN` if the check could not run, which also goes in `errors`) plus a `fleet:` log line. It never upgrades anything and never writes to `NEEDS-PHILL.md`: upgrades happen together, on purpose, with `fleet-sync --apply` (script and `fleet-versions.json` live in `session-handoffs/fleet/` on the Mini; `--apply` copies them to every machine). `--skip fleet` turns it off.
6. **Board hygiene (Mini).** `TASKS.json` rows whose every PR URL is merged become done; `NEEDS-PHILL.md` lines whose every PR URL is merged or closed are removed. Bare `#123` lines are left (repo unknown). Each changed file gets a `.bak-tidy-<ts>` copy; only the last 10 are kept.
7. **Ledger check (after).** Every row this machine owns must still resolve: branch exists locally or on origin; head commit exists locally, on origin or in its bundle; each path exists; PR is open or merged. A missing worktree whose branch exists is restored with `git worktree add`. Anything else is a **LOST** line in the tidy JSON and at the top of `NEEDS-PHILL.md`. Rows that name no branch, path or PR are reported UNVERIFIABLE, not passed.
8. **Must-continue check.** About 10 minutes after each resume: if the session is working, fine. If idle, one nudge: `Continue the standing goal from IN-FLIGHT.md.` If still idle 10 minutes later, it is **STALLED** in the JSON and `NEEDS-PHILL.md`.
9. **Report.** `/Volumes/Mini Mini 2T Storage/ops-board/systems/tidy-<machine>.json` (dry runs: `tidy-<machine>-dryrun.json`): times, free disk before/after, sessions and handoff paths, ledger checks, worktrees removed/kept with reasons, processes killed, disk actions, board changes, LOST, STALLED, errors. MacBook pushes it over ssh; the PC writes `D:\pc-handoff\status\tidy-pc.json` and the Mini relay pulls it.

## Ledger rules

Row format: `| Item | Owner | Repo / branch | Head | PR | Lives at | Next step |`. "Lives at" may start with `PC `, `MacBook ` or `Mini `; a bare `~/` path means the MacBook (the lead writes the ledger there), `/Volumes/` means the Mini, `/mnt/` the PC. Each machine checks only its own rows. The PC reads a copy of the ledger the relay pushes every 5 minutes.

## Running it

- `--dry-run`: plan only. Nothing is deleted, paused, killed, sent or written except the dry-run report.
- `--sessions dry`: list which sessions would get a handoff. `--only-session <name>` limits live handoffs to one tmux session.
- `--ledger-only`: snapshot and check the ledger, nothing else.
- `--skip sessions,settle,worktrees,processes,disk,fleet,board,ledger` and `--settle-seconds N` for testing.
- `--selftest`: the safety predicates (protected names, never-kill list, worktree decision, ledger parser, PAUSE staleness, idle detection). Each was watched failing on a planted defect. `tests/test_estate_tidy.py` adds the destructive paths: a symlinked temp root is skipped, a listening temp service is kept, the installer refuses a symlinked or foreign destination and a sessions-mode file holding anything but `off`, `dry` or `on`.

State: MacBook `~/.estate-tidy/`, Mini `/Volumes/Mini Mini 2T Storage/hot/estate-tidy/`, PC `/home/cloudroom-agent/.estate-tidy/` (`tidy.log`, `runs.jsonl`, `ledger-snapshots/`). launchd stdout/stderr go to `~/Library/Logs/estate-tidy/` on both Macs (launchd cannot open a log on the external SSD: exit 78). PC: `journalctl -u estate-tidy.service`.

## Known limits

- PC Cloudroom threads and `claude -p` jobs are not tmux sessions, so the PC runs with sessions off.
- A row in `IN-FLIGHT.md` is only as checkable as its cells: rows with no branch, path or PR are UNVERIFIABLE. Paths may be split by `,` or ` + `; `pc-bundles/...` means `~/session-handoffs/pc-bundles/...`.
- A squash-merged branch whose remote branch was deleted has its head only in GitHub's PR ref, not a remote branch, so its worktree is kept and listed. Removing those needs a proof the PR ref holds the head; not built.
- The Ops Board renders `systems/mini|pc|macbook|railway.json` only; `tidy-*.json` is not yet drawn on the board (owner: the Ops Board helper).
