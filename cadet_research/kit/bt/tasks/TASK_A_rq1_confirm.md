# TASK A — RQ1 분산분해와 확인 단계 비교

> ### ⚠ 2026-11-03 추가 사항 (이미 작업 중이면 반드시 반영)
>
> **결과 CSV와 설계 파일은 반드시 `read_games`/`read_design` (`bt/analysis/io_utils.py`) 으로 읽는다.** `pd.read_csv` 를 직접 쓰지 않는다.
> pandas 기본 읽기는 식별자를 숫자로 바꾼다: theta_id `686747538e50` → 6.87e+58, `06930348e037` → 앞의 0 이 사라진 지수,
> `242774203459` → 정수, engine_sha `1e0101026959` → `inf`. 본실험 θ 256개 중 4개가 숫자+e 형태, 1개가 숫자만이다.
> 일부 θ 만 담은 파일·표에서는 theta_id 열 전체가 숫자로 읽혀 θ 가 섞이거나 사라진다.
>
> ```python
> import sys; sys.path.insert(0, "bt/analysis")      # cadet_research/kit/ 에서
> from io_utils import read_games, read_design
> df = read_games("bt/analysis/fixtures/pilot2_sample.csv")     # 식별자 열은 str, 수치 열은 숫자
> design = read_design("bt/thetas/main_morris_r16.csv")          # 파라미터 float, trajectory·step int, theta_id 열 포함
> ```
>
> `io_utils.py` 는 bt-study 에 있다 (`git pull origin bt-study` 로 자기 브랜치에 받아 온다). 고치지 말고 가져다 쓴다.
> 테스트: `bt/test_bt.py` 의 `test_read_games_keeps_ids`.

## Claude Code에게

이 파일 하나로 작업을 시작할 수 있게 썼다. 아래 순서를 지켜라.

- **연구 목적 (3줄):**
  1. 근접 공중전 행동트리 (`bt/energy_fighter.yaml`) 의 숫자 파라미터 10개가 성과를 얼마나 좌우하는지 잰다.
  2. 1차 지표는 Δwez = `wez_blue − wez_red` (청·적이 각자 상대를 엔진 WEZ 안에 둔 누적 시간의 차, 초) 다.
  3. 이 TASK 는 그 분산을 θ·기하·상대·상호작용으로 나누는 분석 (RQ1) 과, 후보 θ 가 기준 θ 보다 나은지 판정하는 분석 (확인 단계) 을 만든다.
- **먼저 읽을 파일** (`cadet_research/` 아래):
  1. `kit/bt/CONTRACT.md` §2 (games.csv 열 정의), §5 (wall_clock 처리)
  2. `PREREG_BT.md` §4 (지표), §6.1 (RQ1), §6.4 (확인 단계), §7 (제외 규칙)
  3. `kit/bt/RUNBOOK.md` (실행 흐름 이해용, 실행은 안 함)
- **작업 브랜치:** `bt-task-a` (`git switch -c bt-task-a origin/bt-study`). bt-study 로 직접 push 하지 않는다. 끝나면 `git push origin bt-task-a` 하고 연우에게 알린다.
- **설치:** `cadet_research/kit/` 에서 `python -m pip install -r bt/requirements-analysis.txt` (버전 고정, 다른 버전 설치 금지). Python 3.11.9.
- **수정해도 되는 파일 (이 밖은 수정 금지):**
  - 새로 만들기: `kit/bt/analysis/anova.py`, `kit/bt/analysis/confirm.py`, `kit/bt/analysis/test_anova.py`, `kit/bt/analysis/test_confirm.py`
  - 이 파일 끝의 "질문" 절, "완료 보고" 절
- **마감:** 2026-11-06

## 사양 (PREREG_BT.md 인용 — 이것만 구현한다)

### RQ1 (PREREG_BT.md §6.1 그대로)

