# TASK RUN — 본실험 계산 분담 (PC 를 내는 팀원 모두)

## Claude Code에게

이 파일 하나로 내 PC 몫의 본실험을 준비하고 돌릴 수 있게 썼다. **코드는 고치지 않는다.** 사용자가 자기 PC 번호 (PC1/PC2/PC3) 를 알려 준다.

- **연구 목적 (3줄):**
  1. 근접 공중전 행동트리의 숫자 파라미터 10개가 성과 (1차 지표 Δwez = `wez_blue − wez_red`) 를 얼마나 좌우하는지 잰다.
  2. 본실험은 θ 256개 (라틴 하이퍼큐브 64 + Morris 192) × 48경기 = 12,288경기이고, PC 3대가 나눠 돌린다.
  3. 결과가 PC 마다 같아야 합칠 수 있으므로, 실행 전에 재현 해시를 반드시 확인한다.
- **먼저 읽을 파일** (`cadet_research/` 아래): `kit/bt/RUNBOOK.md` (전부), `kit/bt/CONTRACT.md` 맨 앞 순서·§8 (기준 해시),
  `PREREG_BT.md` §5 (설계·시드), §7 (제외·재실행 규칙).
- **작업 브랜치:** 없음. `bt-study` 를 받아서 돌리기만 한다. 아무것도 커밋·push 하지 않는다.
- **수정해도 되는 파일:** 없음 (이 파일 끝 "질문", "실행 기록" 절만 적어서 연우에게 보낸다).
- **마감:** 태그 `prereg-bt-v1` 이 생긴 뒤 시작. 끝낼 날짜 [팀 결정 필요].

## 0. 태그가 생기기 전에는 실행하지 말 것

`git fetch --tags origin` 후 `git tag -l prereg-bt-v1` 이 아무것도 안 찍으면 **멈춘다.** (`run_bt.py` 도 태그 없이는 bt-main 실행을 거부한다.)

## 1. 준비 (처음 한 번)

1. clone (처음이면): `git clone -c core.longpaths=true -b bt-study https://github.com/yeonwoo-jeong-3812/ai_pilot_core2.git` (Windows 긴 경로 때문에 옵션 필수)
2. `cd ai_pilot_core2/cadet_research/kit` → `git pull origin bt-study` → `git fetch --tags origin`
3. `python -m pip install -r bt/requirements-analysis.txt` (Python 3.11.9)
4. `python bt/test_bt.py` → 마지막 줄 "bt 자가점검 통과"
5. **crosscheck:** `python bt/crosscheck.py` → "전체 해시" 가 **`fc6501b873df43e1`** (CONTRACT.md §8) 과 같아야 한다. 다르면 돌리지 말고 출력 전체를 연우에게 보낸다.
6. 절전 해제 (Windows 설정 → 전원 → 화면·절전 "안 함", 노트북은 전원 연결), 무거운 프로그램 닫기.
7. `--procs` = 논리 코어 수 − 2 (8코어 → 6). 실행 뒤 `wall_clock` 이 1경기라도 나오면 하나 줄여 그 몫을 다시 돌린다 (§4).

## 2. PC 별 배정

| PC | 이름 (누구 PC) | shard |
|---|---|---|
| PC1 | [팀 결정 필요] | `1/3` |
| PC2 | [팀 결정 필요] | `2/3` |
| PC3 | [팀 결정 필요] | `3/3` |

## 3. 실행 명령 (자기 shard 번호 i 로, `cadet_research/kit/` 에서)

```
python bt/run_bt.py bt/thetas/main_lhs64.csv      --prefix bt-main --unlock-confirm --shard i/3 --procs <위 값>
python bt/run_bt.py bt/thetas/main_morris_r16.csv --prefix bt-main --unlock-confirm --shard i/3 --procs <위 값>
```

- 먼저 `--dry` 를 붙여 경기 수를 확인한다 (PC 마다 LHS 1,024경기, Morris 3,072경기).
- 실행 전 점검 (커밋 상태, Python, crosscheck 10경기) 이 자동으로 돈다. "실행 거부" 가 나오면 그 메시지를 그대로 연우에게 보낸다. `--force-dev` 는 쓰지 않는다.
- 이 PC 기준 예상 시간: 1대 몫 (4,096경기) × 약 4.2 s ≈ 4.8시간 (PREREG_BT.md §6.5, PC 사양에 따라 다름).

## 4. 끊겼을 때 재개

- 같은 명령을 그대로 다시 친다. 기록된 경기는 건너뛴다. 결과 파일을 지우거나 고치지 않는다.
- 끝에 `wall_clock N경기` 가 0 이 아니면: 그 줄만 지우는 것은 연우가 한다 (CONTRACT.md §5). 연우에게 알리고 지시를 기다린다.
- `disqualified` 가 하나라도 나오면 **실행을 멈추고** 연우에게 알린다 (PREREG_BT.md §7: 원인 수정 후 해당 θ 전체 재실행).

## 5. 결과 파일과 보내는 곳

- 결과 파일 (이름 바꾸지 말 것): `bt/out/bt-main/games_main_lhs64_shard<i>of3.csv`, `bt/out/bt-main/games_main_morris_r16_shard<i>of3.csv`
- 보내는 곳: **[팀 결정 필요]** (RUNBOOK.md 8번과 같음).
- 보낼 때 함께: crosscheck 출력 마지막 3줄, `python --version`, 아래 "실행 기록".
- 연우가 `bt/merge.py` 로 검사·합친다 (중복·누락·code_commit·engine_sha·opponent_set 불일치·wall_clock·disqualified 가 하나라도 있으면 합치지 않는다).

## 하지 말 것

- 태그 전 실행, `--force-dev` 사용, 코드·설계 파일 수정, 결과 파일 이름 변경·편집, 다른 PC 몫 실행, bt-study 에 push.
- bt-confirm (확인 단계) 은 이 TASK 가 아니다 (RQ3 조건부, 연우가 따로 알린다).

## 막히면 할 일

추측해서 바꾸지 말고 **멈춘다.** 아래 "질문" 절에 적어 연우에게 보낸다.

## 실행 기록

(PC 번호, 시작·끝 시각, --procs, 끝에 찍힌 경기 수와 wall_clock 수)

## 질문

(없으면 비워 둔다)
