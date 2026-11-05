@echo off
rem PC3 bt-main 재개: 기록된 경기는 run_bt.py 가 건너뛰고 남은 것부터 이어서 돈다.
cd /d "%~dp0"
start "BT PC3 run" /min C:\Users\User\venv-bt311\Scripts\python.exe watch_and_run.py
echo 재개했습니다. 진행 상황: %~dp0STATUS.txt
