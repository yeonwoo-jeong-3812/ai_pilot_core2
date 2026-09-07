# 최종 정책(BT) 완전 해설 — `IntelPolicy`는 무엇이고, 실행하면 무슨 일이 벌어지나

> 숫자·상태·D2 서사는 [`CANON.md`](CANON.md)를 정본으로 한다.

이 문서는 우리의 **최종 통합 정책**을 *처음 보는 사람도 따라올 수 있게* 아주 자세히 설명한다. 세 가지를
다룬다: **(1)** IFF가 정확히 무엇을 추측하는가(★중요), **(2)** `python exp_e53_integrated_17.py`를
실행하면 *어떤 코드들이 어떤 순서로* 동작하는가, **(3)** 정책의 내부 구조와 왜 `.yaml`로는 못 쓰는가.

---

## 0. 한 문단 요약 (먼저 큰 그림)

우리 최종 정책은 `new_match_engine/bt/exp_e53_integrated_17.py`의 **`IntelPolicy` 클래스**다. 이건
"적의 *행동 유형*을 (실전에선 관측으로 *스스로 분류*해) 판단하고, 그 유형에 맞는 *교범 독트린*을 골라,
매 순간 *어느 전술(tactic)을 쓸지*만 정하는" 49줄짜리 의사결정기다. 비행기를 *어떻게* 모는지(목표 침로·고도·속도 계산, 조종간 제어, 물리,
명중판정)는 전부 엔진의 다른 계층이 처리한다. 즉 **`IntelPolicy`는 "두뇌의 전술 선택" 부분**이고,
나머지는 손발이다.

---

## 1. ★ IFF는 "적 BT"가 아니라 "적의 *행동 유형*"을 추측한다 (가장 중요)

이걸 먼저 못박는다. 우리 정책의 입력에는 적의 **유형(type)** 이 있다 — `{D2, A3, base}` 중 하나.
**이 유형은 "적이 어느 `.yaml` 파일인가"가 아니라, "적이 *어떻게 싸우는가*(행동 archetype)"다.**

| 잘못된 이해 | ✅ 올바른 이해 |
|---|---|
| "이 적은 `D2_LastDitch_03.yaml`이다"라고 *정체*를 맞힌다 | "이 적은 *최후방어 강하로 하드덱까지 도주하는 행동*을 한다(D2형)"라고 *행동 유형*을 판단한다 |
| 특정 BT 파일을 기억/매칭(과적합) | 행동 패턴을 분류(일반화) |

**왜 이게 중요한가:** 행동 유형으로 판단하면 **그렇게 행동하는 *어떤* 적에게도** 같은 독트린이 통한다.
즉 "lag-angler처럼 각을 안 내주는 적"이면 그 적이 무슨 BT든 A3 독트린(merge 강요+ETM)을 쓴다. 특정
BT를 외운 게 아니라 *행동의 부류*를 잡은 것 — 그래서 일반해다(논문 §8 "과적합이 아닌 이유").

**유형을 *어떻게* 아는가 — 두 가지 길:**
- **① blind 자가분류 (`exp_e49_type_classifier.py`, 기본·실전 배포형):** 적 정보 0으로, **처음 50초간
  적의 *궤적 형상*(rmin·aa_min·reopen)을 관측해 행동 유형을 *스스로 분류*** 한다(아래 §8). 이건
  명백히 *관측된 행동*을 보고 판단하는 것 — BT를 추측하는 게 아니다. **이것이 실전 기본 경로다.**
- **② oracle 모드 (상한 벤치마크만):** 적의 행동 유형을 IFF·정찰이 *미리 알려줄* 때. ⚠ 이건 *평가용
  상한*이지 실전 배포 경로가 아니다. (예전에는 평가 코드가 적 이름에서 유형을 읽었는데
  — `it = "D2" if opp=="D2_LastDitch" ...` — 이는 *답을 훔쳐보는 cheat*였고 실전 불가라 **제거**됐다.
  남은 건 "유형이 주어졌다 가정"하는 oracle 상한 측정뿐이다.)

> 정리: **유형 = 행동 archetype.** blind는 *관측해 스스로 분류*(실전), oracle은 그걸 *주어진* 것으로
> 가정(상한 측정). 어느 쪽이든 "적 BT 추측"이 아니라 "적 *행동* 판단"이다. (상세: §17 발견문서
> [17_findings](17_findings_prediction_and_fidelity.md).)

---

## 2. 실행하면 무슨 일이 벌어지나 — 코드 흐름 (step-by-step)

