#!/usr/bin/env bash
# Note: on main branch this file may not exist yet — checkout pidev/launch-crew-wirein first.
# Mac Mini brain-host setup — Tailscale + Obsidian REST env template.
# Run on the machine that owns ~/2nd Brain (not the Windows dev PC).
set -euo pipefail

echo "==> 1. Install Tailscale (if missing)"
if ! command -v tailscale >/dev/null 2>&1; then
  brew install tailscale
fi
sudo tailscale up || true
echo "Tailscale IP: $(tailscale ip -4 2>/dev/null || echo 'run: tailscale ip -4')"

echo ""
echo "==> 2. Obsidian Local REST API"
echo "    Obsidian → Settings → Community plugins → Local REST API → Enable"
echo "    Copy the API key from plugin settings into OBSIDIAN_TOKEN below."

VAULT="${HOME}/2nd Brain/2nd Brain"
WIKI="${VAULT}/Wiki"
TS_NAME="$(tailscale status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Self',{}).get('DNSName','').rstrip('.'))" 2>/dev/null || echo 'your-mac-mini')"

cat <<EOF

==> 3. Add to Railway / Margot / Pi-CEO env (brain host + remote workers)

export BRAIN1_WIKI_DIR="${WIKI}"
export OBSIDIAN_VAULT="${VAULT}"
export OBSIDIAN_TOKEN="<paste-from-obsidian-plugin>"
export BRAIN_HOST_TAILNET="${TS_NAME}"
export OBSIDIAN_REMOTE_URL="https://${TS_NAME}:27124"

# Supabase (wiki + AIP entity sync)
export SUPABASE_UNITE_GROUP_URL="https://lksfwktwtmyznckodsau.supabase.co"
export SUPABASE_UNITE_GROUP_SERVICE_KEY="<service-role-key>"

==> 4. Windows PC (when Tailscale installed there)
export OBSIDIAN_REMOTE_URL="https://${TS_NAME}:27124"
export OBSIDIAN_TOKEN="<same-key>"
# BRAIN1_WIKI_DIR not required on PC — reads go via REST

==> 5. MacBook Pro
# Install Tailscale + sync Obsidian vault (iCloud/Obsidian Sync)
# Same OBSIDIAN_REMOTE_URL when vault not local

EOF
