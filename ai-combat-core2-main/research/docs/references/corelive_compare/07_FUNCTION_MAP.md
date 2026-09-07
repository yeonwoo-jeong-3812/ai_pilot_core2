# 07 — 코드별 기능 분석 · 파일/함수 1:1 대응표

> 목적: core2 ↔ core-live를 **파일 단위 + 함수 단위**로 1:1 매핑하고, 각 쌍에서 무엇이 있고/없는지(gap)를 명시. `_core2/`·`_corelive_engine/` 정션으로 나란히 diff 가능(README 참조).
> 범위: 전 계층. L1~L4는 확정, 엔진/기하/디브리핑/지원 계층은 병렬 심층읽기 반영.

## 0. 마스터 파일 매핑 (패키지 전경)

| 계층 | core2 (`aircombat/`) | core-live (`src/engine/`, `src/control/`) | 대응 |
|---|---|---|---|
| L4 물리 | `fdm/plant.py` | `control/plant.py` | **1:1 바이트-동일**(경로탐색 1함수 제외) |
| L3 제어 | `control/indi.py` | `control/indi.py` | 1:1(정석 vs LQR결합) |
| L3 자세 | `control/attitude.py`(쿼터니언) | `control/autopilot.py` 내 Euler | 1:1(부분) |
| L3 리미터 | `control/limiter.py`(분리) | `control/indi.py`+`autopilot.py` 내장 | 다:1 |
| L3 최적제어 | — (D2에서 LQR 배제) | `control/lqr.py`, `control/linearize.py` | **core-live 단독** |
| L2 가이던스 | `guidance/bfm_guidance.py` | `control/guidance.py` | 1:1(연속조절 vs 이산기동) |
| L2 근거 | `guidance/doctrine.py`(교범) | `control/constants.py`(실험 NME_*) | 1:1(성격 정반대) |
| L1 선택 | `tactics/conditions.py`(술어) | `control/situation_cost.py`(비용) | 1:1(hard vs soft) |
| L1 BT | `tactics/{dsl,node,policy,context}.py` | `bt/yaml_bt.py`+`policy_yaml/` | 다:다 |
| 기하 | `geometry/{combat_geometry,units,wez}.py` | `engine/obs.py`·`engine/judge.py`·`control/combat_geometry.py` | **core2 분리 vs core-live 분산** |
| 엔진 | `engine/{match,pilot,scenarios,state,tournament,factory}.py` | `engine/{match,match_harness,pilot,scenarios,obs}.py` | 다:다 |
| 대항군 | `engine/opponents/scripted.py` | `bt/`(970 legacy 트리)+`bridge/run_legacy.py` | core2 소수정예 vs core-live 대량 |
| 디브리핑 | `debrief/{acmi,tacview_realtime}.py` | `engine/replay.py` | 1:다 |
| 브리지 | `bridge.py` | `bridge/{core_adapter,legacy_csv,result_compat,run_legacy,verify_swap}.py` | 1:다 |
| 배선 | `engine/factory.py`(DI) | — (ad-hoc 배선) | **core2 단독** |

---

## L4 — 물리/FDM

| | core2 `fdm/plant.py` | core-live `control/plant.py` |
|---|---|---|
| 클래스 | `F16Plant` | `F16Plant` (동일) |
| set_ic/start_engines/trim/step/get_state | 동일 | 동일 |
| capture_state/restore_state | 동일 | 동일 |
| `_find_jsbsim_root()` | 단일경로 | **3-폴백 탐색** |

**기능 판정:** 바이트-동일. 우열 없음(공유기반). core2가 우리 new-engine 기반임의 최강 증거.

---

## L3 — 오토파일럿/제어

### INDI
| | core2 `control/indi.py` (207) | core-live `control/indi.py` (214) |
|---|---|---|
| 클래스 | `INDIRateController` + `SecondOrderLPF` | `INDIController` + `INDIConfig` |
| 각가속도 추정 | **2차 Butterworth 동기화필터**(accel·actuator 지연정합, "the crux") | 단순 유한차분(동기화필터 없음) |
| 효과행렬 G | `identify_G0()` **온라인 유한차분 식별** | `_interp_B(alt,vc)` **LQR 격자 B 쌍선형보간** |
| step | `step(omega_sp)` 순수 rate-loop | `step(sp: Setpoint)` 외측+내측 번들 |
| 의존 | 독립 | `GainScheduledLQR` 필요 |

