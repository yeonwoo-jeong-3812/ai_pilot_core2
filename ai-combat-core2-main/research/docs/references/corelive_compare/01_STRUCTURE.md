# core-live ↔ core2 구조 비교 (Step 1: graphify 구조 분석)

> 작성: 2026-07-13 · 방법: 두 저장소를 각각 graphify로 그래프화하여 노드/계층/모듈 대응을 비교.
> 이 문서는 **구조(as-built) 비교**만 다룬다. L1~L4 계층별 우열 심층 비교는 후속 문서(`02_L4.md` … `05_L1.md`)에서 다룬다.

## 0. 두 저장소의 성격 (한 줄 요약)

| | **core-live** (우리) | **core2** (동료) |
|---|---|---|
| 위치 | `C:/Users/USER/Desktop/AI-pilot/core-live` | `github.com/rokafa-daslab/ai-combat-core2` |
| 성격 | **연구 substrate** — 42/42 챔프를 *생산한* 대형 실험 모노레포 | **as-built 재구현 v2** — 우리 new-engine을 보고 깨끗하게 다시 쓴 정제본 |
| 산출물 vs 과정 | 과정(루프1~16 실험) + 산출물이 한 트리에 공존 | 산출물(정제된 계층 스택)만, 과정 제거 |
| 문서 | 실험 로그·메모리 다수, 통합 아키텍처 문서 없음 | `docs/ARCHITECTURE.md` 단일 정본(D1~D6 설계결정 + 계층정의) |
| 테스트 | 검증 러너(`verify_*.py`) 산재, 통합 스위트 없음 | 86 테스트 스위트 |

**핵심 프레이밍:** core2는 우리 코드의 *경쟁작*이 아니라 *증류본*이다. 동료는 우리 new-engine의 계층 아이디어(L1~L4 다중레이트 + INDI + dphi 리프트벡터 가이던스)를 취해, 실험 잔재를 걷어내고 교범(공군 기본운용교범 F-16C Vol.5)에 근거를 붙여 다시 썼다. 따라서 "우열"은 **연구 생산력(core-live) vs 배포 정합성(core2)** 축으로 읽어야 정확하다.

## 1. graphify 규모 지표

| 지표 | core-live (`src/engine` 루트) | core2 (저장소 루트) |
|---|---|---|
| 그래프 노드 수 | **2,518** | **1,016** |
| depth-2 도달 노드(주요 시드 3개) | **718** | **195** |
| depth-2 지배 노드 유형 | 수십 개 실험 정책 클래스 | 계층 스택 핵심 클래스 |

core-live의 depth-2 노드가 core2의 3.7배인 이유는 코드 품질 차이가 아니라 **실험 정책 클래스의 밀도**다. graphify가 core-live 시드에서 도달한 노드는 `exp_e7_champion`, `exp_e53_integrated_17`, `exp_e27_adaptive`, `exp_e36_cost_policy`, `exp_e10_unified`, `exp_e15_composite`, `FullUnifiedPolicy`, `D2CostUnifiedPolicy` … 로 채워진다. core2 시드는 `Match`, `Pilot`, `TacticPolicy`, `BFMGuidance`, `INDIRateController`, `F16Plant`, `QuaternionAttitudeShim`, `Doctrine` 로 깔끔히 계층당 1~2개다.

## 2. 패키징 구조 대비

### core2 — 단일 `aircombat/` 패키지 (~4,200 LOC, 계층=디렉토리)

```
aircombat/
  tactics/     657  L1  conditions 143 · context 69 · dsl 221 · node 179 · policy 45
  guidance/    416  L2  bfm_guidance 294 · doctrine 122
  control/     368  L3  attitude 88 · indi 207 · limiter 73
  fdm/         191  L4  plant 191
  geometry/    816  ─   combat_geometry 492 · units 176 · wez 148
  engine/      739  ─   match 226 · factory 42 · pilot 135 · scenarios 85 · state 52 · tournament 113 · opponents/scripted 86
  debrief/     283  L5  acmi 172 · tacview_realtime 111
  bridge.py    112       (계층 배선)
```

디렉토리 = 계층이 1:1. 각 계층이 자기 파일 1~3개로 닫혀 있다.

### core-live — 연구 모노레포 `src/engine/` (계층이 파일 안에 혼재)

```
src/engine/
  engine/    1,908 LOC / 11 files   match 316 · obs 244 · judge 230 · scenarios 165 · replay 365 · pilot 127 + 분석툴 5
  control/   3,051 LOC / 12 files   guidance 1007 · verify 481 · autopilot 323 · lqr 253 · indi 214 · plant 198
                                    · situation_cost 133 · linearize 124 · validate_indi 108 · tactic 103 · controller 65 · constants 42
  bt/       14,212 LOC / 110 files  루프1~16 실험 정책 + 최종 통합정책 + policy_yaml 데모
```

**대비 3점:**
- **guidance 모놀리스**: core-live `guidance.py` 1,007 LOC 단일 파일에 L2 가이던스 + NME_* 실험 플래그 다수가 뭉쳐 있다. core2는 같은 역할을 `bfm_guidance.py`(294) + `doctrine.py`(122)로 분리.
- **bt/ 14K LOC**: core-live 전체의 70%가 실험 트리(loops 1~16). core2엔 대응물이 없다 — 실험은 core-live에서 끝나고 결론만 넘어갔다.
- **geometry 분리 여부**: core2는 `geometry/`(combat_geometry·units·wez 816 LOC)를 독립 계층으로 뽑았다. core-live는 동일 기능을 `engine/obs.py`(244)·`engine/judge.py`(230)에 흩어 놓았다 — WEZ/기하 로직이 관측·판정 코드와 섞여 있다.