> - **모형:** 경기별 Δwez = θ + 기하 + 상대 + θ×기하 + θ×상대 + 기하×상대 + 잔차 (시드 잡음 + θ×기하×상대 3중 상호작용, 셀당 관측이 시드뿐이라 분리 불가).
> - **방법:** 균형 완전교차 설계이므로 **고정효과 ANOVA 제곱합 비율 (η²)** 을 분산 비율로 쓴다 (각 항 제곱합 / 전체 제곱합).
> - **균형 검사:** 분석 전에 모든 θ 가 48칸 (기하 3 × 상대 4 × 시드 4) 을 정확히 하나씩 갖는지 검사하고, 아니면 빠진 (또는 겹친) 칸 목록과 함께
>   오류로 멈춘다. wall_clock 경기는 §7 대로 재실행으로 채운 뒤 분석한다 (빈 칸을 둔 채 분석하지 않는다).
> - **불확실성:** **θ 단위 재표집 부트스트랩 2,000회, seed 20261108**, 각 항 η² 의 95% CI (백분위).
>   θ 를 복원추출해 같은 θ 가 여러 번 뽑히면 **뽑힐 때마다 새 θ 이름을 붙여 서로 다른 수준으로** 계산한다 (재표집 표본도 θ 64개 수준의 균형 설계).
> - 데이터: bt-main 의 RQ1 θ 64개 × 48경기 (`main_lhs64.csv`).

### 확인 단계 (PREREG_BT.md §6.4 그대로)

> - θ 4개 (기준 + 후보 3) 를 bt-confirm 시드에서 θ 당 **432경기** 돌린다.
> - **비교:** 후보 θ − 기준 θ 의 **짝 차이 Δwez (같은 기하·상대·시드끼리)**.
> - **검정:** 짝 차이에 대한 **t 분포 (자유도 n − 1)** 로 단측 p, 95% CI, TOST 를 계산한다.
> - **"낫다"** = Holm 보정 후 단측 유의 (α 0.05) **이고** 95% CI 하한 > 0.
> - **"실질적으로 낫다"** = "낫다" **이고** 점추정 ≥ 0.5 s (최소 의미 차이 Δwez 0.5 s).
> - **동등성:** ±0.5 s TOST (α 0.05).
> - 보조 지표 (승률, 체력 차) 도 같은 표에 서술용으로 적는다.

### 지표와 제외 (PREREG_BT.md §4, §7, CONTRACT.md §5)

> - **1차 지표: Δwez = `wez_blue − wez_red`** [s]
> - **보조 지표:** 승률 (청 승 = 1, 무승부·패 = 0), 실제 체력 차 (`hp_blue_raw − hp_red_raw`, 판정 처리 전) … 보조 지표는 함께 보고만 하고 판정에 쓰지 않는다.
> - **체력 차 최소 의미 차이: 10 HP** … 보조 지표라 해석 기준으로만 쓴다.
> - **wall_clock** … 분석에 넣지 않는다.

### 구현할 함수 (이름·입력·출력)

pandas 를 쓴다. 입력 DataFrame 은 games.csv 를 그대로 읽은 것 (열 이름은 CONTRACT.md §2). 셀 = (`scenario`, `opponent`, `seed_salt`).

