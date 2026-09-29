#!/bin/zsh
# estate-sync - propagate skills-library updates in BOTH directions automatically.
# Runs via LaunchAgent every 15 min. Trunk-based: syncs main only; if the repo is
# on a feature branch (a session mid-work), it fetches but never disturbs the tree.
# Fail-safe: any rebase conflict aborts cleanly, logs, and skips the push.
#
# GATED PUBLISH. Ported from estate-sync.ps1 (Windows, 16/08/2026), which received this
# gate the day the hazard was observed while this script - running on the Mac Mini,
# pushing to the SAME PUBLIC origin - did not. The asymmetry stood from 16/08/2026 until
# today, and the suite carried four tests (t19-t22) that FAILED against this file the
# whole time, by design: `_require_gate` raises rather than skips precisely so the hole
# could not render green.
#
# The hazard itself, observed on Windows: a blanket `git add` over the whole tree pushed
# whatever happened to be on disk, so an edit made by anyone - another agent, another
# session, a half-finished thought - became a PUBLIC commit within 15 minutes. At ~14:53
# an agent edited skills/session-handoff/SKILL.md and deliberately did not commit it; at
# 15:09:49 the timer published it, and again at 15:24:49.
#
# This timer can no longer commit a change it was not explicitly given a receipt for.
# Every dirty path is either matched against .estate-sync-receipt (path + sha256,
# one-shot, expiring) or REFUSED BY NAME in the log. Pull is untouched, so skills/ and
# agents/ still arrive from origin every cycle; only the unattended PUBLISH is gated.
#
# To publish deliberately:
#   zsh estate-sync.sh --receipt skills/foo/SKILL.md agents/bar.md
# then let the next cycle run (or run this script with no arguments).
set -u
# Overridable for tests only — the LaunchAgent never sets it, so production is
# unchanged. Without this the script can only be exercised against the real repo,
# i.e. by pushing to origin/main to find out whether it works.
REPO="${ESTATE_SYNC_REPO:-$HOME/.claude}"
LOG="$REPO/logs/estate-sync.log"
# A session actively editing the estate must not have its work swept into a
# "chore(sync)" commit. Two guards, both overridable for tests only.
QUIET_SECS="${ESTATE_SYNC_QUIET_SECS:-300}"      # skip if anything changed this recently
HOLD_MAX_SECS="${ESTATE_SYNC_HOLD_MAX_SECS:-3600}"  # a forgotten hold expires, never blocks forever
HOLD="$REPO/.estate-sync-hold"
# A receipt is a permit for ONE cycle, not a standing licence: it expires by age and is
# deleted the moment it is spent, so a forgotten receipt cannot authorise tomorrow's
# unrelated edit to the same file.
RECEIPT_MAX_SECS="${ESTATE_SYNC_RECEIPT_MAX_SECS:-3600}"
RECEIPT="$REPO/.estate-sync-receipt"

# Paths this timer must never publish, receipt or not. Mirrors $neverSync in the .ps1.
#  .github/                      - workflows EXECUTE on push (the 2026-07-16 hazard).
#  docs/session-handoffs/        - handoffs are session transcripts of private estate work
#                                  and origin is PUBLIC. .gitignore cannot hold this line:
#                                  23 handoffs are already TRACKED, and git never ignores
#                                  a tracked path, so this list is what stops their future
#                                  EDITS being published. Removing the existing 23 or
#                                  rewriting history is a founder decision, not this
#                                  script's.
#  enforcement code              - a workflow that lands wrong is red and visible; a gate
#                                  that lands wrong is GREEN and silently changes what
#                                  every agent on every machine may do. These are the
#                                  paths the old ENFORCEMENT_PATHS array carried.
#  skills/estate-sync/scripts/   - this script IS the gate. It must be committed by a
#                                  human who read the diff, never by itself. The .ps1
#                                  has carried this entry since 16/08; this file did not,
#                                  so until now the timer could publish its own gate.
# Asymmetric on purpose: the pull --rebase below still brings all of these DOWN from
# origin, so a reviewed change still reaches every machine automatically. Only the
# unattended PUSH stops.
NEVER_SYNC=(
  ".github/"
  "docs/session-handoffs/"
  "bootstrap.sh"
  "skills/pr-release-gate/scripts/"
  "skills/engineering-requirements/scripts/"
  "skills/supabase-write-gate/scripts/"
  "skills/enforcement-loop/install/"
  "skills/estate-sync/scripts/"
)
is_never_sync() {
  local p="$1" n
  for n in "${NEVER_SYNC[@]}"; do
    case "$n" in
      */) [[ "$p" == "$n"* ]] && return 0 ;;
      *)  [ "$p" = "$n" ] && return 0 ;;
    esac
  done
  return 1
}

