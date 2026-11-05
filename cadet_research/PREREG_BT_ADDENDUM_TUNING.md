# 사전 분석계획서 추가: 튜닝 BT 비교

> **이 문서는 RQ3 확인 단계 결과를 본 뒤, 튜닝 BT 비교 결과를 보기 전에 작성·수정했다.** (2026-11-05)
> `PREREG_BT.md` (태그 `prereg-bt-v1`) 에 없는 추가 실험이다. 본 계획의 결과는 본실험 RQ1–RQ3 과 구별해 "사후 추가 실험" 으로 보고한다.
> 고정: 연우가 확인한 뒤 태그 **`prereg-bt-tuning-v1`** 을 만든다. 그 전에는 `run_bt.py` 가 `bt-confirm2` 실행을 거부한다.
> 고정 뒤 변경은 이 문서를 고치지 않고 `PREREG_BT_DEVIATIONS.md` 에 "추가 실험" 으로 표시해 덧붙인다.
> 준비 커밋: `ab2a913` (변형·상대·잠금 코드), 초안 `83b07af`. 분석 코드 `bt/analysis/tuning.py` 는 이 문서와 같은 태그 커밋에 넣는다.

## 1. 질문

1. 데이터 기반 튜닝 (RQ2 중요 파라미터 조정, RQ3 대리모델 1위) 이 **처음 보는 상대** 에게도 승률을 높이는가.
2. 교범값 (근거 있는 것만) 과 비교하면 어떤가.
3. RQ2 에서 중요하지 않다고 나온 7개는 정말 승률과 무관한가.

## 2. 교범값 근거 (저장소 안 출처만, 지어낸 수치 없음)

교범 수치는 엔진 `aircombat/guidance/doctrine.py` 의 절 번호 표기를 따랐고, 원 교범과의 대조는 연구진이 따로 확인한다.
V1 은 **교범 수치를 BT 문턱값으로 옮기는 한 가지 방식** 이며, 결과는 이 방식에 한정해 해석한다 ("교범이 낫다/나쁘다" 로 일반화하지 않는다).

| BT 파라미터 | 교범 수치 | 출처 위치 | BT 값으로 옮기는 방법 | 대응 강도 | V1 값 |
|---|---|---|---|---|---|
| fight_kcas | 파이팅 속도 325–375 kt | `doctrine.py` DOCTRINE_BOUNDS `fighting_kts_lo` (4.4.6.2.2); `conditions.below_fighting_speed` 기본값 = `fighting_kts_lo` | 엔진 조건 기본값이 교범 하한을 그대로 쓴다 → 325 | **강함.** 다만 개념 차이: 교범 파이팅 속도는 전투 중 **유지할 목표 속도**, BT 의 fight_kcas 는 **에너지 회복으로 바꾸는 문턱값** | **325** |
| threat_aspect_deg | 머지 진입 판정 aspect 90–150°, 기본 120° | `doctrine.py` `initial_pull_aspect_deg` (4.4.5.2) | 머지 진입 aspect 를 브레이크 노드의 위협 판정 aspect 게이트로 옮김 → 120 | **약함.** 머지 진입 판정과 위협 판정은 다른 개념 | **120** |
| merge_range_ft | 슬랜트 거리 4,000–6,000 ft | `doctrine.py` `slant_ft_lo/hi` (4.4.6.2.1); `bfm_guidance` 머지 진입 기하 `rng < slant_ft_hi` | 머지 진입 거리 상한 → 6000 (기준값과 같음) | 강함 (같은 쓰임) | 6000 |
| gun_range_ft | 교범 근거 없음 (WEZ 3,000 ft 는 심판 규칙) | — | 근거 없음, 기준값 유지 | 없음 | 3000 |
| gun_ata_deg | 교범 근거 없음 (WEZ 30° 는 심판 규칙; ATA 목표 35–50° (4.4.6.2.2) 는 기동 목표대역이라 건 게이트와 다름) | — | 근거 없음, 기준값 유지 | 없음 | 45 |
| energy_min_ft | 에너지 우위 50–75 kt (4.4.6.2.2) | `doctrine.py` `energy_margin_lo/hi` | 단위가 다르다 (kt ↔ 비에너지 ft). 변환식이 저장소에 없어 옮길 수 없음, 기준값 유지 | 없음 | 500 |
| lead_time_s | 교범 근거 없음 (`bfm_guidance` 기본 1.5 s 는 코드 기본값, 출처 표기 없음) | — | 근거 없음, 기준값 유지 | 없음 | 2.0 |
| break_g_burst | 초기 당김 6–8 G (4.4.5.2), "리미터 살짝 아래" 0.8–0.95 (4.4.7.2) | `doctrine.py` `initial_pull_g`, `g_fraction` | g_burst 는 지속↔순간 봉투 보간 비율이라 G 값과 직접 대응하지 않음, 기준값 유지 | 없음 | 0.5 |
| closing_min_fps | 교범 근거 없음 (접근율 깔때기 새들 600–1,500 ft (4.4.12.1) 은 거리 단위) | — | 근거 없음, 기준값 유지 | 없음 | 60 |
| floor_ft | 교범 근거 없음 (하드덱 1,000 ft 는 심판 규칙; `low_altitude` 설명의 "60° 강하 회복에 4,500 ft" 는 절 번호 없는 코드 주석) | — | 근거 없음, 기준값 유지 | 없음 | 4500 |

