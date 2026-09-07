# KIMST 2026 발표 — 핵심 용어집

*행동트리(BT) 기반 AI 전투기 교전 시뮬레이션 플랫폼 · 공군사관학교 국방 AI 시스템 연구실 (DAS Lab)*

---

## 군사 · 공중전 전술

- **BFM (Basic Fighter Maneuvers)** — 기본 전투 기동. 1:1 근접 공중전의 표준 기동 체계
- **OBFM (Offensive BFM)** — 공격 기동. 우세 상황에서 조준·사격으로 연결
- **DBFM (Defensive BFM)** — 방어 기동. 위협받는 상황에서 회피
- **HABFM (High-Aspect BFM)** — 고교차각·정면 대치 기동 (중립 국면)
- **ATA (Antenna Train Angle)** — 기수 지향각. 내 기수와 표적 시선 사이의 각
- **AA (Aspect Angle)** — 애스펙트각. 표적 꼬리 기준으로 내 위치까지의 각
- **HCA (Heading Crossing Angle)** — 기수 교차각. 두 기체 진행 방향의 차이각
- **WEZ (Weapon Engagement Zone)** — 무장 교전 구역. 사격이 유효한 거리·각도 영역
- **WVR / BVR** — 시계 내 / 시계 외 교전 (Within / Beyond Visual Range)
- **LAR (Launch Acceptable Region)** — 미사일 발사 가능 구역
- **Lead / Lag / Pure Pursuit** — 선행 / 후행 / 순수 추격 (표적 전방·후방·직접 조준)
- **TAU (τ)** — 조준·기동 제어용 각. 양력 벡터(기체 대칭면)와 표적 사이 각(roll 보정, deg) — 표적을 선회면에 넣을 롤·당김 방향을 결정. 상황 우열 판단(ATA/AA/HCA)이 아닌 제어 파라미터
- **Hard Deck** — 훈련상 설정한 최저 안전 고도
- **Break Turn / Defensive Spiral** — 급선회 / 방어 나선 (대표 방어 기동)
- **Energy Fight · 1·2-circle** — 에너지 우위 공중전 · 선회전의 형태
- **Red Team** — 대항군 (자동 토너먼트의 상대 에이전트)
- **NM** — 해리 (Nautical Mile)

## AI · 강화학습 · 행동트리(BT)

- **BT (Behavior Tree)** — 행동트리. 전술 의도를 트리로 명시하는 결정론적 제어 구조
- **RL (Reinforcement Learning)** — 강화학습
- **RNN / GRU** — 순환 신경망 / 게이트 순환 유닛 (하위 조종 명령 생성)
- **PPO (Proximal Policy Optimization)** — RNN 제어기 사전학습에 쓰인 강화학습 알고리즘
- **Selector / Sequence** — BT 노드 — 선택(하나 성공까지) / 순차 실행
- **Condition / Action** — BT 노드 — 조건 판정 / 행동 수행
- **Blackboard** — BT 노드 간 공유 데이터 저장소 (15차원 관측 + 전투 기하)
- **tick** — BT를 1회 평가하는 실행 주기
- **Action Space (225)** — 이산 행동 공간 — 고도 5 × 방위 9 × 속도 5
- **Gymnasium** — 강화학습 환경 표준 라이브러리 (OpenAI Gym 후속)
- **Multi-Agent** — 다개체 (편대·2v2 이상 확장)

## 비행역학 · 시뮬레이션

- **6-DoF (Six Degrees of Freedom)** — 6자유도. 3축 이동 + 3축 회전의 완전 운동
- **JSBSim** — 오픈소스 고정밀 비행 동역학 엔진 (F-16 물리)
- **FDM (Flight Dynamics Model)** — 비행 동역학 모델
- **aileron / elevator / rudder / throttle** — 보조익 / 승강타 / 방향타 / 추력 (4채널 조종 입력)
- **stall / spin** — 실속 / 스핀. 비행 안정성 검증 항목
- **HILS (Hardware-In-the-Loop Simulation)** — 하드웨어 연동 시뮬레이션

## 소프트웨어 · 인프라 · 파일

- **YAML** — BT 전술을 선언형으로 기술하는 데이터 형식
- **ACMI** — Tacview 복기 파일 형식 (Air Combat Maneuvering Instrumentation)
- **Tacview** — 교전 궤적 시각화·복기 도구
- **py_trees** — Python 행동트리 라이브러리
- **Supabase / PostgreSQL** — PostgreSQL 기반 백엔드 / 관계형 DB
- **AWS EC2 / Vercel** — 클라우드 서버 / 프론트엔드 배포
- **Separation of Concerns** — 관심사 분리 — 모듈별 책임 분리 설계 원칙
- **화이트리스트 (whitelist)** — 허용 목록 기반 BT 보안 검증

## 평가 지표

- **WEZ 피해 모델 (dHP/dt)** — 거리·조준각(ATA) 함수로 HP 감소율 산출
- **D₀** — 기준 피해율 (25 HP/s)
- **HP (Hit Points)** — 기체 내구도 / 체력
- **승점제 (3/1/0)** — 승·무·패 점수, 동률 시 평균 잔여 HP
- **표준 평가지표** — 위치 우점율 · 선회 가속도 적합성 · 제한 하중 초과율 (향후 고도화)

## 고유명사 · 기타

- **DARPA AlphaDogfight (2020)** — AI가 숙련 조종사를 5:0 완파한 미 DARPA 시연
- **DAS Lab** — 공군사관학교 국방 AI 시스템 연구실
- **ai-combat-(sdk/core/server/web)** — 플랫폼을 구성하는 4개 저장소(모듈)
- **ai-pilot.boramae.club** — 경진대회 포털 · 리더보드
- **Airmanship** — 공중 감각·교전 교리 이해를 포괄하는 조종 역량

---

📧 songhyon.kim@afa.ac.kr · 🌐 ai-pilot.boramae.club
