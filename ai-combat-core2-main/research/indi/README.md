# research/indi — INDI 최적화 연구 하네스

근거·결정: 저장소 루트 `paper.md`(문헌·결정), `plan.md`(일정·발견). 공통 조건은 `runner.py` 상단 상수:
교범 G 봉투(`manual`), 수정 모델 `f16fix`, 명목 자이로 잡음 0.1°/s, Nz 보호 끔.

| 파일 | 실험 | 실행 |
|---|---|---|
| `runner.py` | 1경기·배터리·병렬·경기 캐시 공용 | `python research/indi/runner.py --k_q 14 --duration 90` |
| `limits.py` | 한계 준수 기록기(매치·벤치 공용) | — |
| `combat.py` | 교전 과정 지표 기록기(응답 지연·추종·G 실현률·공세/수세·에너지·사격 기회) | — |
| `bench.py` | **E1** 추종 벤치 (6 운용점 × 4 시험) | `python research/indi/bench.py --filt_hz 6 --json out.json` |
| `sweep.py` | **E2** 단일 변수 민감도 | `python research/indi/sweep.py --seeds 1 2 3 4 --out results/indi/e2_n100.json` |
| `optimize.py` | **E4** PSO + 파레토 (`--box` 로 범위 변경) | `python research/indi/optimize.py --out results/indi/e4.json` |
| `duel.py` | **E3** 기준 vs 튜닝 / **E5** 강건성 / 지연 곡선 / 전술 트리 | 아래 예시 |
| `analyze.py` | 전 결과 → `results/indi/summary.md` (부호·Wilcoxon·McNemar·Holm) | `python research/indi/analyze.py` |
| `figures.py` | 논문 그림 → `results/indi/fig/` | `python research/indi/figures.py` |
| `run_batch*.ps1` | 세션과 무관한 독립 일괄 실행 (1: E3·E5·E2, 2: 범위 확장·양측 튜닝·E2 n=100, 4: 지연 곡선·분리·트리) | `Start-Process powershell -WindowStyle Hidden -ArgumentList '-File','research/indi/run_batch4.ps1'` |

`duel.py` 주요 옵션:
- `--best e4.json --gamma 0 0.3` : B = E4 최적해(여러 개 가능, 기준 A 경기 공유)
- `--b filt_hz=5 --b-name filt5` : 직접 지정한 B (`--best` 와 함께 쓰면 추가 B)
- `--conds nominal stress delay30 delay90 g0_lo g0_hi turb mc dt<틱>` : `dt<틱>` = 임의 측정 지연(1틱 = 8.3 ms)
- `--red-gamma 0` : 대항군도 튜닝 INDI (양측 튜닝)
- `--blue examples/textbook_headon.yaml` : blue 전술 트리 교체

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
경기 결과는 `results/indi/cache/` 에 job 해시로 저장(결과 스키마 버전 `runner.METRICS` 포함) — 같은 명령을 다시 실행하면
끝난 경기는 건너뛴다. 기본 blue 트리·기준 red 경기는 실험 간 캐시를 공유한다.

난수원은 전부 시드 고정: 시나리오 IC(`seed`), 자이로 잡음(경기 시드 — 기준·변경 경기가 같은 잡음열 = 대응 비교),
벤치 잡음(시험·운용점 해시), 난류(`atmosphere/randomseed` = 시드·측), MC 조건(red·시나리오·시드 해시).
