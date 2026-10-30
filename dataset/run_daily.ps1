# Daily dataset maintenance. Entry point for Task Scheduler.
#
# Run once per trading day after 16:00 IST:
#   1. refresh the constituent list and resolve any new tokens
#   2. append the rolling 1-minute window   (forward accumulation)
#   3. refresh end-of-day bars              (cheap, keeps EOD current)
#
# Every step merges on timestamp, so re-running is harmless and a missed day is
# recovered automatically as long as the gap stays inside the ~20-trading-day
# server window.

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$logDir = Join-Path $root 'store\logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
$stamp = Get-Date -Format 'yyyy-MM-dd'
$log = Join-Path $logDir "run_$stamp.log"

function Step {
    param([string]$Name, [string[]]$PyArgs)
    $t0 = Get-Date
    "=== $Name  $(Get-Date -Format 'HH:mm:ss') ===" | Tee-Object -FilePath $log -Append
    & python @PyArgs 2>&1 | Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
    $mins = ((Get-Date) - $t0).TotalMinutes
    "--- $Name exit=$code in $([math]::Round($mins,1))m" | Tee-Object -FilePath $log -Append
    return $code
}

"##### daily run $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') #####" | Tee-Object -FilePath $log -Append

Step -Name 'universe'  -PyArgs @('build_universe.py')   | Out-Null
Step -Name 'harvest1m' -PyArgs @('harvest_intraday.py', '--interval', '1m') | Out-Null
Step -Name 'eod'       -PyArgs @('backfill_eod.py', '--interval', '1d', '--force') | Out-Null

# Commit the data stores on a monthly cadence, not per-harvest. A harvest
# changes ~1,500 files / ~204 MB (one new bar recompresses the whole parquet
# file), so per-run commits would cost ~51 GB/year against ~2.5 GB monthly.
# This is a no-op on every run except the first of a new month.
# Add -Push below once you are happy for the task to push on its own.
"=== snapshot  $(Get-Date -Format 'HH:mm:ss') ===" | Tee-Object -FilePath $log -Append
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'snapshot_store.ps1') 2>&1 |
    Tee-Object -FilePath $log -Append

"##### finished $(Get-Date -Format 'HH:mm:ss') #####" | Tee-Object -FilePath $log -Append
