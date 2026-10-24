# 주장 원장 v1 — PAPER_DRAFT_v2 (가이드 12.2)

작성 2026-10-24. `REVIEW_FORMAT_v1.md`의 입력(A-14, T-15, V-22). 원고 v2의 제목부터 Ⅶ 결론까지(부록·그림 목록·참고문헌 후보 표 제외)에서 뽑은 수치 398개가 아래 71줄 중 하나와 이어진다(문장 ID 기준 전수 대조, 빠진 수치 0개). 문장 ID는 `PAPER_DRAFT_v2_IDS.md`를 따른다.

- ID: `C-` 결과 주장(PAPER_SKELETON §11의 C-01–C-22를 이어받고, 쪼갠 것은 a·b·r 등을 붙임), `N-` 설정·방법 수치, `D-` 논의 수치.
- 상태: 확정(파일 값과 일치), 사전 등록 / 사후 / 서술 / 탐색(STUDY_GUIDE_v3 §7.3 구분), 계산(다른 줄에서 유도), 확인 필요(출처 미비).
- 숫자를 바꿀 때는 이 표를 먼저 고치고, 원고는 "등장 위치" 열로 따라간다(R-02).

| ID | 주장 | 값 | 조건(N, 설정) | 출처(파일·줄) | 등장 위치 | 상태 |
|---|---|---|---|---|---|---|
| N-01 | 조건 하나 = 리그 168경기 × 시드 8 = 1,344경기 | 1,344, 168, 8 | 대칭 리그, 참가자 8, 시나리오 3 | kit/experiments.py(AGENTS_MAIN, LEAGUE, salts 8); kit/out/main/report_E2.md 11행 | Int-P2-3, Env-E-P1-2, Dis-B-P1-4 | 확정 |
| N-02 | 전체 약 14만 경기 | 14, 140,000 | 본실험 71,568 + 추가 실험 | README.md §5.1 85–99행 실험별 경기 수의 합: 본실험 71,568 + ASYM 10,080 + E3X 8,064 + P2-b 1,008 + P4 16,128 + P6 5,376 + P5 4,704 + P7 12,096(+탐침 672) + P8 7,056 + P9-c 2,688 + P9-b 1,344 = 140,784(탐침 제외 140,112). 재생(P2-a·P3·P9-a)은 제외 | Abs-2, EAbs-2 | 계산(본문에 합계 없음 → A-14) |
| N-03 | 행동트리 전술 8종, 시나리오 3종 | 8, 3 | E2·E3 참가자 | kit/experiments.py(AGENTS_MAIN, LEAGUE) | Abs-2, Env-E-P1-1 | 확정 |
| N-04 | JSBSim 1.3.1 | 1.3, 1 | — | kit/requirements.txt | Env-A-P1-1 | 확정 |
| N-05 | 갱신 주기 전술 20 Hz, 유도 60 Hz, 제어기·물리 120 Hz | 20, 60, 120 | — | kit/config/sim.yaml 3–5행 | Env-A-P1-3, Met-A-T-R1 | 확정 |
| N-06 | K = 9 s⁻¹, 동기화 필터 25 Hz(2차) | 9, 25 | 기준 제어기 | kit/aircombat/engine/pilot.py 59행; kit/aircombat/control/indi.py 48행 | Env-B-P1-2, Env-B-P1-3 | 확정 |
| N-07 | 내장 FLCS와 겹치면 달성 G가 4.5–7.2 G에 묶임 | 4.5, 7.2 | 우회 이전 측정 | PAPER_SKELETON.md 103행(원 측정 기록 경로 없음) | Env-B-P1-8 | 확인 필요: 원 로그 경로(V-22) |
| N-08 | Δt = 1/120 s = 8.3 ms, κ는 필요량의 1/κ만 움직임 | 1, 120, 8.3 | — | kit/config/sim.yaml 3행; kit/run.py 44–45행 | Env-C-P1-4, Tab1-Cap | 확정 |
| N-09 | κ 안정 경계 ≈ 0.42, 추종 경계 ≈ 8.4 (선행 실험) | 0.42, 8.4 | 선행 실험(미발표) | 팀 브랜치 research/l3-indi-paper-v2: ai-combat-core2-main/docs/COMPARISON_OLD_VS_CADET.md 56행 | Env-C-P1-5 | 확인 필요: 미발표 선행 연구 인용 방식(T-30) |
| N-10 | 열화 수준(표 1) | 25, 12, 5, 0, 6, 20, 2, 50, 100, 400, 0.25, 3, 0.3, 10, 16, 24, 48, 0.4, 4 | E2 20조건, E3 22조건, E3X 6조건, P8 | kit/experiments.py 88–92·149행; kit/supplementary/p8_conds.json | Tab1-R1, Tab1-R2, Tab1-R3, Tab1-R4, Tab1-R5, Tab1-R6, Tab1-R7 | 확정 |
| N-11 | κ 25의 응답 시상수 ≈ 25/120 = 0.21 s | 0.21, 25 | 단순 모형 어림 | N-08에서 유도(계산) | Tab1-R2 | 계산 |
| N-12 | 원래 구동기: 전 행정 0.3 s 속도 제한 | 0.3 | — | kit/supplementary/p3_timeseries.py 38행(f16.xml kinematic 0.3 s) | Env-D-P1-4, Tab2-R1 | 확정 |
| N-13 | 실제형 구동기 1차 지연 20.2 rad/s, 승강타 60 °/s, 에일러론 80 °/s | 20.2, 60, 80 | P7·P8·P9-c | kit/supplementary/p7_realistic.py 7·27행 | Tab2-R1 | 확정 |
| N-14 | 실제형 이득 여유 16.4 dB, 위상 여유 59.3°(기준 6 dB, 45°) | 16.4, 59.3, 6, 45 | 선형 이산 모형, K 9, 25 Hz | kit/supplementary/p7_design_output.md §2. 기준값 6 dB·45°는 문헌 필요 | Env-D-P1-7 | 확정(기준값은 [확인 필요: 출처]) |
| N-15 | 지연 견딤: 원래 약 1틱부터 자체 진동, 실제형 5틱까지 안정; 적합 20조건 중 10이 자체 진동 | 1, 5, 20, 10 | 교전 없는 시험 비행, 25 Hz | kit/supplementary/p7_design_output.md §1; p7_bench_output.md 13–14행; p1_output.md 113행 | Tab2-R4, Tab2-R5, Tab6-R2 | 확정 |
| N-16 | 종료 규칙: 300 s, 1,000 ft, 100 KCAS 누적 10 s, 체력 0 | 300, 0, 1,000, 100, 10 | — | kit/aircombat/engine/match.py 27–30·450·487–492행; kit/aircombat/bridge.py 60행 | Env-E-P1-3, Env-E-P1-4 | 확정 |
| N-17 | 점수 승 3·무 1·패 0, 무접촉 0 | 3,, 1,, 0, 3, 1 | — | kit/analyze.py 56–69행 | Env-E-P1-6 | 확정 |
| N-18 | 리미터 +9 G/−3 G, 받음각 25°에서 1 G | +9, −3, 25, 1 | — | kit/aircombat/control/limiter.py 73–87행 | Env-E-P1-7 | 확정 |
| N-19 | 기총 500–3,000 ft, 2°·10°·20°·30° 안 100·75·50·25 % | 500, 3,000, 2, 10, 20, 30, 100, 75, 50, 25 | 원래 기총 | kit/aircombat/geometry/units.py 164–176행 | Env-E-P1-8 | 확정 |
| N-20 | Δ점수는 리그 한 바퀴 42경기당 | 42 | 한 기체 열화 | kit/analysis_extra.py(asym 셀: 대상별·시드별 42경기) | Met-A-T-R4 | 확정 |
| N-21 | 오차를 1 Hz에서 둘로 나눔 | 1 | P3 | PREREG_P3.md(경계 1 Hz); kit/supplementary/p3_timeseries.py SPLIT | Met-B-P1-3, Res-C-P3-2, Res-C-P4-5, Res-C-P4-7, Dis-A-P1-9 | 확정 |
| N-22 | 시드 수 cal 8, main 8, gen 4, rep 8, x8 8; 새 시드 8 | 8, 4 | — | kit/experiments.py; kit/out/{cal,main,gen,rep,p8}/games.csv | Met-C-P1-2, Met-C-P1-3, Res-C-P2-7, Tab6-R7 | 확정 |
| N-23 | 적합 E2 20조건, 검증 E3 22조건 | 20, 22 | main 8시드 | kit/experiments.py 88–104행 | Met-C-P1-4, Met-C-P1-5, Res-B-P1-7 | 확정 |
| N-24 | 곡선 모양 LOO: 직선 0.034, 제곱근 0.041, 로그 0.078 | 0.034, 0.041, 0.078 | E2 20조건 | kit/out/main/curve.json(loo_rms) | Met-D-P1-1 | 확정 |
| N-25 | 기술 점수 = 1 − RMS(곡선)/RMS(상수) | 1 | — | kit/out/reanalysis_p0/report_p0.md A | Met-D-P1-2 | 정의 |
| N-26 | 시드 부트스트랩 2,000회 | 2,000 | — | kit/predict.py(N_BOOT) | Met-E-P1-2 | 확정 |
| N-27 | δ_D = 0.079 = 2 × SHAM(κ = 1.000001) 시드별 D 95 백분위 | 0.079, 1.000001, 95 | cal 8시드 | kit/out/cal/tolerance.json | Met-E-P1-3, Met-E-P1-5, Res-A-P1-1 | 확정 |
| N-28 | δ_점수 11.10 = 2 × SHAM |Δ점수| 64개 95 백분위; 대상 3명, 98.33 % | 11.10, 64, 95, 3, 98.33 | cal 8시드 × 참가자 8 | kit/out/cal/delta.json; PREREG_EXTRA.md 43행 | Met-E-P1-8 | 확정 |
| N-29 | 시드 t 재계산: 핵심 5건 유지, 한 기체 열화 개별 칸 30개 중 8개 판정 불가 | 5, 30, 8 | 사후 | kit/supplementary/appc_tinterval_output.md | Met-E-P1-12, Met-E-P1-13, Tab6-R7 | 사후 |
| N-30 | 절전으로 잘린 경기 41 = 본실험·E4 28 + 한 기체 열화 13, 이후 0 | 41, 28, 13, 0 | — | kit/supplementary/rerun_wallclock_output.md; kit/out/asym/wallclock_removed.csv; kit/out/{main,gen}/games.csv | Met-F-P1-5, Met-F-P1-6, Met-F-P1-7, Met-F-P1-8 | 확정 |
| N-31 | 재생 일치 2,744/2,744, 252/252, 252/252 | 2,744, 2,744,, 252, 252, | 같은 PC | kit/supplementary/p3_output.md; asym_replay_output.md; p9ab_output.md | Met-F-P1-9, Res-C-P3-1, Res-E-P2-9 | 확정 |
| C-07a | 가짜 변형 D 시드별 0.000–0.048 | 0.000, 0.048, 0.079 | cal 8시드 | kit/out/cal/report_predict_E1.md 3행 | Res-A-P1-1 | 확정 |
| C-01 | 원래 구성 D = 0.144 + 0.0531·mae, mae 1 °/s당 0.053 [0.050, 0.056] | 1, 0.053, 95, 0.050, 0.056, 0.144, 0.0531 | E2 20조건, main 8시드, 조건당 1,344경기 | kit/out/main/curve.json; kit/out/reanalysis_v2/report_reanalysis_v2.md 11행 | Res-B-P1-1, Res-B-P1-2, Tab6-R1 | 확정 |
| C-01b | 시드 절반으로 따로 잰 상관 0.969, 기울기 0.0543 | 0.969, 0.0543 | 4+4 분할 35가지, 42조건 | FEEDBACK_FOR_CADET_v2.md 179–180행 | Res-B-P1-3 | 사후 |
| C-01c | 무상관 상한 0.460, 적합 20 중 7조건 위, 상한 아래 13조건 기울기 0.0533 | 0.460, 20, 7, 13, 0.0533 | E2 | kit/out/reanalysis_p0/report_p0.md 55·58·77행 | Res-B-P1-4, Res-B-P1-5, Res-B-P1-6 | 사후 |
| C-P0 | 처음 보는 22조건 RMS 0.041 대 상수 0.074, 기술 점수 0.44 [0.38, 0.46](44 %), 다른 상수 0.40, 검증 평균 0.30 | 22, 0.041, 0.074, 44, 0.44, 0.38, 0.46, 0.40, 0.30 | E3 22조건, main 8시드 | kit/out/reanalysis_p0/report_p0.md A; kit/supplementary/derived_numbers_output.md §1 | Res-B-P1-7, Res-B-P1-8, Res-B-P1-9, Res-B-P1-10, Abs-3, EAbs-3 | 사후 |
| C-02 | E3 원인 묶음 평균 오차 −0.003–+0.021, 모두 예측 성공(표 3) | −0.003, +0.021, −0.021, +0.015, +0.001, +0.040, +0.006, −0.008, +0.019, +0.003, −0.007, +0.011, −0.011, +0.013, 95 | E3 22조건, main 8시드, 퍼센타일 2,000회 | kit/out/main/report_predict_E3.md 38–42행 | Res-B-P1-11, Tab3-RH, Tab3-R1, Tab3-R2, Tab3-R3, Tab3-R4, Tab3-R5 | 사전 등록 |
| C-W | D의 약 3분의 1(E2 0.361 중 0.115)이 종료 사유만 변화; W 기울기 0.035, W 기술 점수 0.43 | 3, 1, 0.361, 0.115, 0.035, 0.43 | E2·E3 | kit/out/reanalysis_p0/report_p0.md C; kit/supplementary/derived_numbers_output.md §7 | Res-B-P1-13, Res-B-P1-14, Tab6-R4 | 사후 |
| C-09 | E3X: 동기 24틱 −0.343(같은 mae 10 °/s에서 0.629 대 0.347), κ 100·400 +0.10–0.13 | 24, 0.343, 10, 0.629, 0.347, 100, 400, 0.10, 0.13 | E3X 6조건, main 8시드 | kit/out/extra_report/report_extra.md 80–81·91–92행; kit/supplementary/p3_output.md 80행(동기 24 D 0.347); intro_example_output.md §4(F5_D6 0.629) | Res-C-P2-2, Res-C-P2-3, Res-C-P2-4 | 사전 등록 |
| C-09b | E3X κ 묶음 잭나이프 t 하한 +0.072, 곡선 고정 +0.081 | +0.072, +0.081 | main 8시드 | kit/supplementary/appc_tinterval_output.md 나 | Res-C-P2-5 | 사후 |
| C-03 | 원인별 기울기 0.3배(k_q)–3.8배(κ) | 0.3, 3.8 | E3 | kit/out/reanalysis_v2/report_reanalysis_v2.md 12–13행 | Res-C-P2-6 | 사후 |
| C-09r | 새 시드 재현: 동기 24 −0.343 → −0.320 [−0.350, −0.292], κ +0.114 → +0.121 [+0.092, +0.149] | 24, −0.343, −0.320, −0.350, −0.292, 100, 400, +0.114, +0.121, +0.092, +0.149 | rep 8시드 | kit/supplementary/p4_output.md; kit/out/extra_report/report_extra.md 91–92행 | Tab4-R1, Tab4-R2 | 사전 등록 |
| C-15 | 같은 mae에서 비동기 − 동기 D 차이 +0.282 → +0.236 [+0.219, +0.253] | +0.282, +0.236, +0.219, +0.253 | rep 8시드 | kit/supplementary/p4_output.md(T-C); FEEDBACK_FOR_CADET_v7.md | Tab4-R3 | 사전 등록 |
| C-14 | 둔한 − 진동형 잔차 +0.069(사후) → +0.060 [+0.048, +0.074] (κ 50·100) | +0.069, +0.060, +0.048, +0.074, 50, 100 | rep 8시드, 등록 직선 | kit/supplementary/p4_output.md(T-D); FEEDBACK_FOR_CADET_v7.md | Tab4-R4, Res-C-P5-3 | 사전 등록 |
| C-08r | 한 기체 열화 반등(6틱 − 2틱) +46.5/+36.1 → +50.9/+35.2 | 6, 2, +46.5, +36.1, +50.9, +35.2 | main·rep 8시드, 98.33 % | kit/out/extra_report/report_extra.md; kit/supplementary/p4_output.md(T-B); appc_tinterval_output.md 다 | Tab4-R5, Res-E-P2-7 | 사전 등록(시드 t는 사후) |
| C-12 | 교전 명령 1 Hz 이상 5.6 %(시험 입력 14.4 %), 중앙 0.14 Hz, 대부분 0.5 Hz 아래 | 1, 5.6, 14.4, 0.14, 0.5 | BASE 112 기록(main-0, 중립) | kit/supplementary/p3_output.md 21–23행 | Res-C-P3-2, Res-C-P3-3, Res-C-P3-4, Dis-A-P1-2 | 사전 등록 |
| C-10 | 시험 비행 지표 RMS 0.068 대 상수 0.074 | 0.068, 0.074 | E3 22조건 | kit/supplementary/p1_output.md | Res-C-P3-6 | 사전 등록 |
| C-F5 | 그림 5 예시 mae 1.68 대 1.72 | 1.68, 1.72 | main-0, 중립, 한 경기 | kit/supplementary/fig5_output.md | Res-C-P4-2 | 서술 |
| C-TY | 둔한 형 시간 이동 0.14–0.99 s; 진동형 1 Hz 이상 몫 67–98 %, 약 2–3 Hz, 포화 최대 95 % | 0.14, 0.99, 67, 98, 1, 2, 3, 95 | P3 재생(main-0, 중립 56대진 × 49조건) | FEEDBACK_FOR_CADET_v6.md 53행; kit/supplementary/p3_output.md §3 | Res-C-P4-4, Res-C-P4-5 | 서술 |
| C-13 | 1 Hz 대역 분해: 두 성분 상관 0.957, 나아지지 않음 | 1, 0.957 | E2 | kit/supplementary/p3_output.md 16행 | Res-C-P4-7 | 사전 등록 |
| C-19/20 | 유형 대비 +0.172 [+0.144, +0.201](실제형 κ 25·50), +0.330 [+0.299, +0.358](명령 지연 0.4 s +0.540, 지면 충돌 382 → 942; k_q 0.25 +0.119) | 25, 50, +0.172, +0.144, +0.201, +0.330, +0.299, +0.358, 0.4, +0.540, 382, 942, 0.25, +0.119 | P7 main 8시드; P8 x8 8시드, 조건당 1,344경기 | kit/supplementary/p7_output.md 38행; p8_output.md; derived_numbers_output.md §5 | Res-C-P5-4, Res-C-P5-5, Res-C-P5-6, Res-C-P5-7 | 사전 등록 |
| C-W2 | 승자 변화로 본 유형 대비 +0.039, +0.122, +0.199 | +0.039, +0.122, +0.199 | P4·P7·P8 | kit/supplementary/derived_numbers_output.md §7 | Res-C-P6-1 | 사후 |
| C-18 | 실제형 기울기 0.022(원래의 약 40 %), 비동기 6조건(2–12틱); 원래 곡선 평균 −0.169, 2틱 −0.054·8틱 −0.129·12틱 −0.476; 범위(0.19–10.57) 안 5조건 −0.108, 8틱까지 −0.061 | 6, 2, 12, 0.022, 40, 0.169, −0.054, 8, −0.129, −0.476, 0.19, 10.57, 5, 10, −0.108, −0.061 | P7 main 8시드 | kit/supplementary/p7_output.md §1–2; derived_numbers_output.md §2 | Res-D-P1-1, Res-D-P1-2, Res-D-P1-3, Res-D-P1-4, Abs-3, EAbs-3, Dis-C-P1-2 | 사전 등록(범위별 값은 사후) |
| C-18b | 같은 mae(약 4.7 °/s)에서 D 0.26(실제형) 대 0.39(원래) | 4.7, 0.26, 0.39 | P7 F25_D8 4.62/0.260, 원래 F25_D2 4.86/0.394 | kit/supplementary/p7_output.md §1; derived_numbers_output.md §4 | Res-D-P1-5 | 서술 |
| C-18c | 실제형 4틱까지 mae 0.26–0.28(기준과 같음), 원래 같은 지연 4.9–6.1 | 4, 0.26, 0.28, 4.9, 6.1 | P7 | kit/supplementary/p7_output.md §1 | Res-D-P1-6, Res-D-P1-7 | 서술 |
| C-07 | 흔들림 바닥 D 0.10–0.14(W 0.08–0.10), 약 0.10–0.17 | 0.10, 0.14, 0.08, 0.17 | 실제형 2·4틱; 원래 mae 0.19–0.22 4조건 | kit/supplementary/derived_numbers_output.md §3 | Res-D-P1-8, Tab6-R4 | 사후 |
| C-E | 모두 열화해도 승부 수 1,307 대 1,313 | 1,307, 1,313 | BASE 대 F5_D6, main 8시드 | kit/out/main/report_E2.md 11·31행 | Res-E-P1-2 | 확정 |
| C-08 | ASYM b = +1.59 [+1.08, +2.10]; GunTracker 25 Hz 2틱 −19.5, 6틱 +27.0; RedPrime −7.1–+2.6 | +1.59, +1.08, +2.10, 25, 2, 19.5, 6, 27.0, 1, −7.1, +2.6 | main 8시드, 98.33 % | kit/out/extra_report/report_extra.md(A1·A2); kit/supplementary/appc_tinterval_output.md 가 | Res-E-P2-3, Res-E-P2-4, Res-E-P2-8 | 사전 등록 |
| C-22 | P9-a: 공세 비율 0.011 → 0.165(15배), 수세 0.042 → 0.026, 거친 조준 5–30°, 정조준(2–5°) 0.0043 | 252, 6, 0.011, 0.165, 15, 0.042, 0.026, 5, 30, 2, 0.0043 | 재생 252경기(main-0·1) | kit/supplementary/p9ab_output.md | Res-E-P2-9, Res-E-P2-10, Res-E-P2-11, Res-E-P2-12, Res-E-P2-13 | 서술(사전 지정) |
| C-P2b | 정밀 조준 기총(2°·5°)에서 반등 64 % 남음 | 2, 5, 64 | main 8시드, 98.33 % | kit/supplementary/p2b_output.md | Res-E-P2-16 | 사전 등록 |
| C-P9b | 열화 없이 2.2 Hz 흔들림 주입: +3.8, +25.1점, 판정 불가 | 2.2, +3.8, +25.1 | main 8시드, 98.33 % | kit/supplementary/p9ab_output.md | Res-E-P2-17 | 사전 등록 |
| C-21 | P9-c 실제형 6·8·10·12틱: GunTracker −1.4 → −0.4 → −4.5 → −7.4, Extender +0.1 → −3.0 → −5.0 → −9.8, 반등 없음; 실제형도 6틱부터 자체 진동 | 6, 8, 10, 12, −1.4, −0.4, −4.5, −7.4, +0.1, −3.0, −5.0, −9.8 | main 8시드, 짝은 P7 실제형 BASE | kit/supplementary/p9c_output.md; p7_bench_output.md 14행 | Res-E-P3-2, Res-E-P3-3, Res-E-P3-4, Res-E-P4-3, Dis-A-P1-13 | 사전 등록 |
| C-05/17 | 다른 참가자 12종(시드 4): ΔD 0.000 [−0.027, +0.026], t [−0.049, +0.049]; 절대 +0.045 [+0.020, +0.074], t [−0.005, +0.096]; 원래 참가자 −0.000; ±0.05 | 12, 4, 0.000, −0.027, +0.026, −0.049, +0.049, +0.045, +0.020, +0.074, −0.005, +0.096, −0.000, 0.05 | gen 4시드 | kit/supplementary/e4_tinterval_output.md; e4_boot_output.md; p5_output.md; FEEDBACK_FOR_CADET_v8.md 107행 | Tab5-R1, Tab5-R2, Tab6-R5 | E4 판정은 사후, P5 사전 등록 |
| C-16 | 정밀 조준 기총 대칭: 기울기 0.045 [0.040, 0.051] 대 0.054(6조건·시드 4), 등록 0.053, 수준 +0.08 | 2, 5, 0.045, 0.040, 0.051, 0.054, 6, 4, 0.053, +0.08 | main-0–3 | kit/supplementary/p6_output.md | Tab5-R3 | 사전 등록 |
| D-01 | mae를 D 단위 ±0.02로 재는 데 1–150경기(중앙값 2) | 0.02, 1, 150, 2 | 조건별 | FEEDBACK_FOR_CADET_v3.md 53행(D-7) | Dis-B-P1-2 | 사후 |
| D-02 | 검증 범위 mae ≲ 3.6 °/s, ±0.03–0.05로 사용 | 3.6, 0.03, 0.05 | E3 최대 mae 3.55(k_q 2) | kit/out/main/report_predict_E3.md 20행; FEEDBACK_FOR_CADET_v3.md 57행 | Dis-B-P1-3 | 사후 |
| D-03 | 재보정 약 2.7만 경기 = 20조건 × 1,344 | 2.7, 20, 1,344 | 원래 구성 설계 기준 | N-01·N-23에서 계산 | Dis-B-P1-4 | 계산 |
| D-04 | 느린 명령·평균 0(해석), 동기 24틱 절반, 1 Hz 대역 분해 실패 | 0, 24, 1 | 해석 | Ⅵ-A의 해석; C-12·C-13·C-15 | Dis-A-P1-4, Dis-A-P1-7 | 해석 |
| D-05 | 실제형 비례 상수 약 40 %, 한계 22항목 | 40, 22 | — | C-18; PAPER_OUTLINE_FINAL.md §4 | Dis-C-P1-2, Dis-C-P1-7 | 확정 |
| D-06 | 명령 지연 0.4 s > 비행성 최악 수준 약 0.25 s; k_q 0.25; κ 400 시상수 3.3 s | 0.4, 0.25, 400, 3.3 | — | P8(kit/supplementary/p8_conds.json); 0.25 s는 [확인 필요: MIL-F-8785C/MIL-STD-1797A]; 3.3 = 400/120(계산) | Tab6-R3 | 확인 필요(문헌) |
| D-07 | 롤 추가 탐색: 시드 1개 | 1 | 탐색 | ANALYSIS_LEDGER.md S-3; PREREG_P3.md 11행 | Tab6-R6 | 탐색 |