`cd new_match_engine/bt; python exp_e53_integrated_17.py` 하면 `main`이 돈다(유형 주입은 oracle 상한
측정용 경로; 실전은 §7의 blind 자가분류). 단계별로, *어떤 파일이 동작하는지* 함께 적는다.

### [준비 단계] (main 시작부, exp_e53 55–60행)
1. **`rf, tac = _train(DS_DA)`**
   → `exp_e7_champion.py`의 `_train`이 `exp_e10_unified.py`의 데이터셋 `DS_DA`(DAgger로 모은
   관측→전술 라벨)로 **RandomForest 가치모델 `rf`를 학습**. `tac`은 전술 이름 리스트. *이게 base
   정책의 두뇌.*
2. **`guidance.ETM_TAU = 2.0`**
   → `control/guidance.py`의 전역 변수. ETM(적-궤적예측 조준)의 *예측 선행시간 τ=2초* 설정.
3. **`gs = GainScheduledLQR([...],[...]).build()`**
   → `control/lqr.py`. 고도·속도 격자에서 **LQR 게인을 미리 계산**(자세 안정 제어기의 기반).
4. **`cfg = AutopilotConfig(KP_PSI=0.25); cfg.MAX_PSI_RATE = 30°`**
   → `control/autopilot.py`의 튜닝 파라미터(선회 게인·최대 선회율).

### [17 적과의 루프] (exp_e53 64–85행) — 적 한 명마다 반복
5. **`it = "D2"/"A3"/"base"`** — 이 적의 **행동 유형**(§1). oracle 상한 측정에선 주어지고, 실전(blind)에선
   `exp_e49`가 궤적 형상으로 *스스로 분류*한다(§7).
6. **`p1, p2 = spawn_adt_neutral()`**
   → `engine/scenarios.py`. *정준 중립 초기조건*(90° beam, 3000ft, anti-parallel) 두 기체 생성.
7. **`pol = IntelPolicy(rf, tac, it)`**
   → 우리 정책 인스턴스. 내부에 `AdaptivePolicy`(base 두뇌, `exp_e27_adaptive_subset.py`)를 품음.
8. **`m = Match(p1, p2, gs, cfg1=cfg, cfg2=..., controller1="indi", controller2="lqr")`**
   → `engine/match.py`. **매치 엔진** 생성. 우리(p1)=INDI 제어기, 적(p2)=LQR 제어기.
   ⚠ 이 `main` 경로의 `controller2="lqr"`는 *비캐노니컬*이다 — 캐노니컬 평가는 **both-INDI**
   (`exp_e53_indi_both.py`, 양측 INDI, CANON §4). 약한 LQR 적은 격추수를 부풀린다.
9. **`r = m.run(tactic_fn1=우리정책, tactic_fn2=적BT, duration_s=...)`**
   → 교전을 굴린다(§5에서 한 틱 상세). 캐노니컬 경기 길이는 **300초**(CANON §1; 코드 기본 200s는
   과소집계). `tactic_fn1`=`pol.select`,
   `tactic_fn2`=`_opp(opp)`(적 `.yaml` BT, `exp_e22_chaseforce.py`가 로드).
10. **결과 집계 + replay 저장**(A3·D2는 `.acmi`+csv+plot, `engine/replay.py`·`tools/plot_match_3d_nme.py`).

### [출력]
11. 적별 결과 + 승패 집계. (이 `main` 경로는 유형 주입 = *oracle 상한*이라 D2까지 포함 **17/17**;
    실전 배치인 blind 자가분류는 **16/17**, D2만 무 — CANON §5.)

---

## 3. 코드 참조 지도 — 어느 파일이 무엇을 하나

실행 중 동작하는 파일들을 한 표로(★=핵심 경로):

