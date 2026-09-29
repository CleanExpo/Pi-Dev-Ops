#!/bin/sh
# Re-vendor the K-Dense scientific skills from upstream into library/.
# Review the diff, then commit to skills-library so every machine gets it
# on the next `sh ~/.claude/bootstrap.sh`.
set -e

UPSTREAM="https://github.com/K-Dense-AI/scientific-agent-skills.git"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "Fetching $UPSTREAM ..."
git clone --depth 1 --quiet "$UPSTREAM" "$TMP/src"

if [ ! -d "$TMP/src/skills" ]; then
  echo "error: upstream layout changed — no skills/ directory. Aborting." >&2
  exit 1
fi

echo "Re-vendoring library/ ..."
rm -rf "$HERE/library"
mkdir -p "$HERE/library"
rsync -a --exclude='.git' "$TMP/src/skills/" "$HERE/library/"
cp "$TMP/src/LICENSE.md" "$HERE/library/UPSTREAM-LICENSE.md"
git -C "$TMP/src" rev-parse HEAD > "$HERE/library/UPSTREAM-COMMIT"

python3 "$HERE/build-index.py"

echo
echo "Vendored $(git -C "$TMP/src" rev-parse --short HEAD) — review with:"
echo "  git -C \"\$HOME/.claude\" status -s skills/nexus-scientific"
