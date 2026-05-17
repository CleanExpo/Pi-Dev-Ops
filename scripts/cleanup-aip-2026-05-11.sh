#!/bin/bash
# cleanup-aip-2026-05-11.sh
#
# One-shot post-gcloud-auth cleanup for AIP Day-1 / smoke prod follow-ups.
#
# Prerequisite (run ONCE, in your terminal):
#   gcloud auth login contact@unite-group.in
#   gcloud config set account contact@unite-group.in
#
# Then run this script:
#   bash ~/Pi-CEO/Pi-Dev-Ops/scripts/cleanup-aip-2026-05-11.sh
#
# The script:
#   1. Verifies gcloud is authed as contact@unite-group.in (fail fast if not)
#   2. Captures GCP project_number + billing_account for restore-assist-bfb74
#   3. Unlinks billing from the legacy 'restoreassist' GCP project (orphan spend)
#   4. Captures GOOGLE_CLIENT_ID from Vercel restoreassist production env
#   5. Writes captured values to /tmp/aip-cleanup-captured.json
#
# After it finishes, tell Claude:
#   "patch the AIP Supabase from /tmp/aip-cleanup-captured.json"
# Claude then issues the UPDATE statements via Supabase MCP, updates the seed
# .ts file, and commits the result.
#
# Still-manual after this script (Chrome-driven, ask Claude separately):
#   - Rotate the GOOGLE_CLIENT_SECRET one more time (transcript exposure)
#   - Disable the old ****iezn secret in Cloud Console
#   The OAuth web-client secret API isn't available via gcloud — needs Cloud
#   Console UI. Claude can drive that via Chrome DevTools MCP once you ask.

set -euo pipefail

GCP_PROJECT="restore-assist-bfb74"
LEGACY_GCP_PROJECT="restoreassist"
EXPECTED_ACCOUNT="contact@unite-group.in"
OUT="/tmp/aip-cleanup-captured.json"

# === Pre-flight ===
echo "═══════════════════════════════════════════════════════════"
echo "AIP cleanup — gcloud + Vercel + legacy billing"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "── Pre-flight ─────────────────────────────────────────────"
ACTIVE=$(gcloud config get-value account 2>/dev/null || echo "")
if [ "$ACTIVE" != "$EXPECTED_ACCOUNT" ]; then
  echo "❌ gcloud authed as: '${ACTIVE:-<none>}'"
  echo "   Expected:        '$EXPECTED_ACCOUNT'"
  echo ""
  echo "Run first:"
  echo "  gcloud auth login $EXPECTED_ACCOUNT"
  echo "  gcloud config set account $EXPECTED_ACCOUNT"
  exit 1
fi
echo "✓ gcloud account: $ACTIVE"
echo ""

# === Step 1: Capture GCP metadata for active project ===
echo "── 1. Capture GCP metadata for $GCP_PROJECT ──────────────"
PROJECT_NUMBER=$(gcloud projects describe "$GCP_PROJECT" --format="value(projectNumber)" 2>/dev/null || echo "")
BILLING_RAW=$(gcloud billing projects describe "$GCP_PROJECT" --format="value(billingAccountName)" 2>/dev/null || echo "")
BILLING_ACCOUNT="${BILLING_RAW#billingAccounts/}"
if [ -n "$PROJECT_NUMBER" ]; then
  echo "✓ project_number:  $PROJECT_NUMBER"
else
  echo "⚠ project_number: <empty> — does the account have access to $GCP_PROJECT?"
fi
if [ -n "$BILLING_ACCOUNT" ]; then
  echo "✓ billing_account: $BILLING_ACCOUNT"
else
  echo "⚠ billing_account: <empty> — billing may not be linked yet"
fi
echo ""

# === Step 2: Unlink legacy billing ===
echo "── 2. Unlink billing from legacy $LEGACY_GCP_PROJECT ─────"
LEGACY_BILLING=$(gcloud billing projects describe "$LEGACY_GCP_PROJECT" --format="value(billingEnabled)" 2>/dev/null || echo "false")
LEGACY_UNLINKED=false
if [ "$LEGACY_BILLING" = "True" ]; then
  if gcloud billing projects unlink "$LEGACY_GCP_PROJECT" 2>&1 | tail -3; then
    echo "✓ Unlinked billing from $LEGACY_GCP_PROJECT"
    LEGACY_UNLINKED=true
  else
    echo "⚠ Unlink failed — check IAM on legacy project"
  fi
