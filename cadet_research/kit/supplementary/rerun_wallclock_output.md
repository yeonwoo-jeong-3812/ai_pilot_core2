main: 저장된 재실행 결과 14판을 쓴다 (rerun_wallclock_main.csv). 다시 돌리려면 --replay
   R_sigma_dps_3 TwoCircle vs EnergyFighter neutral main-4: wall_clock/draw → hard_deck/TwoCircle (wall 27.3 s)
   R_sigma_dps_3 Reactive vs LagAngler perch_offense main-4: wall_clock/draw → health_zero/Reactive (wall 46.1 s)
   R_sigma_dps_3 EnergyFighter vs TwoCircle neutral main-4: wall_clock/draw → no_contact/draw (wall 50.2 s)
   R_sigma_dps_3 EnergyFighter vs Reactive headon main-4: wall_clock/draw → timeout/Reactive (wall 50.3 s)
   R_sigma_dps_3 LagAngler vs Reactive perch_offense main-4: wall_clock/draw → timeout/Reactive (wall 50.0 s)
   R_sigma_dps_3 RedPrime vs EnergyFighter neutral main-4: wall_clock/draw → no_contact/draw (wall 49.7 s)
   R_sigma_dps_3 RedPrime vs EnergyFighter perch_offense main-4: wall_clock/draw → timeout/RedPrime (wall 50.1 s)
   R_sigma_dps_3 EnergyFighter vs Extender neutral main-4: wall_clock/draw → timeout/EnergyFighter (wall 49.9 s)
   R_sigma_dps_3 EnergyFighter vs RedPrime perch_offense main-4: wall_clock/draw → timeout/EnergyFighter (wall 50.2 s)
   R_sigma_dps_3 Extender vs EnergyFighter headon main-4: wall_clock/draw → timeout/EnergyFighter (wall 50.2 s)
   R_sigma_dps_3 EnergyFighter vs RedPrime neutral main-4: wall_clock/draw → no_contact/draw (wall 50.1 s)
   R_sigma_dps_3 Extender vs EnergyFighter neutral main-4: wall_clock/draw → health_zero/EnergyFighter (wall 36.6 s)
   R_sigma_dps_3 TwoCircle vs EnergyFighter perch_offense main-4: wall_clock/draw → timeout/TwoCircle (wall 50.4 s)
   R_sigma_dps_3 EnergyFighter vs Extender headon main-4: wall_clock/draw → health_zero/Extender (wall 29.8 s)
gen: 저장된 재실행 결과 14판을 쓴다 (rerun_wallclock_gen.csv). 다시 돌리려면 --replay
   R_kq_2 Lufbery vs RedEnergy neutral gen-2: wall_clock/draw → timeout/Lufbery (wall 52.2 s)
   R_kq_2 AdaptiveAce vs Lufbery neutral gen-2: wall_clock/draw → timeout/AdaptiveAce (wall 51.8 s)
   R_kq_2 AdaptiveAce vs Lufbery headon gen-2: wall_clock/draw → timeout/AdaptiveAce (wall 51.7 s)
   R_kq_2 Lufbery vs RedEnergy perch_offense gen-2: wall_clock/draw → timeout/Lufbery (wall 51.9 s)
   R_kq_2 Lufbery vs AdaptiveAce neutral gen-2: wall_clock/draw → timeout/AdaptiveAce (wall 51.1 s)
   R_kq_2 RedEnergy vs Lufbery neutral gen-2: wall_clock/draw → timeout/Lufbery (wall 52.3 s)
   R_kq_2 RedEnergy vs Lufbery headon gen-2: wall_clock/draw → timeout/RedEnergy (wall 51.8 s)
   R_kq_2 Lufbery vs AdaptiveAce perch_offense gen-2: wall_clock/draw → timeout/Lufbery (wall 52.0 s)
   R_kq_2 RedEnergy vs Lufbery perch_offense gen-2: wall_clock/draw → timeout/Lufbery (wall 51.9 s)
   R_kq_2 Lufbery vs RedTracker headon gen-2: wall_clock/draw → health_zero/Lufbery (wall 6.7 s)
   R_kq_2 AdaptiveAce vs Lufbery perch_offense gen-2: wall_clock/draw → no_contact/draw (wall 52.0 s)
   R_kq_2 Lufbery vs RedEnergy headon gen-2: wall_clock/draw → timeout/Lufbery (wall 51.5 s)
   R_kq_2 LastDitch vs Lufbery neutral gen-2: wall_clock/draw → timeout/Lufbery (wall 51.2 s)
   R_kq_2 Lufbery vs AdaptiveAce headon gen-2: wall_clock/draw → timeout/Lufbery (wall 51.7 s)
