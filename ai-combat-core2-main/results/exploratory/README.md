# results/exploratory — 탐색 단계 결과 (동결, 2026-09-14)

**논문 표·그림에 쓰지 않는다.** 논문 데이터는 `research/l3_indi/` 하네스로 새로 생성한다
(`docs/EXPERIMENT_PLAN.md` §6, `docs/PREREGISTRATION.md`).

- 데이터 파일은 git 추적 대상이 아니며(용량), 읽기 전용으로 설정했다.
- `MANIFEST.csv` 가 파일별 SHA-256, 행 수, 생성 스크립트와 그 커밋, 실행 조건, 요축 법칙, G 계산 방식,
  알려진 문제, **재현 검증 결과**를 담는다. 생성: `python scripts/freeze_exploratory.py`.

## 재현 검증 요약 (코드 커밋 9181fe0 에서 재실행 후 대조)

| 결과 | 파일 수 |
|---|---:|
| 비트 동일 (`identical`, 시계열 전부 포함) | 9 |
| 벽시계 열(`wall_time_s`)만 다르고 나머지 동일 | 9 |
| 구버전 열 구성, 공통 열 값 전부 동일 (`indi_step_limiter_compare`) | 2 |
| 텍스트 출력 동일 (`g_envelope_output.txt`, `measure_g_envelope.py`) | 1 |
| 생성 스크립트 없음 — 교차 대조만 가능 | 7 |

생성 스크립트가 없는 7개 중 `repeat_variance.csv`, `envelope_violation_scan.csv`, `corner_pull_diag/*.csv` 3개는
재현 가능한 스윕 결과와 값이 일치했다. `rudder_zero_compare.csv` 는 러더 정상 3행만 일치(러더 0 행은 대조 대상 없음),
`coordinated_vs_original_compare.csv` 는 구버전 협조선회판 기준이라 대조할 수 없다.

## 2026-09-14 정리 시 삭제한 파일 (중복·동작확인용)

| 삭제 | 사유 (삭제 전 확인) |
|---|---|
| `indi_step_coordinated_summary.csv`, `indi_step_coordinated_15k400_summary.csv`, `g_onset_15k400_summary.csv`, `g_onset_15k450_summary.csv` | 각 스윕 디렉터리의 `summary.csv` 와 **바이트 동일**한 사본 |
| `corner_pull_summary_full.csv`, `indi_step_summary_full.csv` | 각 스윕 `summary.csv` 의 구버전. 공통 22/24열 **전 행 값 일치**, 진단 열만 없음 |
| `indi_step_sweep_quick/`, `corner_pull_sweep_quick/`, `indi_step_sweep_coordinated_quick/` | `--quick` 동작확인 출력 (본 스윕이 상위집합) |
