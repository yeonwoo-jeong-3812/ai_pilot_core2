# E1 보고서

판 2688, 시드 8개 (cal-0 … cal-7), 참가자 8명, 시나리오 headon, perch_offense, neutral

## 1. 승·무·패와 종료 사유 (전 참가자 합계, 무접촉은 양쪽 패)

종료 사유: health_zero 격추, hard_deck 저고도 이탈 패, timeout 시간 종료 후 HP 비교, no_contact 무접촉, stall 실속.

| 조건 | 경기 | 승 | 무 | 패 | health_zero | hard_deck | timeout | no_contact | stall | 피치 추종 상관 | 피치 추종 오차 [°/s] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BASE | 1344 | 1312 | 0 | 1376 | 757 | 378 | 165 | 32 | 12 | 0.964 | 0.24 |
| SHAM | 1344 | 1310 | 2 | 1376 | 759 | 378 | 162 | 33 | 12 | 0.963 | 0.24 |

## δ 등록

SHAM 짝 차이 |Δ점수| (참가자 × 시드 64개)의 95 백분위수 = 5.55점, 2배 = 11.10점, 실용 바닥 = 3.0점(1승) → δ = 11.10점

등록: C:\Users\User\OneDrive\Desktop\cadet_research\cadet_research\kit\out\cal\delta.json

## 2. 참가자별 점수 변화 (리그 한 바퀴당 평균, 기준 조건 대비, δ = 11.10점)

신뢰구간은 99.38 % (한 조건 안 참가자 8명 Bonferroni), 시드 8개 부트스트랩.

BASE 점수(한 바퀴 평균): RedPrime 93.8, TwoCircle 87.4, EnergyFighter 69.8, GunTracker 61.9, PurePursuer 54.4, Reactive 54.4, LagAngler 44.6, Extender 25.9

| 변형 − 기준 | RedPrime | TwoCircle | EnergyFighter | GunTracker | PurePursuer | Reactive | LagAngler | Extender |
|---|---|---|---|---|---|---|---|---|
| SHAM − BASE | +0.4 [+0.0, +1.5] 차이 없음 | -1.1 [-3.4, +0.0] 차이 없음 | -1.5 [-4.5, +0.0] 차이 없음 | +0.8 [+0.0, +2.2] 차이 없음 | +0.0 [-1.9, +1.9] 차이 없음 | -0.2 [-1.5, +0.5] 차이 없음 | +0.4 [-1.4, +1.9] 차이 없음 | +0.9 [-1.6, +4.6] 차이 없음 |

조건별 요약 (없음/불가/있음 참가자 수): SHAM 8/0/0

## 3. 순위 (시드 합산 점수)

| 변형 vs 기준 | Kendall τ | τ 95 % CI | 1위 유지 비율 (부트스트랩) | 변형의 순위 |
|---|---|---|---|---|
| BASE vs BASE | +1.00 | [+1.00, +1.00] | 1.00 | RedPrime(750) > TwoCircle(699) > EnergyFighter(558) > GunTracker(495) > Reactive(435) > PurePursuer(435) > LagAngler(357) > Extender(207) |
| SHAM vs BASE | +0.98 | [+0.93, +1.00] | 0.98 | RedPrime(753) > TwoCircle(690) > EnergyFighter(546) > GunTracker(501) > PurePursuer(435) > Reactive(433) > LagAngler(360) > Extender(214) |

BASE 1위: RedPrime

## 4. 경기 일치율 (같은 대진·시나리오·시드에서 승자와 종료 사유가 기준 조건과 같은 경기의 비율)

무상관 기준 0.614 (BASE 기준): 변형 경기의 결과가 같은 대진·시나리오 BASE 결과 분포에서 독립으로 뽑혔다면 기대되는 일치율. 이 값에 가까우면 개별 경기는 사실상 새로 뽑은 것과 같다.

| 변형 vs 기준 | 경기 일치율 | 95 % CI (시드 단위) |
|---|---|---|
| SHAM vs BASE | 0.981 | [0.971, 0.989] |

