# BT → JSBSim 제어 정보 흐름 분석

> 1 vs 1 공중교전에서 행동트리(BT)로부터 JSBSim FDM까지 제어 정보가 송신/수신되는 전체 경로를 분석한 문서

## 전체 아키텍처 다이어그램

```
[1] BehaviorTreeMatch.run()  ── 매 스텝 루프 ──┐
         │                                       │
[2] BehaviorTreeTask.get_high_level_action()     │
         │  ├─ env.get_obs() → 15차원 정규화 벡터   │
         │  ├─ _update_blackboard() → 관측값 기록   │
         │  └─ tree.tick_once() → BT 노드 실행      │
         │                                       │
[3] BT 액션 노드 (예: ViperStrike.update())      │
         │  ├─ Blackboard에서 전투상태 읽기        │
         │  └─ set_action() → [delta_alt_idx,       │
         │                    delta_hdg_idx,       │
         │                    delta_vel_idx] 기록  │
         │                                       │
[4] env.step(action)                             │
         │  └─ HierarchicalSingleCombatTask.       │
         │     normalize_action()                  │
         │     ├─ 인덱스 → 연속값 변환              │
         │     │   [3,6,2] → [+0.15, +0.785, 0.0] │
         │     ├─ 저수준 RNN 정책 실행              │
         │     │   BaselineActor → 4축 이산 출력    │
         │     └─ 이산 → 연속 제어값 정규화         │
         │       → [-0.3, +0.1, -0.05, 0.65]     │
         │                                       │
[5] agent.set_property_values(action_var, values) │
         │  └─ JSBSim FCS 프로퍼티에 직접 설정      │
         │     fcs/aileron-cmd-norm  = -0.3       │
         │     fcs/elevator-cmd-norm = +0.1       │
         │     fcs/rudder-cmd-norm   = -0.05      │
         │     fcs/throttle-cmd-norm = 0.65       │
         │                                       │
[6] JSBSim FDM 실행 루프                          │
         │  └─ sim.run() ×12회 (agent_interaction) │
         │     ├─ jsbsim_exec.run() → C++ FDM     │
         │     └─ _update_properties() → 상태 동기화│
         │                                       │
[7] 상태 동기화 및 루프 완성                     │
         │  └─ LLA2NEU 좌표 변환, NEU→NED 처리   │
         └─────────────────────────────────────────┘
```

---

## 1단계: 매치 루프

**파일**: `src/match/runner.py` — `BehaviorTreeMatch.run()`

```python
while not done and step_count < self.max_steps:
    # 두 행동트리의 고수준 액션 가져오기
    action1 = task1.get_high_level_action(env, env.ego_ids[0])
    action2 = task2.get_high_level_action(env, env.enm_ids[0])
    
    # 두 액션을 배열로 결합
    action = np.array([action1, action2])
    
    obs, reward, dones, info = env.step(action)
```

- **역할**: 매 스텝마다 두 에이전트의 BT를 tick하고, 결과 액션을 `env.step()`에 전달
- `task1`/`task2`는 각각 독립적인 `BehaviorTreeTask` 인스턴스 (고유 Blackboard 네임스페이스 사용)

---

## 2단계: BT Task의 고수준 액션 결정

**파일**: `src/behavior_tree/task.py` — `BehaviorTreeTask.get_high_level_action()`

```python
def get_high_level_action(self, env, agent_id: str) -> np.ndarray:
    # 1. 관측값 가져오기 (15차원 정규화 벡터)
    obs = self.get_obs(env, agent_id)
    
    # 2. Blackboard 업데이트
    self._update_blackboard(obs, env, agent_id)
    
    # 3. tick 전에 action 초기화
    self.blackboard.set("action", None)
    
    # 4. 행동트리 tick (루트부터 순회)
    self.tree.tick_once()
    
    # 5. Blackboard에서 액션 추출
    action = self._get_action_from_blackboard()
    return action
```

### 2-1. 관측값 수집 (SingleCombatTask.get_obs())

