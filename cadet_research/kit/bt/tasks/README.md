# BT 본실험 팀원 작업 지시서

각 TASK 파일은 **그 파일 하나만 읽고** 팀원의 Claude Code 가 바로 작업을 시작할 수 있게 썼다.
사양의 원본은 `cadet_research/PREREG_BT.md` 와 `cadet_research/kit/bt/CONTRACT.md` 다. 지시서와 둘이 어긋나면 PREREG_BT.md 가 맞다.

> **2026-11-05:** 분석 코드 (`analysis/anova.py`, `confirm.py`, `morris.py`, `surrogate.py`, `test_analysis.py`) 는 TASK_A·B 사양대로 연우가 구현했다
> (팀원 브랜치에 분석 코드가 오지 않아서). 본실험 결과를 보기 전에 커밋했다.

## 지시서 목록

| 파일 | 맡는 사람 | 작업 | 브랜치 | 마감 |
|---|---|---|---|---|
| `TASK_A_rq1_confirm.md` | 코딩 팀원 1 | RQ1 분산분해 (`analysis/anova.py`), 확인 단계 비교 (`analysis/confirm.py`) | `bt-task-a` | 2026-11-06 |
| `TASK_B_morris_surrogate.md` | 코딩 팀원 2 | Morris μ*·μ·σ (`analysis/morris.py`), 대리모델·SHAP (`analysis/surrogate.py`) | `bt-task-b` | 2026-11-06 |
| `TASK_RUN.md` | PC1 연우, PC2 주엽, PC3 주혁 | 본실험 계산 분담 (`--shard i/3`) | 없음 (코드 안 고침) | 태그 `prereg-bt-v1` 생성 뒤 시작, 2026-11-06 까지 결과 전달 |

## 작업 순서

1. 연우: PREREG_BT.md 고정 전 점검표 확인 → 태그 `prereg-bt-v1` 생성 (그 전에는 bt-main·bt-confirm 실행이 거부된다).
2. 코딩 팀원 1·2: TASK_A, TASK_B 를 **동시에** 진행 (서로 다른 파일만 고친다). 시험 데이터 (`bt/analysis/fixtures/`) 로만 개발한다.
   본실험 결과가 없어도 끝낼 수 있다.
3. PC 팀원: 태그가 생기면 TASK_RUN 으로 RQ1·RQ2 를 나눠 돌리고 결과 파일을 팀 공유 구글 드라이브 'BT논문/bt-main' 폴더 에 올린다 (2026-11-06 까지).
4. 연우: 결과를 `bt/merge.py` 로 합치고, TASK_A·B 브랜치를 검토해 bt-study 에 합친 뒤 본실험 결과에 분석을 돌린다.
5. RQ3 (확인 단계) 는 11/13 관문 (대리모델 R² 기준 충족 + 계산 여유) 을 넘을 때만 진행한다 (PREREG_BT.md §1).

## 공통 규칙

- 팀원은 **자기 브랜치에서만** 작업하고 `bt-study` 로 직접 push 하지 않는다. 합치기는 연우가 검토 뒤 한다.
- 지시서의 "수정해도 되는 파일" 밖은 고치지 않는다. 엔진 (`kit/aircombat/`, `jsbsim_data/`, `config/`), 원본 상대 (`kit/agents/`),
  `bt/` 의 기존 코드, PREREG_BT.md, CONTRACT.md 는 고치지 않는다.
- 사양이 모호하면 추측해서 바꾸지 말고, 멈추고 그 TASK 파일 끝 "질문" 절에 적은 뒤 연우에게 알린다.

## Claude Code 에 처음 입력할 한 줄

- 코딩 팀원 1: `cadet_research/kit/bt/tasks/TASK_A_rq1_confirm.md를 읽고 작업을 시작해`
- 코딩 팀원 2: `cadet_research/kit/bt/tasks/TASK_B_morris_surrogate.md를 읽고 작업을 시작해`
- PC 팀원: `cadet_research/kit/bt/tasks/TASK_RUN.md를 읽고 내 PC 몫을 실행할 준비를 해 줘. 나는 PC<번호>야`
