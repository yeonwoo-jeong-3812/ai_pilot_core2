# BT 파라미터 실험: 팀원 계약서

> **처음 받은 팀원 순서** (Python 3.11.9 권장)
> 1. `git clone -c core.longpaths=true -b bt-study https://github.com/yeonwoo-jeong-3812/ai_pilot_core2.git` (Windows 긴 경로 때문에 옵션 필수)
> 2. `cd ai_pilot_core2/cadet_research/kit` 후 `python -m pip install -r requirements.txt`
> 3. `python bt/test_bt.py` → 마지막 줄 "bt 자가점검 통과"
> 4. `python bt/crosscheck.py` → "전체 해시"가 §8의 기준 해시 `fc6501b873df43e1`와 같은지 비교 (다르면 §8)

연구 질문: 근접 공중전 행동트리(BT)의 숫자 파라미터가 승패를 얼마나 좌우하는가.
연구 대상 트리는 `bt/energy_fighter.yaml`이다 (`ai-combat-core2-main/examples/energy_fighter.yaml`을 내용 그대로 복사한 원본. 고치지 않는다). 구조는 그대로 두고 숫자 10개만 바꾼다.
이 문서와 `params.yaml`만 보고 일할 수 있게 썼다. 둘이 어긋나면 `params.yaml`이 맞다.

## 1. 실행 방법

`cadet_research/kit/`에서 실행한다. 설치: `python -m pip install -r requirements.txt` (Python 3.11.9에서 점검).

```bash
python bt/test_bt.py                                        # 자가점검. 처음 한 번, 그리고 bt/ 코드를 고친 뒤 매번 (약 1분)
python bt/run_bt.py bt/thetas/baseline.csv --dry            # 경기 수만 센다
python bt/run_bt.py bt/thetas/baseline.csv --procs 6        # 기본 접두어 bt-smoke
python bt/run_bt.py my_thetas.csv --prefix bt-pilot --procs 6
python bt/run_bt.py my_thetas.csv --limit 20                # 남은 경기 중 앞 20개만
python bt/run_bt.py my_thetas.csv --prefix bt-main --unlock-confirm   # 확증. 사전등록 뒤에만
python bt/trace_match.py --scenario neutral --opponent A2_GunTracker_00 --seed-salt bt-smoke-0   # 경기 끝 10초 동안 실행된 노드
python bt/run_bt.py bt/thetas/r0.csv --prefix bt-cal --r0  # R0 검증 전용: 범위 밖 θ 허용, stage=r0, 결과 bt/out/r0/
python bt/make_tree.py bt/thetas/r0.csv --r0                # θ 목록의 트리만 만들기 (--r0 는 위와 같음)
python bt/validate.py                                       # 검증 표 bt/out/validation.md 다시 만들기
python bt/crosscheck.py                                     # PC 간 재현 점검 (고정 10경기 해시, §8)
python bt/run_bt.py thetas.csv --prefix bt-main --unlock-confirm --shard 2/3   # 여러 PC 분산: 3대 중 2번째 몫 (bt/RUNBOOK.md)
python bt/merge.py thetas.csv --prefix bt-main --out bt/out/bt-main/games.csv a.csv b.csv c.csv   # shard 검사·합치기
python bt/run_bt.py thetas.csv --prefix bt-confirm --unlock-confirm --nseeds 36   # 확인 단계: 셀당 시드 36 (432경기/θ)
python bt/designs.py                                        # 본실험 설계 파일 bt/thetas/main_*.csv 다시 만들기 (SHA-256 출력)
python -m pip install -r bt/requirements-analysis.txt       # 분석 패키지 (bt/analysis/, designs.morris)
python bt/run_bt.py my_thetas.csv --opponents original     # kit 원본 상대로 (기본은 보정 상대 patched)
python bt/run_bt.py bt/thetas/diag.csv --prefix bt-diag --opponents diag-f4000   # 하드덱 진단 반사실 (bt/out/diag_hard_deck.md)
```

