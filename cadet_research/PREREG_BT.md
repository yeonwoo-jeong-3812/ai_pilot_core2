# 사전 분석계획서 (초안): BT 파라미터 실험

> **초안이다. 태그 `prereg-bt-v1` 을 만들기 전.** 근거 파일과 팀 결정 (2026-11-02) 에 없는 내용은 지어내지 않고 **[팀 결정 필요]**로 표시했다.
> 근거 파일 (모두 `cadet_research/kit/bt/` 기준): `params.yaml`, `CONTRACT.md`, `out/validation.md`, `analysis/pilot_rules.md`,
> `out/pilot_report.md`, `out/pilot2_report.md`, `analysis/opponent_patch_rules.md`, `out/diag_hard_deck.md`, `RUNBOOK.md`.
> 고정 뒤 변경은 이 문서를 고치지 않고 `cadet_research/PREREG_BT_DEVIATIONS.md` 에만 추가한다 (§7).

## 고정 전 점검표

태그 `prereg-bt-v1` 을 만들기 직전, 고정할 커밋에서 아래를 모두 확인한다 (`cadet_research/kit/` 에서).

| # | 항목 | 고정 값 | 확인 방법 | 확인 |
|---|---|---|---|---|
| 1 | 엔진 해시 (`engine_sha`) | `1e0101026959` | `python -c "import sys; sys.path.insert(0,'bt'); import run_bt; print(run_bt.engine_sha())"` | [ ] |
| 2 | crosscheck 전체 해시 | `fc6501b873df43e1` (Python 3.11.9) | `python bt/crosscheck.py` (= `CONTRACT.md` §8) | [ ] |
| 3 | 설계 파일 SHA-256 | §5 표의 두 값 | `python bt/test_bt.py` (`test_main_design_files`) 또는 `certutil -hashfile <파일> SHA256` | [ ] |
| 4 | 패키지 버전 | `kit/requirements.txt` + `bt/requirements-analysis.txt` (모두 `==`) | `python -m pip freeze` 와 비교 | [ ] |
| 5 | 시드 규칙 | bt-main 셀당 4 (RQ1·RQ2 공유), bt-confirm 셀당 36 | `python bt/run_bt.py bt/thetas/main_lhs64.csv --prefix bt-main --unlock-confirm --dry` → 3,072, `main_morris_r16.csv` → 9,216 | [ ] |
| 6 | 1차 지표 | Δwez = `wez_blue − wez_red` | 이 문서 §4 | [ ] |
| 7 | 자가점검 | 전부 통과 | `python bt/test_bt.py` | [ ] |
| 8 | 남은 [팀 결정 필요] | "결과 파일 보내는 곳" 하나 (실행 전 정하면 됨) | 이 문서 끝 "남은 결정" | [ ] |

## 0. 고정 전 상태

- 보정 상대 R0 (측정 점검) 은 1차 지표 Δwez 기준으로 통과했다 (`validation.md` §8.2). 승률 기준으로는 민감도 불통과였고,
  그래서 1차 지표를 Δwez 로 바꿨다 (§4, §8). 이 변경은 결과를 본 뒤의 결정이다.
- bt-main·bt-confirm 은 태그 `prereg-bt-v1` 이 생기기 전에는 `run_bt.py` 가 실행을 거부한다 (`--force-dev` 로도 못 건너뜀).

## 1. 연구 질문

- **RQ1 (분산분해):** 근접 공중전 BT (`bt/energy_fighter.yaml`) 의 숫자 파라미터 10개를 바꿨을 때 1차 지표 Δwez 의 분산을
  θ, 교전 기하, 상대와 그 상호작용, 시드 잔차로 나누면 θ 몫은 얼마인가 (모형 §6.1).
  근거: `CONTRACT.md` 머리말 ("숫자 파라미터가 승패를 얼마나 좌우하는가").
- **RQ2 (Morris 중요도와 기하별 순위):** 파라미터별 Morris μ*·μ·σ 로 중요도를 매기고, 더미보다 뚜렷이 큰 파라미터를 가린다.
  그 중요도가 교전 기하 (`perch_offense`, `perch_defense`, `neutral`) 마다 다른가 (판정 §6.2).