## 출처가 비어 있는 줄 (V-22)

| 원장 ID | 문제 | 필요한 것 |
|---|---|---|
| N-02 | "약 14만 경기"는 README 실험별 경기 수를 더한 값(140,784)이다. 합계를 적은 파일이 없고 본문에도 없다 | 본문(Ⅳ-C)에 합계와 내역을 넣거나 초록에서 뺀다 |
| N-07 | 4.5–7.2 G는 PAPER_SKELETON 103행에만 있다. 측정 로그 경로가 없다 | 원 측정 로그 또는 스크립트 경로 |
| N-09 | κ ≈ 0.42·8.4는 팀 브랜치의 미발표 문서에서 왔다 | 선행 실험 인용 방식 결정(T-30) |
| N-14 | 설계 기준 6 dB·45°의 출처가 없다 | 원문을 확인한 문헌 |
| D-06 | 비행성 최악 수준 약 0.25 s의 출처가 없다 | MIL-F-8785C 또는 MIL-STD-1797A 원문의 해당 절 |

## v3에서 원고에 새로 들어온 수치 (2026-10-24)

`PAPER_DRAFT_v3.md`는 위 수치를 그대로 쓰고, 아래 하나만 더했다. 다른 변경은 이미 있던 수치를 옮기거나 다시 쓴 것이다(`CHANGELOG_DRAFT_v3.md`).

| ID | 주장 | 값 | 조건 | 출처 | 등장 위치(v3) | 상태 |
|---|---|---|---|---|---|---|
| C-05/17b | 같은 시드(gen)에서 원래 참가자의 절대 수준 치우침 구간 | −0.000 [−0.033, +0.035] | P5, gen 시드 4개, 퍼센타일 2,000회 | kit/supplementary/p5_output.md 21행 | 표 5 둘째 행 | 사전 등록(P5) |
