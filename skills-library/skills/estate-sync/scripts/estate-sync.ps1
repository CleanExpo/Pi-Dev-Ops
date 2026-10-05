# estate-sync (Windows) - propagate skills-library updates in BOTH directions.
# Runs via Task Scheduler every 15 min (install-task.ps1). Trunk-based: main only;
# feature branches are fetched but never disturbed. Conflicts abort + skip push.
#
# GATED PUBLISH (16/08/2026). origin is a PUBLIC repo. Until today this ran a blanket
# `git add` over the whole tree and pushed whatever happened to be on disk, so an edit
# made by anyone - another agent, another session, a half-finished thought - became a
# public commit within 15 minutes. Observed: at ~14:53 an agent edited
# skills/session-handoff/SKILL.md and deliberately did not commit it; at 15:09:49 this
# script published it as aac5efe, and again at 15:24:49 as ca51c94.
# This timer can no longer commit a change it was not explicitly given a receipt for.
# Every dirty path is either matched against .estate-sync-receipt (path + sha256,
# one-shot, expiring) or REFUSED BY NAME in the log. Pull is untouched, so skills/ and
# agents/ still arrive from origin every cycle; only the unattended PUBLISH is gated.
#
# To publish deliberately:
#   powershell -File estate-sync.ps1 -Receipt -Path skills/foo/SKILL.md,agents/bar.md
# then let the next cycle run (or run this script with no arguments).
param(
  [switch]$Receipt,
  [string[]]$Path = @()
)
$ErrorActionPreference = 'Continue'

# WHY THIS HELPER EXISTS (31/08/2026). With $ErrorActionPreference = 'Continue', a
# failing Get-FileHash writes an error and CARRIES ON: the enclosing statement is
# skipped and the loop keeps going. Both call sites were
# `(Get-FileHash ... -LiteralPath $full).Hash.ToLower()`, so on failure the append or
# the comparison silently did not happen and nothing recorded that.
#
# Observed on windows-latest: the receipt writer printed "receipt written for 1
# path(s)" and exited 0 while writing a receipt containing ONLY its two comment lines
# and no hash at all. Separately, the gate logged "content changed after the receipt
# was written" for a file nobody had touched (t22, failing on main since before this
# change) - the same null hash, compared and found unequal.
#
# The trigger is a separator mismatch: $rel is normalised to FORWARD slashes because
# the receipt must match `git status` output, and Join-Path then produces a mixed
# path like D:\a\estate\skills/demo/NEW.md. Callers now hand this helper a natively
# separated path, and a hash that cannot be computed is an error, never a silent skip.
function Get-Sha256OrFail($fullPath, $label) {
  # .NET directly, NOT Get-FileHash. windows-latest reported
  #   Get-FileHash : The term 'Get-FileHash' is not recognized as the name of a
  #   cmdlet ... CommandNotFoundException
  # for every call. Get-FileHash ships in Microsoft.PowerShell.Utility and is absent
  # or unloadable in the host the test harness launches, so the whole receipt
  # mechanism depended on a cmdlet that is not always there.
  #
  # SHA256 via System.Security.Cryptography has no module dependency, works on
  # PowerShell 2.0 through 7.x, and behaves identically on Windows, macOS and Linux.
  # The receipt format is unchanged: lowercase hex, which is what sha256sum and
  # shasum emit and what estate-sync.sh writes.
  $stream = $null
  $sha = $null
  try {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::OpenRead($fullPath)
    $bytes = $sha.ComputeHash($stream)
    return ([System.BitConverter]::ToString($bytes) -replace '-', '').ToLower()
  } catch {
    return $null
  } finally {
    if ($null -ne $stream) { $stream.Dispose() }
    if ($null -ne $sha) { $sha.Dispose() }
  }
}

