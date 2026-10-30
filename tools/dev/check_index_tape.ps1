$r = Invoke-WebRequest -Uri 'http://localhost:8182/api/market/indices' -TimeoutSec 180 -UseBasicParsing
$j = $r.Content | ConvertFrom-Json
"count      : $($j.indices.Count)"
"groups     : $(($j.indices | ForEach-Object { $_.group } | Sort-Object -Unique) -join ', ')"
"labels     : $(($j.indices | ForEach-Object { $_.label }) -join ' | ')"
"sample row :"
$j.indices[0] | ConvertTo-Json -Compress
