# research — 반사실 롤아웃 증류 연구 하네스 (구명: port_measure)

core2 엔진(aircombat/)을 **블랙박스 오라클**로 호출하는 실험층. 엔진 코드와 격리되어
있으며(판정·비행 계층 무접촉), 대회-정합 정본 정책과 그것을 만든 파이프라인 전체를
담는다. 배경·방법·성적의 전체 서사는 `docs/rollout_distillation_methodology.md`
(1~9부), 자동화 설계는 `docs/AUTOMATION_PLAN.md`.

## 정본 정책 (128승 0무 0패, 회귀 0)

> ⚠️ **배포 후보 자격 보류 (2026-07-20).** 아래 성적은 **고정 초기조건 하나**에서
> 잰 것이다. 초기조건 20종 스윕(3,000판 대응표본)에서 문장 정책은 65.2%, **문장을
> 끈 기저는 70.2%** 로 문장이 순손해였고(McNemar z=−7.12, 순효과 −152판), 방어
> 국면은 표본 전패였다. 원인은 문장 하나하나가 아니라 **합성 절차가 고정 IC 하나
> 위에서 돌았다는 것**이다. 상세와 처방은 [`docs/IC_ROBUSTNESS.md`](../docs/IC_ROBUSTNESS.md).
>
> ⚠️ **G 봉투 교정도 반영할 것 (2026-07-20).** 리미터가 ±9G 대칭이라 실기에 존재할
> 수 없는 −9G 밀기가 허용되고 있었다(유도층 감사 로그에는 −16.25G 명령). F-16 의 음의
> 한계는 기골 설계 하중 −3.0G 다. 교정하자 정본 IC 성적이 **142승 4무 0패 → 136승
> 4무 10패**로 내려갔다 — 정본이 그만큼 비물리적 여유에 기대고 있었다는 실측이다.
> 아래 수치는 모두 **교정 이전** 값이다.

- **정본(루프31, f31_A11)** = 전사 기저 + 점수-장부 게이트 + **함수-구간 문장 11개**
  (관계형+race 9 + 절대예외 2; race=eata−ata 조준 경쟁축, AUC 0.997).
  구(舊)정본 final_v3(문장 10)는 성능 동등(128-0, LOFO 59.4% 동률) — 계보 보존.
- **실행**: `LG_SURGICAL=1 LG_RULEBOX=research/data/blueteam/induced_rules_f31_A11.json`
- **재현(전수 128판, 결정론)**:
  ```
  LG_ONLY=$(cat roster/all_128.txt) LG_REPLAY=1 LG_SURGICAL=1 \
    LG_RULEBOX=research/data/blueteam/induced_rules_f31_A11.json \
    python research/proto_ledger_gate.py
  ```
- 발화 스케줄 지문: `data/blueteam/induced_rules_f31_A11.fingerprint.json` (발화 32판 =
  정확히 플레인 기저 32패 — 96승리판 전 문장 휴면)
- 제출 형식: `agents/champion128.yaml` — 문장이 YAML 가지로 보이는 3층 BT
  (생성기 `gen_champion_yaml.py`, 결과 HPΔ 128/128 연구 런타임과 일치)

## 도구 카탈로그 (파이프라인 스테이지별)

**단일 진입점** — 아래 도구 전부를 한 명령으로 잇는 오케스트레이터(멱등·중단 재개):

```
python -m research.framework run --agent agents/champion128.yaml --roster roster/all_128.txt \
       [--replay] [--lofo] [--dry] [--fresh]
# 불변식(M1) → 플레인 기저 → 폐루프(M2 데몬) → 다이어트 → YAML 번역 → 128 게이트+패리티
python -m research.framework stats|diff|schedule ...   # 결과 통계 / 전판 대조 / 발화 스케줄
```

