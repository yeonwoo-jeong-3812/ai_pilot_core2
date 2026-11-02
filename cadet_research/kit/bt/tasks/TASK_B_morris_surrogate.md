# TASK B — Morris 중요도와 대리모델

## Claude Code에게

이 파일 하나로 작업을 시작할 수 있게 썼다. 아래 순서를 지켜라.

- **연구 목적 (3줄):**
  1. 근접 공중전 행동트리 (`bt/energy_fighter.yaml`) 의 숫자 파라미터 10개가 성과를 얼마나 좌우하는지 잰다.
  2. 1차 지표는 Δwez = `wez_blue − wez_red` (청·적이 각자 상대를 엔진 WEZ 안에 둔 누적 시간의 차, 초) 다.
  3. 이 TASK 는 파라미터 중요도 (Morris μ*·μ·σ, 더미와 비교, 기하별 차이 — RQ2) 와 대리모델 (θ → 평균 Δwez, 조건부 SHAP) 분석을 만든다.
- **먼저 읽을 파일** (`cadet_research/` 아래):
  1. `kit/bt/CONTRACT.md` §2 (games.csv 열 정의), §5 (wall_clock 처리)
  2. `PREREG_BT.md` §4 (지표), §5 (설계: Morris 파일, `trajectory`·`step` 열), §6.2 (Morris), §6.3 (대리모델), §7 (제외 규칙)
  3. `kit/bt/RUNBOOK.md` (실행 흐름 이해용, 실행은 안 함)
- **작업 브랜치:** `bt-task-b` (`git switch -c bt-task-b origin/bt-study`). bt-study 로 직접 push 하지 않는다. 끝나면 `git push origin bt-task-b` 하고 연우에게 알린다.
- **설치:** `cadet_research/kit/` 에서 `python -m pip install -r bt/requirements-analysis.txt` (버전 고정, 다른 버전 설치 금지). Python 3.11.9.
- **수정해도 되는 파일 (이 밖은 수정 금지):**
  - 새로 만들기: `kit/bt/analysis/morris.py`, `kit/bt/analysis/surrogate.py`, `kit/bt/analysis/test_morris.py`, `kit/bt/analysis/test_surrogate.py`
  - 이 파일 끝의 "질문" 절, "완료 보고" 절
- **마감:** 2026-11-06

## 사양 (PREREG_BT.md 인용 — 이것만 구현한다)

### Morris (PREREG_BT.md §6.2 그대로)

> - **입력:** θ 별 48경기 평균 Δwez (기하별 분석은 θ 별 그 기하 16경기 평균).
> - **지표:** 파라미터마다 기본효과의 μ* (절댓값 평균), μ (평균), σ (표준편차). 전체와 기하별로 계산한다.
> - **부트스트랩:** 단위는 **궤적**, **2,000회, seed 20261108**. 95% CI (백분위).
> - **중요 판정:** 파라미터 μ* 의 95% CI 하한 > 더미 μ* 의 95% CI 상한.
> - **기하별 순위:** 기하별 μ* 순위와 기하 쌍 사이 **Spearman 순위 상관** (서술용, 부트스트랩 CI).
>   **"기하별 순위가 다르다"** = 어떤 파라미터가 한 기하에서는 중요, 다른 기하에서는 중요 아님이고, 두 기하 μ* 차이의 95% CI 가 0 을 포함하지 않을 때.

### 설계 (PREREG_BT.md §5 에서)

> - **RQ2 — Morris:** 요인 11개 (dummy 포함), **수준 4, 궤적 16**, SALib 1.6.0 표준 궤적 생성 … 궤적당 θ 12개 → θ 192개 …
>   파일에 `trajectory` (0–15), `step` (0–11) 열이 있어 분석에서 궤적을 복원한다.

### 대리모델 (PREREG_BT.md §6.3 그대로)

> - **모형:** scikit-learn `HistGradientBoostingRegressor`. 입력 θ (10개 + 더미), 출력 θ 별 평균 Δwez.
> - **데이터:** bt-main θ 256개 (RQ1 64 + RQ2 192). **무작위 20% θ 를 떼어 둔다 (seed 20261108).**
> - **보고 조건:** 떼어 둔 데이터 **R² ≥ 0.5 일 때만** SHAP (`TreeExplainer`) 해석을 결과로 보고한다. 미달이면 SHAP 은 보고하지 않는다.

### 지표와 제외 (PREREG_BT.md §4, §7, CONTRACT.md §5)

