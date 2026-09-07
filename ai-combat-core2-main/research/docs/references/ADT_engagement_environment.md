# AlphaDogfight Trials (ADT) 교전 환경 조건 정리

> **출처**: Pope, A. P., Ide, J. S., et al. (2023). *Hierarchical Reinforcement Learning for Air Combat at DARPA's AlphaDogfight Trials*. IEEE Transactions on Artificial Intelligence, Vol. 4, No. 6, pp. 1371–1385.

---

## 1. 시뮬레이션 기반 환경

| 항목 | 내용 |
|------|------|
| 개발 주체 | JHU-APL (Johns Hopkins University Applied Physics Lab) |
| 베이스 | open-source `gym-jsbsim` 환경 확장 |
| FDM | **JSBSim** (F-16, 6-DOF, 고충실도 공력 모델) |
| 항공기 수 | Multi-aircraft 지원 (1v1 WVR dogfight) |
| 센서 노이즈 | 없음 (모든 상태값은 perfect information) |

---

## 2. 시간 / 주기 파라미터

| 항목 | 값 |
|------|------|
| 시뮬레이션 상호작용 주기 | **50 Hz** (low-level policy) |
| Policy Selector 평가 주기 | **10 Hz** (5스텝마다 1회) |
| 에피소드 최대 길이 (T) | **300 초** |
| Multi-step return 최대값 | 25 steps (low-level) / 5 steps (PS) = 0.5초 분량 |

---

## 3. 관측 공간 (Observation Space)

### 3.1 자기 (Ownship)
- 위치: local plane coordinates, velocity, acceleration
- 자세: Euler angles, rates, accelerations
- 공력: α(alpha), β(beta) angles
- 기타: fuel load, thrust, control surface deflection, health

### 3.2 상대 (Opponent)
- 위치: local plane coordinates, velocity
- 자세: Euler angles, rates
- health
- *(자기 대비 acceleration·공력각·연료 등은 제외)*

### 3.3 파생 상태 (실험 항목)
- egocentric / allocentric polar coordinates
- airspeed
- 시간차 delta 상태 (varying time intervals)

---

## 4. 행동 공간 (Action Space)

- **연속(continuous)**, F-16 FCS 직접 입력
- 4축 제어:
  - `aileron`
  - `elevator`
  - `rudder`
  - `throttle`
- 학습 안정화를 위한 절단(truncation):
  - **action 값: 소수점 2자리**
  - **state 값: 소수점 6자리**
  - (GPU 아키텍처 간 floating-point rounding 차이 동기화 목적)

---

## 5. WEZ (Weapon Engagement Zone) — 무장 교전 영역

| 파라미터 | 값 |
|----------|-----|
| 거리 범위 | **500 ft ≤ d ≤ 3000 ft** |
| 원뿔 개구각 | **2°** (기수 방향 spherical cone) |
| 데미지 함수 | $D_{wez} = (3000 - d)/2500$ (WEZ 내), 그 외 0 |

> **Gun snap** = 위 기하 조건(거리 + 2° 콘 내)을 달성한 순간.
> 실제 사격이 아닌 **기하학적 조건**으로 정의됨.

### 5.1 데미지 수식

$$
D_{wez} =
\begin{cases}
\dfrac{3000 - d}{2500} & 500 \text{ ft} \le d \le 3000 \text{ ft} \\
0 & \text{otherwise}
\end{cases}
$$

---

## 6. 종료 / 승패 조건

| 조건 | 결과 |
|------|------|
| 상대 health = 0 | **승리 (Win)** |
| 자기 health = 0 | 패배 (Loss) |
| **고도 < 1000 ft (hard deck) 위반** | 해당 기체 격추 처리 |
| 300초 타임아웃 | **무승부 (Draw)** |

### 6.1 보상 함수 (환경 기본 보상)

누적 데미지의 시간평균:

$$
r_t = \mathbb{E}_{t' \in [0,T]}\left[\sum_{n=0}^{t} D_{wez}(t)\right]
$$

- $T = 300$ s (에피소드 최대 길이)
- 환경 자체 보상은 **sparse** → reward shaping 필요

---

## 7. 핵심 기하 변수 (보상 설계용)

| 변수 | 정의 | 범위 |
|------|------|------|
| Track angle $\theta_t$ | 아군 기수 ↔ 적기 중심선 사이 각 | 0 – 180° |
| Adverse angle $\phi_a$ | 적기 꼬리 ↔ 아군 중심선 사이 각 | 0 – 180° |
| Distance $d$ | 양 기체 간 거리 | ft |
| Closure rate $v_c$ | $d$의 시간미분 | ft/s |
| Altitude $h$ | 지면 위 고도 | ft |

정규화: $\bar{\theta}_t = \theta_t / 180$, $\bar{\phi}_a = \phi_a / 180$

---

## 8. 초기 조건 (Initial Conditions) 카테고리

학습 시 3종으로 분류, 정책별로 다르게 사용:

| 카테고리 | 특징 | 사용 정책 예시 |
|----------|------|----------------|
| **Offensive** | 자기가 WEZ 내 진입한 우세 위치 | AS / CS (100% WEZ 1/2 offensive) |
| **Defensive** | 상대가 자기 WEZ 내 진입한 열세 위치 | 공통 |
| **Neutral / Random** | 무작위 위치·자세·속도 | CZ-1 (50% random + 50% WEZ 1/2 offensive) |

### 8.1 ADT 표준 평가 IC
- 50개 unique 시나리오 × blue/red 양방향 = **100경기 단위**
- offensive/defensive/neutral 혼합

---

## 9. 통신/플랫폼 요약 (참고)

| 항목 | 값 |
|------|-----|
| 학습 프레임워크 | PyTorch v1.3.1 (Ape-X 기반 분산 + SAC) |
| 학습 하드웨어 | AWS EC2 P3.16xlarge (64 CPU, 8× V100 GPU, 488 GiB RAM) |
| Replay buffer | Prioritized Experience Replay (PER), 5.0e6 |
| Actor 수 / instance | 최대 21개 (CPU-bound, JSBSim이 병목) |
| Low-level 학습 시간 | 최대 약 1개월 |
| Policy Selector 학습 시간 | 약 1주 |

---

## 10. 본인 연구(BT–RNN–JSBSim)와의 비교 포인트

| 비교 축 | Pope et al. (ADT) | BT–RNN–JSBSim (KIMST 2026) |
|---------|-------------------|----------------------------|
| Action space | 4축 **연속** (aileron/elev/rudder/throttle) | **225-action 이산 명령 추상화** (BT → RNN → 4축 연속) |
| 제어 계층 | 2-tier (PS → Low-level policy) | 3-tier (BT → RNN → JSBSim) |
| 평가 주기 | PS 10 Hz / Low 50 Hz | **BT 10 Hz / RNN 5 Hz** (Path 2 채택, [BT_TICK_RATE_ANALYSIS.md §8](BT_TICK_RATE_ANALYSIS.md) 참조) |
| WEZ 모델 | 500–3000 ft, 2° 콘, $(3000-d)/2500$ | **500–3000 ft, 2° 콘** (Path 2와 함께 ADT 정합 채택). 데미지 공식은 환경 옵션 분기 |
| 학습 방법론 | SAC + Reward Shaping (HRL) + Self-play | BT 기반 + BFM 자동 분류, RNN은 LAG PPO heading-task 사전학습 |
| 환경 신뢰도 | JSBSim 6-DOF (동일) | JSBSim 6-DOF (동일) |
| 평가 인프라 | DARPA ADT 토너먼트 | ROKAF AI Pilot Competition |

---

*문서 생성일: 2026-05-13*