### 자세 표현
| | core2 `control/attitude.py` (88) | core-live `control/autopilot.py` (323) |
|---|---|---|
| 표현 | **쿼터니언** `QuaternionAttitudeShim`(euler_to_quat/quat_mul/quat_to_euler) | Euler φ/θ (MAX_THETA 클램프) |
| 수직 BFM | **무특이점**(gimbal lock 제거) | θ클램프로 특이점 회피(수직 제약) |
| yaw | r→0 감쇠 | 협조선회 β→0(전술 러더게이트) |
| **감사훅** | — | ✅ `resolution_report() -> dict` (리미터 해소 로그) |

### 리미터 / 최적제어
| | core2 | core-live |
|---|---|---|
| 리미터 | **분리** `CombinedLimiter.limit_omega_sp()` → 클램프+**플래그** | INDIController 내장(조건부 8.2g 게이트)+autopilot |
| LQR | 없음 | `lqr.py`: `GainScheduledLQR`(Riccati, Mach×alt 격자 K보간), `LQRPoint.gain_margin_db()`, `print_stability_proof()` |
| 선형화 | 온라인(identify_G0) | `linearize.py`(precomputed 격자) |

**기능 판정(L3):**
- **core2 우위:** 동기화필터(노이즈강건·실HW), 쿼터니언(수직 무특이점), 분리 감사리미터(플래그).
- **core-live 우위:** LQR+INDI 이중(교차검증 인프라, canonical=both-INDI), 조건부 high-g 전술게이트(승리기여), **이미 감사훅 보유**(`resolution_report`, gain_margin_db, print_stability_proof — 단 core2가 더 체계적).

---

## L2 — 가이던스 (★연구본체)

| | core2 `guidance/bfm_guidance.py` (294) | core-live `control/guidance.py` (1007) |
|---|---|---|
| 클래스 | `BFMGuidance`, `AircraftKinematics`, `GuidanceCommand` | `GuidanceLayer`, `Obs`, `Setpoint`, `ChaseConfig`, `_HeadingKF` |
| 최상위 | `compute() -> GuidanceCommand` **연속 조절 1개** | `compute(tactic, obs) -> Setpoint` → `_dispatch` **이산 25기동** |
| 프리미티브 | **dphi**(리프트벡터 롤증분)+q_cmd(=G·g/V)+thrust | psi\*/h\*/v\* setpoint(autopilot이 뱅크 역산) |
| G 조절 | `_regulate_g()` 5모드(regulate/track_lock/initial_pull/energy_backoff/max_g) | 각 기동함수 내 분산 |
| 파워 | `_power()` 6모드(AB_entry/closure_ctl/AB_accel/decel/margin_regain/MIL_hold) | `_chase_speed()` + 기동별 |
| 기동 어휘 | pursuit3×mode3 + aim_above 요요 | **25 named**: _lead/_pure/_lag/_vertical/_adaptive/_stern_convert/_lag_displacement_roll/_etm_track/_smart_dive/_gun_track/_one_circle/_two_circle/_tight_turn/_lead_turn/_scissors/_high_yoyo/_low_yoyo/_break_turn/_extension/_climb/_level |
| 적 추정 | 무상태(매tick 기하 재유도) | `_HeadingKF` (적 heading KF, stateful) |
| 감사 | ✅ 매tick 12필드 audit dict | 일부(explain은 situation_cost) |

**기능 판정(L2):** 지능위치 분기. dphi 프리미티브·무상태 연속조절·5모드 G법칙·audit = **core2 우위**. 25 named 기동 어휘·설명가능 이산선택·`_HeadingKF` 적추정·42/42 = **core-live 우위**. core2 `track_lock`(LOS율 G하한) ↔ 우리 루프13 closing-gate 동일문제 교차검증.

---

## L2/L1 근거 — 교범 vs 실험, 술어 vs 비용