> - **1차 지표: Δwez = `wez_blue − wez_red`** [s]
> - **wall_clock** … 분석에 넣지 않는다.

### 구현할 함수 (이름·입력·출력)

pandas 를 쓴다. games.csv 에는 궤적 정보가 없다. **θ ↔ 궤적은 설계 파일로 잇는다:** `run_bt.read_thetas(설계 파일)` 로 θ 를 읽고
`make_tree.theta_id(θ)` 가 games.csv 의 `theta_id` 와 같다 (설계 파일의 `trajectory`, `step` 은 같은 행 순서에서 읽는다).

`analysis/morris.py`
| 함수 | 입력 | 출력 |
|---|---|---|
| `theta_means(games_df, design_path, by_geometry=False) -> DataFrame` | games.csv DataFrame (wall_clock 뺀 것), `bt/thetas/main_morris_r16.csv` | θ 마다 한 행: 파라미터 11개, `trajectory`, `step`, `theta_id`, `y` (평균 Δwez). `by_geometry=True` 면 (θ, 기하) 마다 한 행 + `scenario` |
| `elementary_effects(tm) -> DataFrame` | `theta_means` 결과 (한 기하 또는 전체) | 궤적마다 요인마다 한 행: `trajectory, param, ee`. EE = (y(다음 점) − y(이전 점)) / Δ, Δ 는 정규화 단위 (x = (θ − lo)/(hi − lo)) 의 변화량 (SALib `analyze.morris` 정의와 같다) |
| `indices(ee) -> DataFrame` | `elementary_effects` 결과 | 요인마다 `param, mu_star, mu, sigma` |
| `bootstrap(ee, n_boot=2000, seed=20261108) -> DataFrame` | 같음 | `param, mu_star, mu_star_lo, mu_star_hi, mu, sigma` (궤적 단위 재표집, 백분위 95%) |
| `important(boot) -> dict[str, bool]` | `bootstrap` 결과 | 요인 → μ* CI 하한 > dummy μ* CI 상한 |
| `geometry_compare(games_df, design_path, n_boot=2000, seed=20261108) -> dict` | | 기하별 `bootstrap`·`important`, 기하 쌍마다 Spearman (점추정 + 부트스트랩 CI), 요인·기하 쌍마다 μ* 차이 CI 와 "다르다" 판정 |
| `plot_mu_sigma(boot, path)`, `plot_geometry_rank(result, path)` | | μ*–σ 산점도 (dummy 표시, CI 막대), 기하별 μ* 순위 그림 (png) |
| CLI: `python bt/analysis/morris.py <games.csv> --design bt/thetas/main_morris_r16.csv --out <폴더>` | | `morris.csv`, `morris.md`, `morris_geometry.md`, 그림 2개 |

- 기하별 부트스트랩도 같은 궤적 재표집을 쓴다 (한 번 뽑은 궤적 묶음으로 세 기하를 함께 계산하면 차이 CI 가 짝을 이룬다. 다른 방식이 필요하면 "질문").
- SALib `analyze.morris` 를 μ*·μ·σ 점추정 확인에 써도 되지만, CI 는 위 사양 (궤적 재표집 2,000회, seed 20261108, 백분위) 으로 직접 계산한다.

`analysis/surrogate.py`
| 함수 | 입력 | 출력 |
|---|---|---|
| `theta_table(games_df, design_paths) -> DataFrame` | games.csv DataFrame, `[main_lhs64.csv, main_morris_r16.csv]` | θ 마다 한 행: 파라미터 11개 + `y` (48경기 평균 Δwez). 본실험이면 256행 |
| `fit_holdout(tt, frac=0.2, seed=20261108) -> dict` | `theta_table` 결과 | `model`, `r2_holdout`, `train_ids`, `test_ids`. 모형은 `HistGradientBoostingRegressor(random_state=20261108)`, 그 밖의 하이퍼파라미터는 scikit-learn 기본값 |
| `shap_report(fit, tt, out_dir) -> bool` | | R² ≥ 0.5 일 때만 `TreeExplainer` SHAP 값 표 (`surrogate_shap.csv`) 와 그림 (요약 그림) 을 쓰고 True. 미달이면 아무것도 안 쓰고 False |
| CLI: `python bt/analysis/surrogate.py <games.csv> --designs bt/thetas/main_lhs64.csv bt/thetas/main_morris_r16.csv --out <폴더>` | | `surrogate.md` (R², 보고 여부), 조건부 SHAP 파일 |

## 시험 데이터 위치

