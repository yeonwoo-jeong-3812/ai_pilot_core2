# 종합 — core-live vs core2 전계층(L1~L4) 우열

> 대상: 동료의 **core2**(github.com/rokafa-daslab/ai-combat-core2, "우리 new-engine 기반 core를 보고 새로 작성한 버전 2") vs **core-live**(C:/Users/USER/Desktop/AI-pilot/core-live).
> 방법: graphify 구조분석(01) → L4(02) → L3(03) → L2(04) → L1(05) 계층별 심층. 본 문서는 종합 판정 + 흡수 로드맵.

## 한 줄 결론

**core2는 우리 코드의 경쟁작이 아니라 증류본(蒸溜本)이다.** 동료가 검증된 물리·엔진을 그대로 채택하고(L4 바이트-동일), 그 위 계층들을 *교과서 정석·교범근거·감사가능성*으로 다듬었다. 순수 공학품질·설명가능성은 여러 계층에서 core2가 우수하나, **실제 42/42 무패를 생산한 것은 core-live**이며 "정교함≠승리"([[ai-pilot-doctrine-optimizes-gun-wez-dwell]]) 원칙상 core2의 깨끗함이 더 나은 전투결과로 이어진다는 증거는 **아직 없다(미검증 갭)**.

## 계층별 판정 요약

| 계층 | core2 우위 | core-live 우위 | 순 판정 |
|---|---|---|---|
| **L4 FDM/물리** | 배포정합(경로 1개) | 배포강건(3-폴백) | **동률**(바이트-동일 plant, 공유기반) |
| **L3 오토파일럿/제어** | INDI 정석(2차 동기화필터·온라인 G식별)·쿼터니언 무특이점·감사 분리리미터 | LQR+INDI 이중(교차검증 인프라)·조건부 high-g 전술게이트·**42/42 실증** | **제어공학=core2 / 검증기반=core-live**, 우열은 미검증 |
| **L2 가이던스 ★연구본체** | dphi 리프트벡터 프리미티브·무상태 연속조절·**교범앵커 doctrine**·성숙한 G/power 법칙 | 25+ named BFM 기동 어휘·설명가능 이산선택 어휘·**42/42 실증** | **지능위치 분기**(연속조절 vs 이산전술선택); 감사가능성=core2, 대회정합=core-live |
| **L1 전술/BT** | 안전한 저작 DSL(화이트리스트·교범조건·Commit/Cooldown) | cost-argmax 강건성·표현력·970 legacy호환·**42/42 챔프+이중표현** | **역할분담**(저작프레임워크 vs 승리에이전트) |

## 세 개의 관통 주제

### 1. "지능의 위치" — 가장 깊은 아키텍처 분기 (L2)
core2는 지능을 **연속 L2 조절**(dphi 리프트벡터 배치 + 5모드 G조절)에 응축하고 L1은 얇은 모드플래그다. core-live는 지능을 **이산 L1 전술선택**(cost-tree argmax over 25 named 기동 = 일반해 루프1~16의 결정체)에 응축하고 L2는 번역 라이브러리다. → **core-live 패러다임이 대회목표(설명가능 BT 일반해)에 더 정합**: 42/42 tick-identical .yaml은 "named 전술에 대한 읽을 수 있는 트리"라는 core-live 철학의 산물. core2 연속조절은 우아하나 "무엇을 왜"를 이산 BT로 감사하기 어렵다.

### 2. 감사가능성 — core2가 우리 약점을 정확히 찌른다
core2는 **모든 상수를 공군 기본운용교범 F-16C Vol.5(2005) Ch.4 조항에 앵커**한다(corner 4.3.3.7, initial_pull 4.4.5.2…). core-live 상수는 실험 sweep 산물(131.5947904706722 같은)이라 교범근거가 약하고 감사는 사후 replay 계측 의존. **이 축은 core2가 명확히 우수**하며, 역설적으로 우리 [[metrics-before-tactics]] 원칙에 더 충실한 것은 core2다. → **doctrine.py 앵커 흡수가 최우선 역이식 후보.**