`get_obs()`가 JSBSim 시뮬레이터에서 상태를 읽어 15차원 정규화 벡터를 생성한다:

| 인덱스 | 내용 | 단위/정규화 |
|--------|------|-------------|
| 0 | ego 고도 | /5000 (5km 기준) |
| 1-2 | ego roll sin/cos | rad → sin/cos |
| 3-4 | ego pitch sin/cos | rad → sin/cos |
| 5-7 | ego body velocity (x,y,z) | /340 (마하 기준) |
| 8 | ego calibrated airspeed | /340 |
| 9 | delta body velocity x | /340 |
| 10 | delta altitude | /1000 (km 기준) |
| 11 | Aspect Angle (AO) | rad |
| 12 | Tail Angle (TA) | rad |
| 13 | 상대 거리 | /10000 (10km 기준) |
| 14 | side_flag | -1, 0, 1 |

### 2-2. Blackboard 업데이트

`_update_blackboard()`에서 관측값을 딕셔너리로 변환하여 Blackboard에 기록한다:

```python
self.blackboard.observation = {
    "raw": obs,
    "ego_altitude": ego_altitude,       # m
    "ego_vc": ego_vc,                   # m/s
    "distance": distance,               # m
    "roll_deg": roll_deg,               # deg
    "pitch_deg": pitch_deg,             # deg
    "velocity_mag": ego_vc,             # m/s
    "specific_energy": specific_energy, # m (비에너지)
    "ps": ps,                           # m/s (잉여추력)
    ...
}
```

추가로 CombatGeometry 파라미터도 계산하여 기록한다:

| 키 | 설명 | 단위 |
|----|------|------|
| `ata_deg` | Antenna Train Angle | 도(°), 0°~180° |
| `aa_deg` | Aspect Angle | 도(°), 0°~180° |
| `hca_deg` | Heading Crossing Angle | 도(°), 0°~180° |
| `tau_deg` | Target Aspect Angle (TAU) | 도(°), -180°~180° |
| `relative_bearing_deg` | 상대 방위각 | 도(°), -180°~180° |
| `alt_gap_ft` | 고도 차이 | ft (원본) |
| `ata_lead_deg` | 리드 ATA (1초 예측) | 도(°), 0°~180° |
| `tau_lead_deg` | 리드 TAU (1초 예측) | 도(°), -180°~180° |

BFM 상황 분류 결과도 Blackboard에 기록된다:

```python
bfm_situation = self.bfm_classifier.classify(combat_geo)
self.blackboard.set("bfm_situation", bfm_situation)
```

---

## 3단계: BT 액션 노드의 고수준 명령 생성

### 3-1. YAML 트리 구조

YAML 파일(예: `submissions/viper1/viper1.yaml`)이 트리 구조를 정의한다:

```yaml
tree:
  type: Selector
  name: Viper1_Root
  children:
    - type: Sequence          # 1. Hard Deck 회피
      children:
        - type: Condition
          name: BelowHardDeck
        - type: Action
          name: ClimbTo
    - type: Sequence          # 2. 방어 기동
      children:
        - type: Condition
          name: IsDefensiveSituation
        - type: Action
          name: DefensiveManeuver
    - type: Sequence          # 3. 공격 기동
      children:
        - type: Condition
          name: IsOffensiveSituation
        - type: Condition
          name: EnemyInRange
        - type: Action
          name: ViperStrike   # 커스텀 액션
    - type: Action            # 5. 기본 추적
      name: Pursue
```

`loader.py`가 YAML을 파싱하여 py_trees 트리를 생성한다. 커스텀 노드는 `submissions/{name}/nodes/` 폴더에서 자동 로드된다.

### 3-2. 액션 노드의 출력

모든 액션 노드는 `BaseAction.set_action()`을 통해 Blackboard에 **3개의 이산 인덱스**를 기록한다:

```python
def set_action(self, delta_altitude_idx, delta_heading_idx, delta_velocity_idx):
    self.blackboard.action = [delta_altitude_idx, delta_heading_idx, delta_velocity_idx]
```

