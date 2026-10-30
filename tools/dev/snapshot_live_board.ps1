# Snapshots the running app's live board and index tape. The board holds your real
# holdings, so it goes to the git-ignored private/ folder, never to test/.
$out = Join-Path $PSScriptRoot '..\..\private\snapshots'
New-Item -ItemType Directory -Path $out -Force | Out-Null
Invoke-WebRequest -Uri "http://localhost:8182/api/portfolio/deploy-board?amount=25000" -TimeoutSec 240 -UseBasicParsing |
    Select-Object -ExpandProperty Content |
    Set-Content -Encoding utf8 (Join-Path $out 'real_board.json')
Invoke-WebRequest -Uri "http://localhost:8182/api/market/indices" -TimeoutSec 120 -UseBasicParsing |
    Select-Object -ExpandProperty Content |
    Set-Content -Encoding utf8 (Join-Path $out 'real_tape.json')
"done"
