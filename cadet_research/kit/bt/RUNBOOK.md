# 팀원 실행 순서 (여러 PC 분산)

모든 명령은 `cadet_research/kit/` 에서. 자기 번호 i 와 전체 PC 수 n 은 담당자가 정해 준다.

1. **최신 커밋 받기:** `git pull origin bt-study` (처음이면 CONTRACT.md 맨 앞 순서로 clone). `git status` 에 `bt/` 수정이 없어야 한다.
2. **재현 점검:** `python bt/crosscheck.py` → "전체 해시"가 CONTRACT.md §8 과 같아야 한다. 다르면 돌리지 말고 담당자에게 알린다.
3. **절전 해제:** Windows 설정 → 전원 → 화면·절전 "안 함". 노트북은 전원 연결. 실행 중 다른 무거운 프로그램은 닫는다.
4. **--procs 정하기:** 논리 코어 수 − 2 (8코어 → 6). 실행 뒤 `wall_clock` 이 1경기라도 나오면 하나 줄인다.
5. **실행:** `python bt/run_bt.py <θ 목록> --prefix bt-main --unlock-confirm --shard i/n --procs <위 값>` (실행 전 점검을 통과해야 돈다).
6. **재개:** 끊기면 같은 명령을 그대로 다시 친다. 기록된 경기는 건너뛴다.
7. **결과 파일:** `bt/out/bt-main/games_shard<i>of<n>.csv` (이름 바꾸지 말 것). 끝에 찍힌 `wall_clock N경기` 가 0 인지 확인한다.
8. **보내는 곳:** [팀 결정 필요]. 보낸 뒤 담당자가 `python bt/merge.py ...` 로 검사·합친다.
