# 11 — 챔프 → core2 포트 정형 명세 (Formal Port Specification)

> **목적:** core-live 챔프(FullUnifiedPolicy, 42/42)를 core2에 **눈대중이 아니라 명세로** 이식한다.
> 명세를 interlingua(중간언어)로 두면, 번역은 "재작성"이 아니라 **명세-준수 검증(spec-conformance)**이 된다.
> 이 문서 = 이식의 **계약(contract)**. core2 BT는 이 명세를 구현하고, §4 프로토콜로 준수를 증명한다.
>
> **계보:** [[loop6-tree-translation-rationalization]](G6_FORMAL_SPEC.md, Layer B 트리 유리화) +
> [[loop15-d2-00-converted-empty-dive-gate]](empty-dive) + [[loop16-d2-05-headon-suppress-42of42]](deck-HEADON) 위에 최종층 완성.
> 규칙 정본: [[confirmed-competition-rule-wez]].

---

## 0. 핵심 발견 (왜 이식이 가능한가)

**joblib ML 트리가 분기하는 모든 변수가 순간관측의 순수함수다.** `situation_cost.py` 전체 감사 결과:

| 트리 입력 특징 | 정의 | 순간관측 함수? |
|---|---|---|
| `memberships` 5상황 | ata/aa/hca/es_diff의 sigmoid 곱 (`situation_cost.py:62`) | ✅ 순수 |
| `value`,`wez_margin`,`their_margin` | ata/dist/aa/es_diff 합성 (`:44,111,118`) | ✅ 순수 |
| `ata,aa,hca,dist,closure,es_diff,ego_alt,enm_alt,alt_gap` | 원시 기하 | ✅ 순수 |
| **`dive_run`** | 적 지속강하 누적초 (`DiveTracker`) | ❌ **유일한 상태특징** |

→ **트리의 결정 표면은 무상태**다("joblib은 임베드 불가" 장애물 소멸). 오직 스칼라 1개(`dive_run`=`r`)
+ 하류 래치(`c`)·FSM(`armed·kill`)만 상태 기구를 요구한다. **무상태 표면 = core2 조건으로 번역, 상태 = Commit/Cooldown + 신규 관측 2종.**

---

## 1. 챔프 = 3층 하이브리드 오토마톤 (정확 명세)

`full_unified_policy.py:46-97` + `d2_cost_unified_policy.py:55-70`의 **완전·정확** 형식화.

### 1.1 상수 (전부 물리 앵커 — 시계-대리 상수 0개)

```
DIVE_FPS = 80 fps      DIVE_HOLD = 1.5 s     AA_EXTEND = 50°
θ = 0.4                λ = 0.999             S_SHARP = 0.05
HARD_DECK = 1300 ft    WEZ_GUN = OS_DIST     (s_off 티어: OS_CLOS, RECV_CLOS, RECV_AA)
empty-dive pred: dalt<−30 fps · aa<35° · ata<90° · perch>150 ft · run_ed≥2.0 s
deck-suppress:   alt<4500 ft · dist<7000 ft
FSM:             alt<1300 · dist∈{3500,4500,3000,2000,12000} · ata<20 · aa∈{150,90}
```

### 1.2 상태 벡터 Z (매치 시작 시 리셋)

```
r       : dive-onset 클록 [0, DIVE_HOLD]   (Layer B, 누출-리셋)
c       : 지수감쇠 래치 [0, 1]              (Layer B, commit-blend)
run_ed  : empty-dive 클록 [0, ∞)           (Layer A, 하드-리셋)
armed   : 일방향 래치 (한번 true→불변)      (Layer A)
kill    : 히스테리시스 래치                  (Layer A: dist<3500 set, dist>12000 reset)
hist    : (alt, dist) 지연선 — lag-1틱·lag-1.0s만 참조
```

### 1.3 갱신·출력 (매 L1 틱, 실시간 dt)

**Layer C — 무상태 코어 트리** `T(O)` (증류 트리, 상황cost argmax의 근사):
```
b = clf.predict(featurize_s(O, dr=min(r, DIVE_HOLD)))          # 유일 상태입력 dr
  ── w_circ=σ((hca−90)/30), w_ext=σ((−clos−25)/30)·σ((ata−30)/20) 보정:
     w_circ>0.6 또는 w_ext>0.6 → (ata<30? GUN_TRACK : LEAD_TURN)  else b
```

