# 배치 4 (약점 보완): P1 지연 반응 곡선 + 필터 정/역 분리, P2 다른 blue 전술 트리 2종.
# 세션과 무관한 독립 프로세스. 경기 캐시로 중단 후 재실행 시 이어서 진행.
param([int]$Workers = 3)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
$out = Join-Path $root 'results\indi'
$status = Join-Path $out 'batch4_status.txt'
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Add-Content -Encoding utf8 $status }

$dts = @('dt0', 'dt1', 'dt2', 'dt3', 'dt4', 'dt6', 'dt8', 'dt11')     # 0/8/17/25/33/50/67/92 ms
$g0f25 = @('k_p=20.0', 'k_q=12.119693462017066', 'k_att=8.0', 'k_ff=0.03241701230786759',
           'lam=0.1433926589386725', 'filt_hz=25')
$steps = @(
    @{ name = 'P1 dose-response: A, g0, g0.3, filt5 x 8 delays x 100'; log = 'e5_dose';
       args = @('research\indi\duel.py', '--best', 'results\indi\e4.json', '--gamma', '0', '0.3',
                '--b', 'filt_hz=5', '--b-name', 'filt5', '--conds') + $dts +
              @('--seeds', '1', '2', '3', '4', '--out', 'results\indi\e5_dose.json') },
    @{ name = 'P2 blue textbook_headon: nominal, delay30 x 50'; log = 'e3_tree_textbook';
       args = @('research\indi\duel.py', '--best', 'results\indi\e4.json', '--gamma', '0', '0.3',
                '--blue', 'examples/textbook_headon.yaml', '--conds', 'nominal', 'delay30',
                '--seeds', '1', '2', '--out', 'results\indi\e3_tree_textbook.json') },
    @{ name = 'P2 blue starter: nominal, delay30 x 50'; log = 'e3_tree_starter';
       args = @('research\indi\duel.py', '--best', 'results\indi\e4.json', '--gamma', '0', '0.3',
                '--blue', 'examples/starter.yaml', '--conds', 'nominal', 'delay30',
                '--seeds', '1', '2', '--out', 'results\indi\e3_tree_starter.json') },
    @{ name = 'P1 reverse ablation: g0 with filt 25 x 8 delays x 100'; log = 'e5_dose_rev';
       args = @('research\indi\duel.py', '--b') + $g0f25 + @('--b-name', 'g0_f25', '--conds') + $dts +
              @('--seeds', '1', '2', '3', '4', '--out', 'results\indi\e5_dose_rev.json') }
)
foreach ($s in $steps) {
    Log "시작: $($s.name)"
    & python @($s.args + @('--workers', "$Workers")) 1> (Join-Path $out "$($s.log).log") 2> (Join-Path $out "$($s.log).err")
    Log "종료: $($s.name) (exit $LASTEXITCODE)"
}
Log "전체 완료"