### 3-3. 고수준 액션 공간 (5×9×5 = 225가지)

| 축 | 인덱스 | 매핑 값 | 의미 |
|----|--------|---------|------|
| **Altitude** | 0 | -0.40 | 급하강 |
| | 1 | -0.15 | 하강 |
| | 2 | 0.00 | 유지 |
| | 3 | +0.15 | 상승 |
| | 4 | +0.40 | 급상승 |
| **Heading** | 0 | -π/2 (-90°) | 급좌회전 |
| | 1 | -π/3.2 | |
| | 2 | -π/4 (-45°) | 중좌회전 |
| | 3 | -π/8 | 약좌회전 |
| | 4 | 0 | 직진 |
| | 5 | +π/8 | 약우회전 |
| | 6 | +π/4 (+45°) | 중우회전 |
| | 7 | +π/3.2 | |
| | 8 | +π/2 (+90°) | 급우회전 |
| **Velocity** | 0 | -0.08 | 급감속 |
| | 1 | -0.04 | 감속 |
| | 2 | 0.00 | 유지 |
| | 3 | +0.04 | 가속 |
| | 4 | +0.08 | 급가속 |

### 3-4. 액션 노드 예시: ViperStrike

```python
# submissions/viper1/nodes/custom_actions.py
class ViperStrike(BaseAction):
    def update(self) -> py_trees.common.Status:
        obs = self.blackboard.observation
        tau_deg = obs.get("tau_deg", 0.0)  # 실제 도(°) 단위
        distance_ft = obs.get("distance_ft", 10000.0)
        alt_gap_ft = obs.get("alt_gap_ft", 0.0)
        
        # 고도: alt_gap 기반 고도 우위 유지
        # 방향: tau_deg 기반 정밀 추적 (거리별 감도 조절)
        # 속도: 거리 기반 최적화 (WEZ 내 감속, 원거리 급가속)
        
        self.set_action(delta_altitude_idx, delta_heading_idx, delta_velocity_idx)
        return py_trees.common.Status.SUCCESS
```

---

## 4단계: 고수준 → 저수준 변환

**파일**: `src/simulation/envs/JSBSim/tasks/singlecombat_task.py` — `HierarchicalSingleCombatTask.normalize_action()`

`env.step(action)` 내부에서 각 에이전트에 대해 호출된다:

```python
# env_base.py - step() 내부
for agent_id in self.agents.keys():
    a_action = self.task.normalize_action(self, agent_id, action[agent_id])
    self.agents[agent_id].set_property_values(self.task.action_var, a_action)
```

### 4-1. HierarchicalSingleCombatTask.normalize_action()

`env.step()` 내부에서 각 에이전트에 대해 호출된다:

```python
# env_base.py - step() 내부
for agent_id in self.agents.keys():
    a_action = self.task.normalize_action(self, agent_id, action[agent_id])
    self.agents[agent_id].set_property_values(self.task.action_var, a_action)
```

### 4-2. 변환 과정 (3단계 상세)

```python
def normalize_action(self, env, agent_id, action):
    # ① 고수준 인덱스 → 연속값 변환
    raw_obs = self.get_obs(env, agent_id)  # 15차원 관측값
    input_obs = np.zeros(12)
    input_obs[0] = self.norm_delta_altitude[action[0]]   # 예: idx=3 → +0.15
    input_obs[1] = self.norm_delta_heading[action[1]]    # 예: idx=6 → +π/4
    input_obs[2] = self.norm_delta_velocity[action[2]]   # 예: idx=2 → 0.0
    input_obs[3:12] = raw_obs[:9]                        # ego 상태 9차원 추가
    input_obs = np.expand_dims(input_obs, axis=0)       # 배치 차원 추가
    
    # ② 사전 학습된 저수준 RNN 정책 (BaselineActor)
    _action, _rnn_states = self.lowlevel_policy(input_obs, self._inner_rnn_states[agent_id])
    # 출력: 4개 이산 인덱스 [aileron, elevator, rudder, throttle]
    action = _action.detach().cpu().numpy().squeeze(0)
    self._inner_rnn_states[agent_id] = _rnn_states.detach().cpu().numpy()
    
    # ③ 이산 인덱스 → 연속 제어값 정규화
    norm_act = np.zeros(4)
    norm_act[0] = action[0] / 20 - 1.    # aileron:  [0,40] → [-1, 1]
    norm_act[1] = action[1] / 20 - 1.    # elevator: [0,40] → [-1, 1] 
    norm_act[2] = action[2] / 20 - 1.    # rudder:   [0,40] → [-1, 1]
    norm_act[3] = action[3] / 58 + 0.4   # throttle: [0,29] → [0.4, 0.9]
    return norm_act
```

