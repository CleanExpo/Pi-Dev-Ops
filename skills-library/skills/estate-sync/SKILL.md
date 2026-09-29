---
name: estate-sync
description: Use when fleet machines have stale/diverged skills or config ("update didn't reach the other computer"), when setting up a new machine, or when the estate-sync log shows CONFLICT/FAIL. Owns the automatic two-way propagation of the skills-library hub (~/.claude) across all machines.
---

# estate-sync — every machine pulls and pushes the hub automatically

The skills-library repo (`~/.claude`, allowlist-gitignored: only `skills/`, CLAUDE.md,
AGENTS.md, bootstrap.sh sync — settings/projects/secrets never leave a machine) is the
estate's update bus. A 15-minute agent on every machine keeps it flowing both ways:
pull --rebase from main, then a safe selective push of local changes (symlinks never
staged — they carry machine-absolute paths, [[feedback-skills-library-symlink-commits]]).
Trunk-based: main only; a repo sitting on a feature branch is fetched but never touched.

## Install (once per machine)

- macOS: `zsh ~/.claude/skills/estate-sync/scripts/install-launchagent.sh`
  → LaunchAgent `com.unite.estate-sync`, every 15 min + at load.
- Windows: `powershell -ExecutionPolicy Bypass -File %USERPROFILE%\.claude\skills\estate-sync\scripts\install-task.ps1`
  → Task Scheduler job "Unite Estate Sync", every 15 min.
- New machine bootstrap: clone `CleanExpo/skills-library` to `~/.claude` (or run its
  bootstrap.sh), authenticate `gh`, then install the agent.
- **Completion criterion:** `~/.claude/logs/estate-sync.log` shows an `ok: in sync`
  line within 15 minutes of install.

## Publishing is gated (16/08/2026 Windows, 31/08/2026 macOS)

`origin` (CleanExpo/skills-library) is a **public** repo, and until 16/08/2026 the timer ran
`git add .` and published whatever was on disk — third-party edits included (proof: `aac5efe`,
a `skills/session-handoff/SKILL.md` edit an agent had deliberately not committed). **Neither
timer can now commit anything it was not explicitly given a receipt for.** The gate landed on
Windows on 16/08 and on macOS on 31/08; for those fifteen days the Mac Mini could still publish
ungated work to the same public repo, and the suite carried four tests that failed against
`estate-sync.sh` the whole time rather than skipping, so the hole could not render green.

- **Pull is ungated and unchanged.** `skills/`, `agents/` and everything else still arrive from
  origin every cycle. Only the unattended *push* is gated.
- **To publish**, name the files yourself:
  - macOS/Linux: `zsh ~/.claude/skills/estate-sync/scripts/estate-sync.sh --receipt skills/a/SKILL.md agents/b.md`
  - Windows: `powershell -File ~/.claude/skills/estate-sync/scripts/estate-sync.ps1 -Receipt -Path skills/a/SKILL.md,agents/b.md`

  (POSIX takes space-separated paths, PowerShell a comma-separated `-Path` — that is
  `powershell -File`'s argument handling, not a difference of opinion.) Either writes
  `.estate-sync-receipt` (path + sha256, untracked). The next cycle commits exactly
  those files, then deletes the receipt. One-shot, expires after 1h, and a file whose content
  changed after signing is refused — a receipt authorises a *version*, not a filename.
- **Everything else is refused by name in the log**, never committed: `REFUSED: <path> (reason)`.
  A `REFUSED` line is normal, not a fault — it means someone edited a file and did not ask for
  it to be published.
- **Never publishable, receipt or not:** `.github/`, `docs/session-handoffs/`, `bootstrap.sh`,
  the enforcement-script dirs, and `skills/estate-sync/scripts/` itself. Commit those by hand.
- **Every push is secret-scanned** against the diff it is about to publish; one hit refuses the
  whole push (exit 1) and logs the pattern name and file, never the value.
- **Both implementations are now behaviourally identical** and share one suite
  (`test_estate_sync.py`, 26 tests) which runs the POSIX script on macOS/Linux and the
  PowerShell script on Windows. Four sabotages in
  `skills/enforcement-loop/install/positive_control.py` require the gate's four properties —
  receipt required, receipt content-bound, never-sync defence, secret scan — each to turn its
  own named test red.
- **What changes for you day to day:** an edit no longer publishes itself. Write the receipt,
  or the next cycle logs `REFUSED: <path> (no gate receipt - no receipt present)` and the file
  stays local indefinitely. That is the intended steady state, not a fault.

## Health check / troubleshooting

1. `tail -5 ~/.claude/logs/estate-sync.log` — expect `ok: in sync` lines every ~15 min.
2. `HEALTH: tracked deletion(s) present` → a tracked path is missing locally. The cycle
   exits non-zero before staging or pushing and does not emit `ok: in sync`; restore the
   path or deliberately commit its removal after review.
3. `CONFLICT` line → the machine has local commits that no longer rebase: reconcile by
   hand (`git status`, resolve, `git rebase --continue`), then the next cycle resumes.
   The agent never force-pushes and never resolves conflicts itself.
4. `WARN: on branch <x>, not main — N commit(s) behind` → nothing syncs until it is
   back on main. On 28/09/2026 all three machines were found this way, weeks stale
   (RA-7802); `fleet.py health` now reports it for every node. Merge or park the
   branch's work, then switch back to main.
5. Nothing in the log → the agent isn't installed/loaded on this machine; run install.
6. Network layer: machines need not reach each other — sync rides GitHub. Tailscale is
   for direct machine-to-machine work (`tailscale status`); a peer shown `offline` for
   months is a stale node to remove in the admin console (founder action).
- **Completion criterion:** the same commit SHA at `git -C ~/.claude log -1 main` on
  every online machine within one cycle.

## Boundaries

The agent only ever touches `~/.claude` on `main`. It never force-pushes, never deletes
remote branches, never resolves conflicts autonomously, and never syncs untracked paths
(the allowlist gitignore is the contract). Product repos are NOT its business — they
ship via PRs and merge lanes.