- **사전등록 잠금:** `bt-main`, `bt-confirm` 은 `--unlock-confirm` 과 git 태그 `prereg-bt-v1` (사전등록 고정) 이 둘 다 있어야 돈다.
  태그 확인은 `--force-dev`로도 건너뛸 수 없다. 1차 지표는 Δwez (`wez_blue − wez_red`) 다 (`cadet_research/PREREG_BT.md` §4).
- **셀당 시드 수:** `--nseeds` (기본 4). 시드 i 의 `seed_salt` 는 `<접두어>-<i>`. 기본값 4 는 예전 시드와 같다 (`test_bt.py`).
- **실행 전 점검:** `run_bt.py`는 실제로 돌기 전에 ① `bt/`에 커밋 안 된 수정이 없는지 ② Python 버전 ③ crosscheck 전체 해시를
  §8 의 값과 비교하고 하나라도 다르면 실행을 거부한다. 진단용으로만 `--force-dev`로 건너뛴다 (그 결과는 본실험에 쓰지 않는다). `--dry`는 점검하지 않는다.
- **분산 실행:** `--shard i/n`은 `build_jobs` 순서의 k 번째 경기를 (k mod n) + 1 번 몫으로 나눈다. 같은 θ 목록·접두어·상대 묶음·n 이면
  겹치지 않고 빠짐없이 나뉜다 (`test_bt.py`). 결과는 `bt/out/<접두어>/games_<θ 목록 파일 이름>_shard<i>of<n>.csv` (예: `games_main_lhs64_shard2of3.csv`). 합칠 때는 `bt/merge.py`
  (중복·누락·계획 밖 경기, code_commit·engine_sha·opponent_set 불일치, wall_clock, disqualified 를 검사하고 문제가 있으면 합치지 않는다).
  팀원 순서는 `bt/RUNBOOK.md`.
- 결과는 `bt/out/<접두어>/games.csv`에 이어 쓴다. 끊기면 같은 명령을 다시 치면 끝난 경기는 건너뛰고 이어서 돈다.
- `--procs`는 CPU 코어 수보다 작게 준다. 8코어 PC는 6.
- θ 목록 파일: CSV는 첫 줄이 열 이름, JSON은 dict 목록이다. 키는 `params.yaml`의 10개 이름과 `dummy`. 열 순서는 상관없다.
  예시는 `bt/thetas/baseline.csv`.
- θ 하나는 48경기다: 교전 기하 3 (`perch_offense`, `perch_defense`, `neutral`) × 상대 4 × 시드 4.
  상대는 `run_bt.py`의 `OPPONENTS`에 있다: `A2_GunTracker_00`, `B2_Extender_00`, `C1_TwoCircleRate_00`, `D1_Reactive_00`.
- **상대 묶음 (`--opponents`, 기본 `patched`):** `patched` = `bt/opponents_patched/` (원본에서 최우선 low_altitude → climb 노드만
  청 recover 와 같게: floor_ft 4500, g_burst 0.8. 규칙과 diff 는 `bt/analysis/opponent_patch_rules.md`), `original` = `kit/agents/main/` 원본,
  `diag-f4000` = 하드덱 진단 전용 (bt-diag 에서만). 상대 이름은 묶음과 상관없이 같고 `opponent_set` 열로 구분한다.
  결과 폴더: `patched` 는 `bt/out/<접두어>/`, 다른 묶음은 `bt/out/<접두어>-<묶음>/` (예: `bt/out/bt-main-original/`) — 보정 상대 결과에 섞이지 않게.
- 청(blue)은 항상 θ 트리, 적(red)은 항상 상대다. `perch_defense`는 `perch_offense`의 진영을 맞바꾼 기하라서,
  청을 고정해도 공세와 수세가 둘 다 들어간다.

## 2. games.csv 열 (이 순서와 이름이 계약이다)