else
  echo "✓ Already unlinked or no access (billingEnabled=$LEGACY_BILLING)"
fi
echo ""

# === Step 3: Capture OAuth client_id from Vercel ===
echo "── 3. Capture GOOGLE_CLIENT_ID from Vercel ───────────────"
TMP=$(mktemp /tmp/vercel-env.XXXXXX)
trap "rm -f $TMP" EXIT
# Try Pi-Dev-Ops first since that's where Vercel is most likely linked.
# Fall back to RestoreAssist repo if that's where the project linkage lives.
PULL_DIR=""
for d in "/Users/phill-mac/RestoreAssist" "/Users/phill-mac/Pi-CEO/Pi-Dev-Ops"; do
  if [ -d "$d/.vercel" ]; then
    PULL_DIR="$d"
    break
  fi
done
CLIENT_ID=""
if [ -n "$PULL_DIR" ]; then
  echo "  Using Vercel-linked dir: $PULL_DIR"
  cd "$PULL_DIR"
  if vercel env pull --environment production --yes "$TMP" >/dev/null 2>&1; then
    CLIENT_ID=$(grep -E '^GOOGLE_CLIENT_ID=' "$TMP" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || echo "")
  fi
else
  echo "⚠ No .vercel link in RestoreAssist or Pi-Dev-Ops — running 'vercel link' against the restoreassist project would fix this"
fi

if [ -n "$CLIENT_ID" ]; then
  # Print only the prefix; client_id is non-secret but no need to splash it
  echo "✓ client_id captured (${#CLIENT_ID} chars, prefix: ${CLIENT_ID:0:20}…)"
else
  echo "⚠ client_id empty — Vercel env may be encrypted, or env not pulled successfully"
fi
echo ""

# === Step 4: Write captured values to JSON for Claude to ingest ===
echo "── 4. Write captured values to $OUT ──────────────────────"
cat > "$OUT" <<EOF
{
  "captured_at": "$(date -u +%FT%TZ)",
  "gcloud_account": "$ACTIVE",
  "active_gcp": {
    "project_id": "$GCP_PROJECT",
    "project_number": "$PROJECT_NUMBER",
    "billing_account": "$BILLING_ACCOUNT"
  },
  "legacy_gcp": {
    "project_id": "$LEGACY_GCP_PROJECT",
    "billing_unlinked_this_run": $LEGACY_UNLINKED,
    "billing_enabled_before": $([ "$LEGACY_BILLING" = "True" ] && echo "true" || echo "false")
  },
  "vercel": {
    "oauth_client_id": "$CLIENT_ID",
    "client_id_chars": ${#CLIENT_ID}
  }
}
EOF
echo "✓ Written: $OUT"
echo ""

# === Summary ===
echo "═══════════════════════════════════════════════════════════"
echo "✅ Cleanup capture complete"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Captured (also in $OUT):"
echo "  GCP project_number:  $PROJECT_NUMBER"
echo "  GCP billing_account: $BILLING_ACCOUNT"
echo "  OAuth client_id:     ${CLIENT_ID:+captured (}${#CLIENT_ID}${CLIENT_ID:+ chars)}${CLIENT_ID:-<empty>}"
echo "  Legacy billing:      $([ "$LEGACY_UNLINKED" = "true" ] && echo "unlinked this run" || echo "no change")"
echo ""
echo "Next: tell Claude →"
echo "  \"patch the AIP Supabase from /tmp/aip-cleanup-captured.json\""
echo ""
echo "Still pending (Chrome-driven, ask Claude separately):"
echo "  • Rotate GOOGLE_CLIENT_SECRET one more time (Cloud Console + Vercel + 1P)"
echo "  • Disable old ****iezn secret in Cloud Console"
echo ""