| 파일 | 역할 | 호출 시점 |
|---|---|---|
| ★ `bt/exp_e53_integrated_17.py` | **최종 정책 `IntelPolicy` + main 루프** | 진입점 |
| ★ `bt/exp_e27_adaptive_subset.py` | **`AdaptivePolicy`** (base 두뇌: RF argmax + 보정) | `IntelPolicy`가 base일 때 |
| `bt/exp_e7_champion.py` | `_train` (RandomForest 학습) | 준비 |
| `bt/exp_e10_unified.py` | `DS_DA` (학습 데이터셋) | 준비 |
| `bt/exp_e22_chaseforce.py` | `_opp(name)` (적 `.yaml` BT 로더) | 매치마다(적) |
| ★ `control/guidance.py` | **전술 → setpoint(ψ*,h*,V*)** 공식 + ETM | 매 제어틱 |
| ★ `control/indi.py` | **INDI 제어기**(우리): setpoint 추종 → 조종간 | 매 제어틱(우리) |
| `control/autopilot.py` | LQR 제어기(적) + 외측 루프 공식 | 매 제어틱(적) |
| `control/lqr.py` | gain-scheduled LQR 게인 | 준비 + 매 틱 |
| `control/tactic.py` | `Tactic` enum (전술 종류 정의) | 전역 |
| `engine/match.py` | **매치 루프**(다중 rate: 물리120/제어20/BT10/log60 Hz) | `m.run()` |
| `engine/obs.py` | `compute_obs` (상대 관측 계산) | 매 제어틱 |
| `engine/pilot.py` | obs→tactic→guidance→제어 묶음(한 에이전트) | 매 틱 |
| `engine/judge.py` | WEZ 판정·데미지·하드덱 | 매 log틱 |
| `engine/scenarios.py` | `spawn_adt_neutral` (초기조건) | 매치 시작 |
| `engine/replay.py`, `tools/plot_match_3d_nme.py` | `.acmi`·csv·plot 저장 | 매치 끝 |
| (blind) `bt/exp_e49_type_classifier.py` | **형상 분류기**(궤적→행동유형) | blind 모드 |

---

## 4. `IntelPolicy`의 내부 — 세 독트린 (코드 그대로 친절히)

```python
class IntelPolicy:
    def __init__(self, rf, tac, oracle):
        self.base = AdaptivePolicy(rf, tac, corrections=True)  # base 두뇌
        self.typ = oracle            # None=관측 자가분류(실전), 값=그 유형 고정(oracle)
        self.t = 0.0; self.ph = 0    # 시간·phase 상태(메모리)

    def select_obs(self, o):
        self._sync(o)                          # 틱당 1회(멱등): t 증가·바닥 판정·자가분류·V_MAX
        if self._floored: return T.CLIMB        # ① 안전(추락방지) 최우선
        if self.typ == "D2": return self._d2(o)  # ② D2 (SMART_DIVE deck-chase, 기본)
        if self.typ == "A3": return self._a3(o)  # ③ A3 (ETM-merge 2상태)
        return self._base_branch(o)              # ④ base (AdaptivePolicy)

    def _sync(self, o):
        self.t += 0.1
        _floor = D2_DECK_FT if self.typ == "D2" else 2500.0   # ★ D2엔 deck까지 추격(1500)
        self._floored = o.ego_alt_ft < _floor
        ...  # (바닥 아니면) 궤적 형상으로 자가분류 + D2 격리 V_MAX
```

### ① 안전 — 추락 방지 (유형별 바닥)
바닥 고도 아래면 무조건 `CLIMB`(상승). 어떤 전술보다 우선. **바닥은 유형별**: 일반 2500ft,
**D2는 1500ft**(`D2_DECK_FT`). 일반 2500 바닥은 D2 운용고도(~1200–1800ft)보다 높아, D2를 gun 거리로
쫓아 내려갈 때마다 CLIMB로 튕겨 에너지를 잃고 D2가 extend한다 — 그래서 D2엔 deck까지 추격 가능하도록
바닥을 낮췄다(추락 1000ft 위 여유). 이 한 상수가 D2 격파의 열쇠였다(CANON §6).

### ② D2 독트린 — *dive-to-deck extender* 파훼 (`_d2`, 기본 SMART_DIVE)
D2형은 나선강하가 아니라 **얕은 강하로 고도를 속도로 바꿔 하드덱까지 내려가며 도주**하는
extender다. 기본 독트린(`D2_SMART`)은 **연속 3D intercept 강하추격(SMART_DIVE)** + **overshoot 가드**
(`D2_OS_GUARD`, 정렬+고closure+근접이면 `LAG_PURSUIT`로 감속 안착 → deck 고속 관통에 의한 bait-reversal
역전 차단) + **D2 격리 V_MAX 540**(deck 속도 초과 추격). WEZ+정렬이면 `GUN_TRACK`.
이 조합으로 **oracle에서 D2 판정승 → oracle 17/17**(CANON §5·§6). blind에서는 D2를 제때 분류하지
못해 여전히 무(정보한계, §7). (구버전의 시간인덱스 `D2_SEQ` 6단계는 이제 폴백 경로다.)

