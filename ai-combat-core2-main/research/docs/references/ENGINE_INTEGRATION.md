# core 프로젝트 구조와 사용법 — 신엔진(new engine) 기반

> core를 **new engine 기반으로 재작성**한 결과를 정리한다. `new_match_engine`
> (JSBSim + 투명제어 LQR/INDI) 이 core의 **토대**가 되고, 레거시 `.pyd` 경로는
> optional 로 유지된다. 우리 **우승정책·연구 레이어·교재(book)** 가 함께 들어왔다.
> 브랜치 `feat/engine-into-src`, PR #35.

---

## 0. North Star (프레이밍 — 반드시 지킬 것)

이 프로젝트의 논지는 [`docs/book/CANON.md`](book/CANON.md) 0절이 정본이다:

> **"설명 가능하고, 결정론적이며, 교과서로 인용할 수 있는 방법만으로 F-16 자율
> 공중전 조종사를 처음부터 끝까지 구현한다."** — 투명성 · 결정론 · **일반화**.

정책은 특정 적 `.yaml` 신원에 과적합하지 않는다. 적을 **관찰 궤적의 행동유형**으로
blind 자가분류(적 정보 0)하고 그 유형의 독트린을 적용한다 — "그렇게 행동하는 어떤
적"에게도 같은 해가 작동한다. **CANON 의 wording 을 세션 순간의 표현으로 덮지 말 것.**

---

## 1. 전체 구조 — 무엇이 어디에

```
core/
├── src/
│   ├── engine/          ★ 신엔진 (토대). JSBSim + LQR/INDI + 투명정책
│   │   ├── bridge/          레거시 드롭인 어댑터 (--backend 스왑)
│   │   ├── control/         L2~L4 제어 스택 (guidance·autopilot·lqr·indi·plant·tactic·situation_cost)
│   │   ├── engine/          매치 코어 (match·judge·replay·obs·pilot·scenarios)
│   │   ├── bt/              BT 런타임(yaml_bt·tree_policy·situation) + 연구 실험(exp_*·d2_*)
│   │   ├── validation/      검증·분석 스크립트
│   │   ├── policy_yaml/     ★ 우승정책 ours.yaml 계열 + 커스텀노드
│   │   ├── data/ jsbsim_data/ opponents/   엔진 데이터·상대 풀
│   │   └── *.pkl *.npz      학습모델·연구 데이터셋 (정책 자체학습 가능, §5)
│   ├── tools/           ★ 분석·플롯 도구 (plot_match_3d_nme 등). 엔진의 형제 (경로규약 §7)
│   ├── match/           레거시 .pyd 매치 경로 (optional, §6)
│   ├── control/ behavior_tree/  레거시 보조 (py_trees 로더 등)
│   ├── simulation/      JSBSim 서브모듈 (물리)
│   ├── tournament/ submission/ api/   플랫폼 운영
│   └── ...
├── docs/
│   ├── book/            ★ 교재(정본). CANON + 01~17장 + LAB 09 (§4)
│   └── ENGINE_INTEGRATION.md   (이 문서)
├── bt-editor/           BT 편집기 (React/Vite, §8)
└── examples/            에이전트 .yaml (ace, aggressive, defensive, simple, ...)
```

★ = 이번 재작성으로 core에 들어오거나 토대가 된 것.

---

## 2. 신엔진 4계층 (`src/engine/`)

CANON 2절과 동일. 참가자 BT(L1)부터 물리(JSBSim)까지 **전부 투명**하다.

| 계층 | 위치 | 역할 |
|---|---|---|
| L1 BT | `bt/yaml_bt.py`, `bt/tree_policy.py` | .yaml 행동트리 해석·틱 |
| L2 유도 | `control/guidance.py` | 조준·에너지·추적 유도 |
| L3 오토파일럿 | `control/autopilot.py`, `control/lqr.py`, `control/linearize.py` | 캐스케이드 + 게인스케줄 LQR |
| L4 INDI | `control/indi.py`, `control/plant.py` | 증분 비선형 동적역변환 |
| 물리 | `src/simulation/` (JSBSim F16) | 60Hz 적분 |
| 판정 | `engine/judge.py` | hard-deck 우선 승패 |
| 리플레이 | `engine/replay.py` + `src/tools/plot_match_3d_nme.py` | ACMI + 3D plot/report |

---

## 3. 우승정책 — `src/engine/policy_yaml/`

우리 연구의 **최종 산출물**. 단일 파일이 아니라 **번들**이다.

| 파일 | 내용 |
|---|---|
| `ours.yaml` | 17/17 정책(IntelPolicy)의 **구조트리(.yaml) dual** — 의사결정을 BT 노드로 노출 |
| `ours_stage1.yaml` | Stage 1 (단일 액션) 버전 |
| `ours_d2_weakstate.yaml` (+`_SPEC.md`) | D2 약상태 전용 분기 |
| `nodes/custom_actions.py`, `custom_conditions.py`, `_ours_stage2_ctx.py` | 커스텀 BT 노드 → 공유 `IntelPolicy` 의 `_sync/_d2/_a3/_base_branch` 호출 |
| `validate_ours_yaml.py` | .yaml == .py **틱-동일(dual)** 검증 + 17적 both-INDI blind 승수 |

`ours.yaml` 은 `bt/`의 실험 계보(`exp_e53_integrated_17`·`exp_e7_champion`·
`exp_e10_unified`·`exp_e22_chaseforce` 등)와 **학습모델**에 의존한다. 모델은
`run_match.py`/`validate_ours_yaml.py` 가 **런타임에 자체 학습**(`_prime_ours_model`)해
tempfile 로 공유하므로, `bt/*.pkl` 이 없어도 재현된다(있으면 재학습 생략).
→ 그래서 연구 레이어(exp_*)를 통째로 들여와야 정책이 돈다. §5 참조.