- `kit/bt/analysis/fixtures/synth.py`: 정답을 아는 합성 데이터. `synth.morris(path)` 가 `main_morris_r16.csv` θ 192개 × 48경기 CSV 를 만든다.
  정답은 `synth.TRUTH_MORRIS` (중요 파라미터 3개, 더미 포함 나머지 8개 중요 아님, 비선형 1개, floor_ft 는 neutral 에서만 효과 0 → 기하별로 다름).
  합성 CSV 는 커밋하지 않는다 (테스트 안에서 임시 폴더에 만든다). 엔진을 import 하므로 `cadet_research/kit/` 에서 실행한다.
- `kit/bt/analysis/fixtures/pilot2_sample.csv`: 실측 일부 (예비 실험, LHS θ 50개). Morris 형식이 아니다 → `surrogate.theta_table` / `fit_holdout` 이
  실측 형식에서 돌아가는지 확인용으로만 쓴다 (설계 파일 대신 이 CSV 의 θ 열을 쓰는 경로가 필요하면 "질문").

## 완료 기준

`cadet_research/kit/` 에서 `python -m pytest bt/analysis/test_morris.py bt/analysis/test_surrogate.py` 가 모두 통과 (pytest 가 없으면
각 파일을 직접 실행해도 되게 `if __name__ == "__main__":` 를 둔다). 테스트에 최소한 아래가 있어야 한다.

1. `test_morris.py` (합성 데이터 `synth.morris`)
   - `important()` 가 `TRUTH_MORRIS["important"]` 3개를 모두 True, `not_important` 8개 (dummy 포함) 를 모두 False 로 판정.
   - 전체 μ* 가 `TRUTH_MORRIS["mu_star"]` 와 0.4 안에서 같다 (잡음 때문에 정확히 같지 않다).
   - `threat_aspect_deg` 의 σ 가 `fight_kcas` 의 σ 보다 크다 (비선형).
   - `geometry_compare` 가 `floor_ft` 를 "기하별로 다르다" 로 판정하고 (공세·수세 중요, neutral 중요 아님), `fight_kcas` 는 다르지 않다고 판정.
   - seed 가 같으면 부트스트랩 결과가 같다.
2. `test_surrogate.py`
   - 합성 데이터 (`synth.morris`) 로 `fit_holdout` 의 R² 가 0.5 이상 → `shap_report` 가 True 이고 파일을 쓴다.
   - y 를 순수 잡음으로 바꾼 데이터에서는 R² < 0.5 → `shap_report` 가 False 이고 파일을 쓰지 않는다.
   - 같은 seed 면 떼어 둔 θ 와 R² 가 같다. 떼어 둔 비율이 20% (192 θ → 38 또는 39개) 다.

예시 출력 (합성 데이터, 형식 예):

```
param              mu_star  mu_star_lo  mu_star_hi  mu      sigma   important
fight_kcas         3.0x     ...         ...         -3.0x   ...     True
floor_ft           2.0x     ...                                     True
threat_aspect_deg  1.3x     ...                     0.3x    1.2x    True
dummy              0.1x     ...                                     False
...
```

## 하지 말 것

- PREREG_BT.md 에 없는 분석 방법 (다른 민감도 지표, 다른 대리모델, 하이퍼파라미터 탐색, 다른 판정 규칙) 을 새로 만들거나 추가하지 않는다.
- 사양의 숫자 (2,000회, seed 20261108, 20%, R² 0.5, 수준 4·궤적 16) 를 바꾸지 않는다. R² 가 0.5 미만일 때 SHAP 을 결과로 내지 않는다.
- 엔진·`bt/` 기존 코드·설계 파일 (`bt/thetas/main_*.csv`)·PREREG_BT.md·CONTRACT.md·`fixtures/` 를 고치지 않는다. 결과 CSV 를 커밋하지 않는다.
- bt-main·bt-confirm 시뮬레이션을 돌리지 않는다 (이 TASK 는 분석 코드만).
- bt-study 에 직접 push 하지 않는다.

## 막히면 할 일

추측해서 사양을 바꾸지 말고 **멈춘다.** 이 파일 끝 "질문" 절에 질문을 번호로 적고 (무엇이 모호한지, 생각한 선택지), 커밋·push 한 뒤 연우에게 알린다.
답을 받기 전에는 그 부분을 구현하지 않는다 (다른 부분은 계속해도 된다).

## 완료 보고

(끝나면 여기에 적는다: 커밋 번호, 테스트 결과, 합성 데이터로 낸 μ* 표)

## 질문

(없으면 비워 둔다)
