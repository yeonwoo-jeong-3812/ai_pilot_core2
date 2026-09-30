# 배치 5: ② 필터×지연 안정 경계 지도 → ① 비대칭 지연(blue 만 지연) 교전. 독립 프로세스, 캐시로 재개 가능.
param([int]$Workers = 3)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
$out = Join-Path $root 'results\indi'
$status = Join-Path $out 'batch5_status.txt'
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Add-Content -Encoding utf8 $status }
$steps = @(
    @{ name = 'Stability map (9 filt x 8 delays, bench)'; log = 'stab_map';
       args = @('research\indi\stab_map.py', "$Workers") },
    @{ name = 'Asymmetric delay: blue-only 17/33/92 ms, A g0 g0.3 filt5 x 100'; log = 'e5_asym';
       args = @('research\indi\duel.py', '--best', 'results\indi\e4.json', '--gamma', '0', '0.3',
                '--b', 'filt_hz=5', '--b-name', 'filt5', '--conds', 'bdt2', 'bdt4', 'bdt11',
                '--seeds', '1', '2', '3', '4', '--workers', "$Workers", '--out', 'results\indi\e5_asym.json') }
)
foreach ($s in $steps) {
    Log "시작: $($s.name)"
    & python @($s.args) 1> (Join-Path $out "$($s.log).log") 2> (Join-Path $out "$($s.log).err")
    Log "종료: $($s.name) (exit $LASTEXITCODE)"
}
Log "전체 완료"