#!/usr/bin/env bash
# prove-controls.sh — run each control against a PLANTED DEFECT and prove it goes red.
#
# WHY THIS IS IN THE REPO
#
# Every control built on 2026-08-01/02 was proven by watching a terminal. Those transcripts
# live in `.harness/*.txt`, which is gitignored — so the proof that the harness works was
# not in the harness. Third instance of that shape after `incidents.jsonl` (evidence that
# existed only on one machine) and `proof-discipline` (a lesson that lived only in a
# gitignored skills dir). A verifier's proof must be reproducible from the repo, not
# asserted from a transcript nobody else can read.
#
# Each check below plants a defect the control MUST catch, asserts it goes red, removes the
# defect, and asserts it goes green again. A control that cannot be shown to fail is not a
# control. See "The First Run of a New Control Is the FAILING One" in
# skills/proof-discipline/SKILL.md for why every accident here landed on green.
#
# Usage: bash scripts/prove-controls.sh [--fast]
#   --fast   skip the two controls that need a running Next server (~90s)
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FAST=0; [ "${1:-}" = "--fast" ] && FAST=1

PASS=0; FAIL=0
ok()   { echo "  PASS  $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }
hdr()  { echo; echo "── $1"; }

# Every planted artefact is registered here so an early exit still cleans up.
CLEANUP=()
cleanup() { for c in "${CLEANUP[@]:-}"; do eval "$c" >/dev/null 2>&1; done; }
trap cleanup EXIT

# ─────────────────────────────────────────────────────────────────────────────
hdr "C-TREE — review tree-integrity detects a repo mutation"
# Blind to gitignored paths BY DESIGN (the reviewer must write .next/ to run the suite),
# so the planted file must be somewhere git will actually report. Getting this wrong is
# how the control silently passed twice: both plants used *.tmp, ignored repo-wide.
tree_hash() { git status --porcelain | sort | sha256sum | cut -d' ' -f1; }
before="$(tree_hash)"
CLEANUP+=("rm -f '$ROOT/docs/.control-plant.md'")
echo "planted" > docs/.control-plant.md
after="$(tree_hash)"
rm -f docs/.control-plant.md
restored="$(tree_hash)"
[ "$before" != "$after" ] && ok "detects a new non-ignored file" || bad "MISSED a new non-ignored file"
[ "$before" = "$restored" ] && ok "restores exactly (no false positive)" || bad "false positive after cleanup"
# And prove the documented blind spot really is one, so the scope claim is evidenced too.
CLEANUP+=("rm -f '$ROOT/docs/.control-plant.tmp'")
echo x > docs/.control-plant.tmp
[ "$(tree_hash)" = "$before" ] && ok "blind to gitignored paths (documented limit, confirmed)" \
                               || bad "unexpectedly saw an ignored path"
rm -f docs/.control-plant.tmp

# ─────────────────────────────────────────────────────────────────────────────
hdr "C-CFG — codex config detector ignores churn, catches escalation"
CFG="$HOME/.codex/config.toml"
if [ -f "$CFG" ]; then
  cfg_hash() { grep -vE '^\s*(last_updated|last_revision)\s*=' "$1" | sha256sum | cut -d' ' -f1; }
  real="$(cfg_hash "$CFG")"
  T="$(mktemp -d)"; CLEANUP+=("rm -rf '$T'")
  sed 's/^last_updated = .*/last_updated = "2099-01-01T00:00:00Z"/' "$CFG" > "$T/churn.toml"
  sed 's/^sandbox_mode = .*/sandbox_mode = "danger-full-access"/' "$CFG" > "$T/widen.toml"
  printf '\n[projects.%s]\ntrust_level = "trusted"\n' "'d:\\attacker'" >> "$T/trust.toml.base" 2>/dev/null
  cat "$CFG" "$T/trust.toml.base" > "$T/trust.toml" 2>/dev/null
  [ "$(cfg_hash "$T/churn.toml")" = "$real" ] && ok "ignores marketplace timestamp churn" \
                                              || bad "false positive on benign churn"
  [ "$(cfg_hash "$T/widen.toml")" != "$real" ] && ok "detects a widened sandbox_mode" \
                                               || bad "MISSED a widened sandbox_mode"
  [ "$(cfg_hash "$T/trust.toml")" != "$real" ] && ok "detects a new trusted project" \
                                               || bad "MISSED a new trusted project"
else
  echo "  SKIP  ~/.codex/config.toml not present"
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "C-EXEC — execution-proof grep distinguishes a run from a non-run"
EXEC_RE="Tests +[0-9]+ (passed|failed)|Test Files +[0-9]+"
T2="$(mktemp -d)"; CLEANUP+=("rm -rf '$T2'")
printf 'reviewer said it all looks fine\nVERDICT: PASS\n' > "$T2/no-run.txt"
printf ' Test Files  1 passed (1)\n      Tests  7 passed (7)\n' > "$T2/ran.txt"
grep -qE "$EXEC_RE" "$T2/no-run.txt" && bad "claimed execution on a transcript with none" \
                                     || ok "reports ABSENT when the suite did not run"
grep -qE "$EXEC_RE" "$T2/ran.txt" && ok "reports FOUND when the suite did run" \
                                  || bad "MISSED a real suite run"

# ─────────────────────────────────────────────────────────────────────────────
hdr "C10/C4 — a declared delta only excuses its EXACT magnitude"
# The original bug: keying on file+rule alone excused any magnitude, forever.
PROV="dashboard/__tests__/command-centre-provenance.json"
cp "$PROV" "$PROV.bak"; CLEANUP+=("mv -f '$ROOT/$PROV.bak' '$ROOT/$PROV' 2>/dev/null")
perl -0pi -e 's/("auth gate": \{\s*"from": 3,\s*)"to": 0,/$1"to": 1,/s' "$PROV"
( cd dashboard && npx vitest run __tests__/command-centre-readonly.test.ts >/dev/null 2>&1 )
[ $? -ne 0 ] && ok "rejects a declared 3->1 against an actual 3->0" \
             || bad "accepted an off-magnitude exemption"
mv -f "$PROV.bak" "$PROV"
( cd dashboard && npx vitest run __tests__/command-centre-readonly.test.ts >/dev/null 2>&1 )
[ $? -eq 0 ] && ok "green again once the declaration matches" || bad "still red after restore"

# ─────────────────────────────────────────────────────────────────────────────
hdr "C-SECRETS — the scanner sees gitignored files (fixed 2026-08-02)"
# Before the fix this planted secret was invisible: --exclude-standard dropped it.
# --dry-run matters: without it the scanner appends the offending path to .gitignore.
FAKE="AKIA""ZZZZQQQQ1111WWWW"
CLEANUP+=("rm -f '$ROOT/docs/.control-secret.tmp'")
printf "const k = '%s'\n" "$FAKE" > docs/.control-secret.tmp
# Capture FIRST, then grep. secrets_check.py exits 1 when it finds a violation — which is
# the success case here — and under `pipefail` that made the whole pipeline non-zero even
# though grep matched, so this reported FAIL against a working scanner. Same family as
# measuring an exit code through `| head`. Never let a pipeline's exit stand in for a match.
SEC_OUT="$(python scripts/secrets_check.py --dry-run 2>&1 || true)"
case "$SEC_OUT" in
  *control-secret*) ok "detects a secret inside a gitignored path" ;;
  *) bad "MISSED a secret in a gitignored path — the --exclude-standard defect is back" ;;
