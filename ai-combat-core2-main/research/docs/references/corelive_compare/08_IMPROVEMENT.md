# 08 — 양측 부족분 반영 통합 개선안 (best-of-both)

> 목표: core2 부족분 + core-live 부족분을 **모두** 반영한 단일 개선 아키텍처. 각 항목은 (출처·근거·위험·검증법) 명시.
> 대원칙: **"정교함≠승리"([[ai-pilot-doctrine-optimizes-gun-wez-dwell]])** — 어떤 흡수도 42/42 both-INDI 300s 재검증을 통과해야 병합. 감사·안전·정합 개선(전투결과 무해)은 즉시, 제어법칙 변경(틱깨짐)은 검증 게이트 후.

## 0. 통합 원칙 — 두 프로젝트의 정체성

| | core2 | core-live | 통합 지향 |
|---|---|---|---|
| 정체 | 깨끗한 참조구현 · 플랫폼 골격 · 교범근거 | 검증된 연구엔진(42/42) · 광역호환 · 감사인프라 | **core-live 지능 + core2 골격/근거** |
| 지능위치 | 연속 L2 조절 | 이산 L1 전술선택(cost-tree) | **core-live cost-tree 유지**(대회 설명가능성 목표 정합) |
| 결여 대칭 | 검증·안전·정합·지원층 부재 | 근거·중계·DI·기하재사용 부재 | **상호 흡수** |

핵심: core2는 우리 코드의 *더 깨끗한 판본*이나 **전투 실증이 없다**. core-live는 *실제로 이긴* 엔진이나 **근거·위생이 약하다**. 개선안은 **core-live를 베이스로 core2의 위생·근거·중계·안전을 이식**하되, core2의 검증공백(WEZ 버그·무증명)을 넘겨받지 않는다.

---

## 1. ⚠️ 즉시·필수 — WEZ 채점 정합 (correctness P0)

**문제:** core2 `wez.py`는 ATA **30° tiered·거리무관**, core-live `judge.py`는 ATA **12°·거리+각도 선형감쇠**. `docs/RULEBOOK.md` §5 공식 = `dHP/dt=25·f_R(R)·f_ATA(ATA)`, 사거리 500→3000ft 선형, ATA 0→12° 선형 → **core-live가 정본, core2는 룰북 위반(오채점)**.

- **개선:** core2 `wez.py`를 폐기하고 core-live `judge.py`(12°·거리감쇠) 채택. core-live는 이미 정합 — **변경 불필요**.
- **근거:** RULEBOOK §5, `wez_damage_rate.py` 셀프테스트(D(0°,500)=25, D(12°,*)=0, D(*,3000)=0).
- **위험:** 없음(core-live 무변경). core2 배포 시 반드시 교체.
- **검증:** core2에 core-live judge를 이식 후 동일 매치 데미지 궤적 대조 = 0 오차.

---

## 2. core-live로 흡수 (core2 → core-live)

### 2A. 감사·근거 (전투결과 무해 · 즉시 · 최우선)

| # | 항목 | 출처 | 방법 | 검증 |
|---|---|---|---|---|
| A1 | **doctrine.py 교범앵커** | core2 `guidance/doctrine.py` | 우리 `constants.py`/`tactic.py`의 실험상수를 교범조항(F-16C Vol.5 Ch.4)에 매핑하는 `doctrine_refs.py` 신설. **값 변경 없이 출처만 주석/메타** | 42/42 불변(값 동일) |
| A2 | **factory 결함분리** | core2 `factory.py` | `bridge/`에 `load_policy`(참가자 DQ) ↔ `make_pilot`(인프라오류) 2단 경계 도입. 현재 분산 배선을 명시 factory로 | drop-in 회귀 0(`verify_swap`) |
| A3 | **derive_seed SHA256** | core2 `bridge.py` | 결정시드 함수 이식 — 레거시 replay 재현·회귀시드 고정 | 동일시드 동일결과 |

