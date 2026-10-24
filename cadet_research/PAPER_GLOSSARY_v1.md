# 용어집 v1 — PAPER_DRAFT_v2 (가이드 12.1)

시제: 서론·관련 연구·논의는 현재형, 방법·결과·결론은 과거형(원고 v2의 현재 상태, 가이드 5.8 권장과 같음)
단위: 원고 v2는 ft·KCAS·°/s를 SI 환산 없이 쓴다 → G-33 위반, 표기 방식은 [결정 필요](`REVIEW_FORMAT_v1.md` §10)

작성 2026-10-24. 기준은 STUDY_GUIDE_v3 §5.6(영문 용어표)과 §8.2(쓰면 안 되는 표현)이다. "원고에 나온 동의어" 열은 v2에서 같은 개념에 쓴 다른 말이고, 문장 ID는 `PAPER_DRAFT_v2_IDS.md`를 따른다. "보존"은 가이드 10.3에 따라 고칠 때 지우거나 바꾸지 않는 용어이며, v3 §7.3·§8.2에서 정한 판정 어휘와 표시가 여기에 든다. 사용자가 따로 보존을 지정한 문장은 아직 없다([결정 필요]).

## 1. 개념

| 개념 | 채택 용어 | 영문 (v3 §5.6) | 원고에 나온 동의어 → 정리 | 기호 | 첫 정의 위치 | 보존 |
|---|---|---|---|---|---|---|
| 피치 각속도 추종 오차 | 피치 추종 오차(mae) | pitch-rate tracking error (mean absolute error) | "추종 오차"(축약은 피치임이 분명할 때만). 영문 "pitch tracking error" 금지 | mae | Met-A-T-R1 | 예 |
| 결과 변화율 | 결과 변화율 D | outcome change rate | "결과 변화"(축약 허용), "기준과 결과가 달라진 경기의 비율"(Res-B-P1-1, 풀이). D에 "성능 저하" 금지 | D | Met-A-T-R2 | 예 |
| 승자 변화율 | 승자 변화율 W | winner change rate | "승자 변화"(축약 허용) | W | Met-A-T-R3 | — |
| 점수 변화 | Δ점수 | score change | — | Δ점수 | Met-A-T-R4 | — |
| 열화 유무만으로 생기는 결과 변화 | 흔들림 바닥 | outcome-change floor (chaotic divergence floor) | "바닥(혼돈)"(Res-D-P1-9), "바닥"(Tab6-R4) | — | Res-D-P1-9(이름은 Dis-B-T-R2에서 처음) | — |
| 명령을 늦게 따라가는 오차 | 둔한 형 오차 | sluggish (low-bandwidth) error | "둔한 오차"(축약 허용), "둔한 저대역 오차"(Int-P6-3) | — | Met-B-P2-2(Abs-5·Int-P6-3이 먼저 씀) | — |
| 명령 주위에서 빠르게 떠는 오차 | 진동형 오차 | oscillatory (high-frequency) error | "빠르게 떨리는 오차"(Abs-5, Dis-A-P1-4), "빠른 진동 오차"(Int-P6-3), "진동 오차"(Con-P1-3) → 진동형 오차. 영문 limit-cycle error 금지(σ 잡음 포함) | — | Met-B-P2-3 | — |
| 명령 없이 스스로 계속 떠는 상태 | 자체 진동(한계 순환) | limit-cycle oscillation | "스스로 떨었다"(Env-D-P2-1, Res-E-P4-3, Dis-A-P1-13) | — | Env-D-P2-1 | — |
| 처음 쓰는 시드 집합 | 새 시드 | fresh seeds | "처음 쓰는 시드"(Abs-5, Int-P5-5, Res-C-P2-7) → 새 시드 | rep, x8 | Met-C-P1-3 | — |
| 추종 오차를 쓰지 않는 예측 | 상수 예측 | constant predictor | — | — | Met-D-P1-3 | — |
| 제어기 성능을 떨어뜨리는 조작 | 열화 | degradation | "고장" 금지 | — | Env-A-P1-4 | 예 |
| 효과가 없도록 만든 대조 조작 | 가짜 변형 | sham degradation | — | κ = 1.000001 | Met-E-P1-3 | — |
| 조종면 입력이 각가속도에 주는 효과 | 제어효과 | control effectiveness | "조종면 효과"(Env-C-P1-3) → 제어효과 | G(§2 충돌 참고) | Env-B-P1-4 | — |
| INDI 측정 동기화용 2차 필터 | 동기화 필터 | synchronization filter | "필터"(축약 허용) | f_c | Env-B-P1-3 | — |
| 측정만 늦는 지연 | 비동기 측정 지연 | asynchronous measurement delay | "비동기 지연"(축약 허용) | n(틱) | Env-C-P1-8 | — |
| 측정과 입력 기록이 함께 늦는 지연 | 동기 측정 지연 | synchronous measurement delay | "동기 지연"(축약 허용) | n(틱) | Tab1-R5(본문 정의 문장 없음) | — |
| 유도 명령이 늦게 도착하는 지연 | 명령 전달 지연 | command transport delay | "명령 지연"(Tab6-R3) | n(틱) | Env-C-P1-6 | — |
| 이상화된 기준 구성 | 원래 구성 | original (idealized) configuration | "원래 제어기"(Dis-C-P1-2, Tab6-R1), "원래 기준 제어기"(Tab6-R2) → 원래 구성 | — | Env-D-P1-1 | — |
| 실제에 가깝게 바꾼 구성 | 실제형 구성 | realistic sensor–actuator configuration | "실제형 센서·구동기"(Abs-3, Dis-C-P1-2, Con-P1-4), "실제형 제어기"(Res-D-P1-6, Con-P2-1) → 실제형 구성 | — | Env-D-P1-2(Int-P5-5가 먼저 씀) | — |
| 같은 시드의 비교 경기 | 기준 경기, 짝 설계 | baseline game, paired design | — | — | Met-A-P1-1 | — |
| 전술끼리 모두 만나는 대진 | 리그 | round-robin league | — | — | Env-E-P1-1 | — |
| 전술 표현 방식 | 행동트리 전술 | behavior-tree tactic | — | — | Env-A-P1-3 | — |
| 판정 허용 범위 | 허용폭 | equivalence margin | — | δ_D, δ_점수 | Met-E-P1-3, Met-E-P1-8 | 예 |
| 판정 어휘 | 예측 성공 / 예측 실패 / 판정 불가 | prediction equivalent / prediction failed / inconclusive | 그 밖의 판정 말은 v3 §5.7 표를 그대로 쓴다 | — | Met-E-P1-5–7 | 예 |
| 상수 대비 덜 틀린 정도 | 기술 점수 | skill score | — | — | Met-D-P1-2(Int-P6-2가 먼저 씀) | — |
| 결과를 무작위로 뽑을 때의 D | 무상관 상한 | independence ceiling | — | — | Res-B-P1-4 | — |
| 분석 시점 표시 | 사전 등록 / 사후 | pre-registered / post hoc | "결과를 본 뒤의 비교"(Abs-3, Con-P1-1: 초록·결론의 풀이로 허용). 본문 정의는 원고 머리 ">" 메모에만 있음(S-06) | — | Rel-D-P1-2(사전 등록). 사후는 본문 정의 없음 | 예 |
| 조건 기준 표본 밖 | 표본 밖 예측 | out-of-sample prediction | — | — | Int-P5-3, Met-C-P1-6 | — |
| 대리 지표 | 대리 지표 | surrogate metric | — | — | Int-P3-5 | — |
| 공세 위치 비율 | 공세 비율 | offensive-geometry fraction | — | — | Res-E-P2-10 | — |
| 교전 없이 하는 제어기 시험 | 교전 없는 시험 비행 | engagement-free bench test | "시험 비행"(축약 허용), "교전 없는 표준 시험"(Dis-B-P1-6), "교전 없는 시험"(Res-E-P4-3), "표준 시험 입력"(Res-C-P3-5) | — | Tab2-R4(정의 문장 없음) | — |
| mae–D 직선의 기울기 | 기울기 | error-to-outcome slope | "비례 상수"(Abs-3, Dis-C-P1-2, Tab6-R1), "비례 관계"(Con-P1-4) → 기울기. 직선에 절편 0.144가 있어 "비례"는 부정확 | — | Res-B-P1-1 | — |
| 점수의 방향 | 성능의 방향 | direction of performance | "성과의 방향"(Res-E-P4-4) → 성능의 방향. D에는 쓰지 않음 | — | Met-A-T-R4 | — |
| 정밀 조준 기총 | 정밀 조준 기총 | [결정 필요: v3에 영문 없음] | — | — | Res-E-P2-16(Res-E-P2-7이 먼저 씀) | — |
| 반등 대비 | 반등 대비(6틱 − 2틱) | [결정 필요] | — | — | Res-E-P2-7(Met-E-P1-12가 먼저 씀) | — |
| 유형 대비 | 유형 대비(둔한 형 − 진동형 직선 잔차) | [결정 필요] | "직선 잔차 차이"(Tab4-R4) | — | Res-C-P5-1(Met-E-P1-12가 먼저 씀) | — |
| 시드 단위 t 구간 | 시드 t 구간 | seed-level t interval | "시드 단위 t 구간"(Met-E-P1-10). "잭나이프 t 구간"(Res-C-P2-5)은 다른 계산이면 따로 정의 [확인 필요: 부록 C 계산 방식] | — | Met-E-P1-10 | — |
| 부트스트랩 구간 | 퍼센타일 구간 | percentile interval | "95 % CI"(Res-B-P1-1, Tab3-RH), "95 % 구간"(Met-E-P1-5) → 한 말로 | — | 정의 문장 없음(Met-E-P1-2는 부트스트랩만) | — |