=== E3 다시 판정 (잘린 판을 바꿔 끼운 자료) ===
## E2 로 적합, E3 로 검증 (보정)
곡선 (모양 linear, 적합 조건 20개, 시드 8개): D = 0.144 + 0.0531·linear(mae), M = 2.45 + 0.835·linear(mae)
허용폭 δ: D 0.079, M 5.21점
| 조건 | 원인 | 추종 오차 [°/s] | D 실제 | D 예측 | D 오차 [95 % CI] | M 실제 | M 예측 | M 오차 [95 % CI] |
|---|---|---|---|---|---|---|---|---|
| R_kappa_2 | kappa | 0.22 | 0.100 | 0.156 | -0.056 [-0.070, -0.042] | 1.81 | 2.64 | -0.83 [-2.04, -0.08] |
| R_kappa_4 | kappa | 0.26 | 0.115 | 0.158 | -0.042 [-0.063, -0.022] | 1.69 | 2.67 | -0.98 [-1.92, +0.52] |
| R_kappa_8 | kappa | 0.35 | 0.135 | 0.163 | -0.027 [-0.050, -0.001] | 3.14 | 2.75 | +0.39 [-0.78, +1.39] |
| R_kappa_16 | kappa | 0.52 | 0.177 | 0.171 | +0.006 [-0.021, +0.034] | 2.45 | 2.89 | -0.43 [-1.75, +1.10] |
| R_kappa_25 | kappa | 0.68 | 0.211 | 0.180 | +0.031 [+0.000, +0.058] | 3.00 | 3.02 | -0.02 [-1.70, +1.25] |
| R_kappa_50 | kappa | 1.08 | 0.275 | 0.201 | +0.074 [+0.051, +0.103] | 3.58 | 3.35 | +0.23 [-1.03, +1.55] |
| R_kq_0.25 | kq | 0.73 | 0.290 | 0.182 | +0.108 [+0.080, +0.141] | 4.22 | 3.06 | +1.16 [-0.03, +3.15] |
| R_kq_0.5 | kq | 0.40 | 0.204 | 0.165 | +0.039 [+0.019, +0.058] | 3.80 | 2.79 | +1.01 [-0.32, +2.19] |
| R_kq_1.5 | kq | 2.59 | 0.250 | 0.281 | -0.031 [-0.055, -0.007] | 2.31 | 4.62 | -2.30 [-2.98, -0.49] |
| R_kq_2 | kq | 3.55 | 0.301 | 0.332 | -0.032 [-0.060, +0.001] | 4.22 | 5.41 | -1.20 [-1.89, +0.76] |
| R_sigma_dps_0.3 | sigma_dps | 0.26 | 0.109 | 0.158 | -0.049 [-0.059, -0.040] | 2.47 | 2.67 | -0.20 [-1.78, +0.81] |
| R_sigma_dps_1 | sigma_dps | 0.35 | 0.167 | 0.162 | +0.005 [-0.021, +0.028] | 3.33 | 2.74 | +0.58 [-0.59, +1.72] |
| R_sigma_dps_3 | sigma_dps | 0.74 | 0.209 | 0.183 | +0.026 [+0.003, +0.050] | 2.69 | 3.07 | -0.38 [-1.51, +0.99] |
| R_sigma_dps_6 | sigma_dps | 1.58 | 0.261 | 0.228 | +0.033 [+0.013, +0.057] | 2.47 | 3.77 | -1.30 [-2.31, +0.52] |
| R_delay_sync_2 | delay_sync | 0.22 | 0.132 | 0.155 | -0.023 [-0.035, -0.012] | 3.14 | 2.63 | +0.51 [-0.88, +1.70] |
| R_delay_sync_4 | delay_sync | 0.20 | 0.142 | 0.155 | -0.012 [-0.021, -0.004] | 2.45 | 2.62 | -0.17 [-1.32, +0.75] |
| R_delay_sync_8 | delay_sync | 0.24 | 0.171 | 0.157 | +0.014 [-0.001, +0.029] | 2.97 | 2.65 | +0.31 [-0.85, +1.12] |
| R_delay_sync_16 | delay_sync | 0.72 | 0.213 | 0.182 | +0.031 [+0.007, +0.055] | 3.92 | 3.05 | +0.87 [-0.62, +2.52] |
| C_kappa8+async1 | 조합 | 0.35 | 0.126 | 0.162 | -0.036 [-0.054, -0.017] | 1.75 | 2.74 | -0.99 [-2.94, +0.48] |
| C_sigma1+kq0.5 | 조합 | 0.45 | 0.210 | 0.168 | +0.042 [+0.019, +0.064] | 2.95 | 2.83 | +0.12 [-1.04, +1.73] |
| C_kappa4+sync4 | 조합 | 0.41 | 0.148 | 0.165 | -0.017 [-0.032, -0.001] | 3.23 | 2.79 | +0.44 [-0.98, +1.28] |
| C_f12+sigma3 | 조합 | 0.69 | 0.194 | 0.180 | +0.014 [-0.004, +0.033] | 3.89 | 3.02 | +0.87 [-0.18, +2.30] |
원인별 평균 예측 오차와 판정 (주 판정은 D)
| 묶음 | D 평균 오차 [95 % CI] | D 판정 | M 평균 오차 [95 % CI] | M 판정 |
|---|---|---|---|---|
| 원인:delay_sync | +0.003 [-0.007, +0.011] | 예측 성공 | +0.261 [-0.499, +1.062] | 예측 성공 |
| 원인:kappa | -0.003 [-0.021, +0.015] | 예측 성공 | -0.273 [-0.919, +0.304] | 예측 성공 |
| 원인:kq | +0.021 [+0.001, +0.040] | 예측 성공 | -0.094 [-0.673, +0.728] | 예측 성공 |
| 원인:sigma_dps | +0.004 [-0.009, +0.017] | 예측 성공 | -0.228 [-0.859, +0.363] | 예측 성공 |
| 원인:조합 | +0.001 [-0.011, +0.013] | 예측 성공 | +0.080 [-0.670, +0.840] | 예측 성공 |
| 전체 | +0.005 [-0.005, +0.014] | 예측 성공 | -0.071 [-0.486, +0.402] | 예측 성공 |
=== E4 (보정) ===
SHAM: mae 0.21, D 0.013, 예측 0.155, 오차 -0.142
F25_D1: mae 2.91, D 0.329, 예측 0.298, 오차 +0.031
F25_D3: mae 5.49, D 0.507, 예측 0.435, 오차 +0.072
R_kappa_25: mae 0.61, D 0.239, 예측 0.176, 오차 +0.062
R_kq_2: mae 3.49, D 0.342, 예측 0.329, 오차 +0.013
R_sigma_dps_3: mae 0.72, D 0.222, 예측 0.182, 오차 +0.040
열화 5조건 평균 +0.044 [+0.018, +0.074] → 예측 성공