> A1은 우리 [[metrics-before-tactics]] 원칙을 강화하고 감사가능성을 획득하나 **42/42에 무영향**(값 불변) — **위험 최저·가치 최고, 1순위**.

### 2B. 실시간 중계 (기능 신설 · broadcast 파이프라인)

| # | 항목 | 출처 | 방법 | 검증 |
|---|---|---|---|---|
| B1 | **TacviewRealtimeServer** | core2 `debrief/tacview_realtime.py` | TCP:42674 멀티클라이언트 서버를 `engine/replay.py` 옆 `engine/realtime.py`로 이식. 우리 log_row → format_frame 배선 | 실제 Tacview Advanced 연결·프레임 수신 |

> `ai-combat-broadcast`가 core에 의존하므로, 이 서버가 core-live에 있으면 중계 파이프라인이 단일 스택으로 수렴.

### 2C. 기하 재사용 (위생 · dead-code 정리)

| # | 항목 | 출처 | 방법 | 검증 |
|---|---|---|---|---|
| C1 | **CombatGeometry 클래스(3D tau)** | core2 `geometry/combat_geometry.py` | `engine/geometry.py` 신설(ata/aa/hca/**3-2-1 Euler tau**/closure/energy). `obs.compute_obs`가 인라인 대신 이 클래스 호출. `control/combat_geometry.py`(죽은 2D 사본) 폐기 | obs 필드 틱-동일(리팩터 전후 궤적 0오차) |

> ⚠️ **주의:** C1은 obs 계산 경로를 바꾸므로 **틱-동일성 재검증 필수**. tau 3D화는 gun-track lead 정확도↑ 가능성 — 별도 A/B로 승률 영향 측정.

### 2D. L3 제어 정석화 (틱깨짐 · 검증 게이트 B)

| # | 항목 | 출처 | 방법 | 검증 |
|---|---|---|---|---|
| D1 | INDI 2차 동기화필터 | core2 `control/indi.py` `SecondOrderLPF` | 우리 `indi.py`에 accel·actuator 지연정합 필터 추가 | **both-INDI 300s 42/42 재검증** |
| D2 | 쿼터니언 자세 shim | core2 `control/attitude.py` | Euler+MAX_THETA 클램프 → 쿼터니언 무특이점. 수직 BFM 표현력↑ | 42/42 재검증 + 수직기동 승률 A/B |
| D3 | 분리 감사 리미터 | core2 `control/limiter.py` `CombinedLimiter` | 내장 게이트 → 분리 `limit_omega_sp()` 플래그 반환. 우리 `resolution_report()`와 통합 | 42/42 재검증 + 리미터 플래그 로그 |

> D1~D3은 각각 틱값을 바꾼다 → **머지 전 canonical 17+held-out 25 both-INDI 300s 무패 확인 게이트**. 도크트린상 개선 보장 없음 — 실측만이 판정.

### 2E. L1 안전·구조 (참가자 저작 + chatter)

| # | 항목 | 출처 | 방법 | 검증 |
|---|---|---|---|---|
| E1 | **Commit/Cooldown 데코레이터** | core2 `tactics/node.py` | 우리 임시 stateful latch(empty-dive 등)를 재사용 DSL 데코레이터로 팩터. `analyze_chatter.py` pain 해소 | 42/42 틱-동일(동작 등가) |
| E2 | 화이트리스트 검증 DSL | core2 `tactics/dsl.py` | 대회 제출 경로에 화이트리스트+inspect 검증 도입(참가자 안전). 우리 챔프는 신뢰경로 유지 | 미신뢰 YAML 거부 테스트 |
| E3 | 교범조건 어휘 | core2 `tactics/conditions.py` | HABFM/OBFM/DBFM 국면 술어를 `situation_cost.memberships`와 병기(감사) | membership↔술어 일치율 |

> E1은 chatter 제어를 재사용화 — **기능 등가라 42/42 틱-동일 목표**. E2는 참가자 제출 안전(우리 챔프 무관). E3은 감사 병기(값 무변).

### 2F. 개발·테스트 편의