**결과 CSV와 설계 파일은 반드시 `read_games`/`read_design` (`bt/analysis/io_utils.py`) 으로 읽는다.** pandas 기본 읽기 (`pd.read_csv`) 는 숫자+e 형태 theta_id (예: `686747538e50`) 와 숫자만인 theta_id 를 숫자로,
engine_sha `1e0101026959` 를 `inf` 로 바꾼다 (본실험 θ 256개 중 숫자+e 4개, 숫자만 1개). `read_games` 는 식별자·문자열 열을 str 로,
나머지를 숫자로 읽는다 (`test_bt.py` 의 `test_read_games_keeps_ids`). csv 모듈로 읽는 코드 (`run_bt.py`, `merge.py` 등) 는 모든 값이 문자열이라 해당 없다.

| 열 | 뜻 | 단위·값 |
|---|---|---|
| `stage` | 시드 접두어 = 데이터의 쓰임 (§3). `--r0` 실행이면 `r0` | `bt-smoke` 등, `r0` |
| `theta_id` | θ(10개 + dummy)의 해시 앞 12자리. 숫자는 float로 맞춰서 해시한다 (6000과 6000.0은 같다) | 문자열 |
| `merge_range_ft` | `merged.range_ft`: 이 거리 안이면 merge (방어 브레이크 조건의 하나) | ft |
| `threat_aspect_deg` | `foe_threat.aspect_deg`: aspect가 이보다 크면 적 기수가 나를 향함 | ° |
| `gun_range_ft` | `in_gun_envelope.range_ft`: 건 추적 진입 거리 | ft |
| `gun_ata_deg` | `in_gun_envelope.ata_deg`: 건 추적 진입 ATA | ° |
| `fight_kcas` | `below_fighting_speed.kcas`: 이 속도 미만이면 에너지 회복 | kt (KCAS) |
| `energy_min_ft` | `energy_advantage.min_ft`: 이만큼 비에너지가 앞서야 공세 | ft |
| `lead_time_s` | `press_offense.lead_time_s`: 공세 리드 추격의 예측 시간. 범위 0.5–3.0 (엔진 DSL 허용 범위 0.0–3.0 때문) | s |
| `break_g_burst` | `break_defense.g_burst`: 방어 브레이크 G 천장 (0 지속 봉투 ↔ 1 순간 봉투) | 0–1 |
| `closing_min_fps` | `closing.min_fps`: low yo-yo 의 되당김(yoyo_pull_up) 접근율 임계. 트리의 closing 두 개 중 이것만 파라미터이고, yoyo_dive_cut 의 inverter 안 `closing min_fps: 0` 은 고정 | ft/s |
| `floor_ft` | `low_altitude.floor_ft`: 이 고도 아래면 고도 회복 | ft |
| `dummy` | 트리에 안 들어가는 가짜 파라미터. 영향 없음의 기준선 | 0–1 |
| `scenario` | 교전 기하 | `perch_offense` / `perch_defense` / `neutral` |
| `opponent` | 상대 이름 | `OPPONENTS` 키 |
| `opponent_set` | 상대 묶음 (`--opponents`) | `patched` (기본) / `original` / `diag-f4000` |
| `seed_salt` | `<접두어>-<i>`, i = 0..3 (`r0` 도 `--prefix` 의 시드를 쓴다. 예: `bt-cal-0`) | 문자열 |
| `seed` | `derive_seed(scenario, seed_salt)`. 초기조건 지터(고도·속도·방위·거리)를 정한다 | 32비트 정수 |
| `winner` | 승자. `blue` = θ 트리, `red` = 상대, `draw` | |
| `end_reason` | 종료 사유 (엔진 `MatchResult.condition`) | 아래 표 |
| `win_mode` | 청 승리 방식. `winner`·`end_reason`에서 정해진다 (`run_bt.win_mode`). 청이 이기지 않았으면 빈칸 | `shootdown` 상대 체력 0 (`health_zero`), `opp_hard_deck`, `opp_stall`, `judge` 시간 종료 판정 (`timeout`), `other` 그 밖 |
| `hp_blue`, `hp_red` | 종료 체력. 판정패(`hard_deck`, `stall`, `disqualified`)의 패자는 0으로 기록 (run.py·bridge 와 같은 규약) | 0–100 HP |
| `hp_blue_raw`, `hp_red_raw` | 판정 처리 전 실제 남은 체력 (엔진 `MatchResult.hp_*`). 판정패여도 0으로 바꾸지 않는다 | 0–100 HP |
| `wez_blue`, `wez_red` | 상대를 엔진 WEZ 안에 둔 누적 시간 (500–3,000 ft, ATA < 30°) | s |
| `ata_mean_blue`, `ata_mean_red` | 전 구간 평균 ATA (기수와 상대 사이 각, 120 Hz 매 틱) | ° |
| `off_frac` | 공세 시간 비율: 청 ATA < 60° 이고 적 ATA > 120° (20 Hz 표본) | 0–1 |
| `def_frac` | 수세 시간 비율: 청 ATA > 120° 이고 적 ATA < 60° | 0–1 |
| `e_adv_ft` | 비에너지 우위 평균: (h + V²/2g)청 − (h + V²/2g)적 | ft |
| `t_first_wez` | 청이 처음 WEZ 기하(500–3,000 ft, ATA < 30°)에 든 시각. 한 번도 없으면 빈칸 | s |
| `node_frac` | 청 트리가 실행한 action 노드별 시간 비율. JSON 문자열 `{"노드이름": 비율, ...}`, 합 1. 노드 이름은 `Pilot._cmd.name` (dwell 히스테리시스 뒤 실제 명령), 20 Hz 표본 | 0–1 |
| `node_frac_red` | 홍(상대) 트리의 같은 기록 (`foe._cmd.name`). 상대 climb (= low_altitude) 작동 등을 본다 | 0–1 |
| `sim_time_s` | 경기 종료 시각 (시뮬레이션 시간) | s |
| `wall_s` | 실제 걸린 시간. 재현 대상 아님 | s |
| `engine_sha` | `aircombat/`, `jsbsim_data/`, `config/` 내용 해시 앞 12자리 (줄끝·`__pycache__` 무시) | 문자열 |
| `tree_sha` | 실제로 쓴 트리 파일의 sha256 앞 12자리 | 문자열 |
| `code_commit` | 실행 시점 저장소 git 커밋 해시 앞 12자리 (`git rev-parse HEAD`). git 이 아니면 `unknown`. 재현 대상 아님 (crosscheck 해시에서 뺌) | 문자열 |
| `host` | 실행한 PC 이름. 재현 대상 아님 | 문자열 |
| `python_version` | 실행한 Python 버전 (`platform.python_version()`) | 예: `3.11.9` |

