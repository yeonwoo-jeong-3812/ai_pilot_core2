# research/indi — INDI 최적화 연구 하네스

근거·결정: 저장소 루트 `paper.md`(문헌·결정), `plan.md`(일정·발견). 공통 조건은 `runner.py` 상단 상수:
교범 G 봉투(`manual`), 수정 모델 `f16fix`, 명목 자이로 잡음 0.1°/s, Nz 보호 끔.

| 파일 | 실험 | 실행 |
|---|---|---|
| `runner.py` | 1경기·배터리·병렬 공용 | `python research/indi/runner.py --k_q 14 --duration 90` |
| `limits.py` | 한계 준수 기록기(매치·벤치 공용) | — |
| `bench.py` | **E1** 추종 벤치 (6 운용점 × 4 시험) | `python research/indi/bench.py --filt_hz 6 --json out.json` |
| `sweep.py` | **E2** 단일 변수 민감도 | `python research/indi/sweep.py --out results/indi/e2.json` |
| `optimize.py` | **E4** PSO + 파레토 | `python research/indi/optimize.py --out results/indi/e4.json` |
| `duel.py` | **E3** 기준 vs 최적 / **E5** 강건성 | `python research/indi/duel.py --best results/indi/e4.json --gamma 0 0.3 --out results/indi/e3.json` |

모든 드라이버에 `--smoke`(1–2분 동작 확인). 시나리오 `p1_neutral` 은 **E6**(논문 1 조건)로 배터리에 기본 포함.

## 출력 스키마 (JSON)
- **bench** `evaluate()`: `J`(평균 정규화 ISE), `viol`(봉투 초과 G·s), `disqualified`, `by_test{bank,p3211,q_dbl,q_step}`,
  `rows[]`(운용점×시험: `ise_n, rmse, overshoot, settle_s, du_ail, du_elev` + `limits.summary()`)
- **limits** `summary()`: `nz_max, nz_min, env_excess_max, env_excess_int, struct_violation, onset_max, alpha_max,
  roll_rate_max, roll_violation, elev_sat_frac, disqualified`(구조한계 초과 또는 봉투 +0.5G 초과)
- **sweep**: `rows[]{var, value, cfg, J, J_ratio, bench_dq, by_test, duel{n, d_points, d_points_ci, d_hp, d_hp_ci,
  win_rate, dq, nz_max}}`, `games[config][battery]`
- **optimize**: `ref{J,A}`, `best[]{gamma, cost, cfg}`, `pareto[]{cfg, J_ratio, A_ratio}`, `log[]`(전 평가점)
- **duel**: `A, B{이름: cfg}, battery, conds{조건: {games_A, <B이름>: {summary{win_A/B(+Wilson CI), d_points(+CI), d_hp(+CI), kills_A/B, dq_A, dq}, games}}}`

## 재현성
난수원은 전부 시드 고정: 시나리오 IC(`seed`), 자이로 잡음(경기 시드 — 기준·변경 경기가 같은 잡음열 = 대응 비교),
벤치 잡음(시험·운용점 해시), 난류(`atmosphere/randomseed` = 시드·측), MC 조건(red·시나리오·시드 해시).