- **RQ3 (조건부 최적화):** **조건부로만 진행한다.** RQ2 상위 파라미터를 근거로 후보 θ 3개 — 관측 최고 θ 1개와
  대리모델이 예측한 최고 θ 2개 — 를 bt-confirm 시드에서 기준 θ 와 비교해 Δwez 가 나은지 확인한다. 새 최적화 알고리즘은 쓰지 않는다.
  - **진행 조건 (11/13 관문):** 대리모델 R² 기준 충족 (§6.3) **그리고** 계산 여유. 둘 중 하나라도 안 되면 RQ3 는 하지 않는다.
  - **관측 최고 θ:** bt-main 으로 돌린 RQ1·RQ2 θ 전체 (256개) 중 48경기 평균 Δwez 가 가장 큰 θ. 동률이면 승률이 높은 쪽.
  - **선택 편향:** 여러 θ 중 최고를 고르면 그 θ 의 bt-main 평균은 위로 치우친다 (승자의 저주). 그래서 후보의 효과는 bt-main 값이
    아니라 **새 시드 (bt-confirm) 의 확인 단계 결과 (§6.4)** 로만 판단한다.

## 2. 고정 조건

| 항목 | 값 | 근거 |
|---|---|---|
| 엔진 | `kit/aircombat/`, `jsbsim_data/`, `config/` 고치지 않음. `engine_sha` (bt 정의: 세 폴더 내용 해시, 줄끝·`__pycache__` 무시) = **`1e0101026959`** | `CONTRACT.md` §2, §6, §8 |
| 엔진 출처 | core2 `fidelity/pw220-evidence` `3f2569f…`, 스냅샷 2026-10-14 (작업 트리 복사, `ENGINE_VERSION.txt` 의 engine_sha256 `e4da961689713328` 는 다른 해시 정의) | `kit/ENGINE_VERSION.txt` |
| 심판 규칙 | 하드덱 1,000 ft, 실속 (100 kt 미만 누적 10 s), WEZ (500–3,000 ft, ATA < 30°), DPS·HP, 300 s, 오버타임 없음 | `CONTRACT.md` §2, §6 |
| 기체·INDI | 기체·INDI 명목값, L2 교리 기본값, dt 바꾸지 않음 | `CONTRACT.md` §6 |
| 상대 | **보정 상대 4종** (`bt/opponents_patched/`, `--opponents patched` 기본): A2_GunTracker_00, B2_Extender_00, C1_TwoCircleRate_00, D1_Reactive_00 | `opponent_patch_rules.md`, `CONTRACT.md` §1 |
| 상대 보정 내용 | 원본 (`kit/agents/main`, 고치지 않음) 에서 최우선 `low_altitude → climb` 노드만 청 recover 와 같게: floor_ft 1200 → 4500, g_burst 0.8 추가. 나머지 바이트 동일 (`test_bt.py`) | `opponent_patch_rules.md` |
| 보정 근거 | 원본 상대 예비 실험에서 청 승리의 69% 가 상대 하드덱. 추적 20경기 모두 low_altitude 작동 0.25–0.9 s 뒤 하드덱, 9 G 즉시 당김으로도 15/20 회복 불가. 보정 후 상대 하드덱 0.000 (원본 0.264), climb 실행 비율 0.125 | `diag_hard_deck.md`, `out/opponent_patch_check.md` |
| 시작 조건 | 기하 3종. 고도 12,000–18,000 ft (양측 공통), 속도 명목 ± 20 kt, 방위 명목 ± 30°, 분리거리 명목 (6 nm) ± 20%. 지터는 `derive_seed(scenario, seed_salt)` 로 정해진다 | `kit/aircombat/engine/scenarios.py`, `CONTRACT.md` §2·§3 |
| 난수 | 엔진에 다른 난수원 없음. 같은 θ·셀은 실행 환경 열을 뺀 모든 열이 같다. PC 간 재현은 `crosscheck.py` 기준 해시 `fc6501b873df43e1` | `CONTRACT.md` §3, §8 |
| 실행 환경 | Python 3.11.9. 실행 전 점검 (bt/ 커밋 상태, Python, crosscheck 해시, bt-main·bt-confirm 은 태그) 을 통과해야 `run_bt.py` 가 돈다. 결과 행에 `code_commit` 기록 | `CONTRACT.md` §1, `RUNBOOK.md` |
| 패키지 | 실행: `kit/requirements.txt` (numpy 2.4.2, jsbsim 1.3.1, pyyaml 6.0.3). 분석: `bt/requirements-analysis.txt` — scipy 1.17.1, pandas 3.1.0, statsmodels 0.15.0, scikit-learn 1.9.1, shap 0.51.0, SALib 1.6.0, matplotlib 3.11.0 (모두 `==`) | `bt/requirements-analysis.txt` |