`end_reason` 값: `health_zero` 격추, `hard_deck` 1,000 ft 아래로 이탈, `stall` 100 kt 미만 누적 10 s,
`timeout` 300 s 종료 (피해 교환 있음, 체력 많은 쪽 승), `no_contact` 300 s 동안 양쪽 무피해 (무승부),
`disqualified` 트리 오류, `wall_clock` **실제 시간 120 s 안전장치에 걸림 (실행 인공물, §5)**.

`off_frac`, `def_frac`, `e_adv_ft`, `t_first_wez`, `node_frac`, `node_frac_red`는 `bt/monitor.py`가 잰다 (읽기 전용). `node_frac`, `node_frac_red`는 bt에서 추가한 것이다. 앞의 넷은 origin/YEOP의
`research/indi/combat.py`와 같은 정의다. 엔진의 `wez_blue`(120 Hz, 엔진 판정)과 `t_first_wez`(20 Hz 표본)는 표본 주기가 달라
작은 차이가 날 수 있다.

## 3. 시드 규칙

- 접두어가 데이터의 쓰임을 정한다. 섞지 않는다.

  | 접두어 | 쓰임 |
  |---|---|
  | `bt-smoke` | 실행 점검. 결과를 해석하지 않는다 (기본값) |
  | `bt-pilot` | 예비 실험. 설계·효과 크기 감 잡기 |
  | `bt-cal` | 보정. 잡음 크기, 허용폭, 필요한 시드 수를 정하는 데만 쓴다 |
  | `bt-cal-a`, `bt-cal-b` | 보정용 별도 시드 묶음. 같은 θ를 서로 다른 시드로 돌려 시드 잡음을 잰다 |
  | `bt-main` | 본실험. `--unlock-confirm` 없이는 안 돈다 |
  | `bt-confirm` | 확증. `--unlock-confirm` 없이는 안 돈다 |
  | `bt-diag` | 진단·상대 보정 검증 전용. `--opponents diag-f4000`은 이 접두어에서만 쓴다. 결과를 본 실험과 섞지 않는다 |
  | `r0` (stage 값) | R0 검증 전용. `--r0`로 `params.yaml` 범위 밖 θ 를 돌린다. 시드는 `--prefix`의 것을 쓰고 결과는 `bt/out/r0/` |