# Receipt entries carry forward slashes (git's shape); the filesystem wants the native
# separator. On Linux and macOS this is a no-op, which is why the fix is testable under
# pwsh here as well as on Windows.
function Get-NativePath($repoRoot, $relPath) {
  return Join-Path $repoRoot ($relPath -replace '/', [System.IO.Path]::DirectorySeparatorChar)
}
# Test-only override. Task Scheduler never sets this, so production is unchanged.
$repo = if ($env:ESTATE_SYNC_REPO) { $env:ESTATE_SYNC_REPO } else { Join-Path $env:USERPROFILE '.claude' }
$logDir = Join-Path $repo 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir 'estate-sync.log'
# A session actively editing the estate must not have its work swept into a
# "chore(sync)" commit. Both overridable for tests only, mirroring estate-sync.sh.
$quietSecs = if ($env:ESTATE_SYNC_QUIET_SECS) { [int]$env:ESTATE_SYNC_QUIET_SECS } else { 300 }
$holdMaxSecs = if ($env:ESTATE_SYNC_HOLD_MAX_SECS) { [int]$env:ESTATE_SYNC_HOLD_MAX_SECS } else { 3600 }
# A receipt is a permit for ONE cycle, not a standing licence: it expires by age and is
# deleted the moment it is spent, so a forgotten receipt cannot authorise tomorrow's
# unrelated edit to the same file.
$receiptMaxSecs = if ($env:ESTATE_SYNC_RECEIPT_MAX_SECS) { [int]$env:ESTATE_SYNC_RECEIPT_MAX_SECS } else { 3600 }
$hold = Join-Path $repo '.estate-sync-hold'
$receiptFile = Join-Path $repo '.estate-sync-receipt'
function Log($m) { "[{0}] {1}" -f (Get-Date -Format 'dd/MM/yyyy HH:mm:ss'), $m | Add-Content $log }
function AgeSecs($path) { [int]((Get-Date) - (Get-Item $path).LastWriteTime).TotalSeconds }

# Paths this timer must never publish, receipt or not.
#  .github/                      - workflows EXECUTE on push (was the 2026-07-16 hazard).
#  docs/session-handoffs/        - handoffs are session transcripts of private estate work
#                                  and origin is PUBLIC. The gitignore allowlist for them was
#                                  removed on 16/08/2026, which stops NEW ones being seen at
#                                  all; the 23 already-tracked files are not ignorable by
#                                  gitignore (git never ignores a tracked path), so this list
#                                  is what stops their future EDITS being published. The
#                                  existing 23 are deliberately left in place - deleting them
#                                  or rewriting history is a founder decision, not this
#                                  script's.
#  enforcement code              - a workflow that lands wrong is red and visible; a gate that
#                                  lands wrong is GREEN and silently changes what every agent
#                                  on every machine may do. Mirrors ENFORCEMENT_PATHS in
#                                  estate-sync.sh, which the .ps1 had never carried.
#  skills/estate-sync/scripts/   - this script IS the gate. It must be committed by a human
#                                  who read the diff, never by itself.
# Asymmetric on purpose: pull --rebase still brings all of these DOWN from origin, so a
# reviewed change still reaches every machine automatically. Only the unattended PUSH stops.
$neverSync = @(
  '.github/',
  'docs/session-handoffs/',
  'bootstrap.sh',
  'skills/pr-release-gate/scripts/',
  'skills/engineering-requirements/scripts/',
  'skills/supabase-write-gate/scripts/',
  'skills/enforcement-loop/install/',
  'skills/estate-sync/scripts/'
)
function IsNeverSync($p) {
  foreach ($n in $neverSync) {
    if ($n.EndsWith('/')) { if ($p.StartsWith($n)) { return $true } }
    elseif ($p -eq $n) { return $true }
  }
  return $false
}

# Secret shapes refused in the diff about to be published. High-precision provider
# prefixes only: a generic /password\s*=/ would false-positive across a repo of prose and
# stall the sync, and a stalled sync gets disabled. Every pattern's variable part begins
# with a character class, so the pattern list cannot match ITSELF if this file is ever in a
# diff (the failure mode estate-sync.sh's output-path invariant hit on its first version).
# Matches are logged by pattern name and file only - never the matched text.
$secretPatterns = [ordered]@{
  'aws-access-key-id'  = 'AKIA[0-9A-Z]{16}'
  'anthropic-key'      = 'sk-ant-[A-Za-z0-9_-]{16,}'
  'openai-key'         = 'sk-[A-Za-z0-9]{32,}'
  'github-token'       = 'gh[pousr]_[A-Za-z0-9]{30,}'
  'github-pat'         = 'github_pat_[A-Za-z0-9_]{20,}'
  'google-api-key'     = 'AIza[0-9A-Za-z_-]{30,}'
  'slack-token'        = 'xox[baprs]-[A-Za-z0-9-]{10,}'
  'stripe-live-key'    = '[sr]k_live_[0-9a-zA-Z]{20,}'
  'gitlab-pat'         = 'glpat-[A-Za-z0-9_-]{18,}'
  'jwt'                = 'eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}'
  'private-key-block'  = '-----BEGIN [A-Z ]*PRIVATE KEY-----'
}