# macOS ships shasum, Ubuntu (the CI runner) ships both shasum and sha256sum, and
# openssl is the fallback. Resolved at call time rather than assumed: hardcoding
# /bin/zsh in the test harness is the same mistake, and it made 15 tests read as
# breakage on a host that simply lacked the interpreter.
sha256_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then openssl dgst -sha256 "$1" | awk '{print $NF}'
  else return 1
  fi
}

# Secret shapes refused in the diff about to be published. High-precision provider
# prefixes only: a generic password= would false-positive across a repo of prose and
# stall the sync, and a stalled sync gets disabled. Every pattern's variable part begins
# with a character class, so the pattern list cannot match ITSELF if this file ever
# appears in a diff - the failure mode the output-path invariant above hit on its first
# version. Matches are logged by pattern name and file only, never the matched text:
# a scanner that prints the credential it found has moved the credential into the log.
SECRET_PATTERNS=(
  "aws-access-key-id	AKIA[0-9A-Z]{16}"
  "anthropic-key	sk-ant-[A-Za-z0-9_-]{16,}"
  "openai-key	sk-[A-Za-z0-9]{32,}"
  "github-token	gh[pousr]_[A-Za-z0-9]{30,}"
  "github-pat	github_pat_[A-Za-z0-9_]{20,}"
  "google-api-key	AIza[0-9A-Za-z_-]{30,}"
  "slack-token	xox[baprs]-[A-Za-z0-9-]{10,}"
  "stripe-live-key	[sr]k_live_[0-9a-zA-Z]{20,}"
  "gitlab-pat	glpat-[A-Za-z0-9_-]{18,}"
  "jwt	eyJ[A-Za-z0-9_-]{16,}\\.[A-Za-z0-9_-]{16,}\\.[A-Za-z0-9_-]{16,}"
  "private-key-block	-----BEGIN [A-Z ]*PRIVATE KEY-----"
)
ts() { date '+%d/%m/%Y %H:%M:%S' }
log() { echo "[$(ts)] $1" >> "$LOG" }
# The ONE terminal-bound output site, and it exists only for --receipt, which is an
# interactive invocation a human types: refusing to tell them why their receipt was
# rejected would make the gate unusable and get it worked around. The timer path still
# emits nothing but log(). Named rather than inline so the invariant below counts one
# site however many messages --receipt grows.
say() { echo "$1" }
now() { date +%s }
age_of() { echo $(( $(now) - $(stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || now) )) }

# Output-path invariant (2026-08-03, mirrors agent_mesh_health.py): every message this
# script emits flows through log(); the only raw e-cho sites are the log() and age_of()
# helper bodies, and no direct alert channel (c-url / o-sascript / notifier) may exist
# here. An edit adding an output path must update these counts deliberately, or this
# fails closed with the violation named in the log. The hyphenated spellings above and
# the bracket patterns below keep this block out of its own count — the first version
# of this check counted its own comment and failure message (caught by its positive
# control on the clean script).
# 3 as of the receipt-gate port: log(), age_of(), and say(). Raised deliberately, which
# is what the paragraph above asks of an edit that adds an output path.
EXPECTED_RAW_OUTPUT_SITES=3
ACTUAL_RAW=$(grep -c "ech[o] " "$0")
ACTUAL_ALERT=$(grep -c "cur[l] \|osascrip[t]\|terminal-notifie[r]" "$0")
if [ "$ACTUAL_RAW" -ne "$EXPECTED_RAW_OUTPUT_SITES" ] || [ "$ACTUAL_ALERT" -ne 0 ]; then
  log "FAIL: output-path invariant — $ACTUAL_RAW raw output sites (allow $EXPECTED_RAW_OUTPUT_SITES), $ACTUAL_ALERT alert-channel sites (allow 0); review the edit against this header"
  exit 1
