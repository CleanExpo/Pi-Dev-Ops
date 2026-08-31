#!/usr/bin/env bash
# test_claude_memory_backup.sh - red-then-green proof suite for the memory-source
# resolution in scripts/claude_memory_backup.sh. The property under test is that the
# script never backs up a memory directory the operator did not ask for: an explicit
# CLAUDE_MEMORY_DIR is never silently swapped, and an ambiguous basename match is
# refused rather than guessed. Guessing would push ANOTHER PROJECT'S MEMORY to
# $CLAUDE_MEMORY_REMOTE, which is a disclosure, not a mispick.
#
# WHY THIS SUITE NEVER TOUCHES A GIT REMOTE
# The script under test commits and pushes. This suite therefore does NOT run it.
# It awk-extracts only the path-resolution slice - from `set -u` down to (but not
# including) the CLAUDE_MEMORY_REMOTE check - and runs that slice against fake $HOME
# trees under mktemp. Everything after that line (git init / add / commit / push /
# remote set-url) is outside the extracted text, so there is no code path from here to
# a network call. E0 asserts that property on the extracted bytes rather than trusting
# this comment.
#
# WHAT BREAKS THE EXTRACTION: moving the `CLAUDE_MEMORY_REMOTE:-` check away from its
# position immediately after the memory-dir resolution, or renaming that variable, or
# dropping the `set -u` line. Any of those changes what the awk slice captures - too
# little and every case fails at once; too much and E0 fails loudly because git write
# verbs appear in the slice. Fix the awk range, never widen E0.
#
# Green controls are not padding: without them an exit-2 assertion could be passing
# because the fixture is broken rather than because the guard fired.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
# Overridable so this suite can be pointed at a deliberately-sabotaged copy to prove
# it actually fails when the fix is absent. Defaults to the real script.
SRC="${CLAUDE_MEMORY_BACKUP_SH:-$ROOT/scripts/claude_memory_backup.sh}"
T="$(mktemp -d)"
BODY="$T/resolution.body"
PASS=0; FAIL=0

trap 'rm -rf "$T"' EXIT

say() { printf '%s\n' "$*"; }
ok()  { PASS=$((PASS+1)); say "  PASS: $1"; }
bad() { FAIL=$((FAIL+1)); say "  FAIL: $1"; }

# expect: assert the exit code and (optionally) a diagnostic substring, so a case
# cannot pass because some unrelated check failed first.
expect() { # expect <name> <want_rc> <got_rc> <log> [pattern]
  local name="$1" want="$2" got="$3" log="$4" pat="${5:-}"
  if [ "$got" -ne "$want" ]; then
    bad "$name (want rc=$want got rc=$got)"; sed 's/^/    | /' "$log" | tail -4; return
  fi
  if [ -n "$pat" ] && ! grep -qF "$pat" "$log"; then
    bad "$name (rc ok but diagnostic missing: '$pat')"; sed 's/^/    | /' "$log" | tail -4; return
  fi
  ok "$name"
}

# refute: assert a substring is ABSENT from the log.
refute() { # refute <name> <log> <pattern>
  if grep -qF "$3" "$2"; then
    bad "$1 (unexpected: '$3')"; sed 's/^/    | /' "$2" | tail -4
  else
    ok "$1"
  fi
}

say "== Extraction (offline guarantee) =="

awk '/^set -u/{f=1} f && /CLAUDE_MEMORY_REMOTE:-/{exit} f{print}' "$SRC" > "$BODY"

if [ ! -s "$BODY" ]; then
  bad "E0a extraction produced a non-empty slice"
  say "    the awk range no longer matches $SRC - see WHAT BREAKS THE EXTRACTION above"
  say "== SUMMARY pass=$PASS fail=$FAIL =="; exit 1
fi
ok "E0a extraction produced a non-empty slice ($(wc -l < "$BODY") lines)"

# The offline property, asserted on bytes rather than assumed.
if grep -nE 'git (init|add|commit|push|remote)' "$BODY" >/dev/null; then
  bad "E0b extracted slice contains no git write verbs"
  grep -nE 'git (init|add|commit|push|remote)' "$BODY" | sed 's/^/    | /'
else
  ok "E0b extracted slice contains no git write verbs (cannot reach a remote)"
fi

# Positive control on E0b itself: the same grep MUST hit on the whole script, or E0b
# is a broken query returning a comforting null.
if grep -qE 'git (init|add|commit|push|remote)' "$SRC"; then
  ok "E0c control: that grep does fire on the full script (E0b is a real check)"
else
  bad "E0c control: grep found no git verbs in the full script - the query is broken"
fi

