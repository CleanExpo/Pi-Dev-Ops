# claude-chrome-align (Windows) - open the pinned Chrome profile on claude.ai so the
# Claude-in-Chrome extension registers under the SAME account as the Claude Code CLI.
# Mapping: ~/.claude/chrome-align.json {"profileDir": "Profile 1"}
# ASCII only: Windows PowerShell 5.1 reads a BOM-less file as ANSI, so a UTF-8 dash breaks parsing.
$ErrorActionPreference = 'Stop'

$claudeJson = Join-Path $env:USERPROFILE '.claude.json'
# Not ConvertFrom-Json: PS 5.1 is case-insensitive and refuses ~/.claude.json when it holds
# project keys that differ only in case (seen 05/11/2026: 'D:/Unite-Group' and 'd:/Unite-Group').
$raw = Get-Content $claudeJson -Raw
$m = [regex]::Match($raw, '"oauthAccount"\s*:\s*\{[^{}]*?"emailAddress"\s*:\s*"([^"]+)"')
$cliEmail = if ($m.Success) { $m.Groups[1].Value } else { $null }
if (-not $cliEmail) { Write-Error "No oauthAccount in ~/.claude.json - run 'claude' and sign in first" }

$map = Join-Path $env:USERPROFILE '.claude\chrome-align.json'
$chromeDir = Join-Path $env:LOCALAPPDATA 'Google\Chrome\User Data'

if (-not (Test-Path $map)) {
  Write-Host "No mapping yet. CLI account: $cliEmail"
  Write-Host "Chrome profiles on this machine:"
  Get-ChildItem $chromeDir -Directory | Where-Object { $_.Name -eq 'Default' -or $_.Name -like 'Profile *' } | ForEach-Object {
    $prefs = Join-Path $_.FullName 'Preferences'
    if (Test-Path $prefs) {
      $p = Get-Content $prefs -Raw | ConvertFrom-Json
      $email = if ($p.account_info) { $p.account_info[0].email } else { 'no-google-account' }
      Write-Host ("  {0} | {1} | {2}" -f $_.Name, $p.profile.name, $email)
    }
  }
  Write-Host ("Pin one: Set-Content '{0}' '{{""profileDir"": ""Profile 1""}}'" -f $map)
  exit 2
}

$profileDir = (Get-Content $map -Raw | ConvertFrom-Json).profileDir
Write-Host "CLI account:    $cliEmail"
Write-Host "Pinned profile: $profileDir"
Start-Process 'chrome.exe' -ArgumentList "--profile-directory=`"$profileDir`"", 'https://claude.ai/chrome'
Write-Host "Opened claude.ai/chrome in the pinned profile."
Write-Host "CONTRACT: that profile's claude.ai login must be $cliEmail - switch it there once if it differs."
