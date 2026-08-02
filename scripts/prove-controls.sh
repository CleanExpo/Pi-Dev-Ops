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
hdr "C-DISCOVERY — a NEW surface is covered without editing any list"
# The class: a check that knows a fixed set is a check that goes stale silently. It bit the
# navigation detector (four rounds of patterns), C12's entry pages, the auth suite's page list,
# and the auth suite's API list — where /api/command-centre/provider-usage entered with no
# coverage at all. This control plants a brand-new page AND a brand-new API route and asserts
# the auth suite grows to cover them on its own.
count_auth_tests() {
  ( cd dashboard && npx vitest run __tests__/command-centre-auth-coverage.test.ts 2>&1 )     | grep -oE 'Tests +[0-9]+ passed' | grep -oE '[0-9]+' | head -1
}
# An UNCLASSIFIED api route must fail the classification check. This is the control for the
# omission that left /api/kill-switch POST reachable with no credential: it was in neither
# proxy prefix list, so nothing decided anything about it.
UNCL='dashboard/app/api/__control-unclassified'
CLEANUP+=("rm -rf '$ROOT/$UNCL'")
CMREF="$(mktemp)"; CLEANUP+=("rm -f '$CMREF'"); touch -r dashboard/app/api "$CMREF"
mkdir -p "$UNCL"
echo 'export async function POST() { return new Response("{}") }' > "$UNCL/route.ts"
( cd dashboard && npx vitest run __tests__/api-auth-classification.test.ts >/dev/null 2>&1 )
[ $? -ne 0 ] && ok "an unclassified API route fails the classification check"              || bad "a NEW unclassified API route passed — the omission class is open again"
rm -rf "$UNCL"; touch -r "$CMREF" dashboard/app/api
( cd dashboard && npx vitest run __tests__/api-auth-classification.test.ts >/dev/null 2>&1 )
[ $? -eq 0 ] && ok "classification green once the route is classified/removed"              || bad "still red after removing the planted route"

BASE_N="$(count_auth_tests)"
NEWPAGE='dashboard/app/(main)/command-centre/__control-surface'
NEWAPI='dashboard/app/api/command-centre/__control-route'
CLEANUP+=("rm -rf '$ROOT/$NEWPAGE' '$ROOT/$NEWAPI'")
# Planting directories changes the mtime of their PARENTS, which makes C12's freshness check
# read the build as stale for the rest of the run. Snapshot and restore, or this control
# breaks the control that follows it — which it did, on its first full run.
PMREF="$(mktemp)"; AMREF="$(mktemp)"; CLEANUP+=("rm -f '$PMREF' '$AMREF'")
touch -r 'dashboard/app/(main)/command-centre' "$PMREF"
touch -r 'dashboard/app/api/command-centre' "$AMREF"
mkdir -p "$NEWPAGE" "$NEWAPI"
echo 'export default function P() { return null }' > "$NEWPAGE/page.tsx"
echo 'export async function GET() { return new Response("{}") }' > "$NEWAPI/route.ts"
GROWN_N="$(count_auth_tests)"
rm -rf "$NEWPAGE" "$NEWAPI"
touch -r "$PMREF" 'dashboard/app/(main)/command-centre'
touch -r "$AMREF" 'dashboard/app/api/command-centre'
FINAL_N="$(count_auth_tests)"
if [ -n "$BASE_N" ] && [ -n "$GROWN_N" ] && [ "$GROWN_N" -gt "$BASE_N" ]; then
  ok "auth coverage grew ${BASE_N} -> ${GROWN_N} for a new page + new API route, no list edited"
else
  bad "a new page and API route did NOT add coverage (${BASE_N} -> ${GROWN_N}) — a fixed enumeration has crept back"
fi
[ "$FINAL_N" = "$BASE_N" ] && ok "returns to ${BASE_N} once the planted surface is removed"                            || bad "did not return to baseline (${FINAL_N} vs ${BASE_N})"

