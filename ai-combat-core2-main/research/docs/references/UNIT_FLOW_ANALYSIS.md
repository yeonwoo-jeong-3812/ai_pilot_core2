# 단위(Unit) 흐름 — 제로베이스 분석 문서

작성일: 2026-05-28
최종 갱신: 2026-05-28 (P0/P1/P2/P3 권장 수정 적용 완료)
대상 시스템: ai-combat-core (JSBSim ↔ LAG obs ↔ Blackboard ↔ BT 노드 ↔ RNN low-level policy)
목적: 워크스페이스의 모든 수치들이 출처(JSBSim Property)에서부터 BT 노드 파라미터/조건/액션까지 일관된 단위로 변환되는지를 검증하고, 발견된 불일치/버그를 정리한다.

## 적용 상태 요약 (2026-05-28)

| 우선순위 | 항목 | 상태 | 검증 |
|---|---|---|---|
| **P0** | `combat_geometry.energy_state` 좌표계 가정 오류 (NEU vs NED) | **적용 완료** | `test/test_unit_flow.py` (3건) 통과 |
| **P1** | `aa_deg` 표준 BFM 정의로 통일 + `UnderThreat` 임계 의미 반전 (기본 60°→120°) + `EnemyLOSAngle` 매핑 + `opponent_classifier`/`counter_strategy_builder` 단위 보정 | **적용 완료** | `test/test_unit_flow.py` (5건) + `test/test_combat_geometry.py` 통과 |
| **P2** | README `BelowHardDeck` 임계값 3281→1000 ft, "Hard Deck 위반 < 1640ft"→"< 1,000 ft" | **적용 완료** | judge.py `HARD_DECK_M`=1,000 ft와 일치 |
| **P3** | `ego_vx/vy/vz_kts` → `ego_vbody_x/y/z_kts` rename, `delta_vx_kts` → `delta_vbody_x_kts`, `delta_altitude_ft` 제거 (alt_gap_ft로 통일) | **적용 완료** | 외부 참조 없음 확인 후 rename |

> **참고**: 사용자 결정에 따라 P1은 **옵션 A(표준 BFM 정의로 통일)**를 채택. SDK 사용자의 BT YAML이 `aa_deg`/`UnderThreat` 의미에 의존하는 경우 호환성 영향이 있으나, README 및 sdk/README가 이미 표준 의미로 작성되어 있어 문서/코드 정합성이 회복되었다.

> **후속 검증 (2026-05-28)**: 회귀 단위 테스트 16건 통과, 신규 `redteams/red1~5.yaml` 5종 모두 `load_behavior_tree()`로 정상 빌드, 베이스라인 매치 (red1 vs red3 / red5 vs red4) 2판 시뮬레이션에서 예외/안전 위반 없음. 상세 절차는 §6.4 참조.

---

## 1. 전체 데이터 파이프라인

