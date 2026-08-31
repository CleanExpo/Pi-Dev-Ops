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
#   CLAUDE_MEMORY_DIR      explicit memory dir; skips derivation AND the
#                          basename fallback entirely. Set this when several
#                          projects share a repo basename (exit 7).

set -u  # unset vars are an error
set -o pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECTS_DIR="${HOME}/.claude/projects"
ENCODED="${REPO_ROOT//\//-}"      # /home/me/Pi-Dev-Ops -> -home-me-Pi-Dev-Ops
ENCODED="${ENCODED//./-}"
if [ -n "${CLAUDE_MEMORY_DIR:-}" ]; then
    MEMORY_DIR="$CLAUDE_MEMORY_DIR"
    MEMORY_DIR_EXPLICIT=1   # operator named the source; never second-guess it
else
    MEMORY_DIR="${PROJECTS_DIR}/${ENCODED}/memory"
    MEMORY_DIR_EXPLICIT=0
fi
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

# Strip credentials from any git URL before it reaches the log file.
#
# $LOG_FILE is persistent and world-readable by the account that runs this.
# CLAUDE_MEMORY_REMOTE is DOCUMENTED as an SSH URL, which carries no secret —
# but nothing enforces that, and an HTTPS remote of the form
# https://x-access-token:ghp_...@github.com/owner/repo.git is the obvious way to
# run this on a machine with no SSH agent. That is exactly the Windows node this
# script was just fixed to support, so the unsafe case is the one newly in reach.
#
# Two paths reach the log, and both are covered:
#   - the "remote drifted" line below, which prints both URLs;
#   - git's own stderr on push, which quotes the full remote URL on an auth
#     failure ("Authentication failed for 'https://user:token@github.com/...'").
# The second is the more dangerous: it fires precisely when credentials are
# wrong, which is when an operator is most likely to paste the log somewhere.
redact_url() {
    sed -E 's#(://)[^/@[:space:]]+@#\1***@#g'
}

# Fallback: the checkout may sit at a different path than the session that
# wrote the memory (worktrees, a clone under another parent). Match on the
# repo's basename, encoded the same way as the full path above so a dotted
# name like "my.repo" still matches its "-my-repo" directory.
#
# Two rules keep this safe. An explicit CLAUDE_MEMORY_DIR is never overridden:
# the operator named the source, and silently substituting another one pushes
# the wrong memory to $CLAUDE_MEMORY_REMOTE. And an ambiguous match is fatal
# rather than arbitrary — picking one of several same-named projects would
# publish ANOTHER PROJECT'S MEMORY to the configured remote.
if [ "$MEMORY_DIR_EXPLICIT" -eq 0 ] && [ ! -d "$MEMORY_DIR" ] && [ -d "$PROJECTS_DIR" ]; then
    base="$(basename "$REPO_ROOT")"
    base="${base//./-}"
    candidates=()
    for d in "$PROJECTS_DIR"/*/memory; do
        [ -d "$d" ] || continue
        # Literal suffix compare — no ls parsing, and metacharacters in the
        # basename or the project dir name cannot widen the match.
        case "$(basename "$(dirname "$d")")" in
            *-"$base") candidates+=("$d") ;;
        esac
    done

    if [ "${#candidates[@]}" -gt 1 ]; then
        log "ERROR ambiguous memory dir: ${#candidates[@]} projects match basename '$base'."
        for d in "${candidates[@]}"; do
            log "  candidate: $d"
        done
        log "Refusing to guess — set CLAUDE_MEMORY_DIR to the intended one."
        exit 7
    fi

    if [ "${#candidates[@]}" -eq 1 ]; then
        log "derived path absent; falling back to ${candidates[0]}"
        MEMORY_DIR="${candidates[0]}"
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
    log "remote drifted ($(printf '%s' "$current_remote" | redact_url)) → setting to $(printf '%s' "$CLAUDE_MEMORY_REMOTE" | redact_url)"
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
if ! git push -q origin "HEAD:$BRANCH" 2>&1 | redact_url | tee -a "$LOG_FILE" >&2; then
    log "ERROR push failed — check SSH agent + repo access"
    exit 6
fi

log "push complete"