| | core2 | core-live |
|---|---|---|
| 상수근거 | `doctrine.py`: `Doctrine` dataclass, 전상수 **교범조항 인용**(corner 4.3.3.7…), `DOCTRINE_BOUNDS`, `from_yaml`, TUNING_ENABLED=False | `constants.py`: 실험 sweep + `NME_*` env override |
| 상황판정 | `conditions.py`: 18 **술어**(foe_threat/overshoot_risk/is_head_on/is_offensive…), **hard bool** | `situation_cost.py`: **비용함수** J_offensive/J_two_circle/J_one_circle/J_defensive/J_neutral + `value()` + **`explain()`** + memberships(퍼지), **soft argmin** |

**기능 판정:** 교범앵커 = **core2 우위(최우선 흡수)**. 그러나 **선택 패러다임은 상보** — core2=hard 술어(감사쉬움·경계딱딱), core-live=soft 비용+퍼지 membership(강건·knife-edge완화)+이미 `explain()` 보유. → **이상형 = core2 교범상수를 core-live 비용함수의 임계값으로 주입**.

---

## L1 — 전술/BT

| | core2 `tactics/` | core-live |
|---|---|---|
| DSL | `dsl.py`: build_node, **화이트리스트** `_ACTION_KEYS`, inspect검증, 샌드박스 include | `bt/yaml_bt.py`: load_bt, 35조건37액션, **커스텀 파이썬 노드**(stateful) |
| 노드 | `node.py`: 반응형 BT(Status SUCCESS/FAILURE), **Commit/Cooldown 데코레이터**, ctx.t_s 결정론시계 | 커스텀 노드(empty-dive latch, headon-suppress) |
| 정책 | `policy.py`: `TacticPolicy.tick()` + dwell 0.3s 히스테리시스 | `full_unified_policy.py` / `full_unified_42.yaml` |
| 컨텍스트 | `context.py`: ctx.trace 감사 | FullCtx 공유상태 |
| 챔프 | DEFAULT_SPEC(6분기, **미측정**) | **42/42 FullUnifiedPolicy**(.yaml↔.py 틱-동일) |

**기능 판정(L1):** 안전저작DSL·Commit/Cooldown·교범조건어휘 = **core2 우위**. cost-argmax·표현력·970 legacy·42/42·이중표현 = **core-live 우위**. core2 안전DSL로는 챔프 표현불가 ↔ core-live yaml_bt는 미신뢰제출 위험.

---

## 기하/관측/WEZ 계층 ⚠️ 중대 발견

| 기능 | core2 `geometry/` | core-live | 상태 |
|---|---|---|---|
| 기하 프리미티브 | `combat_geometry.py` **CombatGeometry 클래스**(ata/aa/hca/**tau 3-2-1 Euler**/closure/energy_state/overshoot/tc_type) | `engine/obs.py` **인라인**(ata/aa/closure/advantage), `control/combat_geometry.py`=**죽은 사본**(tau 2D 근사) | **core2 재사용층 vs core-live 분산** |
| 단위변환 | `units.py` | `utils/units.py`(거의 동일) | 1:1 |
| **WEZ 데미지** | `wez.py`: ATA **30°** tiered(2°→1.0…30°→0.25), **거리무관** | `judge.py`: ATA **12°** 선형, **거리 선형감쇠** (3000−d)/2500 | **❌ 비호환 — core2가 룰북 위반** |

**⚠️ 검증된 결함(룰북 대조):** `docs/RULEBOOK.md` §5가 공식 WEZ를 명시 — `dHP/dt = 25·f_R(R)·f_ATA(ATA)`, 사거리 500→3000ft 선형감쇠, ATA 0→12° 선형감쇠. **core-live judge.py와 정확히 일치**. → **core2 wez.py(30° tiered·거리무관)는 공식 룰북과 불일치 = core2의 채점 버그.** ATA 20° 표적을 core2는 데미지(tier 0.5) 주지만 룰북/core-live는 0(WEZ 밖). **두 엔진이 같은 게임을 채점하지 않음.**