fi

# Placed before the machine-local pre-hook and before the fetch: writing a receipt
# is a local, interactive act. It must not run another machine's reclaim hook as a
# side effect, and it must not fail because the network is down.
# --receipt: write the permit. Deliberately a separate invocation - the act of NAMING the
# files is the gate, and a mode that could infer them from the dirty tree would just be
# `git add .` with extra steps. Runs before the fetch: writing a receipt is a local act
# and must not fail because the network is down.
if [ "${1:-}" = "--receipt" ]; then
  shift
  if [ "$#" -eq 0 ]; then
    say "usage: estate-sync.sh --receipt <repo-relative-path> [<path>...]"
    exit 2
  fi
  RLINES=("# estate-sync receipt written $(ts) by ${USER:-unknown}"
          "# One-shot: consumed by the next sync cycle, and ignored after ${RECEIPT_MAX_SECS}s.")
  BAD=0
  for arg in "$@"; do
    rel="${arg#./}"
    if [ ! -f "$REPO/$rel" ]; then
      say "REFUSED to receipt (not a file): $rel"; BAD=1; continue
    fi
    if is_never_sync "$rel"; then
      say "REFUSED to receipt (never-sync path): $rel"; BAD=1; continue
    fi
    H=$(sha256_of "$REPO/$rel") || { say "REFUSED to receipt (no sha256 tool available): $rel"; BAD=1; continue }
    RLINES+=("$H  $rel")
  done
  # Fail closed: a partial receipt would silently publish the subset that passed while the
  # author believes the whole set was refused.
  if [ "$BAD" -eq 1 ]; then
    say "no receipt written"
    log "REFUSED: receipt request rejected; no receipt written"
    exit 1
  fi
  printf '%s\n' "${RLINES[@]}" > "$RECEIPT" || { say "FAIL: could not write $RECEIPT"; exit 1 }
  NAMED="${(j:, :)@}"
  say "receipt written for $# path(s): $NAMED"
  log "receipt written for $# path(s): $NAMED"
  exit 0
fi

# Machine-local pre-hook (Mini reclaim, etc). Absent on other hosts — skip.
HOOK="$HOME/.local/bin/estate-sync-pre-hook.sh"
[ -f "$HOOK" ] && /bin/zsh "$HOOK" || true

cd "$REPO" || { log "FAIL: repo missing"; exit 1 }
git fetch origin main --quiet 2>>"$LOG" || { log "FAIL: fetch"; exit 1 }

BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
  # RA-7802: this used to log "skip" and exit 0, and three machines sat off main for
  # weeks unseen. Still never syncs a working branch; it says how far behind it is,
  # and `fleet.py health` reports it for every node.
  BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null)
  [ -n "$BEHIND" ] || BEHIND="?"  # a fallback print would be a 4th raw output site (header caps 3)
  log "WARN: on branch $BRANCH, not main — $BEHIND commit(s) behind origin/main; fetched only, NOT synced"
  exit 0
fi

