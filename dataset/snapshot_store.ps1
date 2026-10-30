# Commit the parquet stores as a periodic snapshot.
#
#   powershell -ExecutionPolicy Bypass -File snapshot_store.ps1            # if due
#   powershell -ExecutionPolicy Bypass -File snapshot_store.ps1 -Force     # now
#   powershell -ExecutionPolicy Bypass -File snapshot_store.ps1 -Push      # and push
#
# Why periodic rather than every harvest: a harvest changes ~1,500 files and
# ~204 MB, because adding even one bar rewrites a whole parquet file and
# zstd-compressed parquet does not delta-compress. Committing every run costs
# roughly 51 GB/year of git objects; committing monthly costs about 2.5 GB.
# Files that genuinely did not change are rewritten byte-identically, so git
# already ignores those for free.
#
# Nothing is pushed unless -Push is passed.

param(
    [switch]$Force,
    [switch]$Push,
    [ValidateSet('monthly', 'weekly')]
    [string]$Cadence = 'monthly'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$repo = & git rev-parse --show-toplevel 2>$null
if (-not $repo) { throw "not inside a git repository" }

$marker = Join-Path $root 'store\state\last_snapshot.txt'
$period = if ($Cadence -eq 'weekly') {
    $c = [System.Globalization.CultureInfo]::InvariantCulture
    $w = $c.Calendar.GetWeekOfYear((Get-Date), 'FirstFourDayWeek', 'Monday')
    "{0}-W{1:d2}" -f (Get-Date).Year, $w
} else {
    Get-Date -Format 'yyyy-MM'
}

$last = if (Test-Path $marker) { (Get-Content $marker -Raw).Trim() } else { '' }
if (-not $Force -and $last -eq $period) {
    "snapshot for $period already taken -- nothing to do (use -Force to override)"
    return
}

# Stage only the data stores; code changes stay under your control.
& git add -- (Join-Path $root 'store') | Out-Null

$staged = & git diff --cached --name-only -- (Join-Path $root 'store')
if (-not $staged) {
    "no store changes to snapshot"
    Set-Content -Path $marker -Value $period -Encoding utf8
    return
}

$count = ($staged | Measure-Object).Count
"staging $count changed file(s) for snapshot $period"

$msg = @"
Store snapshot $period

Periodic snapshot of the parquet data stores ($count files changed).

Taken on a $Cadence cadence rather than per-harvest: a harvest rewrites ~1,500
files / ~204 MB because a single new bar recompresses the whole parquet file,
so committing every run would cost roughly 51 GB/year against ~2.5 GB for
monthly snapshots.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
"@

& git commit -m $msg | Out-Null
if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
Set-Content -Path $marker -Value $period -Encoding utf8
"committed snapshot $period"

if ($Push) {
    $branch = & git rev-parse --abbrev-ref HEAD
    & git push origin $branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed" }
    "pushed $branch"
} else {
    "not pushed (pass -Push to push)"
}
