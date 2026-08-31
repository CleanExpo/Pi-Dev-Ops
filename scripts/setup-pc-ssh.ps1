# setup-pc-ssh.ps1 - give the Windows PC an SSH path to the brain host.
#
# WHY THIS EXISTS
# ---------------
# The PC holds work that cannot reach the rest of the estate. `~/.claude` on this
# machine IS the git repo CleanExpo/skills-library, whose .gitignore is deny-all
# (`*`) plus an allowlist - and `commands/` is not on that allowlist. So
# ~/.claude/commands/*.md (the /done command among them) is structurally invisible
# to git: `git status` cannot see it, the scheduled estate sync cannot see it, and
# no amount of committing will move it. That file's own comments record this exact
# bug ten times over, for .github/, scripts/, agents/ and hooks/.
#
# Allowlisting `commands/**` would fix the sync - and publish those files, because
# skills-library is PUBLIC. That is the same trade the repo already refused for
# session handoffs (see the .gitignore comment removing docs/session-handoffs/).
#
# SSH avoids the trade entirely: the files travel PC -> brain host directly over
# the tailnet and never touch GitHub. Nothing becomes public.
#
# WHAT THIS DOES
#   1. Confirms the OpenSSH client is present (installs the Windows capability if not).
#   2. Creates an ed25519 key if this machine has none.
#   3. Prints the ONE command to run on the brain host to authorise it.
#   4. Tests the connection non-interactively and reports honestly.
#   5. With -SyncCommands, copies ~/.claude/commands/ to the brain host.
#
# USAGE
#   .\scripts\setup-pc-ssh.ps1 -BrainHost "mac-mini.tailnet-name.ts.net" -BrainUser "phill"
#   .\scripts\setup-pc-ssh.ps1 -BrainHost "100.107.147.59" -BrainUser "phill" -SyncCommands
#
# The brain host must have Remote Login enabled (macOS: System Settings ->
# General -> Sharing -> Remote Login). Tailscale must be up on both machines;
# scripts/setup-brain-host.ps1 covers that side.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BrainHost,

    [Parameter(Mandatory = $true)]
    [string]$BrainUser,

    # Copy ~/.claude/commands/ to the brain host after the connection is proven.
    [switch]$SyncCommands,

    # Where the commands land on the brain host.
    [string]$RemoteCommandsDir = "~/estate-inbox/pc-commands",

    [string]$KeyPath = "$env:USERPROFILE\.ssh\id_ed25519"
)

$ErrorActionPreference = "Stop"

function Write-Step { param([string]$Text) Write-Host "`n=== $Text ===" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Text) Write-Host "  OK   $Text" -ForegroundColor Green }
function Write-Warn { param([string]$Text) Write-Host "  WARN $Text" -ForegroundColor Yellow }
function Write-Bad  { param([string]$Text) Write-Host "  FAIL $Text" -ForegroundColor Red }

# -- 1. OpenSSH client --------------------------------------------------------
Write-Step "OpenSSH client"
if (Get-Command ssh -ErrorAction SilentlyContinue) {
    Write-Ok "ssh is on PATH ($((Get-Command ssh).Source))"
} else {
    Write-Warn "ssh not found - installing the Windows OpenSSH.Client capability"
    try {
        Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0 | Out-Null
        Write-Ok "installed"
    } catch {
        Write-Bad "could not install OpenSSH client automatically: $($_.Exception.Message)"
        Write-Host "  Install it by hand: Settings -> System -> Optional features -> OpenSSH Client"
        exit 1
    }
}

# -- 2. Key -------------------------------------------------------------------
Write-Step "SSH key"
$sshDir = Split-Path -Parent $KeyPath
if (-not (Test-Path $sshDir)) { New-Item -ItemType Directory -Path $sshDir -Force | Out-Null }

if (Test-Path $KeyPath) {
    Write-Ok "existing key reused: $KeyPath (never regenerate - it would orphan every host that already trusts this machine)"
} else {
    Write-Warn "no key at $KeyPath - generating one"
    # -N "" = no passphrase: this key is used by unattended sync. It is confined to
    # the tailnet and authorises exactly one account on one host.
    $label = if ($env:COMPUTERNAME) { $env:COMPUTERNAME } else { [System.Net.Dns]::GetHostName() }
    ssh-keygen -t ed25519 -f $KeyPath -N '""' -C "$label-estate" | Out-Null
    if (-not (Test-Path $KeyPath)) { Write-Bad "ssh-keygen did not produce $KeyPath"; exit 1 }
    Write-Ok "generated $KeyPath"
}

$pubKey = (Get-Content "$KeyPath.pub" -Raw).Trim()

