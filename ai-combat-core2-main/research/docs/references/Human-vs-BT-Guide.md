# Human vs BT Match Guide

**조이스틱(저수준 직접 제어) vs AI(행동트리) 매치 가이드**

---

## 개요

인간 플레이어가 조이스틱으로 F-16을 **저수준 직접 제어**(aileron, elevator, rudder, throttle)하며,
행동트리(BT) 기반 AI 에이전트와 1:1 공중전을 수행합니다.

### 제어 방식 비교

| 구분 | 인간 (Blue) | BT AI (Red) |
|------|-------------|-------------|
| 입력 | 조이스틱 축/버튼 | 행동트리 의사결정 |
| 제어 수준 | **저수준** (aileron, elevator, rudder, throttle) | 고수준 (altitude, heading, velocity) |
| 변환 과정 | 없음 — JSBSim 직접 전달 | 학습된 NN 정책으로 저수준 변환 |
| 제어 주기 | 0.2초 (5 Hz) | 0.2초 (5 Hz) |

### 아키텍처

```
Human (Blue)                     BT AI (Red)
┌──────────────┐                ┌──────────────────┐
│ Joystick     │                │ BehaviorTreeTask  │
│ get_raw()    │                │ get_high_level()  │
└──────┬───────┘                └────────┬─────────┘
       │ [ail,elev,rud,thr]             │ [alt,hdg,vel]
       │ 저수준 직접 전달                │ normalize_action
       │                                │ (NN 정책)
       ▼                                ▼
┌─────────────────────────────────────────────────┐
│         JSBSim set_property_values              │
│         (aileron, elevator, rudder, throttle)   │
└─────────────────────────────────────────────────┘
```

---

## 요구사항

### 하드웨어
- **조이스틱**: Logitech G Extreme 3D Pro (권장)
  - Thrustmaster T.16000M FCS, Xbox Controller 도 지원
  - `configs/joystick_mappings.yaml`에서 축/버튼 매핑 설정

### 소프트웨어
- Python 3.10+
- pygame-ce: `pip install pygame-ce`
- 기존 ai-combat-core 의존성 전부

---

## 사용법

### 기본 실행

```bash
# 가상환경 활성화 후
python scripts/run_human_vs_bt.py --agent simple
```

### 전체 옵션

```bash
python scripts/run_human_vs_bt.py \
    --agent <에이전트이름>   # 필수: BT AI 에이전트 (submissions/ 또는 examples/)
    --max-steps 1500         # 최대 스텝 (기본 1500 = 5분)
    --verbose                # 상세 출력
    --deadzone 0.05          # 조이스틱 데드존 (기본 0.05)
    --calibrate              # 시작 전 캘리브레이션 (3초)
    --no-display             # HUD 디스플레이 비활성화
    --no-realtime            # 실시간 동기화 비활성화
    --no-replay              # 리플레이 저장 비활성화
    --scenario human_vs_bt   # 시나리오 (기본: human_vs_bt)
```

### 예시

```bash
# simple AI와 대전
python scripts/run_human_vs_bt.py --agent simple

# eagle1 AI와 5분 대전, 상세 출력
python scripts/run_human_vs_bt.py --agent eagle1 --max-steps 1500 --verbose

# ace AI와 대전, 캘리브레이션 포함
python scripts/run_human_vs_bt.py --agent ace --calibrate --deadzone 0.08
```

---

## 조이스틱 조작

### Logitech G Extreme 3D Pro 기준

| 입력 | 기능 | JSBSim 범위 |
|------|------|-------------|
| 스틱 X축 (좌우) | Aileron (에일러론) | [-1.0, 1.0] |
| 스틱 Y축 (앞뒤) | Elevator (엘리베이터) | [-1.0, 1.0] |
| 스틱 회전 (트위스트) | Rudder (러더) | [-1.0, 1.0] |
| 스로틀 레버 | Throttle (스로틀) | [0.4, 0.9] |
| 트리거 (버튼 0) | 환경 리셋 | - |
| 엄지 버튼 (버튼 1) | 일시정지 | - |
| 사이드 버튼 (버튼 2) | 브레이크 (스로틀 최소) | - |

### 데드존

- 기본 5% 데드존 적용
- 중립 근처의 미세한 떨림 제거
- `--deadzone` 옵션으로 조정 가능

### 캘리브레이션

```bash
python scripts/run_human_vs_bt.py --agent simple --calibrate
```

3초간 조이스틱을 중립에 둔 상태로 대기하면 오프셋을 자동 보정합니다.

---

## 매치 규칙

- **초기 위치**: ADT Neutral Start (양측 15,000ft, 약 3000ft 간격)
- **승리 조건**:
  1. 상대 체력 0 (WEZ 기반 Gun 데미지)
  2. 상대 Hard Deck 위반 (1,000ft 미만)
  3. 시간 종료 시 체력 우위
- **데미지**: WEZ (Weapon Engagement Zone) 기반
  - 기축선 2도 원뿔 내, 거리 152-914m (500-3000ft)
  - 거리에 따른 데미지 계수 적용

---

## HUD 디스플레이

매치 중 pygame 창에 실시간 정보 표시:

- **Aileron / Elevator / Rudder**: 현재 조이스틱 입력값
- **Throttle**: 원시값 → JSBSim 변환값
- **Brake**: 브레이크 버튼 상태
- **MY HP / ENM HP**: 인간/AI 체력
- **Distance**: 적과의 거리 (ft)
- **Step**: 현재/최대 스텝

---

## 리플레이

매치 완료 후 `replays/` 폴더에 `.acmi` 파일 자동 저장.

- Tacview에서 열어 재생 가능
- 양측 제어 입력, 전투 기하, 체력 변화 모두 기록
- 인간 플레이어는 `[Blue] Human(Joystick)` 라벨
- AI 에이전트는 `[Red] <active_node>` 라벨

---

## 커스텀 매핑

`src/simulation/envs/JSBSim/configs/joystick_mappings.yaml`에서 조이스틱별
축/버튼 매핑을 설정합니다:

```yaml
joystick_mappings:
  "Logitech Extreme 3D":
    aileron_axis: 0
    elevator_axis: 1
    rudder_axis: 2
    throttle_axis: 3
    invert_elevator: true
    reset_button: 0
    pause_button: 1
    brake_button: 2
```

새 조이스틱 추가 시 `pygame.joystick.Joystick.get_name()` 반환값을 키로 사용합니다.

---

## 관련 파일

| 파일 | 설명 |
|------|------|
| `scripts/run_human_vs_bt.py` | CLI 실행 스크립트 |
| `src/match/runner_human_vs_bt.py` | 매치 코어 (CombatJoystickInput + HumanVsBTMatchCore) |
| `src/simulation/envs/JSBSim/configs/1v1/NoWeapon/human_vs_bt.yaml` | 환경 설정 |
| `src/simulation/envs/JSBSim/configs/joystick_mappings.yaml` | 조이스틱 매핑 |
| `CHANGELOG_JOYSTICK.md` | 변경 이력 |

---

## 문제 해결

### "연결된 조이스틱이 없습니다"
- USB 연결 확인
- Windows 장치 관리자에서 게임 컨트롤러 인식 확인
- `pip install pygame-ce` 재설치

### 조이스틱 입력이 반대로 작동
- `joystick_mappings.yaml`에서 `invert_*` 설정 변경

### 프레임 드롭 경고
- `--no-replay` 옵션으로 디스크 I/O 감소
- `--no-display` 옵션으로 HUD 비활성화
- 다른 프로세스 부하 확인