| # | 항목 | 출처 | 방법 |
|---|---|---|---|
| F1 | `opponents/scripted.py` kinematic 대항 | core2 | JSBSim 없이 straight/turn/extend/break 대항 → 빠른 dev 루프·단위테스트 |
| F2 | `tournament.py` 로컬 랭킹 | core2 | 로컬 라운드로빈+건틀릿+D8 랭킹(서버 없이 실험) |

---

## 3. core2로 흡수 (core-live → core2) — 동료에게 제안

> 우리가 동료 core2를 개선하도록 돌려줄 항목(양방향 개선의 대칭성).

| # | 항목 | 우리 출처 | core2에 주는 가치 |
|---|---|---|---|
| G1 | ⚠️ **WEZ 룰북 정합** | `judge.py` | **채점버그 수정**(30°→12°+거리감쇠) — 최우선 |
| G2 | plot ACMI + CSV + 결정론검증 | `replay.py` | 분석도구 호환·재현성 증명 |
| G3 | `verify_swap` drop-in 검증 | `bridge/verify_swap.py` | **무증명 배포 위험 제거** |
| G4 | constants 왕복정합 | `control/constants.py` | 반올림 누적오차 제거 |
| G5 | situation_cost 게임값 + cost-argmax | `control/situation_cost.py` | hard 술어 selector의 knife-edge 완화 |
| G6 | 이벤트로그 · damage_dealt · 제어기 런타임교체 | `engine/match.py` | 관측성·A/B 능력 |

---

## 4. 실행 로드맵 (위험도순)

```
Phase 0 (즉시, 무위험):  A1 doctrine앵커 → A2 factory → A3 seed → E3 조건병기
                         └ 전부 값 불변 → 42/42 자동보존, 감사·안전·근거 획득
Phase 1 (기능신설):      B1 TCP중계 → F1 scripted → F2 tournament → G1~G6 core2 역제안
                         └ 신규기능/외부, 챔프 무영향
Phase 2 (위생·틱재검증): C1 CombatGeometry(obs 리팩터) → E1 Commit/Cooldown
                         └ 동작등가 목표, 틱-동일 확인 게이트
Phase 3 (제어정석화):    D1 동기화필터 → D2 쿼터니언 → D3 분리리미터
                         └ 각각 both-INDI 300s 42/42 게이트 통과해야 머지
                         └ 통과 시 부수효과(수직BFM·노이즈강건) A/B로 승률영향 측정
```

**게이트 규칙:** Phase 2·3의 모든 항목은 `canonical 17 + held-out 25 @ both-INDI 300s` 무패·무무 확인 후에만 정본 병합. 회귀 시 해당 항목 격리(tier-O 절제 방식, [[loop16-d2-05-headon-suppress-42of42]] 선례).

---

## 5. 핵심 통찰 — 이 개선안이 답하는 질문

1. **"core2가 더 낫나?"** → 위생·근거·중계·안전은 예. 전투결과는 **미검증**(정교함≠승리). 그래서 개선안은 core-live(실증)를 베이스로, core2의 *검증공백을 넘겨받지 않고* 위생만 흡수.
2. **"우리 부족분은?"** → 근거(doctrine)·중계(TCP)·DI(factory)·기하재사용·L3정석·L1안전·지원층 factory. 전부 core2에 있으니 흡수.
3. **"core2 부족분은?"** → ⚠️WEZ 룰북버그·검증스위트·plot/csv·지원층(constants/tactic/cost)·감사심판. 전부 core-live에 있으니 역제안.
4. **최종형:** core-live cost-tree 지능(42/42) + core2 교범근거·안전골격·실시간중계 + 양측 검증 게이트. **두 프로젝트가 각자 절반씩 옳았고, 합집합이 정답.**

## 관련
[[core2-comparison-structure]] · [[metrics-before-tactics]] · [[ai-pilot-doctrine-optimizes-gun-wez-dwell]] · [[loop16-d2-05-headon-suppress-42of42]] · [[final-bt-cost-unified-17of17]] · [[loop13-e1-draw-converted-closing-gate]]