---

## 4. 교재(book) — `docs/book/`

프로젝트 지식의 본체. **`CANON.md` 가 단일 진실원천**이고 나머지는 이를 따른다.

- 이론·구현 장: `01_problem_and_motivation` … `17_findings_prediction_and_fidelity`
  (BFM 상황, F16, 선형화, LQR, 캐스케이드, INDI, 유도, 관측, 결정정책, 오프라인정책,
  아키텍처, 엔진교체, 시나리오, 검증, 충실도)
- 실습: `LAB_01_hands_on` … `LAB_09_yaml_dojo`
- 정책 해설: `FINAL_POLICY_EXPLAINED.md`, 시작점 `START_HERE_combat.md`

**규칙(CANON 8절):** 문서의 숫자는 캐노니컬 점수(both-INDI)와 일치해야 하고, D2 서사·
충실도 표현은 CANON 그대로 쓴다. 세션 순간 wording 을 append 하지 않는다.

---

## 5. 연구 레이어를 왜 통째로 — 이식 방식

**신엔진이 토대**라는 건 core의 `src/engine/` 이 `new_match_engine` 정본과 **일치**한다는
뜻이다. 기존 core 에는 오래된 큐레이션 스냅샷(47py)이 얹혀 있었는데, 이는 정본보다
**낡아**(예: `tactic.py` 에 `ETM_TRACK` 없음) 우승정책이 돌지 않았다. 그래서:

- `new_match_engine` 전체를 `src/engine/` 로 **충실히 이식**(replays·AddOns·pycache 제외).
- 진입점 계약만 재적용: `bridge/{run_legacy,verify_swap,__init__}` 의
  `new_match_engine.bridge` → `src.engine.bridge`.
- 분석·플롯 도구는 엔진의 **상위 형제** `src/tools/` 로(경로규약 §7).

결과: 라이브 플랫폼 경로(`--backend indi/legacy`)와 우승정책(`validate_ours_yaml`)이
**같은 정본 코드**로 동작. exp_*·validation·모델·데이터셋은 재현을 위해 보존한다
(CANON: "죽은 코드는 삭제 아닌 보존"). **`replays/` 11GB 만 재생성 가능해 git 제외.**

---

## 6. dual-path — 신엔진 메인 + 레거시 optional

| | Path A — 신엔진 (기본) | Path B — 레거시 (optional) |
|---|---|---|
| 위치 | `src/engine/` | `src/match/` (.pyd), `src/control/`, `src/behavior_tree/` |
| 물리·제어 | JSBSim + LQR/INDI (투명) | LAG env + MatchCore(.pyd, RNN) |
| 진입 | `--backend indi` / `lqr` | `--backend legacy` |

`bridge/core_adapter.py` 가 레거시 `src/match/runner.py` 와 **동일 계약**(생성자·`.run()`·
result)을 제공하는 드롭인이라 `--backend` 하나로 바꿔 낀다. 동등성은
`python -m src.engine.bridge.verify_swap` 가 3중 증명(API 패리티·side-by-side·소비자패턴).
레거시는 비교·회귀 기준선으로 남긴다 — 참가자 제출·토너먼트 결정론 baseline 보존.

---

## 7. 경로 규약 (유지보수 시 주의)

엔진 내부 import 는 **파일-상대 sys.path** 다:
`sys.path.insert(0, os.path.join(dirname(__file__), "..", "control"))` 형태.
`new_match_engine` 이 `<root>/new_match_engine/`, 도구가 `<root>/tools/` 였던 구조를 그대로
옮겼으므로 core 에서도 **엔진=`src/engine/`, 도구=`src/tools/`** 를 형제로 둔다. 즉
`bt/` 스크립트의 `"..","..","tools"` = `src/engine/bt/../../tools` = `src/tools/` 로 해석된다.
→ **`src/engine/` 과 `src/tools/` 의 상대 위치를 바꾸지 말 것.**

---

## 8. BT 편집기 — `bt-editor/`

React/Vite 앱(`@xyflow/react`). 소스만 포함(node_modules/dist 는 `.gitignore`).
빌드: `cd bt-editor && npm install && npm run dev`.

**동기화 필수:** 편집기 `src/data/nodes-manifest.json` 노드 사전 ↔ 엔진
`src/engine/bt/yaml_bt.py` 노드 레지스트리. 현재 엔진이 **상위집합**이라 편집기 산출 BT 는
항상 유효하지만, 편집기에 없는 엔진 노드(`HammerHead`·`ImmelmannTurn`·`SplitS`·`SliceTurn`·
`SpiralClimb/Dive`·`Straight`·`TurnLeft/Right`·`Loop` / `IsDisengaging`·`IsNearOffensive`·
`IsScissors`)를 배치하려면 manifest 에 추가해야 한다.

---

## 9. 사용법

```powershell
# 신엔진(투명제어) 매치 + ACMI 리플레이
python scripts/run_match.py --agent1 examples/ace.yaml --agent2 examples/simple.yaml --backend indi

# 레거시 .pyd 로 스왑 (동일 인터페이스)
python scripts/run_match.py --agent1 examples/ace.yaml --agent2 examples/simple.yaml --backend legacy

# 엔진 드롭인 동등성 증명
python -m src.engine.bridge.verify_swap

# 우승정책 검증 (.yaml==.py dual + 17적 both-INDI blind 승수)
cd src/engine/policy_yaml && python validate_ours_yaml.py

# BT 편집기
cd bt-editor && npm install && npm run dev
```

> 교재부터 읽으려면 [`docs/book/START_HERE_combat.md`](book/START_HERE_combat.md) → [`CANON.md`](book/CANON.md).