# ─────────────────────────────────────────────────────────────────────────────
if [ "$FAST" = 0 ]; then
hdr "C12 — runtime route exercising (needs a build; ~90s)"
# ESTABLISH the precondition; do not merely hope for it.
#
# Round-2 review ran this script and got 17/22 — five C12 controls "failed" while
# "refuses to run against a stale build" PASSED. That combination is the signature: every
# C12 invocation returned exit 2 because the build was older than the source, so the
# controls were reporting the precondition, not the thing under test.
#
# It passed 22/22 for me and 17/22 for them from the same tree. That is the "works on my
# machine" failure applied to a control suite, and by this estate's own standard a control
# that is not reproducible is not a control. So this block now BUILDS when the build is
# stale rather than depending on whoever ran it having built recently.
if [ -f dashboard/.next/BUILD_ID ]; then
  node scripts/route-exercise.mjs >/dev/null 2>&1
  if [ $? -eq 2 ]; then
    echo "  NOTE  build is stale — building now so the C12 controls test C12, not the build"
    ( cd dashboard && PI_CEO_URL=https://x.invalid PI_CEO_PASSWORD=x       NEXT_PUBLIC_SUPABASE_URL=https://lksfwktwtmyznckodsau.supabase.co       NEXT_PUBLIC_SUPABASE_ANON_KEY=x SUPABASE_SERVICE_ROLE_KEY=x       npm run build >/dev/null 2>&1 )
    node scripts/route-exercise.mjs >/dev/null 2>&1
    [ $? -eq 0 ] && ok "precondition established: build is fresh"                  || bad "could not establish a fresh build — C12 results below would be meaningless"
  else
    ok "precondition: build was already fresh"
  fi
  # Round-4 review, two defects in THIS script:
  #   · it left page.tsx touched after the stale-build test, so a SECOND run failed at the
  #     clean-surface step — the proof script was not idempotent, and the reviewer hit it.
  #   · planted controls asserted "nonzero", which would accept a crash as a pass. Assert 1.
  PAGE='dashboard/app/(main)/command-centre/page.tsx'
  MTREF="$(mktemp)"; touch -r "$PAGE" "$MTREF"; CLEANUP+=("rm -f '$MTREF'")

  node scripts/route-exercise.mjs --plant-broken-link >/dev/null 2>&1
  [ $? -eq 1 ] && ok "fails (exit 1) on a planted unresolvable link"                || bad "planted broken link did not produce exit 1"
  # Round-3 finding: a link 307ing to a MISSING page passed green, since the hop is neither
  # 404 nor 5xx. Synthetic server, because the app has no redirect chain to borrow.
  node scripts/route-exercise.mjs --self-test-redirects >/dev/null 2>&1
  [ $? -eq 0 ] && ok "redirect walker: 307->404 reports 404, loop reported, 307->200 passes"                || bad "redirect walker did not discriminate"
  # Round-2 finding: the extractor matched slash-prefixed hrefs only, so a rendered RELATIVE
  # link was unmeasured. If this stops failing, that regression is back.
  node scripts/route-exercise.mjs --plant-relative-link >/dev/null 2>&1
  [ $? -eq 1 ] && ok "fails (exit 1) on a planted RELATIVE link (no leading slash)"                || bad "planted relative link did not produce exit 1"

  # Round-4: page discovery must track the route tree, not a hard-coded list.
  ON_DISK=$(find 'dashboard/app/(main)/command-centre' -name 'page.tsx' 2>/dev/null | wc -l | tr -d ' ')
  RENDERED=$(node scripts/route-exercise.mjs 2>&1 | grep -oE 'rendered [0-9]+ pages' | grep -oE '[0-9]+')
  [ -n "$RENDERED" ] && [ "$RENDERED" = "$ON_DISK" ]     && ok "renders every page.tsx on disk ($RENDERED = $ON_DISK) — discovery is not a stale list"     || bad "rendered '$RENDERED' pages but $ON_DISK page.tsx exist — discovery has drifted"

  node scripts/route-exercise.mjs >/dev/null 2>&1
  [ $? -eq 0 ] && ok "passes on the clean surface" || bad "red on a clean surface"

  touch "$PAGE"
  node scripts/route-exercise.mjs >/dev/null 2>&1
  [ $? -eq 2 ] && ok "refuses to run against a stale build" || bad "ran against a stale build"
  touch -r "$MTREF" "$PAGE"   # restore mtime — this script must be re-runnable
  node scripts/route-exercise.mjs >/dev/null 2>&1
  [ $? -eq 0 ] && ok "idempotent: clean again after the stale-build test"                || bad "left the tree dirty — a second run of this script would fail"
else
  echo "  SKIP  no dashboard build present"
fi
fi

echo
echo "════ CONTROLS PROVEN: pass=$PASS fail=$FAIL"
[ "$FAIL" -eq 0 ] || { echo "════ A CONTROL DID NOT DISCRIMINATE — the checks it guards prove nothing."; exit 1; }
echo "════ every control above was observed RED on a planted defect and GREEN without it"