- 패키지 고정 위치: 분석 패키지는 `kit/requirements.txt` 가 아니라 `bt/requirements-analysis.txt` 에 두었다 (kit 파일은 엔진 키트라 bt 작업에서 고치지 않는다.
  분석 파일이 `-r ../requirements.txt` 로 kit 고정을 그대로 불러온다). 설치 뒤 crosscheck 해시가 같음을 확인했다.

## 3. 파라미터

| 이름 | 트리 위치 (노드.키) | 기준 | 범위 | 단위 |
|---|---|---|---|---|
| merge_range_ft | merged.range_ft | 6000 | 4000–9000 | ft |
| threat_aspect_deg | foe_threat.aspect_deg | 150 | 120–170 | ° |
| gun_range_ft | in_gun_envelope.range_ft | 3000 | 1500–3000 | ft |
| gun_ata_deg | in_gun_envelope.ata_deg | 45 | 15–60 | ° |
| fight_kcas | below_fighting_speed.kcas | 280 | 220–330 | kt |
| energy_min_ft | energy_advantage.min_ft | 500 | 0–2000 | ft |
| lead_time_s | press_offense.lead_time_s | 2.0 | **0.5–3.0** | s |
| break_g_burst | break_defense.g_burst | 0.5 | 0–1 | — |
| closing_min_fps | closing.min_fps (yoyo_pull_up 쪽만) | 60 | 0–200 | ft/s |
| floor_ft | low_altitude.floor_ft | 4500 | 3000–7000 | ft |
| **dummy** | 트리에 안 들어감 (영향 없음 기준선) | 0.5 | 0–1 | — |

- 출처: `params.yaml` (단일 진실). 범위 검사는 `make_tree.normalize`. **파라미터 10개와 범위는 바꾸지 않는다** (2026-11-02 팀 결정).
- **lead_time_s 범위 근거:** 기준값 2.0 ± 1.5 로 설정했고, 상한만 엔진 DSL 허용 범위 (0.0–3.0, `aircombat/tactics/dsl.py` `_ACTION_BOUNDS`)
  때문에 3.0 으로 줄였다 (그래서 0.5–3.0).
- `closing` 조건은 트리에 두 곳이다. yoyo_pull_up 의 min_fps 만 파라미터이고 inverter 안의 `min_fps: 0` 은 고정 (`CONTRACT.md` §5).
- 범위 점검 (노드 작동, 재예비 실험): 10개 모두 "작동". gun_ata_deg 하 1/3 (15–30°) 은 gun_track 미실행 경기 87% 로 비활성 기준 (90%) 바로 아래 (`pilot2_report.md` (3)).

## 4. 지표

- **1차 지표: Δwez = `wez_blue − wez_red`** [s] (각자 상대를 엔진 WEZ 안에 둔 누적 시간의 차).
- **보조 지표:** 승률 (청 승 = 1, 무승부·패 = 0), 실제 체력 차 (`hp_blue_raw − hp_red_raw`, 판정 처리 전), win_mode 분포
  (shootdown, opp_hard_deck, opp_stall, judge, other). 보조 지표는 함께 보고만 하고 판정에 쓰지 않는다.