**Layer B — 코어 dive 래치** X=(r,c), `d2_cost_unified_policy.py:55-70`:
```
climb_f = enm_vc·1.68781·sin(enm_theta)              # 적 수직속도 fps (−=강하)
r  ← r+dt   if climb_f < −DIVE_FPS
   ← 0      elif c ≤ θ                                 # 누출-리셋(채터 배제)
fire = (r ≥ DIVE_HOLD) ∧ (aa > AA_EXTEND)             # 지속강하 + 적 도주
c  ← 1  if fire  else  λ·c                            # 지수감쇠 래치
if alt < HARD_DECK: base = CLIMB                       # DECK 하드가드
else:
  gw   = σ((c − θ)/S_SHARP)                            # commit-blend 가중
  base = argmax_a [ gw·s_off(O)[a] + (1−gw)·1[a = T(O)] ]
       s_off 티어: GUN_TRACK 4.0(WEZ∧ata<20) · LAG 2.0 · HEADON 1.5 · SMART_DIVE 1.0
```

**Layer A — empty-dive FSM + deck-HEADON 억제** `full_unified_policy.py:51-97` (loop15/16 오버레이):
```
dalt = (alt − alt₋₁)/dt ;  dop = dist > dist₋₁.₀ₛ ;  perch = alt − enm_alt
pred = (dalt<−30) ∧ (aa<35) ∧ dop ∧ (ata<90) ∧ (perch>150)
run_ed ← run_ed+dt if pred else 0
if ¬armed ∧ run_ed≥2.0 ∧ climb_f<−DIVE_FPS:  armed ← true    # 물리 판별자(비시계)

if ¬armed:                                                    # ── 미발화 (canon 17 경로)
    if base=HEADON ∧ alt<4500 ∧ dist<7000:  OUT = PURE_PURSUIT    [mode=deck_suppress]
    else:                                    OUT = base            [mode=core]
else:                                                         # ── empty-dive FSM
    if alt<1300:                             OUT = CLIMB
    if ¬kill ∧ (dist<3500 ∨ (aa>150 ∧ dist<4500)):  kill ← true
    if kill ∧ dist>12000:                    kill ← false
    if ¬kill:                                OUT = BREAK_TURN      # 미끼(선회로 d 유계)
    elif dist<3000 ∧ ata<20:                 OUT = GUN_TRACK       # snap-kill
    elif aa<90 ∧ dist>2000:                  OUT = SMART_DIVE
    else:                                    OUT = LEAD_TURN
```

**불변식(정본 보존):** canon 17종은 `run_ed≥2` 도달해도 그 순간 `climb_f≥−34.5`(적 수평)→`armed`
영구 false → Layer A가 항상 `base` 통과 → **D2CostUnifiedPolicy와 틱-완전동일**. Layer A는 held-out 2종만
전환하는 직교 오버레이. **이 불변식이 core2 번역의 1차 준수 기준(§4).**

---

## 2. 알파벳 → core2 인터페이스 (3개 번역 사전)

### 2.1 가드(술어) 사전 — core2 12관측 대조

