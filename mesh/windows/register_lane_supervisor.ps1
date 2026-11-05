<#
.SYNOPSIS
Registers the NexusLaneSupervisor scheduled task for the current user (UNI-3291).

.DESCRIPTION
The task runs mesh\lane_supervisor.py tick at logon and every 5 minutes, hidden, as the
signed-in user with ordinary (not elevated) rights, the same way NexusMeshRunner runs.
It stores no password and changes no permission: like every interactive task it runs
only while the user is signed in, so after a reboot it starts at the first sign-in.

  -PrintXml   print the task definition and change nothing
  -Remove     delete the task (the lanes and their state files are left alone)
#>
param(
  [string]$Root = "C:\agent-work",
  [string]$Python = "",
  [string]$TaskName = "NexusLaneSupervisor",
  [switch]$PrintXml,
  [switch]$Remove
)
$ErrorActionPreference = "Stop"

if ($Remove) {
  schtasks.exe /Delete /TN $TaskName /F
  exit $LASTEXITCODE
}

$Script = Join-Path (Split-Path -Parent $PSScriptRoot) "lane_supervisor.py"
if (-not (Test-Path $Script)) { throw "lane_supervisor.py not found beside this folder: $Script" }
if (-not $Python) {
  $py = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
  if ($py) { $Python = Join-Path (Split-Path -Parent $py) "pythonw.exe" }
}
if (-not $Python -or -not (Test-Path $Python)) { throw "pythonw.exe not found; pass -Python <path to pythonw.exe>" }

function X([string]$s) { [System.Security.SecurityElement]::Escape($s) }
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$Start = (Get-Date).AddMinutes(1).ToString("yyyy-MM-ddTHH:mm:ss")
$Arguments = "`"$Script`" tick --root `"$Root`""

$Xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>UNI-3291: resume or hand off agent lanes left dead by a reboot or crash. Pi-Dev-Ops mesh/lane_supervisor.py</Description>
  </RegistrationInfo>
  <Principals>
    <Principal id="Author">
      <UserId>$(X $User.User.Value)</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Hidden>true</Hidden>
  </Settings>
  <Triggers>
    <LogonTrigger>
      <UserId>$(X $User.Name)</UserId>
    </LogonTrigger>
    <TimeTrigger>
      <StartBoundary>$Start</StartBoundary>
      <Repetition>
        <Interval>PT5M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </TimeTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>$(X $Python)</Command>
      <Arguments>$(X $Arguments)</Arguments>
      <WorkingDirectory>$(X (Split-Path -Parent $Script))</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

if ($PrintXml) { $Xml; exit 0 }

$Dir = Join-Path $Root ".lane-supervisor"
New-Item -ItemType Directory -Force $Dir | Out-Null
$File = Join-Path $Dir "$TaskName.task.xml"
[System.IO.File]::WriteAllText($File, $Xml, [System.Text.Encoding]::Unicode)
schtasks.exe /Create /TN $TaskName /XML $File /F
if ($LASTEXITCODE -ne 0) { throw "schtasks /Create failed with exit $LASTEXITCODE" }
schtasks.exe /Query /TN $TaskName /FO LIST