- **체력 차 최소 의미 차이: 10 HP** (보정 상대 잡음 범위 9.0 HP 근거, `validation.md` §8.1). 보조 지표라 해석 기준으로만 쓴다.
- **선택 규칙 (2026-11-02, 결과를 본 뒤 정함 — §8):** "1차 지표는 보정 상대 환경의 R0 민감도·특이도를 통과해야 자격이 있고,
  자격 있는 후보 (pilot_rules 의 원래 후보인 승률, Δwez) 중 예비 실험 R 이 큰 것을 택한다."

  | 후보 | 보정 상대 R0 민감도 (R0-2 − 기준) | 특이도 (미세 θ) | 자격 | 재예비 실험 R (95% CI) |
  |---|---|---|---|---|
  | 승률 | Δ −0.104 (CI −0.238, +0.029) — **X** (기준 θ 승률 약 0.21 바닥 효과) | O | 없음 | 9.72 (6.61, 13.02) |
  | **Δwez** | Δ −1.71 s (CI −2.51, −0.91), 효과/잡음 3.35 — **O** | O | **있음** | **5.46 (3.68, 7.09)** |

  근거: `validation.md` §8.2·§8.2.1, `pilot2_report.md` (1). 이전 규칙 (pilot_rules (2), R 이 큰 쪽) 으로는 승률이었다 (원본 R 비 2.98, 보정 1.78).
- 잡음 범위 (보정 상대, 기준 θ, 시드 묶음 3개 쌍별 최대 |Δ|): Δwez 0.51 s, 승률 0.104, 체력 차 9.0 HP (`validation.md` §8.1).
- 보정 상대에서 청 승리의 68% 가 판정승, 31% 가 격추승 (`pilot2_report.md`).

## 5. 설계

- **θ 당 경기:** 48 (기하 3 × 상대 4 × 시드 4). 같은 단계의 모든 θ 가 같은 48셀 (공통 난수).
- **시드:** RQ1 과 RQ2 는 **같은 bt-main 시드 (셀당 4개, `bt-main-0..3`)** 를 쓴다. 확인 단계는 **bt-confirm, 셀당 36개**
  (`run_bt.py --nseeds 36`, `bt-confirm-0..35`, 3 × 4 × 36 = 432경기/θ). `--nseeds` 기본값 4 는 기존 시드와 같다 (`test_nseeds_default_unchanged`).
- **RQ1 — 라틴 하이퍼큐브:** θ 64개 = `designs.lhs(64, seed=20261108)` (numpy, dummy 포함 11차원, 차원마다 64 층 무작위 배치 + 층 안 균등). 3,072경기.
- **RQ2 — Morris:** 요인 11개 (dummy 포함), **수준 4, 궤적 16**, SALib 1.6.0 표준 궤적 생성 (`SALib.sample.morris.sample`, 최적 궤적 선택 없음),
  생성 난수 seed **20261108** = `designs.morris(16, 4, 20261108)`. 궤적당 θ 12개 → θ 192개 (모두 서로 다름), 9,216경기.
  파일에 `trajectory` (0–15), `step` (0–11) 열이 있어 분석에서 궤적을 복원한다 (`run_bt.py` 는 이 두 열을 θ 에서 뺀다).
- **설계 파일** (`python bt/designs.py` 로 다시 만들면 같은 파일, `test_main_design_files`):

  | 파일 | θ | 경기 (`--dry`) | SHA-256 |
  |---|---|---|---|
  | `bt/thetas/main_lhs64.csv` | 64 | 3,072 | `8710b22ee672c33c9ac1e32f4d8faf198bac2103b9734ca915783a4331b74f90` |
  | `bt/thetas/main_morris_r16.csv` | 192 | 9,216 | `b4818f16c370f03af6bbb908d65aba3187e4d4a4b4ee947915c35cb5f4d9b971` |

  SHA-256 은 LF 줄끝 기준이다. `bt/.gitattributes` 가 이 파일들을 LF 로 받게 하므로 clone 에서도 `certutil` 값이 같아야 한다. 그래도
  `test_main_design_files` (같은 seed 로 다시 만들어 비교) 로 확인한다.
- **확인 (RQ3 조건부):** θ 4개 (기준 + 후보 3) × 432경기 = 1,728경기, bt-confirm 시드.
- **시드 접두어와 용도** (`CONTRACT.md` §3):

  | 접두어 | 쓰임 |
  |---|---|
  | bt-smoke | 실행 점검, 해석 안 함 |
  | bt-pilot | 예비 실험 (끝남: 원본 상대 `games_original.csv`, 보정 상대 `games.csv`) |
  | bt-cal, bt-cal-a, bt-cal-b | 보정: 잡음·허용폭·시드 수 결정 |
  | bt-diag | 진단·상대 보정 검증 |
  | **bt-main** | **본실험 RQ1·RQ2. `--unlock-confirm` 과 태그 `prereg-bt-v1` 이 있어야 돈다** |
  | **bt-confirm** | **확인 단계 (RQ3). 같은 잠금, `--nseeds 36`** |