- 같은 `(scenario, seed_salt)`면 θ와 상대가 달라도 초기조건이 같다 (공통 난수). θ끼리 비교할 때 초기조건 잡음이 상쇄된다.
- 엔진에는 다른 난수원이 없다. 같은 θ·셀은 언제 어디서 돌려도 `wall_s`, `host`를 뺀 모든 열이 같다 (`test_bt.py`가 확인).

## 4. 팀원 몫

- `bt/designs.py`: θ 목록 만들기 (`baseline`, `oat`, `lhs`, `write`). 시그니처와 출력 형식은 파일에 있다.
- `bt/analysis/`: games.csv 분석 (`load`, `score`, `theta_table`, `sensitivity`). 원자료는 읽기만 한다.
- 범위는 `params.yaml`의 `lo`, `hi`를 쓴다. 값 검사는 `make_tree.normalize`가 한다.
- `--r0`(`normalize(θ, r0=True)`)는 R0 검증 전용이다. `params.yaml` 범위 검사만 건너뛰고 엔진 DSL 검사는 그대로 한다
  (예: `lead_time_s` 3.0 초과, `g_burst` 1 초과는 `--r0`여도 거부). 본 실험 θ 에는 쓰지 않는다.

## 5. 알려진 함정

- **`lead_time_s` 범위는 0.5–3.0.** 엔진 DSL 허용 범위(0.0–3.0) 때문이다. 3.0 초과 θ는 `make_tree`가 거부한다.
- **`closing`은 트리에 두 군데 있다.** yoyo_pull_up의 `min_fps`(기준 60)만 `closing_min_fps`이고, inverter 안의 `min_fps: 0`은 고정이다.
- **열 형식이 바뀐 games.csv에는 이어 쓰지 않는다.** `run_bt.py`는 헤더가 지금 계약과 다르면 멈춘다. 옛 파일은 다른 이름으로 옮긴다.
- **`wall_clock`.** 엔진은 경기 하나가 실제 시간 120 s를 넘으면 무승부로 끊는다. PC가 바쁘면 생기고, 재현되지 않는다.
  실행이 끝나면 `run_bt.py`가 개수를 찍는다. 생기면 그 줄을 games.csv에서 지우고 같은 명령을 다시 쳐서 다시 돌린다
  (kit의 `run_extra.py`와 같은 처리). 분석에는 넣지 않는다. 자주 생기면 `--procs`를 줄인다.
- **열이 추가되면 옛 games.csv 와 열이 다르다.** `node_frac_red`는 하드덱 진단 때, `opponent_set`은 상대 보정 때, `code_commit`은 분산 실행 준비 때 추가했다. 그 전 결과 (bt-cal, bt-pilot 등) 에는 없다.
- **원본 상대는 하드덱이 많다.** 원본 상대 4종은 `low_altitude floor_ft`가 1,200 ft 이고 climb 이 g_burst 0 이다 (진단: `bt/out/diag_hard_deck.md`).
  그래서 기본 상대를 보정 상대 (`patched`) 로 바꿨다. `opponent_set` 열이 생기기 전 결과 (예비 실험 `bt-pilot/games_original.csv`,
  진단 `bt-diag/games_diag1.csv`) 는 모두 원본 상대다 (진단의 `_f4000` 이름 상대 제외).
