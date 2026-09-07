# 조이스틱 입력 아키텍처 (Joystick Input Architecture)

이 문서는 `ai-combat-core` 프로젝트 내에서 조이스틱(또는 키보드) 입력을 처리하는 두 가지 주요 클래스인 `JoystickAgent`와 `CombatJoystickInput`의 역할과 구조적 차이를 설명합니다.

## 1. 개요

시뮬레이션 환경(JSBSim)과 상호작용하기 위해 조이스틱 입력을 처리하는 모듈은 크게 두 가지로 나뉩니다:
1. **`JoystickAgent`** (`src/simulation/envs/JSBSim/human_agent/JoystickAgent.py`)
2. **`CombatJoystickInput`** (`src/match/joystick_input.py`)

두 클래스 모두 물리적인 조이스틱 입력(pygame 활용)을 읽어오는 기능을 하지만, **사용되는 맥락(Context)**과 **출력하는 데이터의 형태**가 완전히 다릅니다.

---

## 2. JoystickAgent (강화학습 환경용)

`JoystickAgent`는 AI 에이전트와 동일한 인터페이스를 유지하면서 인간이 시뮬레이터에 개입할 수 있도록 설계된 클래스입니다.

- **목적**: 강화학습(RL) 학습 및 테스트 환경 (`SingleCombatEnv`, `JoystickFreeFlyTask` 등) 내에서의 작동
- **상속 구조**: `BaseAgent` 상속
- **데이터 흐름**:
  1. 조이스틱의 아날로그 입력을 읽음.
  2. `get_action()` 호출 시, 이 입력을 `MultiDiscrete` 공간의 **이산적인 인덱스(Discrete Index)** 형태로 변환. (예: Throttle을 0~30 범위의 정수로 변환)
  3. 반환된 인덱스 배열은 해당 환경의 `Task.normalize_action()` 메서드로 전달됨.
  4. Task 내부 수식에 의해 최종 JSBSim 물리 값(Continuous Value)으로 정규화됨.
- **특징**: AI 정책 네트워크(Policy Network)가 내뱉는 출력(Action Index)과 형태를 100% 동일하게 맞추기 위한 "Mock AI" 역할을 수행합니다.

---

## 3. CombatJoystickInput (실시간 전투 매치용)

`CombatJoystickInput`은 텔레메트리, HUD, 그리고 행동트리(Behavior Tree) AI와의 실시간 교전을 지원하기 위해 성능 위주로 최적화된 독립(Standalone) 클래스입니다.

- **목적**: `runner_human_vs_bt.py` 등 실제 인간 vs AI 전투 매치 런타임에서의 조이스틱 입력 전담 처리
- **상속 구조**: 상속 없음 (Standalone)
- **데이터 흐름**:
  1. 200Hz의 독립된 스레드에서 조이스틱을 백그라운드 폴링(Polling)함.
  2. `get_raw_action()` 호출 시, 조이스틱 입력을 인덱스로 변환하지 않고 즉시 **저수준 물리 제어값(Raw Continuous Value)**으로 변환. (Aileron: `[-1.0, 1.0]`, Throttle: `[0.2, 1.0]` 등)
  3. 반환된 값은 Task의 정규화 단계를 거치지 않고, 매치 런너에서 `env.agents[id].set_property_values()`를 통해 JSBSim 엔진으로 **직접 주입(Bypass)**됨.
- **특징**:
  - 인덱스 변환 및 Task 정규화를 건너뛰어(Bypass) 제어 지연(Latency)을 최소화합니다.
  - 매치 런너 내에서 HUD 시스템과 직접 상호작용합니다.
  - 인간 플레이어의 브레이크 버튼 등 특수 액션을 독립적으로 처리합니다.

---

## 4. 요약 및 주의사항

| 구분 | `JoystickAgent` | `CombatJoystickInput` |
| :--- | :--- | :--- |
| **주 사용처** | RL 학습 / 짐(Gym) 환경 테스트 | 실시간 매치 런너 (`runner_human_vs_bt.py`) |
| **상속** | `BaseAgent` | 없음 (독립 클래스) |
| **출력 형태** | 고수준 이산 인덱스 (Discrete Index) | 저수준 연속 물리값 (Continuous Value) |
| **정규화 과정** | `Task.normalize_action()`을 거침 | 자체 클래스 내에서 정규화 완료 후 엔진에 직결 |
| **스로틀 범위** | 인덱스 매핑 (예: 0~30) | 물리 값 즉시 매핑 (`[0.2, 1.0]`) |

> **⚠️ 주의사항**
> 조이스틱의 제어 범위(예: 스로틀 최대치 변경)를 수정해야 할 경우, **두 클래스 및 관련 Task 파일을 모두 수정**해야 합니다. 
> - `JoystickAgent`를 위해 `Task`의 `normalize_action()` 수식을 변경해야 하며,
> - `CombatJoystickInput`를 위해 해당 클래스 내부의 자체 변환 수식(`_normalize_throttle()`)도 변경해야 실제 매치에 정상적으로 반영됩니다.