- **분산 실행:** `run_bt.py --shard i/n` 으로 나누고 `bt/merge.py` 로 검사·합친다 (`RUNBOOK.md`, `CONTRACT.md` §1).

## 6. 분석

### 6.1 RQ1 — 분산분해

- **모형:** 경기별 Δwez = θ + 기하 + 상대 + θ×기하 + θ×상대 + 기하×상대 + 잔차 (시드).
- **방법:** 균형 완전교차 설계이므로 **고정효과 ANOVA 제곱합 비율 (η²)** 을 분산 비율로 쓴다 (각 항 제곱합 / 전체 제곱합).
- **불확실성:** **θ 단위 재표집 부트스트랩 2,000회, seed 20261108**, 각 항 η² 의 95% CI (백분위).
- 데이터: bt-main 의 RQ1 θ 64개 × 48경기 (`main_lhs64.csv`).
- 참고 (관문 2 에서 쓴 θ 신호 비율): V = var(θ 평균) − mean(경기 간 분산 / n), R = V / N (`pilot_rules.md` (1)).

### 6.2 RQ2 — Morris μ*·μ·σ

- **입력:** θ 별 48경기 평균 Δwez (기하별 분석은 θ 별 그 기하 16경기 평균).
- **지표:** 파라미터마다 기본효과의 μ* (절댓값 평균), μ (평균), σ (표준편차). 전체와 기하별로 계산한다.
- **부트스트랩:** 단위는 **궤적**, **2,000회, seed 20261108**. 95% CI (백분위).
- **중요 판정:** 파라미터 μ* 의 95% CI 하한 > 더미 μ* 의 95% CI 상한.
- **기하별 순위:** 기하별 μ* 순위와 기하 쌍 사이 **Spearman 순위 상관** (서술용, 부트스트랩 CI).
  **"기하별 순위가 다르다"** = 어떤 파라미터가 한 기하에서는 중요, 다른 기하에서는 중요 아님이고, 두 기하 μ* 차이의 95% CI 가 0 을 포함하지 않을 때.

### 6.3 대리모델

- **모형:** scikit-learn `HistGradientBoostingRegressor`. 입력 θ (10개 + 더미), 출력 θ 별 평균 Δwez.
- **데이터:** bt-main θ 256개 (RQ1 64 + RQ2 192). **무작위 20% θ 를 떼어 둔다 (seed 20261108).**
- **보고 조건:** 떼어 둔 데이터 **R² ≥ 0.5 일 때만** SHAP (`TreeExplainer`) 해석을 결과로 보고한다. 미달이면 SHAP 은 보고하지 않는다.

### 6.4 확인 단계 (RQ3 조건부)

- θ 4개 (기준 + 후보 3) 를 bt-confirm 시드에서 θ 당 **432경기** 돌린다.
- **비교:** 후보 θ − 기준 θ 의 **짝 차이 Δwez (같은 기하·상대·시드끼리)**.
- **"낫다"** = Holm 보정 후 단측 유의 (α 0.05) **이고** 95% CI 하한 > 0.
- **"실질적으로 낫다"** = "낫다" **이고** 점추정 ≥ 0.5 s (최소 의미 차이 Δwez 0.5 s).
- **동등성:** ±0.5 s TOST (α 0.05).
- 432경기의 근거: 검정력 표 (95% 신뢰수준, 80%, `validation.md` §8.4) 의 Δwez 0.5 s 필요 경기 수 — bt-cal 합동 sd 217, 재예비 θ 쌍 중앙값 268, 90 백분위 408.
- 보조 지표 (승률, 체력 차) 도 같은 표에 서술용으로 적는다.

### 6.5 계산 예산 (이 PC, `--procs 6`, 보정 상대 4.21 s/경기, `validation.md` §9)

