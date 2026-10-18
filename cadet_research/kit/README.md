# 실험 키트

이 폴더 하나로 실험 전체를 돌린다. 엔진(`aircombat/`, `jsbsim_data/`, `config/`)은 2026-10-14 core2 작업 트리의 스냅샷이고, 버전과 해시는 `ENGINE_VERSION.txt`에 있다. 엔진 파일은 고치지 않는다. 고치면 다른 사람의 결과와 비교할 수 없다.

## 1. 설치

Python 3.12 이상 (점검은 3.14.2).

```bash
cd kit
python -m pip install -r requirements.txt
```

## 2. 본실험 순서

반드시 이 순서로 한다. 분석기는 앞 단계의 등록 파일이 없으면 멈춘다.

| 단계 | 실행 | 분석 | 시간 (20 프로세스) | 남는 것 |
|---|---|---|---|---|
| 0 | `python run.py --selfcheck` | — | 1분 | 화면에 `E0 통과` |
| 1 | `python run.py E1 --procs 20` | `python predict.py E1` | 15–25분 | `out/cal/tolerance.json` (허용폭 δ) |
| 2 | `python run.py E2 --procs 20` | `python predict.py E2` | 2.5–4시간 | `out/main/curve.json` (곡선) |
| 3 | `python run.py E3 --procs 20` | `python predict.py E3` | 2.5–4시간 | `out/main/report_predict_E3.md` (예측 판정) |
| 4 | `python run.py E4 --procs 20` | `python predict.py E4` | 1–1.5시간 | `out/gen/report_predict_E4.md` |

승·무·패와 종료 사유 표는 `python analyze.py E2`처럼 따로 뽑는다. 이 분석기는 리그 점수 판정용으로 만든 것이라, 판정 절은 참고만 한다.

`--procs`는 CPU 코어 수보다 작게 준다. 8코어면 `--procs 6`이고 시간은 약 3배다. 끊기면 같은 명령을 다시 치면 이어서 돈다. 경기 수만 보려면 `--dry`.

## 3. 돌려 보기만 할 때

확증 시드(`main-*`)를 미리 보면 안 된다. 실행 점검은 시드 접두어를 바꾸고 참가자를 3명으로 줄인다.

```bash
for e in E1 E2 E3 E4; do python run.py $e --salts 2 --prefix smoke --quick --procs 20; done
for e in E1 E2 E3 E4; do python predict.py $e --prefix smoke; done
```

약 2,000경기, 20 프로세스로 15–25분.

## 4. 사전 실험 재현

주제를 정한 탐색 데이터(`../FEASIBILITY.md`)를 다시 만든다.

| 명령 | 내용 |
|---|---|
| `python run.py FEAS --procs 20`, `python analyze.py FEAS` | 단계 1 사전 실험 (2,520경기) |
| `python margin.py linear`, `python margin.py bench --procs 20` | 지연 여유: 선형 이론, 제어기 단독 벤치 |
| `python run.py DOSE --procs 20`, `python dose.py` | 필터 × 지연 용량-반응 (7,200경기) |
| `python run.py ROUTE --procs 20`, `python route.py` | 다른 원인 경로 (2,880경기, DOSE와 같은 폴더) |
| `python predict.py FEAS2` | DOSE로 적합, ROUTE로 예측 |
| `python run.py PROBE --procs 20` | 다른 원인으로 추종 오차를 얼마나 키울 수 있는지 탐침 (390경기, `out/probe`) |
| `python run.py SIG --procs 20`, `python predict.py SIG` | 유의성 확인: 시드 6개 `feas3-*`, 14,040경기, 약 1.7시간 |

## 5. 파일

| 파일 | 내용 | 고쳐도 되나 |
|---|---|---|
| `experiments.py` | 조건(열화 원인과 수준), 참가자, 실험 정의 | 새 조건 추가만. 기존 정의를 바꾸면 이미 돈 결과와 섞인다 |
| `run.py` | 열화 주입과 리그 실행, 자가점검 | 버그를 찾았을 때만. 고치면 `--selfcheck` 재통과 |
| `predict.py` | 본실험 분석: 허용폭, 곡선 적합, 예측 검증 | 그림·표 추가는 자유 |
| `analyze.py` | 승·무·패, 종료 사유, 참가자별 점수, 순위 | 자유 |
| `margin.py`, `dose.py`, `route.py` | 사전 실험 분석 | 자유 |
| `agents/main/`, `agents/e4/` | 참가자 8종, 12종 | 아니오 |
| `out/<접두어>/games.csv` | 경기별 원자료. 한 줄이 한 경기 | 아니오 |

`games.csv`의 열: `cond` 조건, `target` (빈칸), `blue`·`red` 참가자, `scenario`, `salt` 시드, `winner` 승자(무승부 `draw`), `condition` 종료 사유(`health_zero` 격추, `hard_deck` 저고도 이탈, `timeout` 시간 종료, `no_contact` 무접촉, `stall` 실속), `hp_blue`·`hp_red` 종료 체력, `*_corr_q`·`*_mae_q_dps` 기체별 피치 추종 상관과 오차 [°/s], `wall_s` 실행 시간.

## 6. 열화가 걸리는 방식

`run.py`는 엔진 파일을 고치지 않는다. 경기마다 `Pilot.setup()`이 INDI를 만든 직후 다음을 덧씌운다.

| 키 | 하는 일 |
|---|---|
| `kappa` | INDI가 믿는 제어효과 행렬 G0의 피치 행에 κ를 곱한다 |
| `kq` | 피치 각속도 게인 `k_rate[1]`에 배율을 곱한다 |
| `filt_hz` | 동기화 필터 세 개를 같은 새 차단주파수로 바꾼다 |
| `sigma_dps` | INDI가 받는 각속도 측정에 백색잡음을 더한다 |
| `delay_async` | 각속도·각가속도 측정만 N틱 전 값을 준다. 소수면 이웃 두 틱을 선형 보간한다 |
| `delay_sync` | 측정과 조종 입력 되먹임을 함께 N틱 전 값으로 준다 (정수만) |

추종 오차(`*_mae_q_dps`)는 잡음과 지연이 들어가기 전의 실제 피치 각속도로 계산한다.