## 2. 기호

| 기호 | 뜻 | 첫 정의 위치 | 문제 |
|---|---|---|---|
| ν | 원하는 각가속도 | Env-B-P1-2 | — |
| K | 각속도 게인(9 s⁻¹) | Env-B-P1-2 | 기여 목록 K1–K3(Int-P6)과 글자가 겹침(G-32 검토) |
| ω_cmd | 각속도 명령 | 정의 없음 | G-30 |
| ω_f, ω̇_f | 필터를 거친 측정 각속도·각가속도 | Env-B-P1-3 | — |
| G | 제어효과 행렬 | Env-B-P1-4 | 하중 단위 "G"(Env-A-P1-3, Env-B-P1-8, Env-E-P1-7)와 충돌(G-32) |
| u, Δu | 조종면 명령, 증분 | 정의 없음 | G-30 |
| u_f | 필터를 거친 조종면 위치 | Env-B-P1-5 | — |
| κ | 제어효과를 κ배로 믿게 하는 배율 | Env-C-P1-3 | — |
| Δt | 제어 주기 1/120 s | Env-C-P1-4 | — |
| n | 지연 틱 수 | Env-C-P1-6 | — |
| k_q | 피치 각속도 게인 배율 | Tab1-R3 | — |
| σ | 각속도 되먹임 백색잡음의 크기 | Tab1-R4 | — |
| f_c | 동기화 필터 차단주파수 | Tab1-R1 | — |
| δ_D, δ_점수 | 허용폭 | Met-E-P1-3, Met-E-P1-8 | — |
| b | mae에 대한 Δ점수의 기울기 | 정의 없음(Res-E-P2-3) | G-30 |
| D, W, mae | §1 참고 | Met-A-T | 식이 없음(A-35) |

## 3. 원고에서 정의 없이 쓴 약어·이름 (S-06)

| 약어·이름 | 처음 쓴 곳 | 상태 |
|---|---|---|
| INDI | 본문 Int-P1-1(초록에는 풀어 씀) | 본문 첫 등장에서 다시 풀어 써야 함 |
| RMS, CI, KCAS | Met-D-P1-2, Res-B-P1-1, Env-E-P1-3 | 풀어 쓰기 없음 |
| E3X, E4, ASYM, P1–P9, P5, P7 | Met-E-P1-13, Met-F-P1-6, Met-F-P1-2, Met-F-P1-2, Met-E-P1-10, Res-E-P4-3 | E4·P 번호는 정의 없음, E3X·ASYM은 정의보다 먼저 씀 |
| GunTracker, Extender, RedPrime | Tab4-R5, Tab4-R5, Res-E-P2-8 | 전술 설명 없음 [확인 필요: `kit/agents/main/*.yaml`] |
| 이중펄스 | Res-C-P3-3 | 풀이 없음 |
| 잭나이프 t 구간 | Res-C-P2-5 | 방법 절에 정의 없음 |