### ③ A3 독트린 — *거리 phase* 상태기계 (`self.ph` 사용)
A3형(각을 안 내주는 standoff lagger)은 **거리에 따라 2상태**:
- 멀면(ph=0) → `LEAD_PURSUIT`로 **merge 강요**(거리 닫기).
- 가까우면(ph=1) → `ETM_TRACK`로 **적 등선회를 τ초 예측 조준**(회피 앞지름).
- WEZ ↔ WEZ×1.8의 **히스테리시스로 진동 방지**. **`self.ph`(상태 메모리)가 핵심.**

### ④ base 독트린 — `AdaptivePolicy` (15종 담당, 일반 정책)
`exp_e27_adaptive_subset.py`:
```python
return Tactic[self.tac[int(self.rf.predict(x)[0].argmax())]]   # RF 가치 argmax
```
- **학습된 RandomForest**가 8개 관측-차 feature(ata/aa/hca/dist/closure/Δes/ego_r/enm_r)로 각 전술의
  *가치*를 예측 → 최고값 전술 선택.
- `corrections=True`면 **무승부 상황(circle/extend)만** 5상황 soft-membership으로 보정(승리 상황은
  안 건드림 = "고치되 망치지 않음"). **연속 수치 계산**(value 예측 + sigmoid 블렌딩).

---

## 5. 한 틱(tick)의 데이터 흐름 — 전술이 비행이 되기까지

`Match.run` 안에서 매 제어틱(20Hz) 벌어지는 일(`engine/match.py`):
```
1. compute_obs(p1,p2)            # engine/obs.py — 상대 기하·에너지 관측 o
2. (10Hz BT틱) tactic = pol.select(p1,p2)     # ★ IntelPolicy — "어느 전술"  ← 이 문서의 정책
                tactic2 = _opp(name)(obs2)    #   적 .yaml BT
3. sp = guidance.compute(tactic, o)           # control/guidance.py — 전술→(ψ*,h*,V*) 공식
4. (6×120Hz 물리서브스텝):
     u = INDIController.step(sp)               # control/indi.py — setpoint 추종 → [thr,elev,ail,rud]
     JSBSim.step()                             # 6-DOF 물리
     judge: WEZ(ATA<12°∧500–3000ft)면 데미지   # engine/judge.py
```
즉 **우리 정책은 ②번 "어느 전술"만** 정한다. ③ guidance가 그 전술의 *목표값*을, ④ INDI가 *조종간*을,
judge가 *명중*을 처리 — **관심사 분리**(이게 설명가능성과 모듈성을 동시에 준다).

---

## 6. 왜 `.yaml`로는 못 쓰나 (적은 `.yaml`인데 우리는 왜 `.py`)

적 17종은 `.yaml` BT(Selector/Sequence/Condition/Action = *무상태 if-then*)다. 그런데 우리 최종 정책은
**`.yaml`로 표현 불가**하다. 세 가지 때문:

| 구성 | `.yaml` 불가 이유 |
|---|---|
| **base (AdaptivePolicy)** | **학습 RandomForest value 예측 + sigmoid 블렌딩** = *연속 계산*. `.yaml`의 이산 Condition(임계 비교)·Action(전술 매핑) 어휘로 표현 불가(`.pkl`을 읽어 argmax/블렌딩은 코드만 가능) |
| **A3 (phase 상태기계)** | **`self.ph` 상태 + 히스테리시스**. `.yaml` BT는 매 틱 *무상태 재평가* — 직전 phase 기억 못 함 |
| **D2 (시간 시퀀스)** | **`self.t` 경과시간 인덱싱**. `.yaml`엔 *시간 카운터·시퀀스 스텝* 개념 자체가 없음 |

> **요지:** 적은 *결정론 if-then*이라 `.yaml`로 충분, 우리는 **(1) 학습값 (2) 상태(phase) (3) 시간
> (시퀀스)** 세 가지를 써서 `.py` 필수.

**구조는 `.yaml`스럽게 *문서화*는 가능**(실행은 .py):
```yaml
# ⚠️ 실행 불가 — 읽기용 구조 스케치. base/phase/time 은 코드 노드.
name: IntelPolicy
tree:
  type: Selector
  children:
    - Seq[ BelowAltitude(2500) ]   → ClimbTo
    - Seq[ BehaviorType == D2 ]    → D2Sequence(t)        # ★코드(시간)
    - Seq[ BehaviorType == A3 ]    → A3PhaseMachine(dist) # ★코드(상태)
    - AdaptivePolicy(value, blend)                        # ★코드(학습)
```
`bt-editor`로 *그릴* 순 있어도(커스텀 노드), `yaml_bt` 인터프리터가 *실행*하진 못한다. **base만** 학습값을
하드 임계 if-then으로 *근사*하면 부분 `.yaml`화 가능(성능↓, LAB 1.2의 손작성 BT가 그 방향). A3/D2는 불가.