# -Receipt: write the permit. Deliberately a separate invocation - the act of naming the
# files is the gate, and a mode that could infer them from the dirty tree would just be
# `git add .` with extra steps.
if ($Receipt) {
  if (-not (Test-Path $repo)) { Write-Output "repo missing: $repo"; exit 1 }
  Set-Location $repo
  # `powershell -File` hands every argument over as a literal string, so `-Path a,b,c`
  # arrives as ONE path named "a,b,c" and the whole request is refused as "not a file".
  # Split here so the documented invocation - and the Task Scheduler style of call this
  # script is already launched with - both work.
  $Path = @($Path | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
  if ($Path.Count -eq 0) {
    Write-Output 'usage: estate-sync.ps1 -Receipt -Path <repo-relative-path>[,<path>...]'
    exit 2
  }
  $lines = @(
    ("# estate-sync receipt written {0} by {1}" -f (Get-Date -Format 'dd/MM/yyyy HH:mm:ss'), $env:USERNAME),
    ("# One-shot: consumed by the next sync cycle, and ignored after {0}s." -f $receiptMaxSecs)
  )
  $bad = $false
  foreach ($p in $Path) {
    $rel = ($p -replace '\\', '/') -replace '^\./', ''
    $full = Get-NativePath $repo $rel
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
      Write-Output "REFUSED to receipt (not a file): $rel"; $bad = $true; continue
    }
    if (IsNeverSync $rel) {
      Write-Output "REFUSED to receipt (never-sync path): $rel"; $bad = $true; continue
    }
    $hash = Get-Sha256OrFail $full $rel
    if ($null -eq $hash) {
      Write-Output "REFUSED to receipt (could not hash): $rel"; $bad = $true; continue
    }
    $lines += "{0}  {1}" -f $hash, $rel
  }
  # Fail closed: a partial receipt would silently publish the subset that passed while the
  # author believes the whole set was refused.
  if ($bad) { Write-Output 'no receipt written'; Log 'REFUSED: receipt request rejected; no receipt written'; exit 1 }
  Set-Content -LiteralPath $receiptFile -Value $lines -Encoding UTF8
  # Read it back. The failure this catches actually happened: "receipt written for 1
  # path(s)" printed over a file with no hash line in it. A success message that has
  # not been checked against the artefact is the whole fault class this repo keeps
  # paying for, and the writer is not exempt from it.
  $written = @(Get-Content -LiteralPath $receiptFile -ErrorAction SilentlyContinue |
               Where-Object { $_ -and -not ($_.TrimStart([char]0xFEFF).Trim().StartsWith('#')) })
  if ($written.Count -ne $Path.Count) {
    Remove-Item -LiteralPath $receiptFile -Force -ErrorAction SilentlyContinue
    Write-Output ("FAILED to write receipt: expected {0} entr(ies), the file holds {1}. No receipt written." -f $Path.Count, $written.Count)
    Log ("FAIL: receipt write verification failed ({0} expected, {1} present); receipt removed" -f $Path.Count, $written.Count)
    exit 1
  }
  $named = ($Path -join ', ')
  Write-Output "receipt written for $($Path.Count) path(s): $named"
  Log "receipt written for $($Path.Count) path(s): $named"
  exit 0
}

Set-Location $repo
git fetch origin main --quiet 2>> $log
if ($LASTEXITCODE -ne 0) { Log 'FAIL: fetch'; exit 1 }

$branch = git branch --show-current
if ($branch -ne 'main') {
    # RA-7802: say how far behind, not just "skip" - see estate-sync.sh
    $behind = git rev-list --count HEAD..origin/main 2>$null
    Log "WARN: on branch $branch, not main - $behind commit(s) behind origin/main; fetched only, NOT synced"
    exit 0
}

git pull --rebase --autostash origin main --quiet 2>> $log
if ($LASTEXITCODE -ne 0) {
  git rebase --abort 2>$null
  Log 'CONFLICT: pull --rebase failed - manual reconcile needed; push skipped'
  exit 1
}

