#!/usr/bin/env bash
# RA-1912 — claude_memory_backup.sh
# Daily auto-commit + push of this repo's Claude memory directory
# (~/.claude/projects/<encoded-repo-path>/memory) to the private GitHub repo
# set in $CLAUDE_MEMORY_REMOTE.
#
# The memory path is DERIVED, never hardcoded: it used to name one machine's
# username and project, so the script silently no-op'd (exit 2) on the other
# two machines in the fleet. Claude Code encodes a project's absolute path by
# replacing "/" and "." with "-", so the same derivation works on every host.
#
# Idempotent:
#   - first run initialises git + sets remote (no-op on subsequent runs)
#   - skips empty commits when nothing changed
#   - non-zero exit only on actual auth/network failure
#
# Required env (export from ~/.zshenv or LaunchAgent EnvironmentVariables):
#   CLAUDE_MEMORY_REMOTE   git@github.com:CleanExpo/claude-memory.git
#
# Optional env:
#   CLAUDE_MEMORY_BRANCH   defaults to "main"
#   CLAUDE_MEMORY_DIR      explicit memory dir; skips the derivation entirely

set -u  # unset vars are an error
set -o pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECTS_DIR="${HOME}/.claude/projects"
ENCODED="${REPO_ROOT//\//-}"      # /home/me/Pi-Dev-Ops -> -home-me-Pi-Dev-Ops
ENCODED="${ENCODED//./-}"
MEMORY_DIR="${CLAUDE_MEMORY_DIR:-${PROJECTS_DIR}/${ENCODED}/memory}"
BRANCH="${CLAUDE_MEMORY_BRANCH:-main}"

# ~/Library/Logs exists on macOS only; the desktops are not macOS.
if [ -d "${HOME}/Library/Logs" ]; then
    LOG_DIR="${HOME}/Library/Logs"
else
    LOG_DIR="${HOME}/.claude/logs"
fi
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/claude-memory-backup.log"

log() {
    printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE" >&2
}

# Fallback: the checkout may sit at a different path than the session that
# wrote the memory (worktrees, a clone under another parent). Match on the
# repo's basename and take the most recently modified candidate.
if [ ! -d "$MEMORY_DIR" ] && [ -d "$PROJECTS_DIR" ]; then
    candidate="$(ls -dt "$PROJECTS_DIR"/*-"$(basename "$REPO_ROOT")"/memory 2>/dev/null | head -1)"
    if [ -n "$candidate" ]; then
        log "derived path absent; falling back to $candidate"
        MEMORY_DIR="$candidate"
    fi
fi

if [ ! -d "$MEMORY_DIR" ]; then
    log "ERROR memory dir not found: $MEMORY_DIR (repo root: $REPO_ROOT)"
    exit 2
fi

if [ -z "${CLAUDE_MEMORY_REMOTE:-}" ]; then
    log "ERROR CLAUDE_MEMORY_REMOTE not set; cannot push. See RESTORE_RUNBOOK.md."
    exit 3
fi

cd "$MEMORY_DIR" || exit 4

# First-run init
if [ ! -d .git ]; then
    log "init: $MEMORY_DIR is not a git repo — initialising"
    git init -q -b "$BRANCH"
    git remote add origin "$CLAUDE_MEMORY_REMOTE"
    # Local guardrail: never accidentally publish anything outside memory/.
    cat > .gitignore <<'EOF'
# Keep this directory tightly scoped — only memory markdown should be versioned.
*.swp
*.swo
.DS_Store
EOF
    log "init complete; will attempt initial push at end of run"
fi

# Ensure remote is current (in case operator rotated SSH URL)
current_remote="$(git remote get-url origin 2>/dev/null || echo '')"
if [ "$current_remote" != "$CLAUDE_MEMORY_REMOTE" ]; then
    log "remote drifted ($current_remote) → setting to $CLAUDE_MEMORY_REMOTE"
    git remote set-url origin "$CLAUDE_MEMORY_REMOTE"
fi

# Stage everything in memory/, commit if there are changes.
git add -A

if git diff --cached --quiet; then
    log "no changes — skipping commit + push"
    exit 0
fi

commit_msg="auto: $(date -u +%Y-%m-%dT%H:%M:%SZ) — $(git diff --cached --name-only | wc -l | tr -d ' ') file(s)"
git commit -q -m "$commit_msg" --author="Claude Memory Backup <noreply@unite-group.com.au>" \
    || { log "ERROR commit failed"; exit 5; }

log "committed: $commit_msg"

# Push (will create remote branch on first run if repo is empty)
if ! git push -q origin "HEAD:$BRANCH" 2>&1 | tee -a "$LOG_FILE" >&2; then
    log "ERROR push failed — check SSH agent + repo access"
    exit 6
fi

log "push complete"