**기능 판정(기하):**
- **core2 우위(구조):** CombatGeometry가 재사용 클래스 1개(ata/aa/**tau 3D**/energy/overshoot/tc_type 응집). core-live는 obs.py 인라인 + control/combat_geometry.py 죽은 사본(혼란).
- **core-live 우위(정합):** WEZ가 **공식 룰북 정본**. obs.Observation 32필드 RL-ready. 단 core-live도 **tau는 2D 근사로 퇴화**(gun-sight lead 부정확)라 core2 3D tau 역이식 가치.

---

## 엔진/하네스 계층

| core2 | core-live | 상태 |
|---|---|---|
| `factory.py`(load_policy YAML→policy, make_pilot, **DQ경계**) | — (호출자가 pilot 스폰) | **core2 단독(참가자 진입 안전)** |
| `match.py`(자족, 3-tier 120/60/20Hz) | `match.py`+`match_harness.py`(제어기 런타임교체, **이벤트로그**, damage_dealt, dwell) | 다:다 |
| `pilot.py`(5계층 전부 캡슐화, telemetry export) | `pilot.py`(guidance+autopilot 래핑, **LQR/INDI 교체**, ETM KF) | 1:1 다른추상 |
| `scenarios.py`(headon/perch/sudden_death 6종+시드지터) | `scenarios.py`(**parametric spawn_param + LHS 7D 샘플링**) | 유사·발산 |
| `state.py`(KinState 최소) | `obs.py`(Observation 32필드 Layer A/B) | 개념중복 |
| `tournament.py`(라운드로빈+건틀릿+D8랭킹) | — (server 책임) | **core2 단독** |
| `opponents/scripted.py`(kinematic 대항, straight/turn/extend/break) | — (항상 JSBSim Pilot) | **core2 단독(빠른 테스트)** |
| — (judge는 match 내장) | `judge.py`(**감사가능 추출** + Victory enum + 테스트) | **core-live 단독** |
| — (ACMI 인라인) | `replay.py`(**결정론검증** + GunVisualizer + 3라이터 ACMI/plot/csv) | **core-live 단독** |
| — (상수 산재) | `match_harness.py`(**단일진리원** LQR격자·CONTROL_HZ·BT_HZ) | **core-live 단독(드리프트 방지)** |

**기능 판정(엔진):**
- **core2 단독 보유(→ core-live가 흡수할 것):** `factory.py`(참가자 진입 DQ경계), `tournament.py`(랭킹), `opponents/scripted.py`(kinematic 대항=빠른 dev 루프).
- **core-live 단독 보유(→ core2가 흡수할 것):** `judge.py`(감사가능 심판 추출), `replay.py`(결정론검증+3라이터), `match_harness.py`(설정 단일진리원), 이벤트로그, damage_dealt, 제어기 런타임교체, parametric+LHS 시나리오.

---

## 디브리핑(리플레이/ACMI) 계층

| 기능 | core2 `debrief/` | core-live `engine/replay.py` | 상태 |
|---|---|---|---|
| 파일 ACMI | `acmi.py` `ACMIWriter`(**증분 스트리밍**, declared set 최적화, ReferenceTime 결정론) | `write_acmi()`(배치 120Hz) | 양쪽 |
| **plot ACMI** | — | `write_acmi_plot()`(**15Hz 다운샘플+이벤트로그+BFM속성+GunVisualizer 트레이서+하드덱/KO pre-scan tail-flush+판정 북마크**) | **core-live 단독** |
| **CSV** | — | `write_csv()`(120Hz 전필드) | **core-live 단독** |
| **실시간 중계** | `tacview_realtime.py` `TacviewRealtimeServer`(**TCP:42674 멀티클라이언트 브로드캐스트**) | — | **core2 단독** ⚠️ |
| 결정론 검증 | — | `replay.py __main__`(2회 실행 궤적 비교) | **core-live 단독** |
| 리플레이 ID | 결정론(동일자 충돌) | 밀리초 유니크 | 성격차 |

**기능 판정(디브리핑):** **core2 단독=TacviewRealtimeServer(TCP 실시간 중계 — broadcast 파이프라인 필수).** **core-live 단독=plot ACMI+CSV+GunVisualizer+결정론검증(3라이터 오케스트레이션).** 메모리의 "write_csv만 호출" 버그는 `core_adapter.run()`이 3라이터 원자호출로 **해소됨**(확인). → 상보: core2 TCP서버 ↔ core-live plot/csv/결정론.