# Freshness is sampled BEFORE the pull, and this ordering is the whole point.
# `git pull --rebase --autostash` stashes dirty tracked files, rebases, then pops — and the
# pop REWRITES those files, setting their mtime to now. Sampling afterwards therefore always
# measured the pop, never the human edit: the guard read "changed 0s ago" every cycle and
# skipped staging forever. Measured 2026-08-18 — cycles at 09:26, 09:41 and 09:53 all skipped
# the same file at 0-1s old, while 21 commits sat unpushed for eight days behind it, including
# the fixes to the release gate that was blocking the manual push.
PRE_SEEN=0
PRE_NEWEST=0
PRE_RECENT=""
PRE_CHANGED=$(git status --porcelain 2>>"$LOG" | sed 's/^...//')
if [ -n "$PRE_CHANGED" ]; then
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    [ -e "$REPO/$f" ] || continue
    A=$(age_of "$REPO/$f")
    if [ "$PRE_SEEN" -eq 0 ] || [ "$A" -lt "$PRE_NEWEST" ]; then
      PRE_NEWEST=$A; PRE_RECENT="$f"; PRE_SEEN=1
    fi
  done <<< "$PRE_CHANGED"
fi

if ! git pull --rebase --autostash origin main --quiet 2>>"$LOG"; then
  git rebase --abort 2>/dev/null
  log "CONFLICT: pull --rebase failed — manual reconcile needed; push skipped"
  exit 1
fi

# A tracked deletion is unresolved estate drift, not an in-sync state. Fail closed
# before staging or pushing anything; restoration/removal requires deliberate review.
DELETED=$(git diff --name-only --diff-filter=D HEAD -- 2>>"$LOG")
if [ $? -ne 0 ]; then
  log "FAIL: tracked deletion health check"
  exit 1
fi
if [ -n "$DELETED" ]; then
  log "HEALTH: tracked deletion(s) present — manual reconcile needed; push skipped"
  while IFS= read -r f; do log "tracked deletion: $f"; done <<< "$DELETED"
  exit 1
fi

# An explicit hold beats any heuristic: a session that knows it is mid-task takes
# it and the timer stays off its work. Capped by age so a crashed session cannot
# wedge the estate out of sync indefinitely — an expired hold is ignored and said so.
if [ -e "$HOLD" ]; then
  HOLD_AGE=$(age_of "$HOLD")
  if [ "$HOLD_AGE" -lt "$HOLD_MAX_SECS" ]; then
    log "skip: hold held for ${HOLD_AGE}s (<${HOLD_MAX_SECS}s) — session working; nothing staged"
    exit 0
  fi
  log "hold is stale (${HOLD_AGE}s >= ${HOLD_MAX_SECS}s) — ignoring it and syncing"
fi

# Quiescence. `git add .` below sweeps whatever is on disk at this instant, so a
# file written seconds ago by a running session becomes a chore(sync) commit —
# the change lands under a message that explains nothing and the author's own
# commit finds nothing left to record. Observed twice on 2026-07-29 (14:35:43,
# 14:50:56), each time taking work an agent was midway through committing.
# This is the same argument the .github suppression below already makes; the only
# thing special about .github was that its half-written state also executes.
# Skipping the whole cycle rather than the recent files is deliberate: staging a
# subset would commit a partial change set, which is worse than waiting 15 minutes.
# SEEN is the sentinel, not NEWEST. A file written in the same second this runs has an
# age of exactly 0, and using 0 to mean "nothing measured" silently disables the guard
# for the freshest possible edit — precisely the case it exists to catch. t13 caught this.
# Uses the PRE-pull sample above, never a fresh stat: after --autostash pops, every dirty
# tracked file reads as 0s old regardless of when a human last touched it.
SEEN=$PRE_SEEN
NEWEST=$PRE_NEWEST
RECENT="$PRE_RECENT"
if [ "$SEEN" -eq 1 ] && [ "$NEWEST" -lt "$QUIET_SECS" ]; then
  log "skip: ${RECENT} changed ${NEWEST}s ago (<${QUIET_SECS}s) — session may be mid-edit; nothing staged"
  exit 0
fi