# -- 3. Authorise on the brain host -------------------------------------------
Write-Step "Authorise this machine on $BrainHost"
Write-Host "Run this ONCE on the brain host (paste it into a terminal there):" -ForegroundColor White
Write-Host ""
Write-Host "  mkdir -p ~/.ssh && chmod 700 ~/.ssh && \"
Write-Host "  echo '$pubKey' >> ~/.ssh/authorized_keys && \"
Write-Host "  chmod 600 ~/.ssh/authorized_keys"
Write-Host ""
Write-Host "(Or, if you can already log in with a password:" -ForegroundColor DarkGray
Write-Host "   type `"$KeyPath.pub`" | ssh $BrainUser@$BrainHost `"mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys`" )" -ForegroundColor DarkGray

# -- 4. Test - non-interactive, so a password prompt counts as a failure ------
Write-Step "Testing the connection"
# BatchMode=yes makes ssh fail instead of prompting. Without it a hung password
# prompt would look like a passing test that never returns.
$probe = ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 `
             -i $KeyPath "$BrainUser@$BrainHost" "echo ssh-ok; hostname" 2>&1
$sshExit = $LASTEXITCODE

if ($sshExit -eq 0 -and ($probe -match "ssh-ok")) {
    Write-Ok "key auth works - remote host reports: $(($probe | Select-String -NotMatch 'ssh-ok') -join ' ')"
} else {
    Write-Bad "could not connect with key auth (exit $sshExit)"
    Write-Host "  $probe"
    Write-Host ""
    Write-Host "  Most likely causes, in order:" -ForegroundColor Yellow
    Write-Host "   1. The authorise step above has not been run on $BrainHost yet."
    Write-Host "   2. Remote Login is off there (macOS: Settings -> General -> Sharing -> Remote Login)."
    Write-Host "   3. Tailscale is down on one end - check 'tailscale status' on both."
    Write-Host "   4. Wrong user: -BrainUser '$BrainUser' must be an account on $BrainHost."
    exit 1
}

# -- 5. Move the files git cannot see -----------------------------------------
if (-not $SyncCommands) {
    Write-Step "Done"
    Write-Host "Re-run with -SyncCommands to copy ~/.claude/commands/ to $BrainHost."
    exit 0
}

Write-Step "Syncing ~/.claude/commands/ -> ${BrainHost}:$RemoteCommandsDir"
$localCommands = Join-Path $env:USERPROFILE ".claude\commands"
if (-not (Test-Path $localCommands)) {
    Write-Warn "no $localCommands on this machine - nothing to sync"
    Write-Host "  If /done lives in a project instead, look for .claude\commands\done.md inside that repo."
    exit 0
}

$files = Get-ChildItem -Path $localCommands -Filter *.md -File
if ($files.Count -eq 0) { Write-Warn "$localCommands holds no .md files"; exit 0 }

Write-Host "  Sending $($files.Count) command file(s):"
$files | ForEach-Object { Write-Host "    $($_.Name)" }

ssh -o BatchMode=yes -i $KeyPath "$BrainUser@$BrainHost" "mkdir -p $RemoteCommandsDir" | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Bad "could not create $RemoteCommandsDir on the brain host"; exit 1 }

scp -o BatchMode=yes -i $KeyPath "$localCommands\*.md" "${BrainUser}@${BrainHost}:$RemoteCommandsDir/"
if ($LASTEXITCODE -ne 0) { Write-Bad "scp failed"; exit 1 }

# Verify by name, not by count. A count passes on whatever an earlier run left
# behind: if scp dropped every file this time, "12 files present" still prints.
# Only the names prove THIS set arrived. An ssh failure yields no names, so the
# check fails closed rather than silently reporting success.
$listing = ssh -o BatchMode=yes -i $KeyPath "$BrainUser@$BrainHost" "ls -1 $RemoteCommandsDir/ 2>/dev/null"
$remoteNames = @($listing | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
$missing = @($files.Name | Where-Object { $remoteNames -notcontains $_ })

if ($missing.Count -gt 0) {
    Write-Bad "$($missing.Count) of $($files.Count) file(s) did NOT arrive in ${BrainHost}:$RemoteCommandsDir"
    $missing | ForEach-Object { Write-Host "    missing: $_" -ForegroundColor Red }
    exit 1
}
Write-Ok "all $($files.Count) file(s) verified by name in ${BrainHost}:$RemoteCommandsDir"
Write-Host ""
Write-Host "These files are NOT in git and were never published. To bring one into the" -ForegroundColor White
Write-Host "estate deliberately, copy it into a repo yourself after reading it." -ForegroundColor White
