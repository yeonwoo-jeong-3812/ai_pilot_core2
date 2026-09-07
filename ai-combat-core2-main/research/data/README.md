# data — blueteam(생산) / redteam(공격) (구명: loop22_labels)

- **`blueteam/`** — 정책을 **만드는 쪽**: 되감기 정답, obs 덤프 CSV, 귀납 문장 JSON·지문, joblib.
  귀납 파이프라인의 입력·산출이며, 아래 유효성 등급표는 이 폴더의 파일 대상.
- **`redteam/`** — 정책을 **공격한 쪽**: 레드팀 전수 프로브 CSV(강건성 증거·P3 반례 큐).
  귀납 입력으로 쓰지 않는다 — 생산 데이터와 섞이면 오염.

## blueteam 유효성 분류

같은 폴더의 데이터라도 **어느 채점 규칙(게임) 아래에서 생성됐는지**에 따라 쓸 수
있는 용도가 다르다. 규칙이 바뀌면 정답이 이식되지 않는다는 것이 이 프로젝트의
실측(방법론 6부: 구규칙 최종구성이 신규칙에서 61-23으로 붕괴)이므로, 아래 3등급을
지켜 사용한다. (대형 CSV는 gitignore — 재생성 커맨드는 `../README.md`.)

## 등급 A — 현행 유효 (현 정책·도구의 입력)

| 파일 | 내용 | 사용처 |
|---|---|---|
| `induced_rules_uprule_final_v3.json` (+`.fingerprint.json`) | **정본 문장 10 + 발화 지문** | 배포·불변식 검사 |
| `induced_rules_uprule_v2.json` 등 uprule 세대 JSON | 신규칙 문장 계보(v1/v2b/rel*/abs*) | 감사·비교 |
| `obs_dump_plain_all_es.csv` (15특징) | 신규칙 플레인 기저 128판 궤적 | lofo_driver·min_rules_bound 입력 |
| `obs_dump_seed{1..3}_v2.csv` | 신규칙 시드 궤적(루프30) | 시드-횡단 분석 |
| `obs_dump_finalv2_all.csv` · `obs_dump_canon_v2.csv` | 배포-구성 궤적 | 지문·2차간섭 분석 |
| `daemon_*` JSON | 무인루프 산출 | M2 감사 |

## 등급 B — 신규칙·구세대 (분석용 유효, 현행 입력으로는 비권장)

| 파일 | 사유 |
|---|---|
| `obs_dump_uprule_{losses,wins}.csv` (12특징) | es_rel·t·fdmg 부재 — 특징 부분집합 분석만 |
| `obs_dump_uprule_v2_all.csv` (13특징) | v1-문장 구성 궤적 — 그 세대 분석 전용 |
| (삭제) `loop22_labels_nose1/` 신규칙 조기 라벨 | 잠정 ATA 수정 엔진(공식 병합 전) 산출 — 정리 시점(2026-07-18)에 로컬 삭제, 결정론 재생성 가능 |
| `induced_rules.json`·`induced_rules_nose.json` | 구세대 문장(현행 미사용) |

## 등급 C — 구규칙 (교차-규칙 분석 전용 — 현행 정책 판단에 사용 금지)

| 파일 | 사유 |
|---|---|
| `labels_*.csv` (정답 1,576) · `obs_dump_C_*.csv` · `obs_dump_v20_ext.csv` | 속도벡터-WEZ 게임의 데이터 — **다른 게임**. "규칙 변경 시 무엇이 이식되는가" 류 비교 연구에만 |
| `rule_tree_12.joblib`·`cost_*.joblib` | 구규칙 12문장·cost 모델 |
| (삭제) `loop21_artifacts/` | 구규칙 초기 아티팩트 — 정리 시점에 로컬 삭제 |