# run_case <label> <repo-basename> <explicit-CLAUDE_MEMORY_DIR-or-empty> [project dirs...]
# A project dir named @DERIVED means "the encoded path of this fake checkout", i.e.
# the happy path where no fallback is needed.
CASE_ROOT=""; CASE_LOG=""; CASE_RC=0; CASE_ENC=""
run_case() {
  local label="$1" reponame="$2" explicit="$3"; shift 3
  local work d
  CASE_ROOT="$T/$label"; CASE_LOG="$T/$label.log"
  work="$CASE_ROOT/work/$reponame"
  rm -rf "$CASE_ROOT"
  mkdir -p "$CASE_ROOT/home/.claude/projects" "$work/scripts"
  # Mirror the script's own encoding of an absolute path.
  CASE_ENC="${work//\//-}"; CASE_ENC="${CASE_ENC//./-}"
  for d in "$@"; do
    [ "$d" = "@DERIVED" ] && d="$CASE_ENC"
    mkdir -p "$CASE_ROOT/home/.claude/projects/$d/memory"
  done
  { cat "$BODY"; printf 'printf "RESOLVED %%s\\n" "$MEMORY_DIR"\nexit 0\n'; } \
    > "$work/scripts/snippet.sh"
  if [ -n "$explicit" ]; then
    env HOME="$CASE_ROOT/home" CLAUDE_MEMORY_DIR="$explicit" \
      bash "$work/scripts/snippet.sh" >"$CASE_LOG" 2>&1
  else
    env -u CLAUDE_MEMORY_DIR HOME="$CASE_ROOT/home" \
      bash "$work/scripts/snippet.sh" >"$CASE_LOG" 2>&1
  fi
  CASE_RC=$?
}
P() { printf '%s/home/.claude/projects/%s/memory' "$CASE_ROOT" "$1"; }

say "== Red cases (must refuse) =="

# R1: two projects share the basename. Picking either would publish one project's
# memory under the other's backup remote.
run_case r1 Pi-Dev-Ops '' -Users-alice-Pi-Dev-Ops -home-bob-clientwork-Pi-Dev-Ops
expect "R1 ambiguous basename refused" 7 "$CASE_RC" "$CASE_LOG" "ambiguous memory dir"
expect "R1b both candidates named in the diagnostic" 7 "$CASE_RC" "$CASE_LOG" \
  "candidate: $(P -home-bob-clientwork-Pi-Dev-Ops)"

# R2: the operator named a source that does not exist yet, and an unrelated project
# shares the basename. The fallback must NOT substitute it.
run_case r2 Pi-Dev-Ops "$T/r2/home/.claude/projects/-my-intended-dir/memory" \
  -Users-someone-else-Pi-Dev-Ops
expect "R2 explicit CLAUDE_MEMORY_DIR is not overridden" 2 "$CASE_RC" "$CASE_LOG" \
  "memory dir not found: $(P -my-intended-dir)"
refute "R2b no fallback was attempted at all" "$CASE_LOG" "falling back"

# R3: nothing matches - unchanged pre-existing behaviour, not a new refusal.
run_case r3 Pi-Dev-Ops '' -Users-alice-SomethingElse
expect "R3 no candidate still exits 2" 2 "$CASE_RC" "$CASE_LOG" "memory dir not found"

say "== Green controls (harness must be able to pass) =="

# G1: exactly one candidate. This is the control that makes every rc=2/rc=7 assertion
# above meaningful - it proves the fixture can resolve a directory at all.
run_case g1 Pi-Dev-Ops '' -Users-alice-Pi-Dev-Ops
expect "G1 single candidate resolves" 0 "$CASE_RC" "$CASE_LOG" \
  "RESOLVED $(P -Users-alice-Pi-Dev-Ops)"

# G2: dotted repo basename. The encoded directory ends in -my-repo, so the fallback
# must encode the basename before matching or this repo can never be backed up.
run_case g2 my.repo '' -Users-phill-my-repo
expect "G2 dotted basename matches its encoded directory" 0 "$CASE_RC" "$CASE_LOG" \
  "RESOLVED $(P -Users-phill-my-repo)"

# G3: happy path - the derived path exists, so the fallback must not run even though
# a same-basename decoy is present.
run_case g3 Pi-Dev-Ops '' @DERIVED -Users-decoy-Pi-Dev-Ops
expect "G3 derived path wins over a decoy" 0 "$CASE_RC" "$CASE_LOG" \
  "RESOLVED $(P "$CASE_ENC")"
refute "G3b fallback did not fire on the happy path" "$CASE_LOG" "falling back"

say "== Edge cases =="

# E1: empty projects/. An unmatched glob under `set -u` must not crash or resolve.
run_case e1 Pi-Dev-Ops ''
expect "E1 empty projects dir exits 2 without crashing" 2 "$CASE_RC" "$CASE_LOG" \
  "memory dir not found"
refute "E1b no bash error from the unmatched glob" "$CASE_LOG" "unbound variable"

# E2: a project directory whose name contains glob metacharacters must not be treated
# as a pattern that widens the match.
run_case e2 Pi-Dev-Ops '' '-Users-x-[Pp]i-Dev-Ops' -Users-y-Other
expect "E2 metacharacters in a project name do not widen the match" 2 "$CASE_RC" \
  "$CASE_LOG" "memory dir not found"

say "== SUMMARY pass=$PASS fail=$FAIL =="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
