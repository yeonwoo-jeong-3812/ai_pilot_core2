# PC3 (주혁) 본실험 실행 기록

- PC: PC3 주혁, shard 3/3, host DESKTOP-VRMJI86 (AMD Ryzen 7 4800H 8C/16T)
- code_commit: a7bbb5f88b9d
- Python 3.11.9

## 실행 기록

| 설계 | --procs | 시작 | 끝 | 경기 수 | wall_clock | disqualified | 파일 |
|---|---|---|---|---|---|---|---|
| main_lhs64 | 14 | 2026-11-03 10:24:37 | 2026-11-03 11:16:11 | 1024 | 0 | 0 | `bt\out\bt-main\games_main_lhs64_shard3of3.csv` |
| main_morris_r16 | 14 | 2026-11-03 11:58:11 | 2026-11-03 14:21:26 | 3072 | 0 | 0 | `bt\out\bt-main\games_main_morris_r16_shard3of3.csv` |

- 11:17–11:56 사용자 요청으로 일시 중단 (Morris 실행 전 점검 중이라 기록된 경기 없음). 재개 때 HEAD = 태그 커밋 a7bbb5f 확인, LHS 는 1,024경기 모두 건너뜀.
- 끝난 뒤 점검: 두 파일 모두 열 = FIELDS, 중복 0, code_commit·engine_sha·opponent_set·python_version 단일 값, wall_clock 0, disqualified 0.

## 질문

- **dummy 기준선이 0 으로 고정된다.** dummy 는 트리에 들어가지 않아서 dummy 만 다른 θ 는 같은 트리·같은 시드로 경기 결과가 완전히 같다.
  그래서 Morris 의 dummy 기본효과가 모두 정확히 0 이고 (이 shard 로 계산해 보니 μ* = μ = σ = 0, 궤적 16개 모두), 부트스트랩 CI 도 [0, 0] 이 된다.
  PREREG §6.2 의 중요 판정 "μ* CI 하한 > 더미 μ* CI 상한" 은 사실상 "μ* CI 하한 > 0" 이 되어 효과가 조금이라도 있는 파라미터는 모두 '중요' 로 판정될 수 있다
  (이 shard 근사로는 10개 모두 μ* 0.39–1.88 s). 시험 데이터 (`fixtures/synth.py`) 는 dummy 에 잡음이 있어 이 상황이 드러나지 않았을 수 있다.
  고정 뒤라 고치지 않았고, 처리 방법 (DEVIATIONS 기록 여부 등) 은 연우 판단에 맡긴다.

## crosscheck 출력 마지막 3줄

```
python_version 3.11.9
engine_sha     1e0101026959
전체 해시      fc6501b873df43e1
```
