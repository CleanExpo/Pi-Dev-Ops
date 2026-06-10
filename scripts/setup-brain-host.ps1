# Windows PC — Tailscale + remote brain env (run after Mac Mini is set up)
# Usage: .\scripts\setup-brain-host.ps1 -BrainHost "mac-mini.tailnet-name.ts.net"

param(
    [Parameter(Mandatory = $true)]
    [string]$BrainHost,

    [string]$BrainIp = "100.107.147.59"
)

Write-Host "Install Tailscale from https://tailscale.com/download/windows if not present."
Write-Host ""
Write-Host "Add to dashboard/.env.local or shell profile:"
Write-Host ""
Write-Host "OBSIDIAN_REMOTE_URL=https://$BrainHost`:27124"
Write-Host "OBSIDIAN_REMOTE_IP=$BrainIp"
Write-Host "OBSIDIAN_TOKEN=<paste-from-mac-mini-obsidian-plugin>"
Write-Host "BRAIN_HOST_TAILNET=$BrainHost"
Write-Host ""
Write-Host "Optional (if syncing vault to this PC):"
Write-Host "BRAIN1_WIKI_DIR=$env:USERPROFILE\2nd Brain\2nd Brain\Wiki"
Write-Host "OBSIDIAN_VAULT=$env:USERPROFILE\2nd Brain\2nd Brain"
