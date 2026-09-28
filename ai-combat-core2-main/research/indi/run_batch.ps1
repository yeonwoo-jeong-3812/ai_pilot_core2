# INDI 연구 본 실행 일괄 (E3 명목 → E5 강건성 → E2 민감도). 세션과 무관한 독립 프로세스로 실행:
#   Start-Process powershell -WindowStyle Hidden -ArgumentList '-File','research\indi\run_batch.ps1','-WaitPid','<pid>'
# 경기 결과는 runner.game 캐시에 쌓이므로 중단 후 재실행하면 이어서 진행한다(끝난 단계는 즉시 통과).
param([int]$WaitPid = 0, [int]$Workers = 3)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
$out = Join-Path $root 'results\indi'
New-Item -ItemType Directory -Force $out | Out-Null
$status = Join-Path $out 'batch_status.txt'
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Add-Content -Encoding utf8 $status }

if ($WaitPid -gt 0) {
    Log "대기: 실행 중인 E3 (PID $WaitPid) 종료"
    while (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) { Start-Sleep -Seconds 60 }
}

$seeds13 = 1..13 | ForEach-Object { "$_" }
$steps = @(
    @{ name = 'E3 nominal'; log = 'e3_nominal';
       args = @('research\indi\duel.py', '--best', 'results\indi\e4.json', '--gamma', '0', '0.3',
                '--conds', 'nominal', '--seeds') + $seeds13 + @('--out', 'results\indi\e3_nominal.json') },
    @{ name = 'E5 robustness'; log = 'e5';
       args = @('research\indi\duel.py', '--best', 'results\indi\e4.json', '--gamma', '0', '0.3',
                '--conds', 'stress', 'delay30', 'delay90', 'g0_lo', 'g0_hi', 'turb', 'mc',
                '--seeds', '1', '2', '3', '4', '--out', 'results\indi\e5.json') },
    @{ name = 'E2 sweep'; log = 'e2';
       args = @('research\indi\sweep.py', '--out', 'results\indi\e2.json') }
)
foreach ($s in $steps) {
    Log "시작: $($s.name)"
    & python @($s.args + @('--workers', "$Workers")) 1> (Join-Path $out "$($s.log).log") 2> (Join-Path $out "$($s.log).err")
    Log "종료: $($s.name) (exit $LASTEXITCODE)"
}
Log "전체 완료"
