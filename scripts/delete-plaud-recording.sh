#!/usr/bin/env bash
# Delete a Plaud recording from the wiki AND Supabase corpus.
# Usage: delete-plaud-recording.sh <slug> [--purge-plaud]
#   <slug> is the wiki page slug, e.g. 2026-05-17-acme-q2-pricing
#
# Reads SUPABASE_UNITE_GROUP_URL + SUPABASE_UNITE_GROUP_SERVICE_KEY from ~/.hermes/.env.
# Does NOT touch the Plaud cloud unless --purge-plaud is passed.

set -euo pipefail

SLUG="${1:-}"
PURGE_PLAUD="${2:-}"
if [[ -z "$SLUG" ]]; then
  echo "Usage: $(basename "$0") <slug> [--purge-plaud]" >&2
  exit 2
fi

WIKI_DIR="$HOME/2nd Brain/2nd Brain/Wiki"
PLAUD_DIR="$WIKI_DIR/plaud"

# Find the wiki page(s) — handle multi-part files via shared base slug
TARGETS=()
shopt -s nullglob
for f in "$PLAUD_DIR/$SLUG.md" "$PLAUD_DIR/$SLUG"-part*.md; do
  [[ -f "$f" ]] && TARGETS+=("$f")
done
shopt -u nullglob

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo "no wiki file matching '$SLUG' under $PLAUD_DIR" >&2
  exit 1
fi

# Load env
ENV_FILE="$HOME/.hermes/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing $ENV_FILE" >&2
  exit 1
fi
SUPA_URL="$(grep '^SUPABASE_UNITE_GROUP_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")"
SUPA_KEY="$(grep '^SUPABASE_UNITE_GROUP_SERVICE_KEY=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")"

for f in "${TARGETS[@]}"; do
  filename="$(basename "$f" .md)"
  page_id="plaud/$filename"
  # Delete from Supabase (best-effort: don't fail the whole run on a single supabase error)
  curl -sS -X DELETE \
    -H "apikey: $SUPA_KEY" \
    -H "Authorization: Bearer $SUPA_KEY" \
    "$SUPA_URL/rest/v1/wiki_pages?id=eq.${page_id//\//%2F}" \
    >/dev/null 2>&1 || echo "warning: supabase DELETE failed for $page_id" >&2
  # Delete wiki file
  rm "$f"
  # Append log
  echo "$(date -u +%Y-%m-%dT%H:%MZ) | plaud-delete | plaud/$filename.md | manual delete" \
    >> "$WIKI_DIR/log.md"
  echo "deleted: $f"
done

if [[ "$PURGE_PLAUD" == "--purge-plaud" ]]; then
  echo "NOTE: --purge-plaud not yet wired; Plaud cloud copy retained" >&2
fi