| 명세 술어 | 변수 | core2 표현 | 상태 |
|---|---|---|---|
| `ata<X` (20/30/35/90) | ata_deg | `nose_far`/`in_gun_envelope` param, `ata_deg` | ✅ |
| `aa>X` / `aa<X` (35/50/90/150) | aa_deg | `foe_threat`/`is_defensive` (aspect_deg) | ✅ 부호정합(고=위협) — **영점 캘리브레이션 검증** |
| `dist<X` / `dop` | dist | `range_ft`, `closing`/`foe_extending` | ✅ / ⚠ dop=1.0s창 |
| `hca` (memberships/보정) | hca_deg | `hca_deg`, `one_circle` | ✅ |
| `closure<X` (s_off/보정) | closure_kts | `closure_fps` | ✅ **단위 ×1.68781 변환** |
| `es_diff`/`value`/margins | 합성 | `energy_diff_ft` + 파생 조건 | ✅ (경계 crisp 근사) |
| `perch>150` | alt−enm_alt | `alt_gap_ft < −150` (perch=−alt_gap) | ✅ |
| `alt<X` (1300/4500) | alt_ft | `low_altitude` param, `alt_ft` | ✅ |
| `base=HEADON` | Layer B 출력 | **`is_head_on` + 저고도·근접 재유도** | ⚠ 코어출력 재구성 |
| `climb_f<−DIVE_FPS` | 적 수직속도 | **`foe_climb_fps` (신규)** | ❌ **관측 GAP-1** |
| `dalt<−30` | 자기 수직속도 | **`self_climb_fps` (신규) 또는 Commit 스냅** | ❌ **관측 GAP-2** |
| `r`,`c`,`run_ed`,`armed`,`kill` | 상태 | Commit/Cooldown (§2.3) | ⚠ 상태기구 |

### 2.2 출력(기동) 사전 — 방출 tactic → core2 7-필드 `(pursuit, max_g, aim_above_ft, lead_time_s, lag_dist_ft, mode, name)`

챔프가 실제 방출하는 집합 = base_tactic 출력 ∪ {PURE, CLIMB, BREAK_TURN, GUN_TRACK, SMART_DIVE, LEAD_TURN}:

| tactic | core2 7-필드 매핑 | 상태 |
|---|---|---|
| PURE_PURSUIT | pursuit=pure, mode=control_zone | ✅ |
| LEAD_PURSUIT/LEAD_TURN | pursuit=lead, lead_time_s>0 | ✅ |
| LAG_PURSUIT | pursuit=lag, lag_dist_ft>0 | ✅ |
| GUN_TRACK | pursuit=lead, mode=stable(포인팅), max_g↑, lead_time↓ | ✅ |
| HEADON | pursuit=pure, mode=control_zone (챔프는 덱서 억제) | ✅ |
| CLIMB | aim_above_ft≫0, 저속 | ✅ |
| BREAK_TURN | max_g=max, pursuit=lag(방어) | ✅ |
| HIGH_YOYO (yoyo=False라 미방출) | aim_above_ft>0 | ✅ (미사용) |
| **SMART_DIVE** | pursuit=pure/lead, aim_above_ft≪0, mode=control_zone, **+ V_MAX=540 sprint** | ⚠ **속도상한 노브 GAP** |

**GAP-3 (SMART_DIVE sprint):** `_apply_vmax`가 SMART_DIVE 시 V_MAX_KTS→540으로 올려 덱-추격 속도를 확보.
core2는 속도상한이 공통 L3 소관 → 7-필드로 못 올린다. **덱-추격 격추(D2)의 충실도 위험.** 단 확정규칙
(30°원뿔·거리무관·2×격추)선 540kt 덱-추격이 불필요할 수 있음 → §4 재검증에서 실측 판단.

### 2.3 상태 사전 — Z → core2 Commit/Cooldown (`node.py`)

| 상태 | 성격 | core2 인코딩 | 충실도 |
|---|---|---|---|
| `armed` | 일방향 래치(불변) | Commit(duration≈매치전체) 첫 발화후 유지 | ✅ 높음 |
| `kill` | 히스테리시스(set/reset 상이경계) | Commit(set) + Cooldown(reset) | ✅ 근사 |
| `c` | 지수감쇠 λ=0.999 | Commit(duration≈92s; λⁿ=θ ⟹ n≈916틱) + SUCCESS 재래치 | ⚠ gw 소프트→crisp 경계손실 |
| **`r`, `run_ed`** | **카운트-업 클록(N초 지속)** | Commit은 순간-SUCCESS 래치 → 지속누적 직접표현 X | ❌ **DSL 표현한계** |

**핵심 상태-표현 발견:** core2 Commit/Cooldown은 **일방향·히스테리시스 래치는 잘, 카운트-업 "N초 지속"
클록은 불완전하게** 표현한다. 챔프의 arm 게이트(`r≥DIVE_HOLD`, `run_ed≥2.0`)가 정확히 카운트-업 클록이다.
이것이 **이식의 최대 난점** — 해법 후보 §3.