## 브리지 계층

| core2 `bridge.py` | core-live `bridge/` | 상태 |
|---|---|---|
| `CompetitionMatch`(V1 서버계약 어댑터) | `core_adapter.py` `BehaviorTreeMatch`(drop-in, replay+CSV+health **원자산출**) | 1:다 |
| `derive_seed()` **SHA256 결정시드**(레거시 replay 재현) | — | **core2 단독** |
| `load_policy`/`make_pilot` **결함분리**(참가자 DQ ↔ 인프라오류) | (factory 부재, 배선 분산) | **core2 단독** |
| — | `verify_swap.py`(**3단 drop-in 검증**: API parity·side-by-side·consumer) | **core-live 단독** |
| — | `result_compat.py`/`legacy_csv.py`(**레거시 하위호환** 래퍼·컬럼) | **core-live 단독** |
| — | `run_legacy.py`(CLI 하네스) | **core-live 단독** |

**기능 판정(브리지):** core2=`derive_seed`(결정시드)+`factory` 결함분리(참가자 진입 안전). core-live=`verify_swap`(배포 무회귀 증명)+하위호환 래퍼. → core2는 검증스위트 부재로 **무증명 배포 위험**, core-live는 결정시드 부재.

## 지원 계층 (core-live 단독 — core2 대응 없음)

| core-live | 기능 | core2 대응 |
|---|---|---|
| `control/constants.py` | 단위/물리 단일진리원, **왕복정합**(KNOT_TO_FT_S↔FT_S_TO_KNOT 역수쌍, float64 무손실), ICAO/CODATA | 없음(상수 산재) |
| `control/situation_cost.py` | **관계형 비용/가치 모델**(wez_margin/their_margin/memberships 5상황 퍼지+J_* + `value()`=제로섬 게임값 + `explain()`), 절대량 금지·상대관측만 | 없음(비용모델 부재; conditions.py hard 술어와 대비) |
| `control/tactic.py` | **통합 Tactic IntEnum 21종** + 불변 게임규칙(judge 동기) + F-16 성능상수(V_CORNER 320·V_RADIUS 260·V_MAX 420) + 기동별 튜닝 | 없음(전술정의 산재) |

**기능 판정(지원):** **core-live 압도** — constants(왕복정합)·situation_cost(설명가능 게임값)·tactic(단일 enum). core2는 이 계층이 사실상 부재(상수·전술·규칙이 여러 파일 산재). 단 core2 `factory.py`의 결함분리는 core-live 지원계층에 없는 안전장치.

---

## 종합 gap 매트릭스 (누가 무엇을 결여했나)

**core2가 결여(→ core-live에서 흡수):**
1. ⚠️ **WEZ 룰북 정합**(core2 30° tiered = 채점버그) → core-live judge.py 채택 **필수**
2. plot ACMI + CSV + GunVisualizer + 결정론검증 (`replay.py`)
3. `verify_swap` drop-in 검증 + 하위호환 래퍼
4. `constants.py` 왕복정합 + `situation_cost.py` 게임값 + `tactic.py` 통합 enum
5. `judge.py` 감사가능 심판 추출 / 이벤트로그 / damage_dealt / 제어기 런타임교체 / parametric+LHS 시나리오

**core-live가 결여(→ core2에서 흡수):**
1. **doctrine.py 교범앵커**(상수 근거) — 최우선
2. **TacviewRealtimeServer**(TCP:42674 실시간 중계)
3. **factory.py 결함분리**(참가자 DQ ↔ 인프라) + `derive_seed` 결정시드
4. **CombatGeometry 재사용 클래스**(3D tau 포함) — obs 인라인/죽은사본 정리
5. L3 정석화: INDI 2차 동기화필터 · 쿼터니언 shim · 분리 감사리미터
6. L1 안전: 화이트리스트 DSL · Commit/Cooldown 데코레이터 · 18 교범조건
7. `tournament.py` · `opponents/scripted.py`(kinematic 대항=빠른 dev)
