#!/usr/bin/env bash
# Smoke test for delete-plaud-recording.sh (file-system part only — Supabase is stubbed).
set -e

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Build a fake wiki + env
mkdir -p "$TMP/2nd Brain/2nd Brain/Wiki/plaud"
echo "# Foo" > "$TMP/2nd Brain/2nd Brain/Wiki/plaud/2026-05-17-foo.md"
echo "# Foo part 2" > "$TMP/2nd Brain/2nd Brain/Wiki/plaud/2026-05-17-foo-part2.md"
echo "# Log" > "$TMP/2nd Brain/2nd Brain/Wiki/log.md"
mkdir -p "$TMP/.hermes"
cat > "$TMP/.hermes/.env" <<EOF
SUPABASE_UNITE_GROUP_URL=http://127.0.0.1:9
SUPABASE_UNITE_GROUP_SERVICE_KEY=fake
EOF

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOME="$TMP" \
  "$SCRIPT_DIR/scripts/delete-plaud-recording.sh" 2026-05-17-foo

# Assert both files are gone
test ! -f "$TMP/2nd Brain/2nd Brain/Wiki/plaud/2026-05-17-foo.md"
test ! -f "$TMP/2nd Brain/2nd Brain/Wiki/plaud/2026-05-17-foo-part2.md"
# Assert log line added
grep -q "plaud-delete" "$TMP/2nd Brain/2nd Brain/Wiki/log.md"

echo "PASS: delete-plaud-recording.sh"