# A tracked deletion is unresolved estate drift, not an in-sync state. Fail closed
# before staging or pushing anything; restoration/removal requires deliberate review.
$deleted = @(git diff --name-only --diff-filter=D HEAD -- 2>> $log)
if ($LASTEXITCODE -ne 0) {
  Log 'FAIL: tracked deletion health check'
  exit 1
}
if ($deleted.Count -gt 0) {
  Log 'HEALTH: tracked deletion(s) present - manual reconcile needed; push skipped'
  $deleted | ForEach-Object { Log "tracked deletion: $_" }
  exit 1
}

# An explicit hold beats any heuristic: a session that knows it is mid-task takes it
# and the timer stays off its work. Capped by age so a crashed session cannot wedge the
# estate out of sync indefinitely.
if (Test-Path $hold) {
  $holdAge = AgeSecs $hold
  if ($holdAge -lt $holdMaxSecs) {
    Log ("skip: hold held for {0}s (<{1}s) - session working; nothing staged" -f $holdAge, $holdMaxSecs)
    exit 0
  }
  Log ("hold is stale ({0}s >= {1}s) - ignoring it and syncing" -f $holdAge, $holdMaxSecs)
}

# Quiescence. Kept although the receipt gate below now strictly dominates it: it costs one
# cycle of latency and it is the guard that already caught two mid-edit sweeps on
# 2026-07-29. `seen` is the sentinel, not the age - a file written in the same second has
# age 0, and using 0 to mean "nothing measured" would disable the guard for the freshest edit.
$seen = $false; $newest = 0; $recent = ''
foreach ($line in @(git status --porcelain 2>> $log)) {
  if ($line.Length -le 3) { continue }
  $f = $line.Substring(3)
  $full = Join-Path $repo $f
  if (-not (Test-Path $full)) { continue }
  $a = AgeSecs $full
  if ((-not $seen) -or ($a -lt $newest)) { $newest = $a; $recent = $f; $seen = $true }
}
if ($seen -and ($newest -lt $quietSecs)) {
  Log ("skip: {0} changed {1}s ago (<{2}s) - session may be mid-edit; nothing staged" -f $recent, $newest, $quietSecs)
  exit 0
}

# Read the receipt. Absent or stale is not an error - it is the normal state of a machine
# nobody is publishing from, and it means the same thing as an empty receipt: stage nothing.
$receiptEntries = @{}
$receiptState = 'no receipt present'
if (Test-Path $receiptFile) {
  $rAge = AgeSecs $receiptFile
  if ($rAge -ge $receiptMaxSecs) {
    $receiptState = "receipt stale ({0}s >= {1}s)" -f $rAge, $receiptMaxSecs
    Log ("REFUSED: {0} - write a fresh one to publish" -f $receiptState)
  } else {
    foreach ($line in @(Get-Content -LiteralPath $receiptFile -Encoding UTF8)) {
      $t = $line.Trim()
      if (($t -eq '') -or $t.StartsWith('#')) { continue }
      $parts = $t -split '\s+', 2
      if ($parts.Count -lt 2) { continue }
      $receiptEntries[$parts[1].Trim()] = $parts[0].ToLower()
    }
    $receiptState = "receipt covers $($receiptEntries.Count) path(s)"
  }
}

