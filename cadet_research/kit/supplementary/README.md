# 보조 분석 (본실험 뒤, 탐색·민감도)

본실험 E1–E4가 끝난 뒤에 한 보조 분석이다. **등록된 판정을 바꾸지 않는다.** 논문에는 부록이나 한계 절의 근거로만 쓴다.
스크립트는 모두 이 폴더에서 `python <파일>`로 돌리며, 경로는 이 폴더 기준 상대 경로다.

| 분석 | 스크립트 | 자료 | 출력 | 요약 |
|---|---|---|---|---|
| 절전으로 잘린 경기의 민감도 | `rerun_wallclock.py` | `rerun_wallclock_main.csv`, `rerun_wallclock_gen.csv` (잘린 28판을 다시 돈 결과) | `rerun_wallclock_output.md` | 엔진의 실시간 120초 안전장치가 노트북 절전 중에 28판을 `wall_clock` 무승부로 끝냈다. 다시 돈 결과로 바꿔 끼워도 E3·E4 판정은 그대로다. 저장된 결과를 쓰며, `--replay`를 주면 28판을 다시 돈다 |
| E4 시드 부트스트랩 | `e4_boot.py` | `../out/main`, `../out/gen` | `e4_boot_output.md` | `predict.py E4`는 점추정만 낸다. 같은 규칙의 부트스트랩 CI: 열화 5조건 평균 오차 +0.045 [+0.020, +0.074] |
| E4 시드 단위 t 구간 | `e4_tinterval.py` | `../out/main`, `../out/gen` | `e4_tinterval_output.md`, `e4_tinterval.json` | 시드 4개 민감도(2026-10-21). ΔD [−0.049, +0.049] 예측 성공 유지, 절대 D [−0.005, +0.096] 판정 불가 |
| 롤 추종 탐색 | `roll_pilot.py` (실행), `roll_analysis.py` (분석) | `roll_pilot_games.csv` (E2·E3 43조건 × 시드 main-0 × neutral, 2,408판), `roll_pilot.log` | `roll_analysis_output.md` | 피치에 롤 추종 오차를 더해도 E3 예측 RMS가 0.041 → 0.041로 나아지지 않는다(실행 전 정한 기준: 20 % 이상 감소). 롤 오차는 BASE에서 이미 5.85 °/s이고 κ·k_q에서는 변하지 않는다. 다시 돈 2,408판은 기록된 판과 모두 같았다 |
| ASYM U자 메커니즘 (P2-a) | `asym_replay.py` | `asym_replay_games.csv` (GunTracker × {BASE, 지연 2·6틱} × 시드 main-0·1, 252경기, 기체별 지표) | `asym_replay_output.md` | 사전 등록 `../../PREREG_P2.md`. 재생 252/252 일치. 6틱에서 대상의 WEZ 시간 2.9배, 상대의 WEZ 시간 −32 %, 저고도 체류 감소, 과하중 없음. 해석은 `../../FEEDBACK_FOR_CADET_v4.md` §2 |
| 정밀 조준 기총 반사실 (P2-b) | `p2b_precise_gun.py` (`--report`는 분석만) | `p2b_games.csv` (GunTracker × {BASE, 지연 2·6틱} × 시드 main-0–7 × 42경기 = 1,008경기, 반사실 기총), `p2b.log` | `p2b_output.md` | 사전 등록 `../../PREREG_P2.md` §P2-b. 기총 조준각 등급만 2° 100 %, 5° 50 %로 바꿈. 판정 **반등 유지**: 반등 +29.6 [+20.2, +38.6](원래 +46.5). 약 43분. 해석은 `../../FEEDBACK_FOR_CADET_v4.md` §4 |
| 교전 없는 벤치 (P1) | `p1_bench.py` (`--check` 재현 확인, `--report` 분석만) | `p1_bench_runs.json` (51조건 × 비행점 3 × 이중펄스 2·사인 4, 942회), `p1.log` | `p1_output.md`, `p1_results.json`, `fig_p1.png` | 사전 등록 `../../PREREG_P1.md`. 판정 **교전 없이 예측 불충분**: 벤치 J̄의 E3 RMS 0.068(상수 0.074, 교전 mae 0.041). 조건 분류: E2 한계 순환 10/20, E3 1/22. 약 20초. 해석은 `../../FEEDBACK_FOR_CADET_v5.md` |
| 시계열 기록 재생 (P3) | `p3_timeseries.py` (`--smoke` 점검, `--report` 분석만) | `p3_games.csv` (49조건 × main-0 × neutral × 56대진 = 2,744경기, 기체별 대역 오차·명령 스펙트럼·시간 이동·승강타 포화), `p3.log` | `p3_output.md`, `p3_results.json`, `fig_p3.png` | 사전 등록 `../../PREREG_P3.md`. 재생 일치 2,744/2,744. 대역 분해 예측 **나아지지 않음**, 교전 명령이 느리다 **지지**. 약 92분. 해석은 `../../FEEDBACK_FOR_CADET_v6.md` |
| 새 시드 독립 재현 (P4) | `p4_replicate.py` (`--smoke` 점검, `--report` 분석만) | `../out/rep/games.csv` (rep-0–7, 대칭 10조건 + 한 기체 열화 2대상 × 4조건, 16,128경기), `p4.log` | `p4_output.md`, `p4_results.json` | 사전 등록 `../../PREREG_P4.md`. T-A·T-B·T-C 재현, T-D 확인. 약 7.7시간. 해석은 `../../FEEDBACK_FOR_CADET_v7.md` |
| 정밀 조준 기총 대칭 열화 (P6) | `p6_precise_sym.py` (`--smoke`, `--report`) | `../out/p6/games.csv` (BASE·SHAM·E2 6조건 × main-0–3, 5,376경기, 반사실 기총), `p6.log` | `p6_output.md`, `p6_results.json` | 사전 등록 `../../PREREG_P6.md`. 기울기 0.045 대 0.054, 동등성 판정 불가, 절편 +0.08. 약 4.3시간. 해석은 `../../FEEDBACK_FOR_CADET_v8.md` §1 |
| E4 치우침의 원인 (P5) | `p5_gen_agents.py` (`--smoke`, `--report`) | `../out/p5/games.csv` (E2 참가자 × BASE·SHAM·E4 5조건 × gen-0–3, 4,704경기), `p5.log` | `p5_output.md`, `p5_results.json` | 사전 등록 `../../PREREG_P5.md`. 같은 시드에서 E2 참가자 치우침 −0.000 대 E4 참가자 +0.045, 판정 불가. 약 2.2시간. 해석은 `../../FEEDBACK_FOR_CADET_v8.md` §2 |
| 실제형 센서·구동기 (P7) | `p7_realistic.py`(구성), `p7_design.py`(선형 설계), `p7_run.py`(`--probe`, `--smoke`, `--report`), `p7_report.py`(분석·조건 선택) | `../out/p7/games.csv` (BASE + 지연 2–12틱 + κ 25·50 × main-0–7, 12,096경기), `p7_probe_games.csv`(탐침 672경기), `p7_conds.json`, `p7.log` | `p7_output.md`, `p7_results.json`, `p7_design_output.md`, `p7_bench_output.md`, `p7_probe_output.md` | 사전 등록 `../../PREREG_P7.md`. 기울기 다르다(0.022), 원래 곡선 예측 실패, 오차 유형 확인. 약 6.1시간. 해석은 `../../FEEDBACK_FOR_CADET_v9.md` |
| κ가 아닌 둔한 원인 (P8) | `p8_run.py` (`--smoke`, `--report`). 명령 전달 지연 `cmd_delay`를 실제형 INDI 안쪽에 건다 | `../out/p8/games.csv` (x8-0–7, 6,720경기), `p8_probe_games.csv`, `p8_conds.json`, `p8.log` | `p8_output.md`, `p8_results.json` | 사전 등록 `../../PREREG_P8.md`. 확인 +0.330 |
| 실제형 한 기체 열화 (P9-c) | `p9c_asym_real.py` | `../out/p9c/games.csv` (2,688경기, 짝은 P7 BASE) | `p9c_output.md`, `p9c_results.json` | 사전 등록 `../../PREREG_P9.md`. 반등 없음 |
| 논문 그림 3·4·6·7 | `paper_figs.py` | 기존 자료만 읽음(경기 0판) | `paper_figs/fig3_curve.png`, `fig4_error_type.png`, `fig6_configs.png`, `fig7_asym.png` | 초안 v2용. 범주색 4개를 순서대로 쓰고 표식 모양을 함께 바꿈 |
| 흔들림 주입·기록 재생 (P9-b·a) | `p9ab_orig.py` | `../out/p9b/games.csv` (1,344경기), `p9a_games.csv` (252경기), `p9.log` | `p9ab_output.md`, `p9ab_results.json` | 판정 불가 / 공세 비율 15배. 해석은 `../../FEEDBACK_FOR_CADET_v10.md` |
| 파생 수치 (사후, 0판) | `derived_numbers.py` | 기존 `games.csv` (읽기만) | `derived_numbers_output.md`, `derived_numbers.json` | 보고서에 직접 없던 숫자의 출처. 공부 문서 `../../STUDY_GUIDE_v3.md` §6 |

`p2b_precise_gun.py`는 엔진 파일을 고치지 않고 작업 프로세스 안에서 `aircombat.geometry.wez.WEZ_ATA_TIERS`만 바꾸며, 경기마다 바뀐 등급이 쓰이는지 확인한다.

`asym_replay.py`는 엔진을 고치지 않고 `match._wez_damage`(틱마다 조준각·거리·피해)와 INDI 호출(n_z, 받음각, 고도, 피치 명령·응답)을 바깥에서 감싼다.

`roll_pilot.py`는 키트 파일을 고치지 않고 `run.apply_knobs` 바깥에 롤 기록만 한 겹 씌운다. 다시 돌리면 약 70분 걸리고,
같은 PC에서는 같은 결과가 나온다.
