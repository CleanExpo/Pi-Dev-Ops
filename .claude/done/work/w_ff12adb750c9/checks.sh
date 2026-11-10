#!/usr/bin/env bash
# Verifier for M-PDO-REAPER-CLOUD-CLAIM-TTL. Locked with the contract.
# usage: checks.sh <red|new|area|ruff|size|scope>
set -u
BASE=bd7d36828c2481b0dae5254f5bb50855c978642a
PY=/Users/phill-mac/Pi-Dev-Ops/.venv/bin/python
WT="/Volumes/Mini Mini 2T Storage/worktrees/Pi-Dev-Ops/reaper-cloud-claim"
cd "$WT" || exit 2
NEWTEST=tests/test_mesh_cloud_claim_renewal.py
OUT="/Volumes/Mini Mini 2T Storage/worktrees/Pi-Dev-Ops/reaper-cloud-claim-check.out"
changed() {
  { git diff --name-only "$BASE"; git ls-files --others --exclude-standard; } | sort -u
}
case "${1:-}" in
  red)
    # The new tests must FAIL on the untouched base commit; its positive controls must pass there.
    S="/Volumes/Mini Mini 2T Storage/worktrees/Pi-Dev-Ops/reaper-cloud-claim-redcheck"
    rm -rf "$S"
    git worktree add --detach "$S" "$BASE" >/dev/null 2>&1 || exit 2
    cp "$NEWTEST" "$S/$NEWTEST"
    ( cd "$S" && "$PY" -m pytest "$NEWTEST" -p no:cacheprovider -q > "$OUT" 2>&1 )
    RC=$?
    git worktree remove --force "$S" >/dev/null 2>&1
    tail -15 "$OUT"
    FAILED=$(grep -Eo '[0-9]+ failed' "$OUT" | grep -Eo '[0-9]+')
    PASSED=$(grep -Eo '[0-9]+ passed' "$OUT" | grep -Eo '[0-9]+')
    echo "base: failed=${FAILED:-0} passed=${PASSED:-0} rc=$RC"
    [ "$RC" -eq 1 ] && [ "${FAILED:-0}" -ge 4 ] && [ "${PASSED:-0}" -ge 2 ]
    ;;
  new)
    "$PY" -m pytest "$NEWTEST" -p no:cacheprovider -q
    ;;
  area)
    FILES=$(grep -rlE "mesh_reaper|session_lease|autonomy_queue|claim_renewal|mesh_work_claims" tests --include='test_*.py' | sort)
    echo "$FILES"
    "$PY" -m pytest $FILES -p no:cacheprovider -q
    ;;
  ruff)
    CH=$(changed | grep '\.py$')
    echo "$CH"
    "$PY" -m ruff check $CH
    ;;
  size)
    "$PY" .github/scripts/file_length_lint.py
    ;;
  scope)
    CH=$(changed)
    echo "$CH"
    ! echo "$CH" | grep -E '^(app/server/autonomy\.py|supabase/|mesh/schema/)'
    ;;
  *) echo "unknown"; exit 2;;
esac