# Read the receipt. Absent or stale is not an error - it is the normal state of a machine
# nobody is publishing from, and it means the same thing as an empty receipt: stage
# nothing. Parsed with awk so a path containing spaces survives, and comment lines are
# dropped before parsing rather than being read as a hash.
typeset -A RECEIPT_MAP
RECEIPT_STATE="no receipt present"
if [ -e "$RECEIPT" ]; then
  R_AGE=$(age_of "$RECEIPT")
  if [ "$R_AGE" -ge "$RECEIPT_MAX_SECS" ]; then
    RECEIPT_STATE="receipt stale (${R_AGE}s >= ${RECEIPT_MAX_SECS}s)"
    log "REFUSED: $RECEIPT_STATE - write a fresh one to publish"
  else
    while IFS=$'\t' read -r rh rp; do
      [ -z "$rp" ] && continue
      RECEIPT_MAP[$rp]="${rh:l}"
    done < <(grep -v '^[[:space:]]*#' "$RECEIPT" \
             | awk 'NF>=2 {h=$1; $1=""; sub(/^[ \t]+/,""); print h "\t" $0}')
    RECEIPT_STATE="receipt covers ${#RECEIPT_MAP} path(s)"
  fi
fi

# THE GATE. Every dirty path is named and decided individually; nothing is sweepable.
# -uall so an untracked directory is enumerated as its files, otherwise a refusal would
# name a directory and hide what is inside it.
# A refusal is the NORMAL steady state of a machine nobody is publishing from, so it is
# logged and the cycle continues at exit 0. Silence here would be the real fault: an
# operator would have no way to tell that edits are piling up unpublished.
TO_STAGE=()
while IFS= read -r line; do
  [ ${#line} -le 3 ] && continue
  p="${line:3}"
  # git quotes paths containing unusual bytes. Strip the wrapper only; a path whose
  # escapes this does not decode simply fails the receipt lookup, which is closed.
  p="${p#\"}"; p="${p%\"}"
  if is_never_sync "$p"; then
    log "REFUSED: $p (never-sync path - this timer must not publish it)"; continue
  fi
  if [ -z "${RECEIPT_MAP[$p]-}" ]; then
    log "REFUSED: $p (no gate receipt - $RECEIPT_STATE)"; continue
  fi
  if [ ! -f "$REPO/$p" ]; then
    log "REFUSED: $p (receipted but not a readable file)"; continue
  fi
  H=$(sha256_of "$REPO/$p") || { log "REFUSED: $p (no sha256 tool available to verify it)"; continue }
  if [ "$H" != "${RECEIPT_MAP[$p]}" ]; then
    # The one-shot binding is to a VERSION, not a filename. Without it an author could
    # receipt a file that a foreign process then rewrites before the timer fires - the
    # exact race the gate exists to close.
    log "REFUSED: $p (content changed after the receipt was written)"; continue
  fi
  TO_STAGE+=("$p")
done <<< "$(git status --porcelain -uall 2>>"$LOG")"

if [ ${#TO_STAGE[@]} -gt 0 ]; then
  git add --ignore-removal -- "${TO_STAGE[@]}" 2>>"$LOG"
fi
# Never stage symlinks themselves: they carry machine-absolute targets, and a symlinked-away
# skill dir reads as a deletion whose propagation would strip skills off other machines.
git diff --cached --name-only | while read -r f; do
  [ -L "$REPO/$f" ] && git restore --staged "$f" && log "unstaged symlink: $f"
done
# Defence in depth: if the staging logic above is ever wrong, a never-sync path still does
# not reach a commit. Fails closed rather than committing what it could not unstage - a
# restore that errors and is ignored would leave the path staged and publish it.
for f in ${(f)"$(git diff --cached --name-only)"}; do
  [ -z "$f" ] && continue
  if is_never_sync "$f"; then
    if ! git restore --staged -- "$f" 2>>"$LOG"; then
      log "FAIL: could not unstage never-sync path $f; commit and push skipped"
      exit 1
    fi
    log "REFUSED: unstaged never-sync path $f"
  fi
done
if ! git diff --cached --quiet; then
  STAGED=(${(f)"$(git diff --cached --name-only)"})
  if ! git commit --quiet -m "chore(sync): $(hostname -s) auto-sync $(ts) [receipted: ${#STAGED[@]} file(s)]" 2>>"$LOG"; then
    log "FAIL: commit; nothing published"
    exit 1
  fi
  log "committed ${#STAGED[@]} receipted file(s): ${(j:, :)STAGED}"
  rm -f "$RECEIPT"
  log "receipt consumed"
fi

# skills-library is exempted from the pr-release-gate receipt requirement itself
# (pr_release_gate.py, commit b3e01d9, 19/07/2026: "automation-synced sync repo").
# That exemption is about not requiring the heavyweight PR+independent-review
# machinery for THIS repo's routine housekeeping — it is not a licence for this
# timer to ship a deliberate commit an interactive session left on main mid-decision.
# Only this script's OWN auto-sync commits (pure machine-state drift, decided by
# nobody, reviewed by nothing) are safe to push unattended. Any other commit ahead
# of origin/main was authored by a session that made a choice — branch it, PR it,
# push it themselves — and this cron is not that choice.
# Concrete: on 06/08/2026 an interactive session's own `git commit` landed on local
# main and this script pushed it to origin within one 15-minute cycle, with no
# review of any kind, before the session had decided how to release it.
AHEAD=$(git log origin/main..main --format='%H%x09%s' 2>>"$LOG")
if [ $? -ne 0 ]; then
  log "FAIL: could not enumerate commits ahead of origin/main"
  exit 1
fi
if [ -n "$AHEAD" ]; then
  HELD=0
  while IFS=$'\t' read -r sha subject; do
    [ -z "$sha" ] && continue
    case "$subject" in
      "chore(sync): "*" auto-sync "*) ;;
      *)
        log "  held: ${sha:0:12} $subject"
        HELD=1
        ;;
    esac
  done <<< "$AHEAD"
  if [ "$HELD" -eq 1 ]; then
    log "skip: non-sync commit(s) ahead of origin/main — a session must push these deliberately; auto-push skipped"
    exit 0
  fi
  # Last check before the payload becomes public and permanent. A receipt proves someone
  # NAMED the file; it does not prove they read every line of it. Scans the added lines of
  # the whole push payload, not just this cycle's staging, because a credential committed
  # three cycles ago is still unpublished until this push and still catchable here.
  DIFF_TMP=$(mktemp) || { log "FAIL: could not create a scratch file for the secret scan; push skipped"; exit 1 }
  ADDED_TMP=$(mktemp) || { rm -f "$DIFF_TMP"; log "FAIL: could not create a scratch file for the secret scan; push skipped"; exit 1 }
  if ! git diff origin/main..HEAD > "$DIFF_TMP" 2>>"$LOG"; then
    rm -f "$DIFF_TMP" "$ADDED_TMP"
    log "FAIL: could not diff the push payload for secrets; push skipped"
    exit 1
  fi
  # Attribute each added line to its file so a hit can be reported by name without the
  # matched text ever being written anywhere.
  awk '/^\+\+\+ b\// { f = substr($0, 7); next }
       /^\+/ && !/^\+\+\+/ { print f "\t" substr($0, 2) }' "$DIFF_TMP" > "$ADDED_TMP"
  HITS=0
  for entry in "${SECRET_PATTERNS[@]}"; do
    sname="${entry%%$'\t'*}"
    srx="${entry#*$'\t'}"
    n=$(grep -E -c -e "$srx" "$ADDED_TMP" 2>/dev/null || true)
    [ -z "$n" ] && n=0
    if [ "$n" -gt 0 ]; then
      for hf in ${(f)"$(grep -E -e "$srx" "$ADDED_TMP" | cut -f1 | sort -u)"}; do
        [ -z "$hf" ] && continue
        log "SECRET-SCAN: $sname matched in $hf (value not logged)"
      done
      HITS=$((HITS + n))
    fi
  done
  rm -f "$DIFF_TMP" "$ADDED_TMP"
  if [ "$HITS" -gt 0 ]; then
    log "REFUSED: push blocked - $HITS secret-shaped match(es) in the diff about to be published; reconcile by hand"
    exit 1
  fi
  if git push origin main --quiet 2>>"$LOG"; then
    log "pushed to origin/main (secret-scan clean)"
  else
    log "FAIL: push (will retry next cycle)"
    exit 1
  fi
fi
log "ok: in sync"