## 3. 변형 6개 (`bt/thetas/tuned6.csv`, `bt/make_tuned6.py`)

"유리한 방향" = RQ2 Morris μ 부호 (fight_kcas −2.73, threat_aspect_deg +1.29, floor_ft −1.25). 크기 = 범위의 유리한 쪽 끝에서 범위 폭의 10% 안쪽.
V4 의 7개 = `numpy.random.default_rng(20261106)` 로 params.yaml 순서대로 범위 안 균등. dummy 는 V6 만 원래 값, 나머지 0.5.

**V5 (V1 + V3) 는 V1 의 변경값이 V3 조정에 모두 덮여 V3 와 같아지므로 제외 (결과 보기 전 결정).** V1 의 교범 변경 중 fight_kcas·threat_aspect_deg 는 V3 가 덮어쓰고, merge_range_ft 6000 은 기준값과 같다.
변형 이름은 초안과 맞추려고 V6 을 그대로 쓴다.

| 변형 | theta_id | merge | threat | gun_rng | gun_ata | fight | e_min | lead | brk_g | closing | floor |
|---|---|---|---|---|---|---|---|---|---|---|---|
| V0 기준 | f2306532ecff | 6000 | 150 | 3000 | 45 | 280 | 500 | 2.0 | 0.5 | 60 | 4500 |
| V1 교범값 | ebb06b6dc5b2 | 6000 | **120** | 3000 | 45 | **325** | 500 | 2.0 | 0.5 | 60 | 4500 |
| V2 fight 만 | 4d0aa26cf7cd | 6000 | 150 | 3000 | 45 | **231** | 500 | 2.0 | 0.5 | 60 | 4500 |
| V3 중요 3개 | 630a071bd00e | 6000 | **165** | 3000 | 45 | **231** | 500 | 2.0 | 0.5 | 60 | **3400** |
| V4 하위 7개만 | 10b30efa09a5 | **4430.6** | 150 | **2432.7** | **26.08** | 280 | **1206.2** | **2.432** | **0.546** | **18.30** | 4500 |
| V6 대리 1위 | c1e4a1d09296 | 4626.9 | 163.5 | 1884.4 | 20.54 | 227.2 | 672.0 | 2.160 | 0.988 | 8.55 | 3730.9 |

**사전 예상 방향 (판정에 쓰지 않음, 검정은 계획대로 양측):** V2·V3·V6 > V0, V1 < V0 (교범값 두 개가 RQ2 의 유리한 방향과 반대 — fight_kcas 를 올리고 threat_aspect_deg 를 내림), V4 ≈ V0.

## 4. 상대 묶음

- **patched:** 본실험 보정 상대 4종 (A2, B2, C1, D1).
- **heldout (처음 보는 상대):** `kit/agents/main` 에서 본실험 4종을 뺀 A1_PurePursuer_00, A3_LagAngler_00, B1_EnergyFighter_00, red_prime.
  `bt/opponents_heldout/`. A1·A3·B1 은 `opponent_patch_rules.md` 와 같은 보정 (최우선 low_altitude → climb: floor_ft 1200 → 4500, g_burst 0.8),
  red_prime 은 보정 대상 노드가 없고 이미 더 강한 고도 안전장치 (floor_ft 4500 + lookahead_s 3.5 + g_burst 1.0, `crash_recovery`) 가 있어 원본 그대로.
- **heldout 합격 점검** (기준 θ × 48경기, bt-smoke 시드, `bt/out/heldout_check.md`): 상대 하드덱 0.000 (≤ 0.05), 상대별 최대 0.000 (≤ 0.10),
  고도 회복 노드 실행 비율 평균 0.101 (≤ 0.20) → **합격**. wall_clock 0.