### 4-3. 저수준 정책 신경망 (BaselineActor)

- **모델 파일**: `model/baseline_model.pt`
- **구조**: RNN 기반 (GRU 레이어, hidden state 128차원)
  ```python
  class BaselineActor(nn.Module):
      def __init__(self, input_dim=12):
          self.base = MLPBase(input_dim, '128 128')    # 2층 MLP
          self.rnn = GRULayer(128, 128, 1)             # GRU 레이어
          self.act = ACTLayer(128, [41, 41, 41, 30])   # 4축 이산 출력
  ```
- **입력**: 12차원 = delta 3개 + ego 상태 9개
- **출력**: 4개 이산 액션 인덱스 → 정규화 후 연속 제어값
- **RNN 상태**: 에이전트별 유지 (self._inner_rnn_states[agent_id])

이 정책은 "고수준 의도(상승/좌회전/가속 등)를 실현하기 위해 조종면을 어떻게 움직여야 하는지"를 학습한 모델이다.

### 4-4. (선택) Classical PD 제어기 — RNN 우회

`AICOMBAT_CONTROLLER=classical` 환경변수 설정 시, `normalize_action()`은 `_use_classical_controller()` 분기를 통해
RNN(BaselineActor)을 **호출하지 않고** `src/control/classical_controller.py`의 stateless PD로 조종면을 직접 생성한다
(`_classical_compute()`). agent별 별도 인스턴스로 저역통과 필터 상태를 격리한다.

```python
# singlecombat_task.py - HierarchicalSingleCombatTask.normalize_action()
if self._use_classical_controller():           # AICOMBAT_CONTROLLER == "classical"
    return self._classical_compute(env, agent_id, action)
# (미설정 시 기존 RNN 경로)
```

- **변환**: BT 5×9×5 인덱스 → 연속 setpoint(PITCH ±20° / BANK ±65° / SPEED 220~450 kts) → 저역통과(α=0.85) → PD.
- **Tactical Maneuver 경로**: BT 노드가 `set_maneuver([...])`로 연속 maneuver(6타입)를 출력하면,
  `env.task._maneuver_buffer`를 거쳐 `ClassicalController.compute_from_maneuvers()`가 격자를 우회해 정밀 추종한다
  (`src/behavior_tree/maneuvers.py`). 기존 `set_action()`은 자동으로 maneuver로 변환된다.
- 기본값(`nn`)에서는 이 분기를 타지 않으므로 위 4-1~4-3 경로가 그대로 유지된다 (후방호환).

---

## 5단계: JSBSim 프로퍼티 설정

**파일**: `src/simulation/envs/JSBSim/core/simulatior.py` — `AircraftSimulator.set_property_values()`

```python
def set_property_values(self, props, values):
    """여러 프로퍼티에 값을 한 번에 설정"""
    if not len(props) == len(values):
        raise ValueError("mismatch between properties and values size")
    for prop, value in zip(props, values):
        self.set_property_value(prop, value)

def set_property_value(self, prop, value):
    """개별 프로퍼티 설정 (범위 클램핑 포함)"""
    if isinstance(prop, Property):
        # 값 범위 제한
        if value < prop.min:
            value = prop.min
        elif value > prop.max:
            value = prop.max
        # JSBSim C++ FDM에 직접 기록
        self.jsbsim_exec.set_property_value(prop.name_jsbsim, value)
```

