$r = Invoke-RestMethod -Uri 'http://localhost:8182/api/market/indices' -TimeoutSec 180
$rows = $r.indices
$out = @()
$out += "total rows : $($rows.Count)"
$out += "ok rows    : $(($rows | Where-Object status -eq 'ok').Count)"
$out += "unavailable: $(($rows | Where-Object status -ne 'ok').Count)"
$out += ''
$out += 'by group:'
$rows | Group-Object group | Sort-Object Name | ForEach-Object {
    $ok = ($_.Group | Where-Object status -eq 'ok').Count
    $out += ("  {0,-10} {1,2} rows, {2,2} live" -f $_.Name, $_.Count, $ok)
}
$out += ''
$out += 'field coverage on live rows:'
$live = $rows | Where-Object status -eq 'ok'
foreach ($f in 'last', 'day_chg', 'day_chg_pct', 'low_52w', 'high_52w', 'off_high_pct') {
    $n = ($live | Where-Object { $null -ne $_.$f }).Count
    $out += ("  {0,-13} {1}/{2}" -f $f, $n, $live.Count)
}
$out += ''
$out += 'sample:'
$live | Select-Object -First 6 | ForEach-Object {
    $out += ("  {0,-16} {1,12} {2,9} {3,8}%  L {4,12}  H {5,12}" -f `
            $_.label, $_.last, $_.day_chg, $_.day_chg_pct, $_.low_52w, $_.high_52w)
}
$out += ''
$out += 'unavailable labels: ' + (($rows | Where-Object status -ne 'ok' | ForEach-Object label) -join ', ')
$out | Set-Content -Encoding utf8 (Join-Path $PSScriptRoot '..\..\private\scratch\tape_check.txt')
