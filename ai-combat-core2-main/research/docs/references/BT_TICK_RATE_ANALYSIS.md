# BT Tick 주기 변경 — 분석 및 의사결정 문서

작성일: 2026-05-13
대상 시스템: ai-combat-core (BT-vs-BT 매치), ai-combat-sdk (사용자 BT 작성)
배경: SDK 사용자로부터 "BT 결정 빈도를 현재 5 Hz보다 더 자주 가져갈 수 있게 해달라"는 요구 도출

---

## 1. 현재 시스템의 시간 계층

```
JSBSim 물리 적분    : 60 Hz       (sim_freq=60, dt_phys=1/60s)
env.step (BT-vs-BT) : 5  Hz       (agent_interaction_steps=12 → 12×1/60=0.2s)
env.step (Human-vs-BT): 20 Hz     (agent_interaction_steps=3 → 0.05s; runner가 BT만 5Hz로 throttle)
BT tick + RNN 추론  : 5  Hz       (= env.time_interval; 액션은 ZOH로 유지)
```

핵심 정의:
- `env.time_interval = agent_interaction_steps / sim_freq` ([env_base.py:52-53](../src/simulation/envs/JSBSim/envs/env_base.py#L52-L53))
- 이 값이 곧 BT tick 주기다.
- BT의 저수준 4채널 명령은 매 env.step 시작 시 `set_property_values`로 적용되고, 이후 `agent_interaction_steps` physics step 동안 그대로 유지된다 (Zero-Order Hold).

---

## 2. 5 Hz에 묶여 있는 결정적 의존성

| # | 위치 | 의존성 | 위험도 | 자동 스케일? |
|---|------|--------|--------|-------------|
| A | `singlecombat_task.py:308-350` `HierarchicalSingleCombatTask.normalize_action` — **BaselineActor RNN (lowlevel_policy)** | LAG 사전학습 모델이 0.2s 결정 주기로 학습됨 ([baseline.py:78](../src/simulation/envs/JSBSim/model/baseline.py#L78) `env_time_interval = 0.2`). RNN hidden state가 tick마다 1회 갱신 → 학습 시 가정한 시간 스케일이 깨짐 | **치명** | ✗ 재학습 필요 |
| B | `actions.py:121-156` `TimedAction` (Immelmann/SplitS/HammerHead/BarrelRoll/Loop) | `duration_steps`는 BT tick 단위 정수. 모든 YAML/기본값이 5 Hz를 묵시 가정한 채 튜닝됨 — F-16이 그 tick 수 안에 실제 자세 변환을 마치도록 경험적으로 정해진 값 | **치명** | ✗ YAML/기본값 일괄 보정 또는 베이스 클래스 시간 단위화 |
| C | `task.py:130-132` Ps(specific excess power) 차분 | `ps_fts = (E_cur - E_prev) / dt`. dt가 작아지면 수치미분 노이즈 증가 | 중 | △ 공식은 dt-스케일하나 분자 노이즈가 dt에 반비례로 커짐 |
| D | `wez_engine.py` / `health_manager.calculate_damage(geo, dt)` | `damage_per_second * dt` — dt 선형. 러너가 `env.time_interval`을 전달 | 저 | ✓ |
| E | `singlecombat_with_missle_task.py:105` `lock_duration = deque(maxlen=int(1/env.time_interval))` | `env.time_interval` 기반이라 자동 스케일 | 저 | ✓ |
| F | `match_rules.yaml` `max_steps` ↔ `time_limit_seconds` | tick 빨라지면 매치 길이 환산만 하면 됨 | — | ✓ (`time_limit_seconds` 기반 환산) |

---

## 3. 본질적 평가 — BT tick 빈도 증가가 의미 있는가?

### 3.1 4가지 한계 기준에서 본 이론적 최대치

| 관점 | 한계 | 근거 |
|------|------|------|
| 물리 시뮬레이션 | **60 Hz** (= sim_freq) | 그 이상 tick해도 같은 상태를 두 번 봄 |
| 관측 정보량 (Nyquist) | **10–20 Hz** | 항공기 자세 신호 대역폭 ~5–10 Hz |
| 제어 안정성 (outer loop) | **~5 Hz** (현 RNN), ~10 Hz (재학습 시) | inner loop 대역폭의 1/5~1/1 |
| 전술 결정 변화율 | **1–2 Hz** | OODA timescale, BT 분기 전환 빈도 |
| 계산 가능성 (현 PC) | ~150–300 Hz | BT+RNN+obs 합쳐 3–6 ms/tick |

### 3.2 일반적 결론

- **너그러운 WEZ(현 12°) 기준에선 5 Hz가 거의 최적.** 그 이상은 정보·결정·제어 어느 관점에서도 추가 이득이 없거나 마이너스.
- 단 **WEZ tightening** 같은 시스템적 변화(예: ATA 12°→4°)와 결합되면 분석이 달라짐:
  - 4° WEZ residence time = 0.13–0.27 s
  - 5 Hz 샘플링 주기 0.2 s가 통과 사건을 놓칠 수 있음
  - 이 경우 직접 처방은 **`env.step` rate 상승(20 Hz)** — BT tick과 별개
- **사용자 요구가 "BT 결정 자체를 더 자주"라면**, 아래 §4 경로로 진행.

---

## 4. 구현 경로

### Path 1 — 가장 싼 경로: BT 10 Hz, RNN도 10 Hz로 그대로 (재학습 없음)

**변경:**
- `agent_interaction_steps`: 12 → 6 (env.step = 10 Hz)
- 러너 구조 그대로, RNN(`lowlevel_policy`)도 자동 10 Hz 호출

**효과:**
- BT 조건 재평가 빈도 2배 ✓ (사용자 요구 충족)
- RNN GRU hidden state가 학습 분포보다 2배 빠르게 recurr → 분포 시프트
- 실제 영향은 경험적. F-16 6-DOF는 짧은 시간 스케일에서 부드러우므로 2배 정도는 미세 떨림으로 끝나는 경우 多

**비용:** YAML 한 줄 + 러너 수정 거의 없음. 수 시간 작업
**리스크:** 제어면 진동 가능. 자기대전 5~10매치 정성 평가 필요
**판정:** 첫 시도. 대부분의 SDK 사용자 만족 가능성이 가장 높음

### Path 2 — 결정과 제어 분리: BT 10 Hz 결정, RNN 5 Hz 추론

**변경:**
- BT tick 10 Hz로 빠르게 — 조건 평가 + action 선택 자주 수행
- RNN 추론은 2 BT-tick에 1번 (`runner_human_vs_bt.py`의 `BT_TICK_EVERY` 패턴을 `runner_core.py`에도 이식)
- 사이 tick의 BT 결정은 *결정만 됨*, 다음 RNN tick에서 반영

**효과:**
- BT 입장에선 매 100 ms마다 결정 가능 ✓
- RNN/제어면은 5 Hz (학습 분포 보존, 재학습 없음)
- 제어 응답성은 그대로, **BT의 hysteresis·debounce·이벤트 감지·`TimedAction._step` 카운터는 2배 정밀**

**비용:** Path 1과 비슷, 러너 수정 약간 더 많음
**리스크:** 거의 없음 (BT는 자기 hidden state가 없음)
**한계:** BT가 새 setpoint를 정해도 다음 RNN tick까지 안 받음 → 결정-제어 latency 최대 200 ms (BT-내부 latency는 100 ms)
**판정:** "BT가 더 잘 반응한다" 체감을 안전하게 제공. 권장 본선

### Path 3 — 완전 재학습: BT/RNN 모두 10/20 Hz

**변경:**
- `heading.yaml`도 동일하게 `agent_interaction_steps` 변경
- `train_heading.sh` 재실행 → `baseline_model.pt` 교체
- TimedAction `duration_steps` 일괄 보정 (§5 참조)
- 평가 매치로 회귀 검증

**비용:**
- 본 PC (i7-4790, 4C/8T, GTX 750 2GB): **24~36 시간/주파수**
- 클라우드 c6i.4xlarge: **4~6 시간/주파수**
- 검증·튜닝 포함 총 ~3일

**효과:** 진짜 제어 대역폭 2배. WEZ tightening 등 미래 변경에 더 강한 시스템
**판정:** Path 1·2 검증 후 한계가 명확할 때만 진행

### 경로 비교 요약

| 경로 | BT 결정 빈도 | RNN 추론 빈도 | 재학습 | 코드 변경 | 리스크 |
|------|------------|---------------|--------|----------|--------|
| 현 상태 | 5 Hz | 5 Hz | — | — | — |
| Path 1 | 10 Hz | 10 Hz | ✗ | 최소 | 제어 진동 가능 |
| Path 2 | 10 Hz | 5 Hz | ✗ | 소 | 거의 없음 |
| Path 3 | 10~20 Hz | 10~20 Hz | ✓ (수 시간~수십 시간) | 중 | 회귀 가능, 검증 필요 |

---

## 5. 공통 부수 작업 (어느 경로든 필요)

### 5.1 TimedAction 단위 환산 — 필수

`duration_steps` 정수 카운트는 5 Hz 기준 튜닝값. tick rate 변경 시 의미 시간이 비례 변형됨.

**옵션 A (권장)** — 환경 config에 `bt_tick_rate_hz` 추가, 베이스 클래스가 자동 비례 환산:

```python
class TimedAction(BaseAction):
    REFERENCE_TICK_HZ = 5.0
    def __init__(self, name, duration_steps):
        super().__init__(name)
        cur_rate = self.blackboard.get("/TickRateHz") or self.REFERENCE_TICK_HZ
        self._duration = max(1, int(round(duration_steps * cur_rate / self.REFERENCE_TICK_HZ)))
```

→ YAML 호환성 유지. 기존 `duration_steps: 15` 작성은 새 tick rate에서도 동일한 *실 시간*(3 s) 의미.

**옵션 B** — `duration_seconds` 필드 도입, `duration_steps`는 deprecate.

### 5.2 `max_steps` ↔ `time_limit_seconds` 정리

[match_rules.yaml:7](../config/match_rules.yaml#L7)의 `time_limit_seconds: 300`을 1차 진리로 삼고, runner가 시작 시 `max_steps = int(time_limit_seconds / env.time_interval)`로 자동 계산하도록 수정.

### 5.3 관측/로깅 빈도와 결정 빈도의 분리 (별건이지만 동시 검토 가치 있음)

SDK 사용자가 추가로 "관측/CSV 로깅이 더 촘촘하면 좋겠다"를 요구한 배경 → BT 결정 빈도와는 독립적으로 해결 가능:

- `env_base.step()`에 `on_substep` 콜백 도입, runner가 inner loop의 매 sub-step마다 raw state를 샘플링
- BT 결정 5 Hz / RNN 5 Hz를 유지한 채 텔레메트리만 60 Hz로 끌어올릴 수 있음
- 이미 [runner_human_vs_bt.py:_mixed_step](../src/match/runner_human_vs_bt.py#L142-L199)이 조이스틱 폴링용으로 동일 패턴 구현 중

---

## 6. 권고 실행 순서

1. **이번 주**
   - Path 1 구현 (`agent_interaction_steps: 12 → 6`)
   - TimedAction 자동 스케일러 (§5.1 옵션 A) 동시 도입
   - 자기대전 5~10매치로 안정성 정성 평가

2. **Path 1이 불안정하면**
   - Path 2로 전환 (BT 10 Hz / RNN 5 Hz, `BT_TICK_EVERY` 분리)

3. **두 경로 모두 부족하면**
   - Path 3 진행 (클라우드 c6i.4xlarge 권장, 본 PC는 비효율)
   - 학습 후 모델 교체 + 회귀 검증 매치

4. **부수 정리**
   - `max_steps` ↔ `time_limit_seconds` 통합 (§5.2)
   - sub-step 콜백 도입으로 로깅/관측 빈도 분리 (§5.3)

---

## 7. ADT 두 문서 종합 (Pope 2023 + DeMay 2022)

§1–§6은 코드 분석만으로 도출한 결론. 이후 [ADT_engagement_environment.md](ADT_engagement_environment.md) (Pope) 와 [ADT_paper.pdf](ADT_paper.pdf) (DeMay/APL Technical Digest 2022) 를 검토해 외부 기준이 추가됨.

### 7.1 ADT가 정한 시간 계층

| 항목 | ADT (Pope) | 현 시스템 | 격차 |
|------|-----------|----------|------|
| Low-level policy | 50 Hz | 5 Hz | 10× |
| Policy Selector (outer) | 10 Hz | 5 Hz | 2× |
| WEZ 콘 | 2° | 12° | 6× 너그러움 |
| WEZ 거리 | 500–3000 ft | 동일 | — |
| Hard deck | 1000 ft | 동일 | — |

### 7.2 DeMay (APL) 회고에서 보강된 컨텍스트

- APL의 Basic 적 AI도 **PID 3-loop (outer/middle/inner)** 구조 — 우리 BT→RNN→FCS와 동형
- 챔피언 Heron Systems = **Pure RL self-play**, hybrid 팀(Lockheed 등)을 16–4로 꺾음
- Heron의 승리 요인: **"aggressive and highly accurate forward gun attacks at the merge"** — 머지 직후 고대역폭 정조준 사격
- APL 스스로 인정한 한계: **"perfect state information"** — 센서 노이즈 없음. 우리도 동일 가정

### 7.3 세 가지 독립 동력

이번 결정에 작용하는 동력:

| # | 동력 | 출처 | 요구 |
|---|------|------|------|
| D1 | SDK 사용자 요구 | 본 프로젝트 직접 요구 | BT 결정 빈도 5 Hz 이상 |
| D2 | ADT 벤치마크 정합 | Pope 2023, DeMay 2022 | PS 10 Hz, low-level 50 Hz, WEZ 2° |
| D3 | WEZ tightening 안전성 | 자체 검토 (앞서 4°→2° 논의) | env.step ≥ 15 Hz (Nyquist) |

---

## 8. 최종 권고 (결정)

### 8.1 결정 매트릭스

| 옵션 | BT | RNN | env.step | WEZ | D1 | D2 | D3 | 코스트 |
|------|-----|-----|----------|-----|----|----|----|---------|
| 현 상태 | 5 Hz | 5 Hz | 5 Hz | 12° | ✗ | ✗ | ✗ | 0 |
| Path 1 단순 | 10 Hz | 10 Hz | 10 Hz | 12° | ✓ | △ (PS만) | △ | 수 시간 + 안정성 리스크 |
| **Path 2 + WEZ 정합 (채택)** | **10 Hz** | **5 Hz (캐시)** | **20 Hz** | **2°** | **✓** | **✓ (PS+WEZ)** | **✓** | **~1주, 재학습 없음** |
| Path 3 부분 | 10 Hz | 10 Hz (재학습) | 10 Hz | 2° | ✓ | ✓✓ | ✓ | +학습 24–36 h |
| Path 3 완전 (ADT 풀정합) | 10 Hz | 50 Hz (재학습) | 60 Hz | 2° | ✓ | ✓✓✓ | ✓ | +학습 24–36 h, agent_interaction_steps=1 |

### 8.2 채택안: Path 2 + ADT WEZ 정합

```
JSBSim 물리       : 60 Hz   (sim_freq=60, 변경 없음)
env.step          : 20 Hz   (agent_interaction_steps: 12 → 3)
  - WEZ 잔류 감지 + 데미지 적분: 20 Hz  ← D3 충족
BT tick           : 10 Hz   (env.step 2회당 BT 1회, BT_TICK_EVERY=2)
  - BT 조건 평가 + action 선택: 10 Hz   ← D1, D2(PS) 충족
RNN 추론          :  5 Hz   (env.step 4회당 RNN 1회, RNN_TICK_EVERY=4)
  - 학습 분포 보존, 재학습 불필요
WEZ 콘            :  2°     (ADT Pope 정합)             ← D2(WEZ) 충족
WEZ 거리/하드덱   : 500–3000 ft / 1000 ft (이미 동일)
```

### 8.3 채택 근거

- **D1 (SDK 요구)** ✓ : BT 결정 100 ms 간격
- **D2 (ADT PS rate)** ✓ : 10 Hz 정확 일치
- **D2 (ADT WEZ)** ✓ : 2°, $(3000-d)/2500$ 공식 정확 일치
- **D2 (ADT low-level)** △ : 5 Hz vs 50 Hz 격차 존재. 단 BaselineActor가 RNN으로 자세 추적을 부드럽게 흡수하므로 outer 비교 의미 보존. 논문 §관련연구에 "low-level은 5 Hz 유지, PS만 정합"으로 명시.
- **D3 (WEZ tightening 안전성)** ✓ : 20 Hz env.step으로 2° 콘 통과 사건(잔류시간 0.13–0.27 s) 안정 검출
- **재학습 0** : BaselineActor 그대로 사용

Path 1을 채택하지 않는 이유: BT/RNN 모두 10 Hz로 올리면 RNN 분포 시프트 발생. 실패 시 후퇴 비용 발생. Path 2는 결정론적으로 학습 가정을 보존.

Path 3 즉시 진행하지 않는 이유: ADT low-level 50 Hz까지 가는 재학습 + 회귀 검증 부담이 큼. 우선 Path 2로 SDK 요구·ADT PS·WEZ 정합을 모두 충족한 뒤, 정량적 부족이 입증되면 단계적으로 Path 3 진행.

### 8.4 실행 체크리스트

```
[1] config 변경
    src/simulation/envs/JSBSim/configs/1v1/NoWeapon/bt_vs_bt.yaml
      agent_interaction_steps: 12 → 3
    config/match_rules.yaml
      max_steps 제거 또는 time_limit_seconds로 자동 환산

[2] WEZ 상수
    src/utils/units.py
      WEZ_MAX_ANGLE_DEG: 12.0 → 2.0
    src/control/health_manager.py
      calculate_damage 공식을 ADT 형식으로 옵션 분기
      (또는 신규 함수 calculate_damage_adt 추가)

[3] 러너 분리 패턴 (runner_core.py에 이식)
    BT_TICK_EVERY = 2     # 10 Hz
    RNN_TICK_EVERY = 4    # 5 Hz
    BT 캐시(action) + RNN 캐시(low-level) 분리 관리

[4] TimedAction 자동 스케일 (§5.1 옵션 A)
    REFERENCE_TICK_HZ = 5.0
    duration_steps = duration_steps × (현 BT Hz / 5)
    → 기존 YAML 호환성 유지

[5] 회귀 검증 (DeMay 사다리 차용)
    Zombie/Rosie/BUD/우리 BT 4-tier 토너먼트
    20 engagement per match-pair, kill ratio 보고
```

### 8.5 검증 게이트

채택안 적용 후 다음을 통과해야 production 진행:

| 게이트 | 기준 |
|--------|------|
| 자기대전 안정성 | 동일 BT 양측, 20 매치, 결과 50% ± 10%p |
| ADT-style 머지 행동 | 머지 직후 평균 ATA < 5° 유지 시간 ↑ |
| Hard deck 위반율 | ≤ 5% (현 수준 유지) |
| 매치 평균 길이 | 60–180 초 범위 |
| SDK 사용자 체감 | 별도 인터뷰 — "더 자주 결정한다" 체감 확인 |

### 8.6 한 줄 요약

**BT 10 Hz / RNN 5 Hz (캐시 분리) + env.step 20 Hz + WEZ 2° 채택. 재학습 없음. ADT PS·WEZ 정합 + SDK 요구 + WEZ tightening 안전성 동시 충족.**

---

## 10. 확정 (2026-05-26) — A/B 매치로 검증

§8의 채택안(Path 2: BT 10 Hz / RNN 5 Hz / env.step 20 Hz)을 빈도 sweep 매치로 사후 검증함.

### 10.1 실험 설계

- 환경변수 `AICOMBAT_BT_HZ` 도입 — runner_core(`BT_TICK_EVERY`)와 BehaviorTreeTask(`BT_TARGET_HZ`) 양쪽에서 동일 값 참조
- 5 페어 × 2~3 Hz × 10 매치 = **110 매치** 실측
- 활성 시나리오 `1v1/NoWeapon/bt_vs_bt.yaml` (env.step 20 Hz 고정)
- 동일 셔플 분포·동일 reward 함수, BT_TARGET_HZ만 변경

| 페어 | 5 Hz | 10 Hz | 20 Hz |
|---|---|---|---|
| ace vs simple | draw=10 | draw=10 | — |
| viper1 vs eagle1 | draw=10 | draw=10 | — |
| **taipan vs GwangPung** | **GP=10** | **taipan=10** | **GP=10** |
| taipan vs sonny | sonny=3, draw=7 | sonny=5, draw=5 | — |
| GwangPung vs sonny | sonny=6, draw=4 | sonny=6, draw=4 | — |

### 10.2 핵심 발견

**1. 비단조(non-monotonic) peak at 10 Hz** — taipan vs GwangPung 단조성 sweep:

| Hz | taipan reward | GwangPung reward |
|---|---|---|
| 5 | −31.31 | −14.90 |
| **10** | **−23.98 (peak)** | −22.60 |
| 20 | −48.98 | −47.39 |

→ 10 Hz가 taipan의 sweet spot, 양쪽 극단(5/20)에서 손해.

**2. 메커니즘 — taipan의 WEZ 진입 (ACMI 분석)**:

| Hz | taipan in-WEZ steps | GwangPung in-WEZ | GwangPung HP |
|---|---|---|---|
| 5 | 1.8 | 16.0 | 100.0 |
| 10 | **30.6** | 16.8 | 94.8 |
| 20 | **0.0** | **51.6** | 100.0 |

- **5 Hz**: BT가 느려 짧은 WEZ 윈도우(<100 ms)를 못 잡음 → SnapShot/GunEngagement 거의 발동 안 됨
- **10 Hz**: BT가 충분히 빨라 윈도우 포착 + RNN 5 Hz와 정수비 위상 정합 → WEZ 진입 30.6 step → 승
- **20 Hz**: BT가 RNN보다 4× 빠름 → RNN tick 사이 transient BT 출력을 RNN이 sample → 핵심 가지 latch 못함 → WEZ 진입 0

**3. 트리별 Hz sensitivity (5→10 Hz reward delta)**:

| 트리 | vs 적1 | vs 적2 | 경향 |
|---|---|---|---|
| taipan (공격·BFM·snapshot) | +7.33 | +3.08 | **10 Hz 선호** |
| GwangPung (positional) | −7.70 (vs taipan) | +3.48 (vs sonny) | mixed |
| sonny (단순 berserker) | −2.38 | −2.33 | 약하게 5 Hz 선호, **전반적 Hz robust** |

→ Hz 민감도는 **트리 복잡도와 BFM 의존도**에 비례. 단순/positional 트리는 Hz robust, 공격적·short-window 트리는 10 Hz에 의존.

### 10.3 확정 사항

```
JSBSim 물리       : 60 Hz   (sim_freq=60, 변경 없음)
env.step          : 20 Hz   (agent_interaction_steps=3)  ← 토너먼트 고정
BT action tick    : 10 Hz   (BT_TICK_EVERY = round(0.1 / 0.05) = 2)  ← 토너먼트 고정
BT condition subtick : 20 Hz (매 env.step) ← 자동, 짧은 이벤트 감지
RNN 저수준 정책   :  5 Hz   (RNN_TICK_EVERY = 4, ZOH cache)  ← LAG 학습 분포 보존
```

이 값들은 토너먼트 디폴트로 **고정**. `AICOMBAT_BT_HZ` 환경변수는 참가자가 자기 트리의 Hz 민감도를 자가 진단할 때만 사용 가능 (토너먼트 채점에는 적용 안 됨).

### 10.4 공정성 고지

위 수치는 **중립 물리 상수가 아니라 경쟁 변수**임을 명시. 데이터가 보여주는 시스템 편향:

- **공격적·BFM 기반·short-window opportunistic 전략에 유리**한 환경
- **단순 positional / 비반응적 트리에는 영향 없음** (Hz 무관 결과 동일)
- **5 Hz·20 Hz로 변경 시 결과가 뒤집힐 수 있는 페어 존재** (taipan vs GwangPung)

따라서 참가자에게는 디폴트 10 Hz에 대해 튜닝할 것을 권장하며, 자기 트리가 다른 Hz에서 어떻게 동작하는지 점검하려면 `$env:AICOMBAT_BT_HZ` 값을 바꿔 로컬 매치를 돌릴 수 있다.

### 10.5 재현 자료

- 실험 러너: [scripts/exp_bt_hz_ab.py](../scripts/exp_bt_hz_ab.py)
- ACMI 행동 분석: [scripts/acmi_bt_analysis.py](../scripts/acmi_bt_analysis.py)
- 원본 결과 JSON: `exp_{5,10,20}hz_*.json` (총 11개 파일)
- ACMI 리플레이: `replays/` (총 70개, 매 step ActiveNode/Health/Distance/ATA 기록)

---

## 11. 참고: 핵심 파일 경로

- BT 러너 (BT-vs-BT): [src/match/runner_core.py](../src/match/runner_core.py)
- BT 러너 (Human-vs-BT, 분리 패턴 참조): [src/match/runner_human_vs_bt.py](../src/match/runner_human_vs_bt.py)
- BT Task: [src/behavior_tree/task.py](../src/behavior_tree/task.py)
- BT Action 노드 (TimedAction): [src/behavior_tree/nodes/actions.py](../src/behavior_tree/nodes/actions.py)
- LAG env: [src/simulation/envs/JSBSim/envs/env_base.py](../src/simulation/envs/JSBSim/envs/env_base.py)
- Hierarchical task (RNN 호출): [src/simulation/envs/JSBSim/tasks/singlecombat_task.py](../src/simulation/envs/JSBSim/tasks/singlecombat_task.py)
- BaselineActor 모델: [src/simulation/envs/JSBSim/model/baseline_actor.py](../src/simulation/envs/JSBSim/model/baseline_actor.py)
- 학습 설정: [external_repo/LAG/scripts/train_heading.sh](../external_repo/LAG/scripts/train_heading.sh), [external_repo/LAG/envs/JSBSim/configs/1/heading.yaml](../external_repo/LAG/envs/JSBSim/configs/1/heading.yaml)
- WEZ 엔진: [src/match/wez_engine.py](../src/match/wez_engine.py), [src/control/health_manager.py](../src/control/health_manager.py)
- 매치 규칙: [config/match_rules.yaml](../config/match_rules.yaml)