### 설정되는 JSBSim FCS 프로퍼티 4개

| 프로퍼티 | JSBSim 이름 | 범위 | 설명 |
|----------|-------------|------|------|
| `fcs_aileron_cmd_norm` | `fcs/aileron-cmd-norm` | [-1, 1] | 에일러론 명령 (롤 제어) |
| `fcs_elevator_cmd_norm` | `fcs/elevator-cmd-norm` | [-1, 1] | 엘리베이터 명령 (피치 제어) |
| `fcs_rudder_cmd_norm` | `fcs/rudder-cmd-norm` | [-1, 1] | 러더 명령 (요 제어) |
| `fcs_throttle_cmd_norm` | `fcs/throttle-cmd-norm` | [0.4, 0.9] | 스로틀 명령 (추력 제어) |

---

## 6단계: JSBSim FDM 물리 시뮬레이션 실행

**파일**: `src/simulation/envs/JSBSim/envs/env_base.py`, `src/simulation/envs/JSBSim/core/simulatior.py`

```python
# env_base.py - step() 내부 시뮬레이션 루프
for _ in range(self.agent_interaction_steps):  # 12회 반복
    for sim in self._jsbsims.values():
        sim.run()  # JSBSim FDM 1스텝 실행
    for sim in self._tempsims.values():
        sim.run()  # 임시 시뮬레이터 (미사일 등)

# simulatior.py - 개별 시뮬레이터 실행
def run(self):
    """JSBSim C++ FDM 실행 및 상태 동기화"""
    if self.is_alive:
        if self.bloods <= 0:
            self.shotdown()  # 체력 소진 시 격추 처리
        result = self.jsbsim_exec.run()       # JSBSim C++ FDM 1스텝 실행
        if not result:
            raise RuntimeError("JSBSim failed.")
        self._update_properties()              # 결과를 Python 객체에 동기화
        return result
    else:
        return True  # 격추된 항공기는 건너뜀
```

### 시뮬레이션 타이밍

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| `sim_freq` | 60 Hz | JSBSim 적분 주파수 |
| `agent_interaction_steps` | 12 | BT tick당 JSBSim 실행 횟수 |
| **BT tick 간격** | **0.2초** | 12 × (1/60) = 0.2초 |
| `max_steps` | 1000 (기본) | 최대 스텝 수 (= 200초) |

### `_update_properties()` — 시뮬레이션 결과 동기화

JSBSim FDM 실행 후 물리 상태를 Python 객체에 동기화한다:

```python
def _update_properties(self):
    # 위치 (경도, 위도, 고도) 읽기
    self._geodetic[:] = self.get_property_values([
        Catalog.position_long_gc_deg,    # 경도 [deg]
        Catalog.position_lat_geod_deg,     # 위도 [deg] 
        Catalog.position_h_sl_m           # 고도 [m]
    ])
    # LLA → NEU 좌표 변환 (전투장역 기준)
    self._position[:] = LLA2NEU(*self._geodetic, self.lon0, self.lat0, self.alt0)
    
    # 자세 (롤, 피치, 요) 읽기
    self._posture[:] = self.get_property_values([
        Catalog.attitude_roll_rad,           # 롤 [rad]
        Catalog.attitude_pitch_rad,          # 피치 [rad]
        Catalog.attitude_heading_true_rad    # 요 [rad]
    ])
    
    # 속도 (v_north, v_east, v_down) 읽기
    self._velocity[:] = self.get_property_values([
        Catalog.velocities_v_north_mps,      # 북쪽 속도 [m/s]
        Catalog.velocities_v_east_mps,       # 동쪽 속도 [m/s]
        Catalog.velocities_v_down_mps         # 아래쪽 속도 [m/s]
    ])
    # NED → NEU 변환 (v_down → -v_up)
    self._velocity[2] = -self._velocity[2]
```

