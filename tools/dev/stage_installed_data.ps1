$ErrorActionPreference = 'Stop'
$repoData = Join-Path $PSScriptRoot '..\..\backend\data'
# New installs use 'Ponfolio'; installs from before the rename keep their old folder.
$installed = Join-Path $env:LOCALAPPDATA 'Programs\Ponfolio\backend\data'
if (-not (Test-Path $installed)) {
    $installed = Join-Path $env:LOCALAPPDATA 'Programs\AIEI Wealth Terminal\backend\data'
}
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $env:TEMP "aiei_repo_backend_data_$stamp"

if (Test-Path $repoData) {
    Copy-Item $repoData $backup -Recurse -Force
    Write-Output "BACKUP  -> $backup"
} else {
    New-Item -ItemType Directory -Path $repoData -Force | Out-Null
    Write-Output "BACKUP  -> (repo data did not exist)"
}

Copy-Item (Join-Path $installed '*') $repoData -Recurse -Force
Write-Output "COPIED  <- $installed"

Write-Output '--- repo backend data now contains ---'
Get-ChildItem $repoData | Select-Object Name, LastWriteTime | Format-Table -AutoSize | Out-String -Width 160
$backup | Set-Content -Encoding utf8 (Join-Path $PSScriptRoot '..\..\private\last_data_backup_path.txt')
