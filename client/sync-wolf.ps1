# Hermes Wolf Autonomous Skill Sync Installer
# Registers a background Scheduled Task to auto-pull hermes-skills at logon
$SyncScript = "$HOME\hermes-skills\sync.ps1"
if (-not (Test-Path $SyncScript)) {
    Write-Warning "hermes-skills directory not found at $HOME\hermes-skills. Cloning first..."
    git clone https://github.com/amrlazw/hermes-skills.git "$HOME\hermes-skills"
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$SyncScript`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "HermesWolfSkillSync" -Action $Action -Trigger $Trigger -Settings $Settings -Force
Write-Host "[OK] HermesWolfSkillSync scheduled task registered. Wolf will auto-sync skills at logon." -ForegroundColor Green
