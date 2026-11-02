# BT 파라미터 실험: 팀원 계약서

> **처음 받은 팀원 순서** (Python 3.11.9 권장)
> 1. `git clone -b bt-study https://github.com/yeonwoo-jeong-3812/ai_pilot_core2.git`
> 2. `cd ai_pilot_core2/cadet_research/kit` 후 `python -m pip install -r requirements.txt`
> 3. `python bt/test_bt.py` → 마지막 줄 "bt 자가점검 통과"
> 4. `python bt/crosscheck.py` → "전체 해시"가 §8의 기준 해시 `c7a8776f48d4ba9d`와 같은지 비교 (다르면 §8)

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
```

- 결과는 `bt/out/<접두어>/games.csv`에 이어 쓴다. 끊기면 같은 명령을 다시 치면 끝난 경기는 건너뛰고 이어서 돈다.
- `--procs`는 CPU 코어 수보다 작게 준다. 8코어 PC는 6.
- θ 목록 파일: CSV는 첫 줄이 열 이름, JSON은 dict 목록이다. 키는 `params.yaml`의 10개 이름과 `dummy`. 열 순서는 상관없다.
  예시는 `bt/thetas/baseline.csv`.
- θ 하나는 48경기다: 교전 기하 3 (`perch_offense`, `perch_defense`, `neutral`) × 상대 4 × 시드 4.
  상대는 `run_bt.py`의 `OPPONENTS`에 있다: `A2_GunTracker_00`, `B2_Extender_00`, `C1_TwoCircleRate_00`, `D1_Reactive_00`.
- 청(blue)은 항상 θ 트리, 적(red)은 항상 상대다. `perch_defense`는 `perch_offense`의 진영을 맞바꾼 기하라서,
  청을 고정해도 공세와 수세가 둘 다 들어간다.

## 2. games.csv 열 (이 순서와 이름이 계약이다)

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
| `sim_time_s` | 경기 종료 시각 (시뮬레이션 시간) | s |
| `wall_s` | 실제 걸린 시간. 재현 대상 아님 | s |
| `engine_sha` | `aircombat/`, `jsbsim_data/`, `config/` 내용 해시 앞 12자리 (줄끝·`__pycache__` 무시) | 문자열 |
| `tree_sha` | 실제로 쓴 트리 파일의 sha256 앞 12자리 | 문자열 |
| `host` | 실행한 PC 이름. 재현 대상 아님 | 문자열 |
| `python_version` | 실행한 Python 버전 (`platform.python_version()`) | 예: `3.11.9` |

`end_reason` 값: `health_zero` 격추, `hard_deck` 1,000 ft 아래로 이탈, `stall` 100 kt 미만 누적 10 s,
`timeout` 300 s 종료 (피해 교환 있음, 체력 많은 쪽 승), `no_contact` 300 s 동안 양쪽 무피해 (무승부),
`disqualified` 트리 오류, `wall_clock` **실제 시간 120 s 안전장치에 걸림 (실행 인공물, §5)**.

`off_frac`, `def_frac`, `e_adv_ft`, `t_first_wez`, `node_frac`는 `bt/monitor.py`가 잰다 (읽기 전용). `node_frac`는 bt에서 추가한 것이다. 앞의 넷은 origin/YEOP의
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
- θ 목록에 같은 θ가 두 번 있으면 한 번만 돈다. dummy만 다른 θ는 트리 파일은 같고 `theta_id`는 다르다.

## 6. 하면 안 되는 것

- kit의 `aircombat/`, `jsbsim_data/`, `config/`, `run.py`, `run_extra.py`를 고치지 않는다. INDI 논문과 같은 엔진이어야 비교할 수 있다.
  `engine_sha`가 바뀌었으면 결과를 섞지 않는다.
- 심판 규칙(하드덱 1,000 ft, 실속, WEZ, DPS, HP, 300 s, 오버타임 없음), 기체·INDI 명목값, L2 교리 기본값, dt, 상대 트리를 바꾸지 않는다.
- `tree_template.yaml`의 구조나 자리표시자 밖 숫자를 바꾸지 않는다. 바꾸면 `test_bt.py`가 실패해야 정상이다.
- `bt-main`, `bt-confirm` 결과를 사전등록 전에 보지 않는다. 점검은 `bt-smoke`로 한다.
- `games.csv`를 손으로 고치지 않는다. 예외는 §5의 `wall_clock` 줄 삭제 하나뿐이다.
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
| `bt/designs.py`, `bt/analysis/` | 팀원 몫 (빈 틀) |
| `bt/thetas/` | θ 목록 (`baseline.csv`, `validation.csv`, `r0.csv`) |
| `bt/trees/` | 생성된 트리 (자동, git 제외) |
| `bt/out/<접두어>/games.csv`, `bt/out/r0/games.csv` | 원자료 (git 제외) |
| `bt/out/validation.md`, `bt/out/hard_deck_traces.md` | 검증 결과와 하드덱 경기 추적 (git 포함) |
| `bt/out/validation_runs/` | 검증 4(병렬 수)와 옛 열 형식 smoke 원자료 |

`tree_template.yaml` 머리말의 "원본:" 주석은 `ai-combat-core2-main/examples/energy_fighter.yaml`을 가리킨다 (그 파일도 저장소에 그대로 있고 `bt/energy_fighter.yaml`과 내용이 같다). 주석을 고치면 `tree_sha`가 바뀌어 기존 결과와 비교할 수 없어서 그대로 둔다.

## 8. PC 간 재현 점검 (`bt/crosscheck.py`)

기준 θ 로 고정 10경기 (bt-smoke 시드, 기하 3종 × 상대 4 섞음) 를 돌려 결과 열의 해시를 찍는다. 파일은 쓰지 않는다.
해시에 넣는 열은 `run_bt.FIELDS`에서 실행 환경 열 (`wall_s`, `host`, `python_version`, `engine_sha`)을 뺀 전부다.

**기준 PC 결과** (2026-11-02, 커밋 `66d2d2b` 이후, 두 번 돌려 같음):

| 항목 | 값 |
|---|---|
| python_version | 3.11.9 |
| engine_sha | `1e0101026959` |
| **전체 해시** | **`c7a8776f48d4ba9d`** |

| 경기 | 결과 | 경기 해시 |
|---|---|---|
| perch_offense / A2_GunTracker_00 / bt-smoke-0 | red timeout | `97b1ee1fb633` |
| perch_offense / C1_TwoCircleRate_00 / bt-smoke-1 | red health_zero | `68df22e62c54` |
| perch_offense / D1_Reactive_00 / bt-smoke-2 | blue hard_deck | `027e532c1f72` |
| perch_defense / B2_Extender_00 / bt-smoke-0 | red health_zero | `85cff8c9ffa9` |
| perch_defense / D1_Reactive_00 / bt-smoke-1 | red health_zero | `a16338b2a801` |
| perch_defense / A2_GunTracker_00 / bt-smoke-3 | blue hard_deck | `b76964ada423` |
| neutral / A2_GunTracker_00 / bt-smoke-0 | blue hard_deck | `a046998e011f` |
| neutral / B2_Extender_00 / bt-smoke-2 | red health_zero | `91eeb94067ef` |
| neutral / C1_TwoCircleRate_00 / bt-smoke-3 | red health_zero | `c89fc93064ca` |
| neutral / D1_Reactive_00 / bt-smoke-1 | red health_zero | `673ebace65e3` |

전체 해시가 다르면: ① `engine_sha`가 다르면 엔진 파일이 다른 것이니 저장소를 다시 받는다. ② `engine_sha`는 같고 Python 버전이
다르면 3.11.9 로 맞춰 다시 돌린다. ③ 둘 다 같은데 다르면 경기별 해시로 다른 경기를 찾아 기준 PC 담당자에게 알린다.
결과가 다른 PC 의 games.csv 는 기준 PC 결과와 섞지 않는다. `wall_clock` 경고가 나오면 다른 프로그램을 닫고 다시 돌린다.