## 3. L1~L4 계층 모듈 대응표

| 계층 | 역할·주파수 | core2 모듈 | core-live 모듈 |
|---|---|---|---|
| **L1** 전술 | BT tick, 20/10Hz | `tactics/` (dsl·node·conditions·context·policy) | `bt/` (110 files) + `control/tactic.py` |
| **L2** 가이던스 | dphi 리프트벡터·q_cmd/G·thrust, 60Hz ★연구본체 | `guidance/bfm_guidance.py` + `doctrine.py` | `control/guidance.py` (1007 LOC 모놀리스) |
| **L3** 오토파일럿 | 쿼터니언 shim + 리미터 + INDI, 120Hz | `control/{attitude,indi,limiter}` | `control/{autopilot,indi,lqr,controller,linearize}` |
| **L4** FDM | JSBSim 6-DoF 래핑, 120Hz | `fdm/plant.py` | `control/plant.py` |
| **기하** | LOS·aspect·ATA·WEZ | `geometry/{combat_geometry,units,wez}` | `engine/{obs,judge}` (혼재) |
| **엔진** | 매치 루프·스케줄러 | `engine/{match,pilot,factory,scenarios,state,tournament}` | `engine/{match,pilot,scenarios,run_nme,match_harness}` |
| **L5** 디브리핑 | ACMI/Tacview | `debrief/{acmi,tacview_realtime}` | `engine/replay.py` |

### 구조적 분기 4개 (후속 심층비교의 착지점)

1. **L3 제어기: INDI-only(core2) vs INDI+LQR(core-live).**
   core2는 설계결정 D2에서 PID/LQR를 명시 배제하고 순수 파이썬 INDI만 JSBSim에 직결. core-live는 `indi.py`(214)와 `lqr.py`(GainScheduledLQR, 253)를 **둘 다** 보유. → L3 비교의 핵심 쟁점.

2. **L2 근거: 교범-grounded(core2) vs 실험-누적(core-live).**
   core2 `doctrine.py`는 공군 기본운용교범 F-16C Vol.5 (2005) Ch.4에 전술을 앵커. core-live `guidance.py`는 루프별 NME_* 플래그가 켜켜이 쌓인 실험 누적물. → L2 비교의 핵심 쟁점.

3. **기하 계층화: 독립 layer(core2) vs 관측/판정 혼재(core-live).**
   core2 `geometry/`가 WEZ·단위·기하를 재사용 가능한 계층으로 분리. core-live는 `obs.py`/`judge.py`에 결합. → 재사용성·테스트가능성 차이.

4. **전술 표현: 정적 DSL(core2) vs 실행형 .yaml + .py 이중(core-live).**
   core2 `tactics/dsl.py`(221)가 BT DSL을 정의. core-live는 최종 챔프를 `full_unified_policy.py`와 틱-동일 `full_unified_42.yaml` 이중으로 유지(설명가능성). → L1 비교의 핵심 쟁점.

## 4. 구조 관점 예비 우열 (상세는 계층별 후속)

| 축 | 우위 | 근거 |
|---|---|---|
| 배포 정합성·가독성 | **core2** | 계층=디렉토리 1:1, 모놀리스 없음, 86 테스트, as-built 문서 |
| 문서화·설계 추적성 | **core2** | ARCHITECTURE.md D1~D6 설계결정 + 교범 근거 |
| 기하/WEZ 재사용성 | **core2** | geometry 독립 계층 |
| 연구 생산력·탐색 폭 | **core-live** | bt/ 14K LOC로 42/42 챔프를 *실제로 생산*, LQR/INDI 양자 보유 |
| 설명가능 산출물 이중화 | **core-live** | .yaml↔.py 틱-동일 챔프(대회 제출형) |
| 검증 실측 인프라 | **core-live** | per-tick 계측·리플레이 3종·held-out 러너 |

**결론(구조 단계):** core2는 *더 깨끗한 배포본*, core-live는 *더 강한 연구엔진*. 동료의 v2는 우리 아키텍처를 검증·정제한 것이지 대체한 것이 아니다. 진짜 우열은 계층별 **알고리즘 내용**(L2 가이던스 법칙, L3 제어 안정성, L1 전술 표현력, L4 FDM 충실도)에서 갈리며, 그건 후속 문서에서 코드를 대조해 판정한다.

## 5. 다음 단계

- `02_L4.md` — FDM/물리: `fdm/plant.py`(191) vs `control/plant.py`(198). JSBSim 배선·적분·상태추출 대조.
- `03_L3.md` — 제어: core2 INDI-only vs core-live INDI+LQR. 안정성·리미터·쿼터니언 shim 대조.
- `04_L2.md` — 가이던스: core2 `bfm_guidance`+`doctrine`(교범) vs core-live `guidance.py`(실험누적). dphi 리프트벡터 법칙 대조.
- `05_L1.md` — 전술: core2 DSL/node vs core-live .yaml+.py 이중 챔프. 표현력·설명가능성 대조.
- `06_SUMMARY.md` — 종합 우열 + 흡수할 아이디어 목록.