| 단계 | 경기 | PC 1대 [h] | PC 3대 [h] |
|---|---|---|---|
| RQ1 LHS 64 × 48 | 3,072 | 3.6 | 1.2 |
| RQ2 Morris 수준 4, 궤적 16 (θ 192) × 48 | 9,216 | 10.8 | 3.6 |
| 확인 θ 4 × 432 | 1,728 | 2.0 | 0.7 |
| **합계** | **14,016** | **16.4** | **5.5** |
| 선택: 원본 상대 견고성 64 × 48 (2.72 s/경기) | 3,072 | 2.3 | 0.8 |

PC 3대는 같은 사양 가정 (실측 아님). 다른 PC 결과는 crosscheck 해시가 같고 `merge.py` 검사를 통과할 때만 합친다.

## 7. 제외·재실행 규칙과 계획 변경 기록

- **wall_clock** (실제 시간 120 s 안전장치): 실행 인공물. 그 줄을 games.csv 에서 지우고 같은 명령으로 다시 돌린다. 분석에 넣지 않는다
  (`CONTRACT.md` §5). `merge.py` 는 wall_clock 이 남아 있으면 합치지 않는다.
- **disqualified:** 생성 오류로 본다. **실행을 중단하고, 원인을 고친 뒤 해당 θ 전체 (그 단계의 θ 당 경기 전부) 를 다시 돌린다. 건수를 기록한다.**
  `merge.py` 는 disqualified 가 있으면 합치지 않는다.
- **끊긴 실행:** 같은 명령으로 재개. `run_bt.py` 가 기록된 경기를 건너뛴다 (재개 키에 `opponent_set` 포함). 끝난 뒤 중복·누락 0 을 확인한다.
- **여러 PC:** `code_commit`·`engine_sha`·`opponent_set` 이 모두 같아야 합친다 (`merge.py`).
- **열 형식이 바뀐 games.csv 에는 이어 쓰지 않는다.** 옛 파일은 내용을 고치지 않고 이름만 바꿔 보관 (`CONTRACT.md` §5).
- `games.csv` 는 손으로 고치지 않는다 (예외: wall_clock 줄 삭제) (`CONTRACT.md` §6).
- **고정 뒤 변경 기록:** 태그 `prereg-bt-v1` 뒤에는 **이 문서 본문을 고치지 않는다.** 변경은 `cadet_research/PREREG_BT_DEVIATIONS.md` 에
  날짜, 커밋, 이유, 영향만 한 줄씩 추가한다. 고정 전 변경은 §8 에 적는다 (선례: `validation.md` "판정 규칙 변경 기록", §8.2.1).

## 8. 지금까지의 변경 이력 (고정 전)