```
JSBSim Property (raw)
  ├─ position_h_sl_m              : m
  ├─ attitude_(roll|pitch|heading)_rad : rad
  ├─ velocities_v_(north|east|down)_mps : m/s   (NED 속도)
  ├─ velocities_(u|v|w)_mps       : m/s         (Body 속도)
  ├─ velocities_vc_mps            : m/s         (CAS)
  ├─ velocities_p_rad_sec         : rad/s       (Roll rate)
  └─ accelerations_n_pilot_*_norm : G
        │
        ▼
┌─ LAG get_obs (정규화 15차원, observation_space [-10, 10]) ────┐
│  obs[0]  altitude_m / 5000           (5 km 단위)               │
│  obs[1..4] sin/cos(roll, pitch)      (rad 분해)                │
│  obs[5..8] body_vel_mps / 340        (마하 단위, 340 m/s)      │
│  obs[9]  Δv_body_mps / 340                                     │
│  obs[10] Δalt_m / 1000               (km 단위, 양수=적이 위)   │
│  obs[11] ego_AO                      (rad, [0, π])             │
│  obs[12] ego_TA                      (rad, [0, π])             │
│  obs[13] R_m / 10000                 (10 km 단위)              │
│  obs[14] side_flag                   (-1, 0, +1; sign of cross)│
└────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─ BehaviorTreeTask._update_blackboard (항공 단위로 환원) ──────┐
│  obs[0]*5000  → meters_to_feet → ego_altitude_ft / altitude_ft │
│  obs[5..8]*340 → ms_to_knots   → ego_v(x|y|z|c)_kts            │
│  obs[10]*1000 → meters_to_feet → delta_altitude_ft             │
│  obs[11], obs[12]              → ego_AO_rad, ego_TA_rad        │
│  obs[13]*10000 → meters_to_feet → distance_ft                  │
│  obs[14]                       → side_flag                     │
│                                                                 │
│  + CombatGeometry(p_a, p_t, v_a, v_t, roll)                    │
│    ├─ 입력 단위: NEU 좌표 (m), NED 속도 (m/s), roll (rad)     │
│    └─ 출력: ata_deg, aa_deg, hca_deg, tau_deg,                 │
│            relative_bearing_deg, alt_gap_ft,                   │
│            closure_rate_kts, turn_rate_degs, energy_diff_ft   │
└────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─ Blackboard (BT 노드들이 읽는 '항공 단위' 표면) ──────────────┐
│  observation: {*_ft, *_kts, *_deg, *_rad}                      │
│  글로벌 키 (`/`-prefix): /Distance_ft, /Speed_kts,             │
│    /CurrentRoll_deg, /CurrentPitch_deg, /ClosureRate_kts,     │
│    /TurnRate_degs, /EnergyDiff_ft, /MyLOSAngle, ...           │
└────────────────────────────────────────────────────────────────┘
        │
        ▼
BT Action 노드 → set_action([alt_idx 0..4, head_idx 0..8, vel_idx 0..4])
        │ (BaseAction.set_action: ego_vc_kts 기준 속도 거버너 적용)
        ▼
HierarchicalSingleCombatTask.normalize_action
  └→ low-level RNN (5 Hz, ZOH cache) → [aileron, elevator, rudder, throttle]
        │
        ▼
JSBSim FCS 입력
  ├─ fcs_aileron_cmd_norm  ∈ [-1, 1]
  ├─ fcs_elevator_cmd_norm ∈ [-1, 1]
  ├─ fcs_rudder_cmd_norm   ∈ [-1, 1]
  └─ fcs_throttle_cmd_norm ∈ [0.4, 0.9]
```

---

## 2. 단위 시스템 정의 — 코드베이스 컨벤션

### 2.1 BT 표면 단위 (Blackboard / 노드 파라미터)

| 차원 | 단위 | 접미사 | 출처 모듈 |
|------|------|--------|-----------|
| 거리 | feet (ft) | `_ft` | [src/utils/units.py](../src/utils/units.py) |
| 고도 | feet (ft) | `_ft` | 동일 |
| 속도 | knots (kts) | `_kts` | 동일 |
| 접근 속도 | knots (kts) | `_kts` | 동일 |
| 각도 | degrees | `_deg` | [src/control/combat_geometry.py](../src/control/combat_geometry.py) |
| 각속도 | deg/s | `_degs` | 동일 |
| 에너지(He) | feet | `_ft` | [src/behavior_tree/task.py](../src/behavior_tree/task.py) |
| 라디안 (예외: ego_AO/ego_TA) | rad | `_rad` | LAG obs[11], obs[12] |

### 2.2 변환 상수

