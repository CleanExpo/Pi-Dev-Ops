param(
  [switch]$DryRun,
  [string]$Target = "$HOME\.claude\skills"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$RepoSkills = Join-Path $RepoRoot "skills"

if (-not (Test-Path -LiteralPath $RepoSkills -PathType Container)) {
  Write-Error "ERROR: skills dir not found at $RepoSkills"
}

if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
  if ($DryRun) {
    Write-Host "CREATE  $Target"
  } else {
    New-Item -ItemType Directory -Path $Target -Force | Out-Null
  }
}

$linked = 0
$updated = 0
$current = 0
$skipped = 0
$failed = 0

function Get-LinkTarget {
  param([string]$Path)
  $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
  if ($null -eq $item) { return $null }
  if ($null -ne $item.Target) { return [string]$item.Target }
  return $null
}

function Is-ReparsePoint {
  param([string]$Path)
  $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
  return ($null -ne $item -and (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0))
}

Get-ChildItem -LiteralPath $RepoSkills -Directory | Sort-Object Name | ForEach-Object {
  $name = $_.Name
  $src = $_.FullName
  $skillMd = Join-Path $src "SKILL.md"
  if (-not (Test-Path -LiteralPath $skillMd -PathType Leaf)) { return }

  $dst = Join-Path $Target $name
  $exists = Test-Path -LiteralPath $dst

  try {
    if ($exists -and (Is-ReparsePoint $dst)) {
      $target = Get-LinkTarget $dst
      $resolvedTarget = if ($target) { try { (Resolve-Path -LiteralPath $target).Path } catch { $target } } else { "" }
      $resolvedSrc = (Resolve-Path -LiteralPath $src).Path
      if ($resolvedTarget -eq $resolvedSrc) {
        $current += 1
        return
      }
      Write-Host "UPDATE  $name (re-point link)"
      if (-not $DryRun) {
        Remove-Item -LiteralPath $dst -Force
        New-Item -ItemType Junction -Path $dst -Target $src | Out-Null
      }
      $updated += 1
    } elseif ($exists) {
      Write-Host "SKIP    $name (real dir in `$HOME\.claude\skills - left untouched)"
      $skipped += 1
    } else {
      Write-Host "LINK    $name"
      if (-not $DryRun) {
        New-Item -ItemType Junction -Path $dst -Target $src | Out-Null
      }
      $linked += 1
    }
  } catch {
    Write-Host "FAIL    $name ($($_.Exception.Message))"
    $failed += 1
  }
}

$prefix = if ($DryRun) { "(dry-run) " } else { "" }
Write-Host "${prefix}done: $linked linked, $updated updated, $current current, $skipped skipped, $failed failed -> $Target"
if ($skipped -gt 0) {
  Write-Host "Note: skipped real dirs are machine-local; move them into Pi-Dev-Ops/skills/ to make them portable."
}

if ($failed -gt 0) { exit 1 }
