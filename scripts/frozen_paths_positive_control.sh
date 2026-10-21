#!/bin/bash
# Positive control for check_frozen_paths.py on the real tree: plant an edit to a
# frozen file in a throwaway worktree commit and require the guard to fail naming it.
# Leaves the caller's worktree untouched. Exit 0 only if the guard caught the plant.
set -u
TARGET="app/server/tao_loop.py"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
SCRATCH_PARENT="${FROZEN_CONTROL_TMP:-${TMPDIR:-/tmp}}"
TMP=$(mktemp -d "$SCRATCH_PARENT/frozen-control.XXXXXX") || exit 2
cleanup() { git worktree remove --force "$TMP" >/dev/null 2>&1; rm -rf "$TMP"; }
trap cleanup EXIT

git worktree add --quiet --detach "$TMP" HEAD || exit 2
[ -f "$TMP/$TARGET" ] || { echo "precondition failed: $TARGET absent — control would be vacuous"; exit 2; }
python3 "$ROOT/scripts/check_frozen_paths.py" --verify-manifest >/dev/null \
  || { echo "precondition failed: manifest not sound at HEAD"; exit 2; }

echo "# frozen-paths positive control" >> "$TMP/$TARGET"
git -C "$TMP" -c user.name=frozen-control -c user.email=frozen-control@invalid \
  commit --quiet -am "planted edit to a frozen file" || exit 2
PLANT=$(git -C "$TMP" rev-parse HEAD)

OUT="$TMP/.guard-output"
(cd "$TMP" && python3 "$ROOT/scripts/check_frozen_paths.py" --base HEAD~1 --head "$PLANT") > "$OUT" 2>&1
RC=$?
cat "$OUT"
if [ "$RC" -eq 1 ] && grep -q "  $TARGET$" "$OUT"; then
  echo "CONTROL PASS: guard failed on the planted edit to $TARGET"
  exit 0
fi
echo "CONTROL FAIL: guard exit $RC did not name $TARGET"
exit 1
