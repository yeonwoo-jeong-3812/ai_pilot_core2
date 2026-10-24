# 그림 5 재생 기록 (서술, 판정 없음)

대진: Reactive 대 RedPrime

시드 main-0, 시나리오 neutral, 기록 대상은 청 기체. 선택 규칙과 조건은 `fig5_timeseries.py` 머리말.

| 조건 | 원자료와 같은 경기 | 승자 | 종료 사유 | 청 기체 mae [°/s] | 청 기체 비행 시간 [s] |
|---|---|---|---|---|---|
| BASE | 예 | RedPrime | health_zero | 0.273 | 197.7 |
| R_sigma_dps_6 | 예 | RedPrime | health_zero | 1.719 | 151.3 |
| R_kappa_100 | 예 | RedPrime | health_zero | 1.684 | 134.7 |

조건 평균(`p3_output.md`): κ 100 mae 1.64·D 0.332, σ 6 mae 1.62·D 0.261. 그림은 한 경기의 예시이며, 유형 효과의 근거는 P4·P7·P8의 사전 등록 대비다.