esac
rm -f docs/.control-secret.tmp

# ─────────────────────────────────────────────────────────────────────────────
if [ "$FAST" = 0 ]; then
hdr "C12 — runtime route exercising (needs a build; ~90s)"
if [ -f dashboard/.next/BUILD_ID ]; then
  node scripts/route-exercise.mjs --plant-broken-link >/dev/null 2>&1
  [ $? -ne 0 ] && ok "fails on a planted unresolvable link" || bad "passed with a broken link"
  node scripts/route-exercise.mjs >/dev/null 2>&1
  [ $? -eq 0 ] && ok "passes on the clean surface" || bad "red on a clean surface"
  touch "dashboard/app/(main)/command-centre/page.tsx"
  node scripts/route-exercise.mjs >/dev/null 2>&1
  [ $? -eq 2 ] && ok "refuses to run against a stale build" || bad "ran against a stale build"
  echo "  NOTE  source touched — rebuild before relying on C12 again"
else
  echo "  SKIP  no dashboard build present"
fi
fi

echo
echo "════ CONTROLS PROVEN: pass=$PASS fail=$FAIL"
[ "$FAIL" -eq 0 ] || { echo "════ A CONTROL DID NOT DISCRIMINATE — the checks it guards prove nothing."; exit 1; }
echo "════ every control above was observed RED on a planted defect and GREEN without it"
