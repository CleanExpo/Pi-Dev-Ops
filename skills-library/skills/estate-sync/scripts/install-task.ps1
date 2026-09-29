# Install the estate-sync scheduled task (Windows): runs estate-sync.ps1 every 15 minutes.
$script = Join-Path $env:USERPROFILE '.claude\skills\estate-sync\scripts\estate-sync.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd
Register-ScheduledTask -TaskName 'Unite Estate Sync' -Action $action -Trigger $trigger -Settings $settings -Force
Write-Host "Installed 'Unite Estate Sync' (every 15 min). Log: ~\.claude\logs\estate-sync.log"
