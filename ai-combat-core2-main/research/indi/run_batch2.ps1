# 배치 2 (2026-09-29): E4 범위 확장 → 확장 해 교전 검증 → 양측 튜닝 → E2 표본 확대.
# 세션과 무관한 독립 프로세스로 실행. 경기 캐시로 중단 후 재실행 시 이어서 진행.
#   Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','research\indi\run_batch2.ps1'
param([int]$Workers = 3)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
$out = Join-Path $root 'results\indi'
$status = Join-Path $out 'batch2_status.txt'
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Add-Content -Encoding utf8 $status }

$s13 = 1..13 | ForEach-Object { "$_" }
$s4 = @('1', '2', '3', '4')
$steps = @(
    @{ name = 'E4 wide box (k_p 4-40, k_att 2-16, gamma 0)'; log = 'e4_wide';
       args = @('research\indi\optimize.py', '--gammas', '0', '--box', 'k_p=4,40', 'k_att=2,16',
                '--out', 'results\indi\e4_wide.json') },
    @{ name = 'E3 wide nominal (325)'; log = 'e3_wide_nominal';
       args = @('research\indi\duel.py', '--best', 'results\indi\e4_wide.json', '--gamma', '0',
                '--conds', 'nominal', '--seeds') + $s13 + @('--out', 'results\indi\e3_wide_nominal.json') },
    @{ name = 'E3 wide delay (100 x 2)'; log = 'e3_wide_delay';
       args = @('research\indi\duel.py', '--best', 'results\indi\e4_wide.json', '--gamma', '0',
                '--conds', 'delay30', 'delay90', '--seeds') + $s4 + @('--out', 'results\indi\e3_wide_delay.json') },
    @{ name = 'Mirror: red tuned gamma 0 (nominal, delay30)'; log = 'e3_mirror';
       args = @('research\indi\duel.py', '--best', 'results\indi\e4.json', '--gamma', '0', '0.3', '--red-gamma', '0',
                '--conds', 'nominal', 'delay30', '--seeds') + $s4 + @('--out', 'results\indi\e3_mirror.json') },
    @{ name = 'E2 n=100 (seeds 1-4)'; log = 'e2_n100';
       args = @('research\indi\sweep.py', '--seeds') + $s4 + @('--out', 'results\indi\e2_n100.json') }
)
foreach ($s in $steps) {
    Log "시작: $($s.name)"
    & python @($s.args + @('--workers', "$Workers")) 1> (Join-Path $out "$($s.log).log") 2> (Join-Path $out "$($s.log).err")
    Log "종료: $($s.name) (exit $LASTEXITCODE)"
}
Log "전체 완료"