`analysis/anova.py`
| 함수 | 입력 | 출력 |
|---|---|---|
| `load(path) -> DataFrame` | games.csv 경로 | **결과 CSV와 설계 파일은 반드시 `read_games`/`read_design` (`bt/analysis/io_utils.py`) 으로 읽는다.** (`read_games(path)` 로 읽는다) `end_reason == "wall_clock"` 행을 뺀 DataFrame + `dwez` 열 (= wez_blue − wez_red). 뺀 수를 출력한다 |
| `check_balance(df, n_seeds=4)` | `load` 결과 | 모든 θ 가 (기하 3 × 상대 4 × 시드 4) 48칸을 정확히 하나씩 가지면 통과. 아니면 `ValueError` — 메시지에 빠진 칸 `(theta_id, scenario, opponent, seed_salt)` 목록과 겹친 칸 목록. `eta2()` 와 `eta2_bootstrap()` 이 시작할 때 부른다 |
| `resample_thetas(df, rng) -> DataFrame` | `load` 결과, `numpy.random.Generator` | θ 를 복원추출 (θ 수만큼) 한 표본. 뽑힐 때마다 새 θ 이름 (`theta_id` 를 `<원래 id>#<뽑힌 순번>` 처럼) 을 붙여, 같은 θ 가 두 번 뽑혀도 서로 다른 수준이 된다 |
| `eta2(df) -> dict[str, float]` | `load` 결과 | 키 `theta`, `geometry`, `opponent`, `theta:geometry`, `theta:opponent`, `geometry:opponent`, `residual` → η². 합 = 1 |
| `eta2_bootstrap(df, n_boot=2000, seed=20261108) -> DataFrame` | `load` 결과 | 열 `term, eta2, ci_lo, ci_hi` (`rng = numpy.random.default_rng(seed)` 로 `resample_thetas` 를 n_boot 번, 백분위 95%) |
| `plot_eta2(table, path)` | `eta2_bootstrap` 결과 | 항목별 η² 막대 + 95% CI 오차 막대 그림 (png) |
| CLI: `python bt/analysis/anova.py <games.csv> --out <폴더>` | | `<폴더>/rq1_eta2.csv`, `rq1_eta2.md` (표), `rq1_eta2.png` |

`analysis/confirm.py`
| 함수 | 입력 | 출력 |
|---|---|---|
| `paired(df, baseline_id) -> DataFrame` | games.csv DataFrame (wall_clock 뺀 것), 기준 θ 의 `theta_id` | 후보 θ × 셀마다 한 행: `theta_id, scenario, opponent, seed_salt, d_dwez, d_win, d_hp` (후보 − 기준). 짝이 안 맞는 셀이 있으면 오류 |
| `compare(df, baseline_id, alpha=0.05, mid=0.5) -> DataFrame` | 같음 | 후보마다 한 행: `theta_id, n, mean, ci_lo, ci_hi, p_one_sided, p_holm, better, practically_better, p_tost, equivalent, win_diff, hp_diff` |
| CLI: `python bt/analysis/confirm.py <games.csv> --baseline <theta_id> --out <폴더>` | | `<폴더>/confirm.csv`, `confirm.md` |

- 짝 비교의 검정·CI·TOST 는 짝 차이에 대한 t 분포 (자유도 n − 1) 로 계산한다 (PREREG_BT.md §6.4).
- `win_diff`, `hp_diff` 는 보조 지표 짝 차이 평균 (서술용, 판정에 안 씀).

## 시험 데이터 위치

- `kit/bt/analysis/fixtures/pilot2_sample.csv`: 실측 일부 (보정 상대 재예비 실험, θ 50개 × 48경기, 분석에 필요한 열만). **실행되는지 확인용** (정답 없음).
- `kit/bt/analysis/fixtures/synth.py`: 정답을 아는 합성 데이터. `synth.rq1(path)`, `synth.confirm(path)` 로 CSV 를 만들고 정답은 `synth.TRUTH_RQ1`, `synth.TRUTH_CONFIRM`.
  합성 CSV 는 커밋하지 않는다 (테스트 안에서 임시 폴더에 만든다). 엔진을 import 하므로 `cadet_research/kit/` 에서 실행한다.

## 완료 기준

`cadet_research/kit/` 에서 `python -m pytest bt/analysis/test_anova.py bt/analysis/test_confirm.py` 가 모두 통과 (pytest 가 없으면
`python bt/analysis/test_anova.py` 처럼 각 파일을 직접 실행해도 되게 `if __name__ == "__main__":` 를 둔다). 테스트에 최소한 아래가 있어야 한다.

