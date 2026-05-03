# RA-1912 — Restore-from-clean-Mac runbook

If the Mac mini SSD dies and you're starting from a brand-new macOS install, this is the one-page recovery for the Hermes + Claude Memory + Pi-CEO local stack.

## What's at risk (state of play 2026-05-03)

| Artifact | Location | Backup status |
|---|---|---|
| Claude memory (27 .md files) | `~/.claude/projects/-Users-phill-mac-Pi-CEO/memory/` | **Phase 1: this runbook + daily push to `CleanExpo/claude-memory`** |
| Hermes daemon source | `~/.hermes/hermes-agent` (git, origin = anthropics) | Recoverable from git remote |
| Hermes config | `~/.hermes/config.yaml` (4,000+ char Margot persona) | Phase 2: symlink into claude-memory repo |
| Hermes secrets (9 keys) | `~/.hermes/.env` | **Phase 2: 1Password migration** (founder action) |
| Hermes Workspace UI | `~/hermes-workspace` (git, origin = outsourc-e) | Recoverable from git remote |

## Phase 1 install (Claude memory backup)

Founder one-time setup:

1. Create the GitHub repo:
   ```bash
   gh repo create CleanExpo/claude-memory --private --description "Claude Code memory backup for Pi-CEO Second Brain"
   ```

2. Confirm SSH access:
   ```bash
   ssh -T git@github.com
   # Expect: "Hi phill-mac! You've successfully authenticated..."
   ```

3. Install LaunchAgent (template is committed as `.plist.example`; copy to
   a real `.plist` in your LaunchAgents dir):
   ```bash
   cp ~/Pi-CEO/scripts/com.phillmcgurk.claude-memory-backup.plist.example \
      ~/Library/LaunchAgents/com.phillmcgurk.claude-memory-backup.plist
   chmod +x ~/Pi-CEO/scripts/claude_memory_backup.sh
   launchctl load ~/Library/LaunchAgents/com.phillmcgurk.claude-memory-backup.plist
   ```

4. Trigger an initial run to seed the remote:
   ```bash
   bash ~/Pi-CEO/scripts/claude_memory_backup.sh
   tail ~/Library/Logs/claude-memory-backup.log
   ```

   Expected log on first run:
   ```
   init: ...memory/ is not a git repo — initialising
   committed: auto: ... — 28 file(s)
   push complete
   ```

5. Verify daily schedule:
   ```bash
   launchctl list | grep claude-memory
   ```

## Restore from a clean Mac (when the SSD has died)

1. Install homebrew + git + uv:
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   brew install git gh uv
   gh auth login
   ```

2. Restore Claude memory:
   ```bash
   mkdir -p ~/.claude/projects
   cd ~/.claude/projects
   git clone git@github.com:CleanExpo/claude-memory.git -Users-phill-mac-Pi-CEO/memory
   ```

3. Restore Hermes Agent + config (Phase 2 will version config.yaml in the same repo):
   ```bash
   git clone https://github.com/anthropics/hermes.git ~/.hermes/hermes-agent
   cd ~/.hermes/hermes-agent && hermes setup
   ```

4. Restore secrets from 1Password (Phase 2 — pending founder migration):
   ```bash
   # When Phase 2 lands:
   #   op signin
   #   op read "op://hermes/openrouter-key" > ~/.hermes/.env.tmp
   #   ... per-secret read into .env ...
   ```
   Until Phase 2: re-create `~/.hermes/.env` manually from the 1Password vault you keep separately.

5. Restore Hermes Workspace:
   ```bash
   git clone git@github.com:outsourc-e/hermes-workspace.git ~/hermes-workspace
   cd ~/hermes-workspace && pnpm install && pnpm dev
   ```

6. Re-install the daily backup LaunchAgent (closes the loop):
   ```bash
   cp ~/Pi-CEO/scripts/com.phillmcgurk.claude-memory-backup.plist.example \
      ~/Library/LaunchAgents/com.phillmcgurk.claude-memory-backup.plist
   launchctl load ~/Library/LaunchAgents/com.phillmcgurk.claude-memory-backup.plist
   ```

## Phase 2 (founder action — not yet shipped)

- Create 1Password vault `hermes` and migrate the 9 secrets out of `~/.hermes/.env`.
- Rewrite Hermes startup to source secrets via `op read`.
- Symlink `~/.hermes/config.yaml` into the claude-memory repo so the Margot persona is versioned.

## Verification

Run weekly: `gh repo view CleanExpo/claude-memory --json pushedAt` — confirm latest push is < 25h old. If older, the LaunchAgent is broken or the founder rotated keys; tail the log file and fix.

## Related

- Linear: RA-1912
- Memory: `feedback_autonomy.md` (the autonomy mandate this protects)
- Memory: `reference_hermes_update_runbook.md` (Hermes update procedure)