| 날짜 (커밋) | 변경 | 결과를 본 뒤인가 | 근거 |
|---|---|---|---|
| 2026-11-02 (`66d2d2b`) | lead_time_s 범위를 0.5–3.0 으로 (기준 2.0 ± 1.5, 상한만 엔진 DSL 3.0) | 아니오 (실행 전) | `params.yaml`, `CONTRACT.md` §5 |
| 2026-11-02 (`66d2d2b`) | 망가진 θ A·B 검증 불통과 → 예비 관찰로만 기록, R0 로 재설계 | 예 | `validation.md` §3 |
| 2026-11-02 (`66d2d2b`) | **R0 판정 규칙 변경**: "모든 R0 후보가 (a)(b) 통과" → "민감도 (노드 확인된 악화 θ 하나 이상이 두 지표 모두 (b) 통과) + 특이도 (미세 θ 두 지표 모두 잡음 안)" | **예** (R0-1·2·3 결과 뒤) | `validation.md` "판정 규칙 변경 기록" |
| 2026-11-02 (`ca71978`) | 예비 실험 판단 규칙 사전 고정 | 아니오 | `pilot_rules.md` |
| 2026-11-02 (`2b632f0`) | 상대 하드덱 진단 (설계 변경 없음) | — | `diag_hard_deck.md` |
| 2026-11-02 (`fd10dc2` → `de142b2`) | **상대 보정**: 상대 climb 노드를 청 recover 와 같게 (floor_ft 4500, g_burst 0.8). 기본 상대를 보정 상대로 | **예** (원본 상대 예비 실험·진단 뒤). 보정 규칙·합격 기준은 실행 전 커밋 | `opponent_patch_rules.md` |
| 2026-11-02 (`0c9aa99`) | 보정 상대로 예비 실험 재실행 (규칙 그대로) | — | `pilot2_report.md` |
| 2026-11-02 (`0a60685`) | 보정 상대에서 측정 점검 재확인: 승률·wez 차 두 지표 규칙으로 R0 불통과 (승률 민감도) | — | `validation.md` §8 |
| 2026-11-02 (`3070529`) | **1차 지표 변경: 승률 → Δwez.** 새 선택 규칙 ("보정 상대 R0 민감도·특이도 통과 후보 중 예비 실험 R 이 큰 것"). R0 판정은 1차 지표 기준, 보조 지표는 보고만. 이전 규칙: pilot_rules (2) "R 이 큰 쪽, 1.5배 이내면 Δwez" → 승률 | **예** (pilot·pilot2·보정 상대 R0 결과 모두 뒤) | `validation.md` §8.2.1 |
| 2026-11-02 (`3070529`) | 계획 미정 항목 1차 채움 (RQ3 조건부, RQ1 모형, Morris 수준 4·궤적 16·seed 20261108, 중요 판정, 대리모델 R² ≥ 0.5, 확인 432경기·TOST ±0.5 s, LHS seed 20261108, disqualified 처리) | 예 (예비 실험·보정 결과 뒤, 본실험 전) | 이 문서 |
| 2026-11-02 (`7be2b06`) | 남은 결정 채움 (관측 최고 θ, 체력 차 10 HP, 패키지 고정, `--nseeds`·시드 규칙, η² ANOVA, Morris 부트스트랩·기하 차이 정의, HGB 대리모델, Holm·TOST, 고정 뒤 변경 기록), 설계 파일 생성·SHA-256, 태그 잠금 | 예 (본실험 전) | 이 문서 |

## 9. 한계

- **단일 BT 구조:** `energy_fighter.yaml` 하나의 구조에서 숫자 10개만 바꾼다. 결과는 이 구조에 한정된다 (`CONTRACT.md` 머리말).
- **보정 상대:** 상대의 고도 안전장치를 청과 같게 바꿨다. 원본 상대 (core-live 자동 번역, "core2 물리로 재계측 대상") 와 다르다.
  보정 상대 결과를 원본 상대로 일반화할 수 없다. 원본 상대 견고성 점검은 선택 단계다 (§6.5).
- **1차 지표 변경:** 1차 지표 (Δwez) 는 예비 실험과 측정 점검 결과를 본 뒤 정했다. Δwez 는 엔진 WEZ 기하에 머문 시간이라
  승패와 같지 않다. 승률·체력 차·win_mode 는 보조로 함께 보고한다.
- **기총 노드 저활성:** gun_track 은 재예비 실험에서 경기의 64% 에서 한 번도 실행되지 않고 평균 실행 비율 0.4% 다.
  gun_range_ft, gun_ata_deg 의 효과는 작게 나올 수 있다. gun_ata_deg 하 1/3 은 비활성 기준 바로 아래 (87%) (`pilot2_report.md`).
- **C1 상대 승률 바닥 효과:** C1_TwoCircleRate_00 상대 청 승률이 원본 0.028, 보정 0.003 이다. 기준 θ 의 전체 승률도 약 0.21 로 낮다.
- **판정승 비중:** 보정 상대에서 청 승리의 68% 가 판정승 (300 s 종료 시 체력 비교) 이다 (`pilot2_report.md`).
- **관측 최고 θ 선택 편향:** RQ3 후보는 bt-main 에서 고르므로 bt-main 값은 낙관적이다. 확인 단계 (새 시드) 로만 판단한다 (§1).
- **PC 간 차이:** 다른 PC·Python 버전의 결과는 crosscheck 해시가 같을 때만 합친다.

## 남은 결정 ([팀 결정 필요] 모음)

1. 결과 파일 보내는 곳 (`RUNBOOK.md` 8번, `bt/tasks/TASK_RUN.md`) **[팀 결정 필요]**