---

## 3. 번역 계획 (명세 → core2 YAML BT)

### 3.1 필요 확장 (core2 공통층 — 승인 필요)

1. **`foe_climb_fps` 관측 추가** (GAP-1): 적 수직속도. `context.py` TacticContext에 필드 1개.
   §6 정보정책 정합(적 HP 아님, 순수 기하 추정량). Layer B 래치 + Layer A arm 양쪽이 소비.
2. **`self_climb_fps` 관측 추가** (GAP-2): 자기 수직속도. 비행층이 이미 앎 → 노출만. `foe_climb_fps`와 대칭.
3. **카운트-업 클록** (GAP, §2.3): 세 선택지 —
   (a) 조건 `foe_climb_fps<−DIVE_FPS`를 자식으로 둔 **Commit(1.5s) 지속-근사** (충실도 손실 측정),
   (b) `dive_dwell_s` 파생관측 1개 추가(비행층 누적, arm 게이트 정확 표현),
   (c) DSL에 `sustain` 노드 신설 — **커스텀노드 금지(dsl.py)라 기각.**
   → **권장 (b)**: 관측 1개가 Commit-근사보다 명세-충실. GAP-1과 합쳐 신규관측 총 2~3개.

### 3.2 트리 라우팅 (커스텀노드 없이)

`decide()`의 `mode ∈ {core, deck_suppress, empty_dive}` 3분기를 core2 **selector** 최상위로:
```
selector:
  - sequence: [condition:armed(Commit), <empty-dive FSM subtree>]        # armed 래치
  - sequence: [condition:is_head_on+low_alt+close, action:PURE_PURSUIT]   # deck_suppress
  - <core cost-tree>                                                      # Layer B+C 유리화(tier-C)
```
core cost-tree = G6 Layer B의 36분기 물리앵커 트리를 core2 18조건으로 재작성(경계 crisp 근사).

### 3.3 유의점 (틱레이트 결합 해소)

- core-live bt=10Hz(dt=0.1 하드코딩), **core2 L1=20Hz(dt=0.05)**. `r+=0.1`·`hist[-10]`(1.0s창)은
  **틱레이트 결합** → core2선 반드시 **실시간(초)**으로 재표현(`ctx.dt_s` 누적, 1.0s=20틱). policy.py의
  self-accumulated 클록이 이를 지원.
- 단위: closure kts↔fps, 각도 부호 영점(aa/aspect_deg) 캘리브레이션 필수(§2.1).

---

## 4. 명세-준수 검증 프로토콜 (2단계 게이트)

**게이트 1 — 틱-동일 불변식(§1.3):** core2 BT가 canon 17종서 `armed` 영구 false 유지 →
core 경로만 통과 → core2 코스트트리가 D2CostUnified와 **동일 tactic 시퀀스**(틱-동일 0/N) 산출하는지.
실패 시 = 트리 crisp-근사 경계 손실 위치 특정(tier-P 회귀와 동류, 절제로 회복).

**게이트 2 — 확정규칙 42전 재검증:** core2 엔진(DPS 25→50 동기화 후), both-INDI **300s**로 canon 17 +
held-out 25. **42/42 가정 금지** — 확정 WEZ(30°원뿔·거리무관·2×격추)는 다른 게임 → 승/무/패 실측.
replay(ACMI+plot+csv) 필수([[feedback-replays-mandatory]]).

**성공 정의:** 게이트1 틱-동일(코어 충실) + 게이트2 무패(≥판정승, R<0.2 불패선). 게이트2서 무/패 발생 시 =
확정규칙 고유(챔프가 12°게임 과적합) → [[metrics-before-tactics]]로 지표 진단 후 재국지화.

## 관련
[[core2-function-map-and-improvement]] · [[core2-comparison-structure]] · [[confirmed-competition-rule-wez]] ·
[[loop6-tree-translation-rationalization]] · [[loop15-d2-00-converted-empty-dive-gate]] ·
[[loop16-d2-05-headon-suppress-42of42]] · [[formal-advantage-event-laws]] · [[metrics-before-tactics]]