| 스테이지 | 도구 | 역할 |
|---|---|---|
| **진입점** | `framework.py` | 전 스테이지 오케스트레이션 + 검증 서브커맨드(stats·diff·schedule) |
| S0 채점 | `proto_ledger_gate.py` | 배치 대전 러너(LG_* env; replay·CSV·디브리프 자동) |
| S1 진단 | `metric_scanner.py` | 지표은행 × AUC 전수 — 판별자 자동 보고 |
| S4 되감기 | `branch_search.py` | 반사실 강제-개입 전수(BS_* env; 시드 지원). `BS_TARGET=opp` = 레드팀 모드(상대측 강제 — 구 red_search 흡수, 뚫림=P3 반례) |
| S5 귀납 | `rule_induct.py` | 증인→조건상자 합성(엄격분리·진입틱 검증; RI_* env) |
| S7 무인루프 | `cegis_daemon.py` | 채점→수확→귀납→재채점 자동 반복(CD_* env) |
| S8 자가검증 | `pipeline_invariants.py` + `test_pipeline_invariants.py` | 함정 카탈로그의 기계 검사(pytest) |
| 검증 실험 | `lofo_driver.py` | 가족-제외 교차검증(LOFO) |
| 증명서 | `min_rules_bound.py` | 문장 수 하한(충돌그래프+z3 MIS) |
| 정본 런타임 클로저 | `champion_core.py` `champion_pilot.py` `run_champion_match.py` `rescore_ported.py` `transcribe.py` `run_transcribed_match.py` `prototype_floor_recovery.py` | 증류트리·전사 기저·로스터·계측 매치 (정책 실행에 필요) |
| 진단 보조 | `debrief.py` | replay 분석·비교(--compare 6패널) — 로직 정본은 `aircombat.debrief.replay_debrief`(승격 완료), 여기는 호환 shim |
| 공정2·3 번역 | `gen_champion_yaml.py` | 문장 JSON → `agents/champion128.yaml` 3층 BT 생성(손편집 금지·재생성) |
| 공정3 스냅 | `gen_base_snap.py` | 증류트리 joblib → `base_tree.json` 명시 분기(경계-정확 20만 벡터 검증) — 제출물 런타임서 joblib/sklearn 의존 제거 |
| 공정3b 다이어트 | `slim_rules.py` | 문장 박스의 발화-무관 축 제거(전-발화 스케줄 불변 증명; 132→51축) + 경계 4자리 정리 → `…_A11_slim.json` (YAML 표시 정본) |

루트 .py 는 위 17개가 전부다. 과거 프로토타입·일회성 진단·구규칙 체인 도구
26종 + YAML 동치 진단 3종(`diag_eqv*`)은 정리 시점(2026-07-18)에 삭제됐고,
필요하면 git 이력에서 복구한다. 데이터의 유효성 등급은 `data/README.md` 참조.

## 데이터 배치

| 경로 | 내용 | 저장소 포함 |
|---|---|---|
| `models/` | 증류트리 joblib (자립화 — core-live 불필요) | ✓ |
| `data/blueteam/*.json` | 문장(세대별)·지문·귀납 산출 | ✓ |
| `data/blueteam/*.csv` | obs 덤프(대형) | ✗ 재생성: 채점 커맨드에 `LG_OBSDUMP=<경로>` |
| `../roster/` | 상대 64종 YAML + `all_128.txt` 판 목록 (엔진 배치 러너와 공용이라 최상위) | ✓ |
| `campaigns/witness/` | 되감기 증인 로그(케이스별 정답 목록) | ✓ |
| `campaigns/logs/` | 캠페인 실행 로그 전체 | ✓ |
| `campaigns/lofo/` | LOFO 행렬·fold 로그 | ✓ |
| `../replays/legacy/` 세대 녹화 | ACMI·CSV·PNG (17GB) | ✗ 결정론 재생성(위 재현 커맨드 + 세대별 env는 `replays/README.md`) |
| `results/` | 핵심 결과 큐레이션 | ✓ |
| `data/redteam/` | 레드팀 전수 CSV | ✓ |