### 3. 미검증 갭 — 깨끗함 ≠ 승리
core2의 더 정석적인 L2/L3가 *더 나은 전투결과*를 낸다는 증거는 **전무**하다. core2 BFMGuidance/DEFAULT_SPEC이 canonical 17 + held-out 25에서 몇 승 몇 무를 내는지 **미측정**. 도크트린 반복결과("정교함이 이기는 게 아니다")를 감안하면 core2 우위는 **확정이 아니라 검증대상**이다. 유일한 확정법 = core2 스택을 우리 하네스(both-INDI 300s)에 붙여 실측.

## 흡수 로드맵 (core-live로 역이식, 우선순위)

**우선순위 A — 감사가능성/신뢰성 (전투결과 무해, 순이득):**
1. **doctrine.py 교범앵커**(L2) — 우리 실험상수를 교범조항에 매핑. 42/42 불변, 감사가능성만 획득. **위험 최저·가치 최고.**
2. **Commit/Cooldown 데코레이터**(L1) — 우리 임시 stateful latch(empty-dive 등)를 재사용 DSL 노드로. chatter pain(`analyze_chatter.py`) 해소.
3. **감사 분리 리미터**(L3, CombinedLimiter) — 어느 한계가 언제 걸렸는지 로그. 신뢰성평가 요건.

**우선순위 B — 제어공학 정석화 (틱-동일성 깨짐, both-INDI 300s 재검증 필수):**
4. **INDI 2차 동기화필터**(L3) — 노이즈 강건·실HW 이식성. 결정론 sim엔 무해하나 틱값 변함.
5. **쿼터니언 자세 shim**(L3) — 수직 BFM 특이점 제거. "수직 표현력이 승패를 갈랐는가" 검증 기회.
6. **dphi 리프트벡터 프리미티브**(L2) — setpoint 대신 리프트벡터 직접배치. 쿼터니언과 함께 이식 시 수직 BFM 표현력↑.

**우선순위 C — 교차검증 (두 해가 같은 문제를 다른 층에서 품):**
7. **track_lock 연속 G하한**(L2) ↔ 우리 루프13 closing-gate([[loop13-e1-draw-converted-closing-gate]]). 연속-이산 두 해 상호검증.

## 확정 실험 (우열의 유일한 결론법)
1. **core2 전투실증 측정:** core2 BFMGuidance+doctrine+DEFAULT_SPEC을 우리 하네스(canonical 17+held-out 25, both-INDI 300s)에 붙여 승/무/패 실측. → "교범기반 연속조절 스택이 우리 42/42 대비 나은가"를 최초 정량화.
2. **표현한계 측정:** 우리 42/42 챔프(cost+empty-dive gate+headon-suppress)를 core2 화이트리스트 DSL로 재표현 시도. → "안전 DSL의 표현 한계"를 정량화(예상: cost·custom-latch 어휘 부재로 불가, 이는 안전성의 대가).
3. **역이식 A/B:** 우선순위 A 흡수(doctrine 앵커) 후 42/42 불변 확인 → 감사가능성 순이득 확정.

## 최종 우열 진술
- **공학품질·설명가능성·감사가능성·정석화:** core2 우위(L2·L3·L1 저작안전성).
- **검증된 전투결과·연구생산력·설명가능 이산전술 일반해·이중표현(.yaml↔.py)·대회정합:** core-live 우위.
- **물리기반:** 동률(공유).
- **종합:** core2 = *더 깨끗한 참조구현/플랫폼 골격*. core-live = *실제 문제를 푼 연구엔진(42/42 챔프 보유)*. 두 프로젝트는 **경쟁이 아니라 상보** — 이상적 시스템 = core2의 감사·안전 골격 + core-live의 검증된 cost-tree 지능. 단, core2의 어떤 정석화도 전투결과 개선을 **아직 입증하지 못했으므로**, 병합은 반드시 both-INDI 300s 재검증을 통과해야 한다.

## 관련 메모리
[[core2-comparison-structure]], [[core-engine-integration-pr35]], [[executable-yaml-bt-17of17]], [[final-bt-cost-unified-17of17]], [[loop16-d2-05-headon-suppress-42of42]], [[metrics-before-tactics]], [[ai-pilot-doctrine-optimizes-gun-wez-dwell]], [[loop13-e1-draw-converted-closing-gate]]