# THE GATE. Every dirty path is named and decided individually; nothing is sweepable.
# -uall so an untracked directory is enumerated as its files, otherwise a refusal would
# name a directory and hide what is inside it.
$toStage = @()
foreach ($line in @(git status --porcelain -uall 2>> $log)) {
  if ($line.Length -le 3) { continue }
  $p = $line.Substring(3).Trim()
  if ($p.StartsWith('"') -and $p.EndsWith('"')) { $p = $p.Substring(1, $p.Length - 2) }
  if (IsNeverSync $p) { Log "REFUSED: $p (never-sync path - this timer must not publish it)"; continue }
  if (-not $receiptEntries.ContainsKey($p)) { Log "REFUSED: $p (no gate receipt - $receiptState)"; continue }
  $full = Get-NativePath $repo $p
  if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { Log "REFUSED: $p (receipted but not a readable file)"; continue }
  $h = Get-Sha256OrFail $full $p
  if ($null -eq $h) {
    # Distinguish "could not read it" from "it changed". Reporting the second for the
    # first is what sent t22 chasing a content change nobody had made.
    Log "REFUSED: $p (could not compute its hash - NOT a content change)"; continue
  }
  if ($h -ne $receiptEntries[$p]) { Log "REFUSED: $p (content changed after the receipt was written)"; continue }
  $toStage += $p
}
if ($toStage.Count -gt 0) { git add --ignore-removal -- $toStage 2>> $log }
# Never stage symlinks (they carry machine-absolute targets)
git diff --cached --name-only | ForEach-Object {
  $p = Join-Path $repo $_
  if ((Test-Path $p) -and ((Get-Item $p -Force).LinkType)) { git restore --staged $_; Log "unstaged symlink: $_" }
}
# Defence in depth: if the staging logic above is ever wrong, a never-sync path still does
# not reach a commit. Fails closed rather than committing what it could not unstage.
foreach ($f in @(git diff --cached --name-only)) {
  if (IsNeverSync $f) {
    git restore --staged -- $f 2>> $log
    if ($LASTEXITCODE -ne 0) { Log "FAIL: could not unstage never-sync path $f; commit and push skipped"; exit 1 }
    Log "REFUSED: unstaged never-sync path $f"
  }
}
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  $staged = @(git diff --cached --name-only)
  git commit --quiet -m ("chore(sync): {0} auto-sync {1} [receipted: {2} file(s)]" -f $env:COMPUTERNAME, (Get-Date -Format 'dd/MM/yyyy HH:mm:ss'), $staged.Count) 2>> $log
  if ($LASTEXITCODE -ne 0) { Log 'FAIL: commit; nothing published'; exit 1 }
  Log ("committed {0} receipted file(s): {1}" -f $staged.Count, ($staged -join ', '))
  Remove-Item -LiteralPath $receiptFile -Force -ErrorAction SilentlyContinue
  Log 'receipt consumed'
}
# skills-library is exempted from the pr-release-gate receipt requirement itself
# (pr_release_gate.py, commit b3e01d9, 19/07/2026: "automation-synced sync repo").
# That exemption is about not requiring the heavyweight PR+independent-review
# machinery for THIS repo's routine housekeeping - it is not a licence for this
# timer to ship a deliberate commit an interactive session left on main mid-decision.
# Only this script's OWN auto-sync commits (pure machine-state drift, decided by
# nobody, reviewed by nothing) are safe to push unattended. Mirrors estate-sync.sh.
$ahead = @(git log origin/main..main --format='%H%x09%s' 2>$null)
if ($LASTEXITCODE -ne 0) { Log 'FAIL: could not enumerate commits ahead of origin/main'; exit 1 }
if ($ahead.Count -gt 0) {
  $held = $false
  foreach ($line in $ahead) {
    $parts = $line -split "`t", 2
    if ($parts.Count -lt 2) { continue }
    if ($parts[1] -notmatch '^chore\(sync\): .* auto-sync ') {
      Log ("  held: {0} {1}" -f $parts[0].Substring(0, 12), $parts[1])
      $held = $true
    }
  }
  if ($held) {
    Log 'skip: non-sync commit(s) ahead of origin/main - a session must push these deliberately; auto-push skipped'
    exit 0
  }
  # Last check before the payload becomes public and permanent. A receipt proves someone
  # named the file; it does not prove they read every line of it.
  $diff = @(git diff origin/main..HEAD 2>> $log)
  if ($LASTEXITCODE -ne 0) { Log 'FAIL: could not diff the push payload for secrets; push skipped'; exit 1 }
  $inFile = ''
  $hits = 0
  foreach ($dl in $diff) {
    if ($dl.StartsWith('+++ b/')) { $inFile = $dl.Substring(6); continue }
    if ((-not $dl.StartsWith('+')) -or $dl.StartsWith('+++')) { continue }
    foreach ($name in $secretPatterns.Keys) {
      if ($dl -cmatch $secretPatterns[$name]) {
        Log "SECRET-SCAN: $name matched in $inFile (value not logged)"
        $hits++
      }
    }
  }
  if ($hits -gt 0) {
    Log ("REFUSED: push blocked - {0} secret-shaped match(es) in the diff about to be published; reconcile by hand" -f $hits)
    exit 1
  }
  git push origin main --quiet 2>> $log
  if ($LASTEXITCODE -eq 0) { Log ("PUSHED to origin/main: {0} commit(s), secret-scan clean" -f $ahead.Count) } else { Log 'FAIL: push (retry next cycle)'; exit 1 }
}
Log 'ok: in sync'