이 동기화된 상태가 다음 스텝에서 `get_obs()` → Blackboard → BT 노드로 전달되어 루프가 완성된다.

---

## 데이터 흐름 요약 (수치 예시)

```
┌─────────────────────────────────────────────────────────────────┐
│  BT 액션 노드 (ViperStrike 등)                                  │
│  CombatGeometry 기반 판단:                                      │
│  - tau_deg = 15°, distance = 2500m, alt_gap = -300m            │
│  출력: [delta_alt_idx, delta_hdg_idx, delta_vel_idx]            │
│        예: [3, 6, 2] = "상승 + 중우회전 + 속도유지"              │
└──────────────────────┬──────────────────────────────────────────┘
                       │ Blackboard "action" 키
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  HierarchicalSingleCombatTask.normalize_action()                │
│  ① 인덱스→연속값: [3,6,2] → [+0.15, +π/4, 0.0]                │
│ ② 저수준 NN 정책: 12D 입력 → 4D 이산 출력                      │
│     - BaselineActor(GRU) → [20, 25, 18, 15]                    │
│ ③ 정규화: → [aileron, elevator, rudder, throttle]              │
│             [0.0, +0.25, -0.1, 0.658]                          │
└──────────────────────┬──────────────────────────────────────────┘
                       │ set_property_values()
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  JSBSim FDM (F-16 비행역학 모델)                                 │
│  fcs/aileron-cmd-norm  = 0.0    (에일러론 중립)                │
│  fcs/elevator-cmd-norm = +0.25  (엘리베이터 상승)               │
│  fcs/rudder-cmd-norm   = -0.1   (러더 좌측)                    │
│  fcs/throttle-cmd-norm = 0.658  (스로틀 65.8%)                 │
│  → jsbsim_exec.run() ×12회 (0.2초 시뮬레이션)                   │
│  → _update_properties()로 상태 동기화                           │
└─────────────────────────────────────────────────────────────────┘
```

## 관련 파일 목록

| 파일 | 역할 |
|------|------|
| `src/match/runner.py` | 매치 루프, 두 BT 에이전트 대전 실행 |
| `src/behavior_tree/task.py` | BT ↔ LAG 환경 통합, Blackboard 관리 |
| `src/behavior_tree/loader.py` | YAML → py_trees 트리 변환, 커스텀 노드 로드 |
| `src/behavior_tree/nodes/actions.py` | 기본 액션 노드 (Pursue, ClimbTo 등) |
| `src/behavior_tree/nodes/conditions.py` | 기본 조건 노드 (BelowHardDeck 등) |
| `submissions/{name}/nodes/custom_actions.py` | 커스텀 액션 노드 |
| `submissions/{name}/nodes/custom_conditions.py` | 커스텀 조건 노드 |
| `submissions/{name}/{name}.yaml` | 행동트리 구조 정의 |
| `src/simulation/envs/JSBSim/tasks/singlecombat_task.py` | 고수준→저수준 변환, 저수준 NN 정책 + classical 분기 |
| `src/control/classical_controller.py` | (선택) Classical PD 제어기 — `AICOMBAT_CONTROLLER=classical` |
| `src/behavior_tree/maneuvers.py` | (선택) Tactical Maneuver 출력 인터페이스 (Z-series) |
| `src/simulation/envs/JSBSim/envs/env_base.py` | 환경 step/reset, JSBSim 실행 루프 |
| `src/simulation/envs/JSBSim/core/simulatior.py` | JSBSim FDM 래퍼, 프로퍼티 읽기/쓰기 |
| `src/control/combat_geometry.py` | 전투 기하학 파라미터 계산 (ATA, TAU 등) |
| `src/control/bfm_classifier.py` | BFM 상황 분류 (공격/방어/중립) |
| `model/baseline_model.pt` | 사전 학습된 저수준 RNN 정책 가중치 |
