# 도그파이트 러너 자체 점검 — commit cbd6147b5fdbc7752d6280334173a9af6a74df4d

- 실행: 2026-09-26 14:35:12, 벽시계 46 s, 경기 15, 트리 깨끗함=True
- Python 3.11.9
- 결과: **전체 통과** (21/21)

| 검사 | 결과 | 근거 |
|---|---|---|
| 기준 주입+기록 = 배치 그대로 (headon) | PASS | winner blue vs blue / condition timeout vs timeout / time_s 300.0 vs 300.0 / hp_blue 34.58333333333382 vs 34.58333333333382 / hp_red 6.250000000000266 vs 6.250000000000266 |
| 기준 주입+기록 = 배치 그대로 (neutral) | PASS | winner draw vs draw / condition no_contact vs no_contact / time_s 300.0 vs 300.0 / hp_blue 100.0 vs 100.0 / hp_red 100.0 vs 100.0 |
| 기준 주입+기록 = 배치 그대로 (perch_defense) | PASS | winner red vs red / condition timeout vs timeout / time_s 300.0 vs 300.0 / hp_blue 48.43750000000002 vs 48.43750000000002 / hp_red 100.0 vs 100.0 |
| 기준 주입+기록 = 배치 그대로 (perch_offense) | PASS | winner red vs red / condition timeout vs timeout / time_s 300.0 vs 300.0 / hp_blue 65.8333333333328 vs 65.8333333333328 / hp_red 79.89583333333242 vs 79.89583333333242 |
| WEZ·ATA 재계산 = 엔진 판정 (headon) | PASS | WEZ 차 8.88e-15 s, ATA 차 1.04e-12°, 틱 36000 |
| WEZ·ATA 재계산 = 엔진 판정 (neutral) | PASS | WEZ 차 0.00e+00 s, ATA 차 4.41e-13°, 틱 36000 |
| WEZ·ATA 재계산 = 엔진 판정 (perch_defense) | PASS | WEZ 차 7.55e-15 s, ATA 차 1.71e-13°, 틱 36000 |
| WEZ·ATA 재계산 = 엔진 판정 (perch_offense) | PASS | WEZ 차 4.88e-15 s, ATA 차 8.67e-13°, 틱 36000 |
| 결정론: 같은 경기 두 번 → 모든 지표 동일 | PASS | 다른 열 [] |
| 주입 효과: λ_q 25 → 경기 중 J_q 가 기준과 다름 (A27 §7-1) | PASS | J_q 기준 0.2107 → λ25 0.3351; 결과 blue/timeout → red/health_zero |
| 난류(중) 결정론: 두 번 → 동일 | PASS | 다른 열 [] |
| 난류(중) 효과: 기준과 다름 | PASS | J_q 기준 0.2107 → 난류 0.2793 |
| 잡음 0.03 + 지연 4 틱 결정론: 두 번 → 동일 | PASS | 다른 열 [] |
| WEZ·ATA 재계산 = 엔진 판정 (λ25) | PASS | WEZ 차 2.75e-14 s |
| WEZ·ATA 재계산 = 엔진 판정 (난류) | PASS | WEZ 차 1.15e-14 s |
| WEZ·ATA 재계산 = 엔진 판정 (잡음+지연) | PASS | WEZ 차 8.44e-15 s |
| WEZ·ATA 재계산 = 엔진 판정 (가짜 짝) | PASS | WEZ 차 8.88e-15 s |
| 프록시: 잡음만(N=0) → PlantProxy 와 비트 동일 | PASS | 최대차 0 |
| 프록시: 지연만(σ=0) → PlantProxy 와 비트 동일 | PASS | 최대차 0 |
| 프록시: 잡음+지연 N=4 → 잡음 측정값을 4 틱 늦게 돌려줌 | PASS | 대조 236 틱, 최대차 0 |
| 결합 설계: 2^(6-2) 해상도 IV·주효과 직교 (A31 §6) | PASS | 칸 16, 균형=True, 주효과 직교=True, 해상도 IV=True, A×C 별칭 ['BE'], A×D 별칭 ['EF'] |

정보(판정 아님): 가짜 짝(λ_q 1+1e-6, headon): blue/timeout/300.00s HP 34.6-6.3 → blue/timeout/300.00s HP 34.6-6.3

경기당 벽시계 [s]: 37.7, 37.6, 38.0, 37.3, 39.8, 38.8, 39.8, 39.0, 39.6, 23.0, 8.8, 8.7, 40.7, 40.7, 34.3