- θ 목록에 같은 θ가 두 번 있으면 한 번만 돈다. dummy만 다른 θ는 트리 파일은 같고 `theta_id`는 다르다.

## 6. 하면 안 되는 것

- kit의 `aircombat/`, `jsbsim_data/`, `config/`, `run.py`, `run_extra.py`를 고치지 않는다. INDI 논문과 같은 엔진이어야 비교할 수 있다.
  `engine_sha`가 바뀌었으면 결과를 섞지 않는다.
- 심판 규칙(하드덱 1,000 ft, 실속, WEZ, DPS, HP, 300 s, 오버타임 없음), 기체·INDI 명목값, L2 교리 기본값, dt, 상대 트리를 바꾸지 않는다.
- `tree_template.yaml`의 구조나 자리표시자 밖 숫자를 바꾸지 않는다. 바꾸면 `test_bt.py`가 실패해야 정상이다.
- `bt-main`, `bt-confirm` 결과를 사전등록 전에 보지 않는다. 점검은 `bt-smoke`로 한다.
- `games.csv`를 손으로 고치지 않는다. 예외는 §5의 `wall_clock` 줄 삭제 하나뿐이다.
- 결과 CSV 는 커밋하지 않는다. **예외: `bt/analysis/fixtures/pilot2_sample.csv`** (분석 코드 시험용 고정 파일. 보정 상대 재예비 실험
  `bt-pilot/games.csv` 에서 분석에 필요한 열만 뽑은 것, θ 50개 2,400경기, 약 0.8 MB). 합성 시험 데이터는 `fixtures/synth.py` 로 만들고 커밋하지 않는다.
- `run.py`를 import 하지 않는다. import 하면 `Pilot.setup`이 바뀐다.

## 7. 폴더 구성 (`cadet_research/kit/`)

| 위치 | 내용 |
|---|---|
| `aircombat/`, `jsbsim_data/`, `config/`, `run.py`, `ENGINE_VERSION.txt` | 엔진 (고치지 않는다) |
| `agents/main/` | 상대 트리. 쓰는 것은 `run_bt.OPPONENTS`의 4개 |
| `bt/energy_fighter.yaml` | 연구 대상 원본 트리 |
| `bt/params.yaml`, `bt/tree_template.yaml`, `bt/make_tree.py` | θ 정의와 트리 생성 |
| `bt/run_bt.py`, `bt/monitor.py`, `bt/trace_match.py` | 실행, 관측, 노드 추적 |
| `bt/test_bt.py`, `bt/validate.py`, `bt/crosscheck.py` | 자가점검, 검증 표, PC 간 재현 점검 |
| `bt/merge.py`, `bt/RUNBOOK.md` | 여러 PC 결과 검사·합치기, 팀원 실행 순서 |
| `bt/requirements-analysis.txt` | 분석 패키지 버전 고정 (`kit/requirements.txt` 를 불러온 뒤 추가) |
| `bt/thetas/main_lhs64.csv`, `bt/thetas/main_morris_r16.csv` | 본실험 설계 파일 (PREREG_BT.md §5, SHA-256 고정). `.gitattributes` 로 줄끝 LF |
| `bt/analysis/fixtures/` | 분석 시험 데이터: `pilot2_sample.csv` (실측 일부), `synth.py` (정답을 아는 합성 데이터와 정답값) |
| `bt/tasks/` | 팀원 작업 지시서 (README.md 부터) |
| `bt/designs.py`, `bt/analysis/` | 팀원 몫 (빈 틀) |
| `bt/thetas/` | θ 목록 (`baseline.csv`, `validation.csv`, `r0.csv`, `pilot_lhs50.csv`, `diag.csv`) |
| `bt/opponents_patched/` | 보정 상대 (기본 상대 묶음). 원본과 다른 곳은 최우선 노드 두 줄뿐 (`test_bt.py`가 확인) |
| `bt/diag_opponents/` | 진단 전용 상대 복사본 (floor_ft 1200 → 4000 만 다름). 본 실험에 쓰지 않는다 |
| `bt/diag_trace.py`, `bt/diag_report.py` | 하드덱 진단 (재실행 추적, 보고서) |
| `bt/trees/` | 생성된 트리 (자동, git 제외) |
| `bt/out/<접두어>/games.csv`, `bt/out/r0/games.csv` | 원자료 (git 제외) |
| `bt/out/validation.md`, `bt/out/hard_deck_traces.md` | 검증 결과와 하드덱 경기 추적 (git 포함) |
| `bt/out/validation_runs/` | 검증 4(병렬 수)와 옛 열 형식 smoke 원자료 |