1. `test_anova.py`
   - `synth.rq1` 데이터에서 `eta2()` 7개 값이 `TRUTH_RQ1["eta2"]` 와 `TRUTH_RQ1["tolerance"]` (1e-6) 안에서 같다.
   - 같은 데이터에서 `eta2_bootstrap(n_boot=200)` 의 각 CI 가 점추정을 포함하고, seed 가 같으면 결과가 같다.
   - `pilot2_sample.csv` 로 CLI 가 오류 없이 돌고 세 파일을 만든다 (η² 합 = 1).
   - **균형 검사:** `synth.rq1` 데이터에서 한 행을 지우면 `eta2()` 가 `ValueError` 를 내고, 메시지에 지운 칸 `(theta_id, scenario, opponent, seed_salt)` 이 들어 있다.
     한 행을 복제해도 (겹친 칸) 오류를 낸다.
   - **재표집 이름 붙이기:** `resample_thetas` 결과는 항상 θ 이름이 64개로 서로 다르고 이름마다 정확히 48행이며 (`check_balance` 통과),
     같은 원래 θ 가 두 번 이상 뽑힌 표본이 실제로 나오는 seed 에서 그 θ 가 서로 다른 이름 여럿으로 들어 있다.
     또 그런 표본에서 θ 항의 자유도 (서로 다른 θ 수준 − 1) 가 63 이다 (같은 이름으로 합쳐 버리면 63 보다 작아진다).
2. `test_confirm.py`
   - `synth.confirm` 데이터에서 후보 3개의 `mean` 이 `TRUTH_CONFIRM` 의 delta 와 1e-9 안에서 같고, `better`, `practically_better`, `equivalent` 가 정답과 같다.
   - `p_one_sided` 가 정답 참고값과 소수 3자리에서 같고, `ci_lo`, `ci_hi` 가 정답 `ci95` 와 0.001 안에서 같다.
   - 짝이 안 맞는 데이터 (후보에서 한 행을 지움) 를 주면 오류를 낸다.

예시 출력 (합성 데이터, 형식 예):

```
term               eta2    ci_lo   ci_hi
theta              0.3000  ...     ...
geometry           0.1000  ...
...
theta_id      n    mean   ci_lo  ci_hi  p_one_sided  p_holm  better  practically_better  p_tost  equivalent
<cand_big>    432  0.800  0.611  0.989  6.1e-16      ...     True    True                ...     False
<cand_small>  432  0.200  0.011  0.389  0.0191       ...     True    False               ...     True
<cand_zero>   432  0.000 -0.189  0.189  0.5          ...     False   False               ...     True
```

## 하지 말 것

- PREREG_BT.md 에 없는 분석 방법 (다른 모형, 다른 보정, 다른 지표, 혼합효과 모형 등) 을 새로 만들거나 추가하지 않는다.
- 사양의 숫자 (2,000회, seed 20261108, α 0.05, 0.5 s, Holm, TOST ±0.5 s) 를 바꾸지 않는다.
- 엔진·`bt/` 기존 코드·PREREG_BT.md·CONTRACT.md·`fixtures/` 를 고치지 않는다. 결과 CSV 를 커밋하지 않는다.
- bt-main·bt-confirm 시뮬레이션을 돌리지 않는다 (이 TASK 는 분석 코드만).
- bt-study 에 직접 push 하지 않는다.

## 막히면 할 일

추측해서 사양을 바꾸지 말고 **멈춘다.** 이 파일 끝 "질문" 절에 질문을 번호로 적고 (무엇이 모호한지, 생각한 선택지), 커밋·push 한 뒤 연우에게 알린다.
답을 받기 전에는 그 부분을 구현하지 않는다 (다른 부분은 계속해도 된다).

## 완료 보고

(끝나면 여기에 적는다: 커밋 번호, 테스트 결과, pilot2_sample 로 낸 η² 표)

## 질문

(없으면 비워 둔다)
