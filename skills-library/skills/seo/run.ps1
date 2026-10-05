# Run any script in this skill through the skill's own venv (PowerShell).
# Bash equivalent: run.sh — see that file for why this exists.
# Refuses to fall back to system Python: a missing venv should be a one-line
# diagnosis, not an ImportError from deep inside a script.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false, Position = 0)]
    [string]$Script,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$winPy  = Join-Path $here '.venv\Scripts\python.exe'
$nixPy  = Join-Path $here '.venv/bin/python'

if (Test-Path $winPy) {
    $py = $winPy
} elseif (Test-Path $nixPy) {
    $py = $nixPy
} else {
    # Plain stderr, not Write-Error: Write-Error wraps a one-line diagnosis in a
    # CategoryInfo/FullyQualifiedErrorId block that buries it.
    [Console]::Error.WriteLine(@"
seo: no venv at $here\.venv — refusing to fall back to system Python.
Create it with:
  python -m venv "$here\.venv"
  "$here\.venv\Scripts\python.exe" -m pip install -r "$here\requirements.txt"
  "$here\.venv\Scripts\python.exe" -m playwright install chromium   # only for capture_screenshot / analyze_visual
"@)
    exit 2
}

if (-not $Script) {
    Write-Host 'usage: .\run.ps1 <script> [args...]      e.g. .\run.ps1 backlinks summary --help'
    Write-Host 'scripts:'
    Get-ChildItem (Join-Path $here 'scripts\*.py') | ForEach-Object { '  ' + $_.BaseName }
    exit 64
}

if ($Script -notmatch '[\\/]') {
    if ($Script -notmatch '\.py$') { $Script = "$Script.py" }
    $Script = Join-Path $here (Join-Path 'scripts' $Script)
}

if (-not (Test-Path $Script)) {
    [Console]::Error.WriteLine("seo: no such script: $Script")
    exit 66
}

& $py $Script @Args
exit $LASTEXITCODE
