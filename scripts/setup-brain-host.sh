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
echo "    Enable the non-encrypted HTTP server too; Tailscale Serve terminates HTTPS."
echo "    Copy the API key from plugin settings into OBSIDIAN_TOKEN below."

VAULT="${HOME}/2nd Brain/2nd Brain"
WIKI="${VAULT}/Wiki"
TS_NAME="$(tailscale status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Self',{}).get('DNSName','').rstrip('.'))" 2>/dev/null || echo 'your-mac-mini')"
TS_IP="$(tailscale ip -4 2>/dev/null | head -n 1 || true)"

echo ""
echo "==> 3. Tailscale Serve bridge"
echo "    Tailnet HTTPS :27124 → Obsidian local HTTP :27123"
if command -v tailscale >/dev/null 2>&1; then
  tailscale serve --bg --https=27124 http://127.0.0.1:27123 || true
  tailscale serve status || true
else
  echo "    tailscale CLI not found; run after Tailscale is installed."
fi

cat <<EOF

==> 4. Add to Railway / Margot / Pi-CEO env (brain host + remote workers)

export BRAIN1_WIKI_DIR="${WIKI}"
export OBSIDIAN_VAULT="${VAULT}"
export OBSIDIAN_TOKEN="<paste-from-obsidian-plugin>"
export BRAIN_HOST_TAILNET="${TS_NAME}"
export OBSIDIAN_REMOTE_URL="https://${TS_NAME}:27124"
export OBSIDIAN_REMOTE_IP="${TS_IP:-100.x.y.z}"

# Supabase (wiki + AIP entity sync)
export SUPABASE_UNITE_GROUP_URL="https://lksfwktwtmyznckodsau.supabase.co"
export SUPABASE_UNITE_GROUP_SERVICE_KEY="<service-role-key>"

==> 5. Windows PC (when Tailscale installed there)
export OBSIDIAN_REMOTE_URL="https://${TS_NAME}:27124"
export OBSIDIAN_REMOTE_IP="${TS_IP:-100.x.y.z}"
export OBSIDIAN_TOKEN="<same-key>"
# BRAIN1_WIKI_DIR not required on PC — reads go via REST

==> 6. MacBook Pro
# Install Tailscale + sync Obsidian vault (iCloud/Obsidian Sync)
# Same OBSIDIAN_REMOTE_URL when vault not local

EOF