## 5. 실행

- θ: `bt/thetas/tuned6.csv` (6개). 묶음 2개 × 기하 3 × 상대 4 × 시드 36 = θ·묶음당 432경기.
- 시드 접두어 **`bt-confirm2`** (기존 어느 실행에도 쓰지 않음), `--nseeds 36`, `--unlock-confirm`, 태그 `prereg-bt-tuning-v1` 필요.
- 결과 폴더: `bt/out/bt-confirm2/` (patched), `bt/out/bt-confirm2-heldout/` (heldout).
- 명령: `python bt/run_bt.py bt/thetas/tuned6.csv --prefix bt-confirm2 --unlock-confirm --nseeds 36 [--opponents heldout] [--shard i/n]`.
- 경기 수: 묶음당 2,592 (6 θ × 432), 합계 **5,184경기**. PC1 단독, 태그 커밋에서 `--procs 5`.
- 제외·재실행: `PREREG_BT.md` §7 그대로 (wall_clock 은 백업 → 그 줄만 삭제 → 태그 커밋에서 재실행, disqualified 는 중단·원인 수정·해당 θ 재실행).

## 6. 분석 (`bt/analysis/tuning.py`)

- **1차 지표: 승률** (청 승 = 1, 그 외 0).
- **주 비교 (묶음별):** V1, V2, V3, V4, V6 각각과 V0 의 짝 비교 (같은 기하·상대·시드, 432쌍). 짝 이진 차이 (변형 승 − V0 승) 평균의 95% CI (짝 차이에 대한 t 분포, 자유도 n − 1)
  와 McNemar 검정 (불일치 쌍의 정확 이항 검정, 양측). **Holm 보정: 묶음별 5개 비교.**
- **추가 비교 (묶음별):** V3 vs V1, V6 vs V3 — 같은 방식 (짝 차이 CI, McNemar). 이 2개는 주 비교와 다른 가족으로 Holm 보정 (가족 크기 2).
- **동등성:** V4 vs V0 승률 ±5%p TOST (짝 차이, t 분포, α 0.05). 동등하면 "하위 7개는 승률과 무관" 을 지지.
- **판정은 묶음 전체 (상대 4종) 로 한다.**
- **상대별 보고 (서술용):** 상대별 승률은 항상 보고한다. 그 묶음에서 **V0 승률이 5% 미만인 상대** (바닥 상대, 예상: C1_TwoCircleRate_00, red_prime) 를 표시하고,
  바닥 상대를 뺀 결과 (짝 차이·CI) 도 함께 보고한다. 이것은 판정에 쓰지 않는다.
- **보조 지표 (서술용, 판정에 안 씀):** Δwez, 실제 체력 차 (hp_blue_raw − hp_red_raw), 승리 방식 분포, 청 하드덱 비율, 무접촉 비율.
- **탐색 분석 (서술용, 판정 없음):**
  - (가) V0·V1·V2·V3·V6 의 청 노드 실행 비율 (node_frac), 특히 energy_recover, break_defense.
  - (나) 같은 θ 의 청 격추당함 비율, 청 하드덱 비율, hp_blue_raw, e_adv_ft 평균 — 공격성이 생존을 희생하는가.
  - (다) V1·V3·V6 의 V0 대비 승률 차를 patched 와 heldout 에서 나란히, 상대별 표 포함.
- 분석 코드는 결과를 보기 전에 이 문서와 같은 태그 커밋에 넣는다.

## 7. 한계

- 추가 실험은 RQ2·RQ3 결과를 본 뒤 설계했다 (변형 V2–V6 은 RQ2 결과에 기대어 만들었다). 확증 증거가 아니라 일반화 점검으로 해석한다.
- heldout 은 4종뿐이고, red_prime 은 다른 상대와 고도 보정 방식이 다르다.
- C1 상대에서 본 승률 바닥 효과가 heldout 에도 있을 수 있다 (점검에서 red_prime 상대 기준 θ 승률 0/12).
- V1 은 교범 수치를 BT 문턱값으로 옮기는 한 가지 방식일 뿐이고, threat_aspect_deg 는 대응이 약하다 (§2).
- 시뮬레이션에 없는 위험 (다른 적기, 미사일, 연료, G 내성, 센서 한계) 과 모델 충실도 차이는 이 실험으로 확인할 수 없다.
