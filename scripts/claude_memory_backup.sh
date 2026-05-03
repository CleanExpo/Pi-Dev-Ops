#!/usr/bin/env bash
# RA-1912 — claude_memory_backup.sh
# Daily auto-commit + push of ~/.claude/projects/-Users-phill-mac-Pi-CEO/memory
# to the private GitHub repo set in $CLAUDE_MEMORY_REMOTE.
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

set -u  # unset vars are an error
set -o pipefail

MEMORY_DIR="${HOME}/.claude/projects/-Users-phill-mac-Pi-CEO/memory"
BRANCH="${CLAUDE_MEMORY_BRANCH:-main}"
LOG_FILE="${HOME}/Library/Logs/claude-memory-backup.log"

log() {
    printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE" >&2
}

if [ ! -d "$MEMORY_DIR" ]; then
    log "ERROR memory dir not found: $MEMORY_DIR"
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