---

## 7. 블라인드 모드 — 행동 유형을 *어떻게* 분류하나 (`exp_e49`)

intel이 없을 때, `exp_e49_type_classifier.py`의 `TypeClassifierPolicy`가 **처음 50초간 적의 궤적 형상을
관측**해 행동 유형을 *분류*한다 — **적 BT가 아니라 *행동*을 보고**:
```python
self.rmin   = min(self.rmin, o.distance_ft)   # 최소거리
self.aa_min = min(self.aa_min, o.aa_deg)      # 최소 aspect(꼬리 얼마나 잡았나)
...
reopen = o.distance_ft - self.rmin            # 최접근 후 재이탈량
if self.aa_min > 30 and self.rmin > 3000:  typ = "D2"   # wide-orbit 회피자
elif reopen < 3000:                        typ = "A3"   # tight standoff lagger
else:                                      typ = "base"
```
- **D2형:** 넓은 orbit으로 꼬리를 안 내줌(`aa_min`↑, `rmin`↑).
- **A3형:** 붙었다가 크게 안 빠지는 tight standoff(`reopen`↓).
- 이 3특징으로 {A3,D2}가 나머지 15와 *거짓양성 0* 분리(exp_e48).

> 이게 §1의 핵심을 코드로 증명한다: **유형 분류는 *관측된 행동(궤적 형상)* 으로 한다 — 적의 정체/BT를
> 추측하는 게 아니다.** 단 blind는 분류에 시간이 걸려 D2의 t=0 위치 선점을 놓침(관측-행동 deadlock)
> → 16/17. 이는 D2가 운동학적으로 못 잡혀서가 아니라(oracle 17/17로 격파 증명) *제때 분류하지
> 못하는 정보한계*일 뿐이다(CANON §6).

---

## 8. 채점 모드 — realistic 16/17(충실) · 성능 17/17 · blind 16/17 · oracle 17/17

같은 정책을 여러 *채점 조건*으로 평가. 캐노니컬 설정은 both-INDI + 교범러더(0.2) + high-g ON + 300s
(CANON §4). 모두 env 플래그로 보존:

| 모드 | 실행 | 러더 | 결과 |
|---|---|---|---|
| **realistic** (충실) | `exp_e53_indi_both.py` (양측 INDI, `INDI_RUD_MAX_CRUISE=0.2`) | 교범(수동 최소) | **16/17** |
| **성능** | 기본 1.0 cap | **비교범 대형 수동 러더(nose-skid)** | **17/17** |
| **blind** (실전 배치) | realistic 기반, 적 정보 0 자가분류 | 교범 | **16/17** (D2만 무) |
| **oracle** (상한 벤치마크) | 유형 given | 교범 | **17/17** |

realistic 천장이 **16/17**인 것은 *조건부 high-g*(g-cap 4.8g→8.2g, 조준 중·에너지 충분일 때만)로 A3를
깼기 때문이다(15→16). 8.2g는 F-16 구조한계 9g 안이라 **충실**하다(비교범 nose-skid와 다름). yaw 물리도
충실(±30°·NASA Cndr·FLCS 자동조정). guidance heading은 SOTA-최적(`validation/guidance_vs_sota.py`).

realistic·blind의 잔여 1승(D2)은 *fidelity 결함이 아니다*: D2는 운동학적으로 격파 가능하며(deck-floor
수정 → **oracle 17/17**, CANON §6), blind에서 무승부인 것은 D2를 제때 유형 분류하지 못하는 *정보한계*
때문이다. 성능 17/17의 추가 승은 *비교범 대형 수동 러더*라는 여분 제어권한에서 온다.

> 상세: [17_findings](17_findings_prediction_and_fidelity.md) §17.5(g-cap)·§17.6(blind 정보한계)·
> §17.10(D2 격파).

---

## 9. 실행

```
cd new_match_engine/bt
python exp_e53_integrated_17.py blind      # 실전 기본: 16/17 (행동유형을 관측해 자가분류)
python exp_e53_indi_both.py                # realistic(충실) 16/17 (양측 INDI, 교범 러더, high-g)
python exp_e53_integrated_17.py            # oracle 상한: 17/17 (유형 주입) — 실전 아님
```

> 관련 문서: **LAB 2**(이긴 BT vs 17적 .yaml), **`guidance_vs_sota.py`**(guidance 최적성),
> **`START_HERE_combat.md`**(통합 실행기). 적 17 .yaml = `opponents/zoo/`.