`tree_template.yaml` 머리말의 "원본:" 주석은 `ai-combat-core2-main/examples/energy_fighter.yaml`을 가리킨다 (그 파일도 저장소에 그대로 있고 `bt/energy_fighter.yaml`과 내용이 같다). 주석을 고치면 `tree_sha`가 바뀌어 기존 결과와 비교할 수 없어서 그대로 둔다.

## 8. PC 간 재현 점검 (`bt/crosscheck.py`)

기준 θ 로 고정 10경기 (bt-smoke 시드, 기하 3종 × 상대 4 섞음) 를 돌려 결과 열의 해시를 찍는다. 파일은 쓰지 않는다.
해시에 넣는 열은 `run_bt.FIELDS`에서 실행 환경 열 (`wall_s`, `host`, `python_version`, `engine_sha`)을 뺀 전부다.

**기준 PC 결과** (2026-11-02, 기본 상대를 보정 상대 `patched` 로 바꾸고 `opponent_set` 열을 추가한 뒤 다시 잼, 두 번 돌려 같음. 이전 값 `8ccad3d1e0e7ae05` (원본 상대, opponent_set 열 없음), `c7a8776f48d4ba9d` (node_frac_red 열도 없음) 는 쓰지 않는다):

| 항목 | 값 |
|---|---|
| python_version | 3.11.9 |
| engine_sha | `1e0101026959` |
| **전체 해시** | **`fc6501b873df43e1`** |

| 경기 | 결과 | 경기 해시 |
|---|---|---|
| perch_offense / A2_GunTracker_00 / bt-smoke-0 | red timeout | `1ca188075bc2` |
| perch_offense / C1_TwoCircleRate_00 / bt-smoke-1 | red health_zero | `dac1256efcad` |
| perch_offense / D1_Reactive_00 / bt-smoke-2 | red timeout | `83878c731863` |
| perch_defense / B2_Extender_00 / bt-smoke-0 | red health_zero | `318eead7ebc4` |
| perch_defense / D1_Reactive_00 / bt-smoke-1 | red timeout | `823047364e7c` |
| perch_defense / A2_GunTracker_00 / bt-smoke-3 | red timeout | `d97e38d34ddc` |
| neutral / A2_GunTracker_00 / bt-smoke-0 | red health_zero | `3b8902423605` |
| neutral / B2_Extender_00 / bt-smoke-2 | red health_zero | `18663bdef731` |
| neutral / C1_TwoCircleRate_00 / bt-smoke-3 | red health_zero | `272c265338d0` |
| neutral / D1_Reactive_00 / bt-smoke-1 | red timeout | `52a812a5352f` |

전체 해시가 다르면: ① `engine_sha`가 다르면 엔진 파일이 다른 것이니 저장소를 다시 받는다. ② `engine_sha`는 같고 Python 버전이
다르면 3.11.9 로 맞춰 다시 돌린다. ③ 둘 다 같은데 다르면 경기별 해시로 다른 경기를 찾아 기준 PC 담당자에게 알린다.
결과가 다른 PC 의 games.csv 는 기준 PC 결과와 섞지 않는다. `wall_clock` 경고가 나오면 다른 프로그램을 닫고 다시 돌린다.
