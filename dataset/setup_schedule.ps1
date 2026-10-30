# Register (or re-register) the daily harvest with Windows Task Scheduler.
#
#   powershell -ExecutionPolicy Bypass -File setup_schedule.ps1
#   powershell -ExecutionPolicy Bypass -File setup_schedule.ps1 -Remove
#
# Default fire time is 17:00 local. The NSE intraday feed lags the live session
# by several hours, so anything after ~16:30 IST captures the full day. If this
# machine is not on IST, set -At to the local equivalent of ~17:00 IST.

param(
    [string]$At = '17:00',
    [string]$TaskName = 'NSE-Dataset-Daily',
    [switch]$Remove
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $root 'run_daily.ps1'

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    "removed scheduled task '$TaskName'"
    return
}

if (-not (Test-Path $script)) { throw "missing $script" }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $root

# Monday-Friday only; NSE holidays simply produce a no-op merge.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $At

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description 'Append NSE rolling 1-minute window + refresh EOD bars' -Force | Out-Null

"registered '$TaskName' -- Mon-Fri at $At"
"  script : $script"
"  logs   : $(Join-Path $root 'store\logs')"
"run now  : Start-ScheduledTask -TaskName '$TaskName'"
"-StartWhenAvailable is set, so a run missed while the machine was off fires on next boot."
