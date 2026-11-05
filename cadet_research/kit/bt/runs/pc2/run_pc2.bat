@echo off
rem PC2 (shard 2/3) bt-main run. Re-run this file to resume; recorded games are skipped.
set PYTHONIOENCODING=utf-8
set PY=D:\BTBT\venv311\Scripts\python.exe
set LOG=D:\BTBT\run_pc2_log.txt
set OUT=D:\BTBT\run_pc2_out.txt
cd /d D:\BTBT\ai_pilot_core2\cadet_research\kit
echo START %date% %time% >> %LOG%
%PY% bt\run_bt.py bt\thetas\main_lhs64.csv --prefix bt-main --unlock-confirm --shard 2/3 --procs 5 >> %OUT% 2>&1 || goto fail
echo LHS_DONE %date% %time% >> %LOG%
%PY% bt\run_bt.py bt\thetas\main_morris_r16.csv --prefix bt-main --unlock-confirm --shard 2/3 --procs 5 >> %OUT% 2>&1 || goto fail
echo END rc=0 %date% %time% >> %LOG%
exit /b 0
:fail
echo END rc=FAIL %date% %time% >> %LOG%
exit /b 1
