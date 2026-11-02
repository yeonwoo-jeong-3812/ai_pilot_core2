# 상대 고도 안전장치 보정 규칙

**이 문서는 보정 상대를 만들고 돌리기 전에 커밋했다.** 근거는 `bt/out/diag_hard_deck.md` (상대 하드덱 진단).
엔진, 심판 규칙, `kit/agents/` 원본 상대 파일은 고치지 않는다. 보정 상대는 `bt/opponents_patched/`에 새로 만든다.

## 원칙과 범위

- **원칙 (대칭성):** 상대에게 청 트리 (`bt/energy_fighter.yaml`, 기준 θ) 와 같은 고도 안전장치를 준다.
- **범위:** 상대 트리의 최우선 `low_altitude → climb` 노드만 바꾼다. 나머지는 바이트 단위로 같다 (줄끝 포함).
  `bt/test_bt.py`가 이것을 확인한다.

## 1단계: 청 recover 노드와 같은 값

청 기준 θ 의 최우선 노드 (`bt/energy_fighter.yaml` 19–20행, 파일에서 그대로 읽음):

```yaml
- condition: {name: low_altitude, floor_ft: 4500}
- action: {pursuit: pure, g_burst: 0.8, aim_above_ft: 4000, name: recover_altitude}
```

| 키 | 청 recover (기준 θ) | 상대 원본 climb (4종 동일) | 보정 상대 |
|---|---|---|---|
| condition | low_altitude | low_altitude | low_altitude |
| floor_ft | 4500 | 1200.0 | **4500.0** |
| lookahead_s | (없음 = 0) | (없음) | (없음) — 2단계에서만 |
| pursuit | pure | pure | pure |
| g_burst | 0.8 | (없음 = 기본 0) | **0.8** |
| aim_above_ft | 4000 | 4000.0 | 4000.0 |
| name | recover_altitude | climb | climb (유지) |

- `name`은 노드 이름표일 뿐 동작에 쓰이지 않는다 (DSL 은 이름을 기록·추적에만 쓴다). 상대 노드 기록 (`node_frac_red`)
  에서 원본 상대와 같은 키로 비교하려고 `climb`을 유지한다. 동작을 정하는 키는 모두 청 recover 와 같다.
- 숫자는 상대 파일의 원래 표기 (소수점 한 자리) 를 따른다. 값은 같다.

## 2단계 (1단계 불합격일 때만, 한 번만)

- `low_altitude`에 `lookahead_s: 6.0`을 추가한다. 나머지는 1단계 그대로.
- 근거: 엔진 `aircombat/tactics/conditions.py` `low_altitude` 설명문 — "730fps 강하에서 4,500ft 는 6초뿐인데 60° 강하
  회복에 4,500ft 가 든다. lookahead_s 는 침하율에 비례해 트리거를 앞당기므로 수평비행에서는 기본과 동일하게 동작한다."
  즉 floor 4,500 ft 가 6 초 분량의 강하 여유라는 설명이다. 6 초 앞의 예상 고도로 판정하면, 가파른 강하에서는
  침하율 × 6 초만큼 일찍 회복을 시작하고 수평비행에서는 1단계와 같다.

## 합격 기준 (상대 행동만 본다. 청 승률·wez 는 기준에 쓰지 않는다)

- 실행: 청 θ 3개 (`bt/thetas/diag.csv` = 기준 θ 에서 floor_ft 만 3000, 4500, 7000) × 48경기, `bt-diag` 시드, 보정 상대.
- **상대 하드덱 비율** = 상대가 하드덱에 닿은 경기 (`end_reason == hard_deck` 이고 `winner == blue`) / 경기 수.
  전체 (144경기) **5% 이하**, 상대별 (36경기씩) **10% 이하**.
- **상대 climb 실행 비율** = `node_frac_red`의 `climb` 값, 144경기 평균 **20% 이하** (회복만 하느라 싸우지 않는 상대 방지).
- 셋 모두 만족하면 합격. 1단계 불합격이면 2단계를 한 번 시도. 2단계도 불합격이면 결과만 보고하고 멈춘다.
- 함께 적는 것 (기준 아님): 승리 방식 분포, 청 하드덱 비율, 상대별 climb 비율.

## 합격 뒤 (재예비 실험)

- `bt/analysis/pilot_rules.md`는 고치지 않고 그대로 적용한다. θ 는 `bt/thetas/pilot_lhs50.csv` 50개 그대로, `bt-pilot` 시드,
  보정 상대로 2,400경기. 결과는 `bt/out/pilot2_report.md`, 원본 상대 예비 실험과 나란히 비교한다.
