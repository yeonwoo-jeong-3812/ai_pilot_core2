# replays — 세대 색인과 재생성 규약

세대 폴더(ACMI+CSV+디브리프 PNG, 판당 3파일)는 용량(총 ~17GB) 때문에 저장소에서
제외한다. **엔진이 결정론이므로 전 세대가 커맨드로 비트-동일 재생성된다** — 아래
표의 env 로 `proto_ledger_gate.py` 를 `LG_REPLAY=1` 과 함께 실행하면 된다.
공통: `LG_ONLY=$(cat roster/all_128.txt)` (84판 세대는 `LG_SCOPE=full` 사용).

| 세대 폴더 | 성적 | 구성 env |
|---|---|---|
| `ledger_auto_uprule_finalv3_128_0/` | **128-0-0 (정본)** | `LG_SURGICAL=1 LG_RULEBOX=…final_v3.json` |
| `ledger_auto_uprule_v2b_128_0/` | 128-0-0 (절대혼합 대안) | `…uprule_v2.json` (r2-선두 병합본) |
| `ledger_auto_uprule_rules7_84_0/` | 84-0-0 (1회전) | `…uprule.json`, `LG_SCOPE=full` |
| `ledger_auto_uprule_rel_126_2/` | 126-2 (관계형 1차) | `…uprule_rel.json` |
| `ledger_auto_upstream_gateonly_61_23/` | 61-23 (플레인 게이트) | 문장 env 없음, `LG_SCOPE=full` |
| `ledger_auto_upstream_rulebox_61_23/` | 61-23 (구문장 불활성 재현) | `LG_RULEBOX`만, `LG_SURGICAL` 미설정 |
| `ledger_auto_upstream_pipper4500_65_19/` | 65-19 (전역 파이퍼 반증) | `LG_PIPPER=1 LG_PIPPER_RNG=4500`, `LG_SCOPE=full` |
| `ledger_auto_newrule_oldengine_83_1/` 등 구룰 3종 | 구엔진 시대 | 해당 커밋 체크아웃 필요(방법론 1~5부) |
| `daemon_*/` | M2 무인복구 작업분 | `cegis_daemon.py` (CD_TAG 별) |
| `diag_singles/` 등 진단 폴더 | 단판 드릴 | 각 로그 참조 |

저장소 포함분: `witness/`(되감기 증인 로그 — 정답 데이터), `logs/`(캠페인 실행
로그 전체), `lofo/`(가족-제외 교차검증 행렬·fold 산출).

세대 보존 규율: 실행 **전** 폴더명을 세대명으로 확정하고, 기존 폴더 덮어쓰기는
`pipeline_invariants.claim_generation_dir` 가 거부한다.