| 상수 | 값 | 정의 위치 |
|------|----|-----------|
| `M_TO_FT` | 3.28084 | [src/utils/units.py:14](../src/utils/units.py#L14) |
| `MS_TO_KNOT` | 1.94384 | [src/utils/units.py:22](../src/utils/units.py#L22) |
| `KNOT_TO_FT_S` | 1.68781 | [src/utils/units.py:24](../src/utils/units.py#L24) |
| `HARD_DECK_M` | `feet_to_meters(1000)` = 304.8 | [src/utils/units.py:163](../src/utils/units.py#L163) |
| `WEZ_MIN_RANGE_M` | 152.4 (= 500 ft) | [src/utils/units.py:164](../src/utils/units.py#L164) |
| `WEZ_MAX_RANGE_M` | 914.4 (= 3,000 ft) | [src/utils/units.py:165](../src/utils/units.py#L165) |
| `WEZ_MAX_ANGLE_DEG` | 12.0 | [src/utils/units.py:166](../src/utils/units.py#L166) |
| LAG 정규화: altitude | / 5000 (5 km) | [singlecombat_task.py:114](../src/simulation/envs/JSBSim/tasks/singlecombat_task.py#L114) |
| LAG 정규화: velocity | / 340 (마하 1) | [singlecombat_task.py:119-122](../src/simulation/envs/JSBSim/tasks/singlecombat_task.py#L119-L122) |
| LAG 정규화: Δaltitude | / 1000 (1 km) | [singlecombat_task.py:126](../src/simulation/envs/JSBSim/tasks/singlecombat_task.py#L126) |
| LAG 정규화: range | / 10000 (10 km) | [singlecombat_task.py:129](../src/simulation/envs/JSBSim/tasks/singlecombat_task.py#L129) |

---

## 3. 단위 변환 검증 — 정상 동작 영역

| # | 변환 단계 | 코드 위치 | 검증 결과 |
|---|-----------|-----------|-----------|
| 1 | JSBSim → LAG obs 정규화 | [singlecombat_task.py:81-132](../src/simulation/envs/JSBSim/tasks/singlecombat_task.py#L81-L132) | OK |
| 2 | obs[0]*5000 → meters → feet | [task.py:135-137](../src/behavior_tree/task.py#L135-L137) | OK |
| 3 | obs[5..8]*340 → m/s → knots | [task.py:190-193](../src/behavior_tree/task.py#L190-L193) | OK (단, body frame 표기 모호 → §6) |
| 4 | obs[13]*10000 → meters → feet | [task.py:179-180](../src/behavior_tree/task.py#L179-L180) | OK |
| 5 | ATA / HCA deg 계산 (acos 후 *180/π) | [combat_geometry.py:86-101,145-158](../src/control/combat_geometry.py#L86-L158) | OK |
| 6 | Closure Rate m/s → kts (ms_to_knots) | [task.py:261](../src/behavior_tree/task.py#L261) | OK |
| 7 | Hard Deck 임계 (1,000 ft = 304.8 m) | [units.py:163](../src/utils/units.py#L163) ↔ [judge.py:91-92](../src/match/judge.py#L91-L92) | OK |
| 8 | Specific Energy (He) ft 단위 (g_ft=32.174) | [task.py:140-144](../src/behavior_tree/task.py#L140-L144) | OK |
| 9 | Ps (Specific Excess Power) ft/s 차분 | [task.py:146-162](../src/behavior_tree/task.py#L146-L162) | OK |
| 10 | FlightSafetyMonitor (G, rad/s, kts) | [flight_safety_monitor.py:31-95](../src/control/flight_safety_monitor.py#L31-L95) | OK |
| 11 | TimedAction tick rate 자동 환산 (5→10 Hz) | [actions.py:139-162](../src/behavior_tree/nodes/actions.py#L139-L162) | OK |
| 12 | BT 파라미터 접미사 규약 (`*_ft`, `*_kts`, `*_deg`) | [conditions.py](../src/behavior_tree/nodes/conditions.py), [actions.py](../src/behavior_tree/nodes/actions.py) | OK |
| 13 | side_flag 부호 (양수=적이 오른쪽) | [utils.py:101](../src/simulation/envs/JSBSim/utils/utils.py#L101) → [task.py:220-222](../src/behavior_tree/task.py#L220-L222) | OK |
| 14 | WEZ 거리/각도 (500–3,000 ft, ±12°) | [health_manager.py:21-23](../src/control/health_manager.py#L21-L23) | OK |
| 15 | turn_rate (rad/s → deg/s) | [combat_geometry.py:198-228](../src/control/combat_geometry.py#L198-L228) | OK |
| 16 | alt_gap (NEU 컨벤션, 양수=적이 위) | [combat_geometry.py:322-331](../src/control/combat_geometry.py#L322-L331) | OK |

---

## 4. 발견된 불일치 / 버그

### 4.1 [P0 / 치명] `energy_state` 좌표계 가정 오류 — 부호 반전 버그

#### 근본 원인

[src/simulation/envs/JSBSim/utils/utils.py:29-40](../src/simulation/envs/JSBSim/utils/utils.py#L29-L40)의 `LLA2NEU`는 이름 그대로 **NEU(North-East-Up)**를 반환하므로, `p_a[2]`는 **위로 갈수록 양수**.

```python
def LLA2NEU(lon, lat, alt, lon0=120.0, lat0=60.0, alt0=0):
    """Convert from Geodetic Coordinate System to NEU Coordinate System.
    Returns:
        (np.array): (North, East, Up), unit: m
    """
    n, e, d = pymap3d.geodetic2ned(lat, lon, alt, lat0, lon0, alt0)
    return np.array([n, e, -d])
```

그러나 `CombatGeometry.energy_state()`는 NED(Down 양수)로 잘못 가정:

```python
# src/control/combat_geometry.py:260-263
g = 9.80665
# NED frame: Down이 양수 → 고도 = -p[2]
my_alt = -self.p_a[2]
tgt_alt = -self.p_t[2]
```

#### 영향 분석

LLA2NEU에서 `p_a[2] = +h_a` (양수 고도)이므로 `my_alt = -h_a` (음수).

| 변수 | 코드 결과 | 의도된 의미 | 부호 |
|---|---|---|---|
| `my_alt` | `-h_a` (음수) | `+h_a` | 반전 |
| `alt_advantage = my_alt > tgt_alt` | `-h_a > -h_t` ⟺ `h_a < h_t` | `h_a > h_t` | **정반대** |
| `energy_diff` (고도 성분) | `+(h_t - h_a)` | `+(h_a - h_t)` | **정반대** |
| `energy_advantage` | 적이 더 높을 때 True | 아군이 더 높을 때 True | **정반대** |

`spd_advantage`는 속도 크기 비교라 좌표계 무관 → 영향 없음.

#### 파급 범위

[src/behavior_tree/task.py:286-299](../src/behavior_tree/task.py#L286-L299)에서 BB로 노출되는 키들이 모두 정반대 부호로 동작:

- 조건 노드:
  - `IsEnergyAdvantage` ([conditions.py:838-857](../src/behavior_tree/nodes/conditions.py#L838-L857))
  - `IsAltAdvantage` ([conditions.py:860-875](../src/behavior_tree/nodes/conditions.py#L860-L875))
  - `EnergyDiffAbove` ([conditions.py:1026-1046](../src/behavior_tree/nodes/conditions.py#L1026-L1046))
  - `EnergyHigh` ([conditions.py:412-428](../src/behavior_tree/nodes/conditions.py#L412-L428))
  - `HasSuperior`, `NotSuperior` ([conditions.py:450-485](../src/behavior_tree/nodes/conditions.py#L450-L485))

- 액션 노드:
  - `EnergyFight` ([actions.py:1404-1469](../src/behavior_tree/nodes/actions.py#L1404-L1469))
  - `TCFight`의 `energy_advantage` 분기 ([actions.py:1490,1524-1529](../src/behavior_tree/nodes/actions.py#L1490))

#### 권장 수정 (2줄)

```python
# src/control/combat_geometry.py:261-263
# Before:
# NED frame: Down이 양수 → 고도 = -p[2]
my_alt = -self.p_a[2]
tgt_alt = -self.p_t[2]

# After:
# LLA2NEU 출력은 NEU (Up 양수), 고도 = +p[2]
my_alt = self.p_a[2]
tgt_alt = self.p_t[2]
```

> 참고: 같은 클래스의 `alt_gap()` ([combat_geometry.py:322-331](../src/control/combat_geometry.py#L322-L331))은 NEU 가정으로 작성되어 이미 올바름. 클래스 내에서도 두 함수의 좌표계 가정이 충돌하고 있어 이 수정으로 일관성이 회복된다.

---

### 4.2 [P1 / 의미적 충돌] `aa_deg` 정의가 표준 BFM 교범과 반대

#### 코드 정의

[src/control/combat_geometry.py:125-143](../src/control/combat_geometry.py#L125-L143):

```python
def aa_deg(self) -> float:
    """AA (Aspect Angle) - 목표물의 꼬리에서 공격자까지 측정한 각도 (deg)
    
    교범 기준 정의 (Figure 4.1, Geometric Relationships):
        ...
    """
    # 표준 공식: acos(dot(-v_a, rho_a))
    # -v_a = 아군 꼬리 방향, rho_a = 아군→적 LOS
    neg_v_a = [-self.v_a[0], -self.v_a[1], -self.v_a[2]]
    aa = math.acos(...)
```

이 공식은 **"적이 아군의 꼬리 방향에 있는 정도"** = 사실상 `180° - ATA`.

#### README 정의 (정반대)

[README.md:517-519](../README.md#L517-L519):

```
0°   → 내가 적의 정후방(6시) — 가장 유리한 공격 위치
90°  → 내가 적의 측면(3/9시)
180° → 내가 적의 정면(12시) — 적이 나를 조준 중, 가장 위험
```

→ README는 **표준 BFM 정의** (target's tail vs target→attacker LOS).

표준 공식:

```python
neg_v_t = [-self.v_t[0], -self.v_t[1], -self.v_t[2]]   # 적의 꼬리 방향
neg_rho = [-self.rho_a[0], -self.rho_a[1], -self.rho_a[2]]  # 적→아군 LOS
aa = math.acos(dot(neg_v_t, neg_rho) / ...)
```

#### 영향 분석

| 노드 | 코드 의미로 동작 | 표준 의미로 가정 시 |
|------|------------------|---------------------|
| `UnderThreat(aa < 60)` | "적이 내 꼬리 60° 이내" → 위협 (의미 일치) | "내가 적 꼬리 60° 이내" → 공격 유리 (반대) |
| `BFMClassifier.is_offensive (ata<45 ∧ aa<100)` | "적 정면조준 + 적이 내 꼬리 100° 이내" → 의미상 모순 | "적 정면조준 + 내가 적 꼬리 100° 이내" → 표준 OBFM |
| `BFMClassifier.is_defensive (aa > 90 ∧ ata > 60)` | "적이 내 전방 + 내 측면" → 부정합 | "내가 적 전방 노출 + 적이 내 측면" → 표준 DBFM |

#### 결론

- `UnderThreat`는 코드 의미와 일관 (정상 동작)
- `BFMClassifier`의 OBFM/DBFM 임계값은 표준 의미를 가정한 채 작성되어 있어 **실제 동작이 의도와 어긋남**
- OBFM 판정이 의도보다 좁아지고 DBFM이 잘못 트리거될 수 있음

#### 권장 수정 (택1)

**옵션 A — 표준 정의로 통일 (안전)**:
- `aa_deg()` 공식을 표준으로 교체 (위 표준 공식 적용)
- `UnderThreat` 임계값을 `aa > 120°`로 의미 반전

**옵션 B — 현 코드 의미 유지**:
- README의 AA 설명을 코드 의미에 맞게 갱신
- BFMClassifier 임계값을 코드 의미에 맞춰 재작성

옵션 A가 외부 학습 자료(교범, 논문)와의 일관성을 유지하므로 권장.

---

### 4.3 [P2 / 문서 vs 코드 불일치] BelowHardDeck 임계값 혼재

[README.md:243](../README.md#L243):
```
- BelowHardDeck(threshold=3281): Hard Deck 위반 위험 (고도 < 임계값, ft)
```

실제 코드:

```python
# src/behavior_tree/nodes/conditions.py:303-305
def __init__(self, name: str = "BelowHardDeck", threshold_ft: float = 1000):
    super().__init__(name)
    self.threshold = threshold_ft  # ft (기본값: 1000ft, 경기 규칙 기준)
```

판정 기준:
```python
# src/utils/units.py:163
HARD_DECK_M = feet_to_meters(1000)      # 1,000 ft
```

**문제**: README 본문에 1,000 / 1,640 / 3,281 ft 3가지 수치가 혼재. 참가자가 README 예시(3,281 ft)만 보고 BT를 작성하면 실제 판정 기준(1,000 ft)을 인지하지 못해 즉시 실격당할 수 있음.

#### 권장 수정

- README의 `threshold=3281` → `threshold=1000`으로 정정
- 다른 임계값 예시(`IsMerged`, `EnergyDiffAbove` 등)도 코드 기본값과 일치하는지 일괄 점검

---

### 4.4 [P3 / 가독성] body 속도 vs NED 속도 변수명 모호

[src/behavior_tree/task.py:190-193](../src/behavior_tree/task.py#L190-L193):

```python
"ego_vx_kts": ms_to_knots(obs[5] * 340),
"ego_vy_kts": ms_to_knots(obs[6] * 340),
"ego_vz_kts": ms_to_knots(obs[7] * 340),
"ego_vc_kts": ego_vc_kts,
```

`obs[5..7]`는 LAG `state_var[9..11]` = `velocities_(u|v|w)_mps` = **body frame 속도**. 그러나 변수명 `ego_vx_kts`는 NED 또는 world frame을 연상시킴.

NED 속도(`velocities_v_(north|east|down)_mps`)는 별도 경로 `ego_obs_raw[6:9]`로 CombatGeometry에만 전달되며 BB에는 노출되지 않음.

#### 권장 수정

- 키 이름을 `ego_vbody_x_kts` 등으로 명시화
- 또는 NED 속도(`ego_vn_kts`, `ego_ve_kts`, `ego_vd_kts`)를 추가로 BB에 노출

---

### 4.5 [P3 / 중복] `delta_altitude_ft` ↔ `alt_gap_ft` 두 변수의 동시 존재

같은 의미("적 고도 - 아군 고도, 양수=적이 위")의 두 변수가 BB observation에 모두 존재 ([task.py:195](../src/behavior_tree/task.py#L195), [task.py:253](../src/behavior_tree/task.py#L253)).

| 변수 | 산출 경로 | 좌표계 | 정밀도 |
|------|-----------|--------|--------|
| `delta_altitude_ft` | LAG obs[10] (정규화 디노말) | LAG 내부 | clip(-10, 10) 영향 받음 |
| `alt_gap_ft` | `CombatGeometry.alt_gap` (NEU) | LLA2NEU | 직접 계산, clip 없음 |

부호 컨벤션은 동일하지만, 두 산출 경로가 별개여서 향후 리팩터링 시 한쪽만 변경하면 의미 분기가 발생할 위험.

코드베이스 내 액션 노드는 거의 모두 `alt_gap_ft`만 사용 중.

#### 권장 수정

- `delta_altitude_ft`를 `alt_gap_ft`의 별칭으로 통합하거나 deprecate

---

## 5. 우선순위별 권장 조치

| 우선순위 | 항목 | 영향 | 수정 비용 |
|----------|------|------|-----------|
| **P0** | `combat_geometry.py:262-263` 부호 반전 버그 | BFM 우위 판정 전체가 반대 — 매치 결과 왜곡 | 2줄 수정 |
| **P1** | `aa_deg` 정의와 BFMClassifier 임계값 일관성 | OBFM/DBFM 트리거가 의도와 어긋남 | 표준 정의 적용 + UnderThreat 임계 조정 |
| **P2** | README BelowHardDeck 임계값 1000/1640/3281 ft 혼재 | 참가자 BT 즉시 실격 가능 | README 일괄 정정 |
| **P3** | `ego_vx_kts` 명명, `delta_altitude_ft` 중복 | 노드 작성자 오해 | 별칭/리네임 |

---

## 6. 회귀 검증 방법

P0/P1 수정 시 동작이 정반대로 바뀌므로, 베이스라인 매치 회귀 테스트로 영향 범위를 확인할 것.

### 6.1 P0 수정 검증

```bash
# 수정 전후 동일 시드에서 매치 실행
python scripts/run_match.py --agent1 eagle1 --agent2 simple --log-csv
python scripts/run_match.py --agent1 viper1 --agent2 eagle1 --log-csv
python scripts/run_match.py --agent1 ace --agent2 aggressive --log-csv
```

확인 포인트:
- `EnergyFight` 진입 빈도 변화
- `IsAltAdvantage` 트리거 시점이 실제 고도 우위와 일치하는지
- 매치 결과(승자/체력 분포)의 회귀 영향

### 6.2 P1 수정 검증

```bash
# BFM 분류 분포가 매치 진행 중 합리적으로 변하는지 확인
python scripts/audit_match.py --replay <ACMI_FILE>
```

확인 포인트:
- OBFM/DBFM/HABFM 비율의 시간적 변화
- ATA가 작을 때 OBFM이 트리거되는지 (정상)
- 적이 후방에서 추격 중일 때 DBFM이 트리거되는지 (정상)

### 6.3 단위 변환 단위 테스트 신설 (권장)

`test/test_unit_flow.py`를 새로 만들어 다음을 검증:
- LLA2NEU 출력이 Up 양수임을 단위 테스트로 고정
- `CombatGeometry.alt_gap`의 부호 (적이 위 → 양수)
- `CombatGeometry.energy_state`의 alt_advantage (아군이 위 → True)
- LAG obs 정규화 → BB ft/kts 환원의 round-trip 정확도 (오차 < 1%)

### 6.4 후속 검증 결과 (2026-05-28)

P0/P1/P2/P3 수정과 신규 redteams BT가 모두 정상 동작함을 다음 절차로 확인했다.

#### (a) 회귀 단위 테스트

```bash
.venv\Scripts\activate
python -m pytest test/test_unit_flow.py test/test_combat_geometry.py -v
# 결과: 16 passed (4.24s)
```

| 파일 | 검증 항목 | 통과 |
|------|-----------|------|
| `test/test_unit_flow.py` | LLA2NEU Up 양수, `alt_gap` 부호, `energy_state` alt_advantage, 표준 `aa_deg` 0/90/180°, `UnderThreat` 임계 120° | 11/11 |
| `test/test_combat_geometry.py` | basic geometry, head-on, tail chase, roll effect, altitude difference | 5/5 |

#### (b) redteams BT YAML 로드 검증

새로 생성된 5종 BT(red1~red5)를 `load_behavior_tree()`로 빌드해 노드 클래스/파라미터명 일치를 확인:

| 파일 | 노드 수 | 사용 단위 키워드 | 결과 |
|------|---------|------------------|------|
| `redteams/red1.yaml` | 8 | `threshold_ft: 1200`, `min_velocity_kts: 500` | OK |
| `redteams/red2.yaml` | 14 | `threshold_ft: {1200, 16404}`, `min_velocity_kts: {210, 260}` | OK |
| `redteams/red3.yaml` | 5 | `threshold_ft: 1200` | OK |
| `redteams/red4.yaml` | 17 | `aa_threshold_deg: 120.0`, `max_altitude_ft: 6562`, `target_advantage_ft: 1640` | OK |
| `redteams/red5.yaml` | 36 | `threshold_ft: {152, 624, 914, 4000, 6562, 8202, 13123, 16404}`, `threshold_deg: 4.4`, `max_distance_ft: 624.0`, `max_los_angle_deg: 12.0` | OK |

전 YAML이 새 표준 (P2: `BelowHardDeck` 1000 ft 이상, P1: `UnderThreat` 임계 120°) 을 준수한다. 수동 임계값 오버라이드와 충돌하는 사례는 발견되지 않음.

#### (c) 베이스라인 매치 회귀 (시뮬레이션)

```bash
python scripts/run_match.py --agent1 redteams/red1.yaml --agent2 redteams/red3.yaml --rounds 1 --max-steps 600 --quiet
python scripts/run_match.py --agent1 redteams/red5.yaml --agent2 redteams/red4.yaml --rounds 1 --max-steps 600 --quiet
```

| 매치 | 결과 | 양측 HP | wall-clock |
|------|------|---------|------------|
| red1 vs red3 (단순 표적기 vs Hard Deck+Pursue) | 600/600 timeout 무승부 | 100 / 100 | 5.65 s |
| red5 vs red4 (정밀 사격/에너지 vs 위협대응 중급) | 600/600 timeout 무승부 | 100 / 100 | 6.47 s |

red5가 사용하는 P1 의존 노드 (`UnderThreat`, `IsEnergyAdvantage`, `IsOvershootRisk`, `IsOneCircle`) 가 새 좌표계/AA 정의 하에서 예외 없이 동작했고, Hard Deck 위반(P2 임계 1000 ft) / 안전 위반(STALL/SPIN/OVERLOAD) 도 발생하지 않았다 (HP 100 유지).

> **결론**: P0/P1/P2/P3 수정은 회귀 단위 테스트 + redteams BT 빌드 + 베이스라인 매치 3단계로 정상성이 검증되었다.

---

## 7. 부록 — Blackboard 키 사전

### 7.1 `observation` dict 키

| 키 | 단위 | 출처 | 비고 |
|----|------|------|------|
| `ego_altitude_ft` | ft | obs[0]*5000 → m_to_ft | |
| `altitude_ft` | ft | 동일 (BelowHardDeck용 별칭) | |
| `ego_vbody_x_kts`, `ego_vbody_y_kts`, `ego_vbody_z_kts` | kts | body velocity *340 → ms_to_knots | **body frame** (§4.4), P3 rename 적용 |
| `ego_vc_kts`, `velocity_mag_kts` | kts | obs[8]*340 → ms_to_knots | CAS |
| `delta_vbody_x_kts` | kts | obs[9]*340 → ms_to_knots | body x 차이, P3 rename 적용 |
| ~~`delta_altitude_ft`~~ | — | (제거) | P3에서 `alt_gap_ft`로 통일 |
| `ego_AO_rad`, `ego_TA_rad` | rad | obs[11], obs[12] | LAG 직접 |
| `distance_ft` | ft | obs[13]*10000 → m_to_ft | |
| `side_flag` | -1/0/+1 | obs[14] | 양수=적이 오른쪽 |
| `specific_energy_ft` | ft | h + v²/2g (g_ft=32.174) | |
| `ps_fts` | ft/s | dHe/dt | |
| `roll_deg`, `pitch_deg`, `heading_deg` | deg | rad → degrees | heading은 [0, 360) |
| `ata_deg`, `aa_deg`, `hca_deg` | deg | CombatGeometry, [0, 180] | aa_deg 의미 §4.2 |
| `tau_deg`, `relative_bearing_deg` | deg | CombatGeometry, [-180, 180] | |
| `ata_lead_deg`, `tau_lead_deg` | deg | CombatGeometry.get_lead_params | lookahead 1 s |
| `alt_gap_ft` | ft | CombatGeometry.alt_gap (NEU) | 양수=적이 위 |
| `closure_rate_kts` | kts | combat_geo.closure_rate * MS_TO_KNOT | 양수=접근 |
| `turn_rate_degs` | °/s | combat_geo.turn_rate | g·tan(roll)/v 근사 |
| `in_39_line`, `overshoot_risk` | bool | CombatGeometry | |
| `tc_type` | str | '1-circle' / '2-circle' | |
| `energy_advantage`, `alt_advantage`, `spd_advantage` | bool | combat_geo.energy_state | **§4.1 영향** |
| `energy_diff_ft` | ft | meters_to_feet(energy['energy_diff']) | **§4.1 영향** |
| `bfm_situation` | enum | BFMClassifier.classify | OBFM/DBFM/HABFM/UNKNOWN |
| `ego_health`, `ego_damage_dealt`, `ego_damage_received` | HP | runner.inject_match_state | |
| `in_wez`, `enm_in_wez` | bool | wez_engine | |

### 7.2 글로벌 키 (`/`-prefix)

| 키 | 단위 | 사용 노드 |
|----|------|-----------|
| `/Distance_ft` | ft | InEnemyWEZ |
| `/CurrentRoll_deg` | deg | (참고용) |
| `/CurrentPitch_deg` | deg | IsVerticalMove |
| `/Speed_kts` | kts | (참고용) |
| `/MyLOSAngle` | deg (abs) | LOSAbove, LOSBelow |
| `/EnemyLOSAngle` | deg | InEnemyWEZ |
| `/TurnLeft`, `/TurnRight` | bool | TurnLeft, IsTurningLeft, IsTurningRight |
| `/ClosureRate_kts` | kts | ClosureRateAbove, ClosureRateBelow |
| `/TurnRate_degs` | °/s | TurnRateAbove |
| `/In39Line`, `/OvershootRisk` | bool | Is39Line, IsTargetInSight, IsOvershootRisk |
| `/TCType` | str | IsOneCircle, IsTwoCircle |
| `/EnergyAdvantage`, `/AltAdvantage`, `/SpdAdvantage` | bool | IsEnergyAdvantage, IsAltAdvantage, IsSpdAdvantage **§4.1** |
| `/EnergyDiff_ft` | ft | EnergyDiffAbove **§4.1** |
| `/MergeDistance_ft` | ft | IsMerged |
| `/Superior` | bool | HasSuperior, NotSuperior **§4.1** |
| `/EnergyState` | bool | EnergyHigh **§4.1** |
| `/TickRateHz` | Hz | TimedAction (자동 환산용) |

---

## 8. 참고 자료

- [README.md](../README.md) — BT 노드 레퍼런스 및 단위 정의
- [docs/RULEBOOK.md](RULEBOOK.md) — 매치 규칙 (Hard Deck, WEZ, 안전 위반)
- [docs/BT_TICK_RATE_ANALYSIS.md](BT_TICK_RATE_ANALYSIS.md) — Tick rate 의사결정
- 논문: "공대공 전투 모의를 위한 규칙기반 AI 교전 모델 개발" (Figure 4.1, Geometric Relationships)
