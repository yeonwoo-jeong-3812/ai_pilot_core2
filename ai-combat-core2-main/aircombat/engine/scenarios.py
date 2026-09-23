"""시나리오 초기조건(IC) — BEM 국면 매핑 + 결정론 시드 랜덤화 + 진영 스왑.

리그 시나리오 세트는 BEM 국면을 커버한다(부분-교리 트리가 순위를 얻지 못하게):
  headon        HABFM  헤드온 머지 (V1 룰북식 대칭 IC)
  perch_offense OBFM   blue 가 red 후방 6,000ft·+100kt 우위 (기존 "perch")
  perch_defense DBFM   perch_offense 의 진영 스왑 — blue 가 열위
  neutral       중립 머지 — blue 3시(E=+1,500ft) 남향, red 9시(E=-1,500ft) 북향,
                3,000ft 측방 이격. 역할 대칭 → turning room 배분(1/2-circle) 판단
  p1_neutral    논문 1(이민석 외 2022, ADD) 실험조건 재현 — neutral 기하, 분리 2,000–3,000 ft
                (100 ft), 고도 5,000–20,000 ft(500 ft), 속도 300–450 kts(1 kt) 양측 공통.
                seed=None 이면 범위 중앙(12,500 ft·375 kts·2,500 ft). 연구 전용(리그 미사용).
  duel          headon 과 같은 기하. 단 방위·속도 지터를 **양측 공통**으로 뽑아
                180° 회전 대칭 IC 를 만든다 → 어느 진영에도 조준 우위(ΔATA)가 없다.
                진영 스왑이 불가능한 단판(현장 결선 토너먼트)용.

시드: 난수원은 외부 주입 seed 하나뿐(불변식 — 자생 난수 0). 같은 (scenario, seed)
→ 항상 같은 IC. seed=None 이면 지터 없는 기준 IC (기존 동작 보존).
IC dict 형식: {"blue"|"red": {pos:(N,E,D)ft, psi:deg, kcas, alt:ft}}.
"""
from __future__ import annotations

import random

NM_TO_FT = 6076.12

SCENARIOS = ("headon", "perch_offense", "perch_defense", "neutral", "duel", "p1_neutral")

# 시드 지터 범위 — 분포는 룰북에 공지되는 값 (좁게 시작, 밸런스 리그에서 조정)
# 건드리지 말 것 (2026-07-31 실측, 배터리 80경기 × 3설정). 현행이 국소 최적:
#   좁힘(14~16k·±10°·±10kt) 불일치 70%(무상관 64%), 참가자 승점차 +5
#   현행(12~18k·±30°·±20kt) 불일치 55%(무상관 65%), 참가자 승점차 +29
#   넓힘(10~20k·±45°·±30kt) 불일치 68%(무상관 65%), 참가자 승점차 −2
# 현행만 무상관 기대치 아래(=셀 반복성 존재)다. 지터 폭은 노이즈원이 아니라 실력차가
# 드러나는 국면을 만드는 신호원이며, 양방향 모두 그 균형을 깬다.
_ALT_RANGE_FT = (12000.0, 18000.0)
_SPEED_JITTER_KCAS = 20.0      # 명목 속도 ± 이 값 (절대 재추첨 아님 — 아래 주 참조)
_HEADING_JITTER_DEG = 30.0     # 명목 방위 ± 이 값
_SEP_JITTER = 0.2              # 명목 분리거리 ± 20%

# 속도 지터는 **명목값 대비 상대**여야 한다. 절대 분포에서 재추첨하면 시나리오가
# 설계한 속도 차가 지워진다 — perch 의 +100kt 공격자 우위가 시드 붙은 전 매치에서
# 사라져(실측 dV −34~+34kt) 공격자가 WEZ 에 접근조차 못 하고 무접촉 타임아웃이
# 났다. 고도는 현재 전 시나리오가 양측 동일이라 공통 추첨이 안전하지만, 고도차를
# 쓰는 시나리오를 추가한다면 여기도 상대 지터로 바꿔야 한다.


def _base_ic(scenario: str, range_ft: float) -> dict:
    if scenario in ("headon", "duel"):
        alt = 15000.0
        return {
            "blue": dict(pos=(0.0, 0.0, -alt), psi=0.0, kcas=350.0, alt=alt),
            "red": dict(pos=(range_ft, 0.0, -alt), psi=180.0, kcas=350.0, alt=alt),
        }
    if scenario in ("perch_offense", "perch_defense"):
        # 분리 6,000ft = WEZ(3,000ft) 밖 — DPS 50 에서 3,000ft 시작은 방어자가
        # 브레이크 전에 즉사(~2.3s). BEM 표준 perch 셋업(3/6/9k)의 중간값.
        ic = {
            "blue": dict(pos=(-6000.0, 0.0, -15000.0), psi=0.0, kcas=450.0, alt=15000.0),
            "red": dict(pos=(0.0, 0.0, -15000.0), psi=0.0, kcas=350.0, alt=15000.0),
        }
        return swap_sides(ic) if scenario == "perch_defense" else ic
    # neutral: blue 3시 방향(E=+1,500ft) 남향, red 9시 방향(E=-1,500ft) 북향 — 3,000ft 측방 대치
    return {
        "blue": dict(pos=(0.0, 1500.0, -15000.0), psi=180.0, kcas=350.0, alt=15000.0),
        "red": dict(pos=(0.0, -1500.0, -15000.0), psi=0.0, kcas=350.0, alt=15000.0),
    }


def initial_conditions(scenario: str, range_nm: float = 6.0,
                       seed: int | None = None) -> dict:
    """시나리오 IC. seed 지정 시 결정론 지터(고도·속도·방위·분리거리) 적용."""
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario 는 {SCENARIOS} 중 하나: {scenario!r}")
    if scenario == "p1_neutral":
        return _p1_neutral_ic(seed)
    ic = _base_ic(scenario, range_nm * NM_TO_FT)
    if seed is None:
        return ic

    rng = random.Random(seed)
    alt = rng.uniform(*_ALT_RANGE_FT)
    sep = 1.0 + rng.uniform(-_SEP_JITTER, _SEP_JITTER)
    # duel 은 방위·속도를 양측 **공통**으로 한 번만 뽑는다(대칭 IC). 다른 시나리오는
    # 종전대로 측별 독립 추첨 — 추첨 순서를 바꾸면 기존 시드의 IC 가 전부 달라져
    # 리더보드 재현성이 깨지므로, 공통 추첨은 반드시 분기 안에서만 할 것.
    common = None
    if scenario == "duel":
        common = (rng.uniform(-_HEADING_JITTER_DEG, _HEADING_JITTER_DEG),
                  rng.uniform(-_SPEED_JITTER_KCAS, _SPEED_JITTER_KCAS))
    for side in ("blue", "red"):
        s = ic[side]
        n, e, _ = s["pos"]                       # 기본 IC 는 전부 D = -alt
        s["pos"] = (n * sep, e * sep, -alt)      # 수평 스케일 + 공통 고도
        s["alt"] = alt
        if common is None:
            dpsi = rng.uniform(-_HEADING_JITTER_DEG, _HEADING_JITTER_DEG)
            dkcas = rng.uniform(-_SPEED_JITTER_KCAS, _SPEED_JITTER_KCAS)
        else:
            dpsi, dkcas = common
        s["psi"] = (s["psi"] + dpsi) % 360.0
        s["kcas"] += dkcas
    return ic


def _p1_neutral_ic(seed: int | None) -> dict:
    """논문 1 §5: 이산 격자에서 균일 추첨 (별도 분기 — 기존 시나리오 추첨 순서 불변)."""
    if seed is None:
        alt, kcas, sep = 12500.0, 375.0, 2500.0
    else:
        rng = random.Random(seed)
        alt = 5000.0 + 500.0 * rng.randint(0, 30)
        kcas = float(rng.randint(300, 450))
        sep = 2000.0 + 100.0 * rng.randint(0, 10)
    half = sep / 2.0
    return {   # neutral 과 같은 역할 대칭 기하 (blue 3시 남향, red 9시 북향)
        "blue": dict(pos=(0.0, half, -alt), psi=180.0, kcas=kcas, alt=alt),
        "red": dict(pos=(0.0, -half, -alt), psi=0.0, kcas=kcas, alt=alt),
    }


def swap_sides(ic: dict) -> dict:
    """진영 스왑 — 같은 기하에서 blue/red 역할만 교대 (다전제 미러의 2번째 판)."""
    return {"blue": dict(ic["red"]), "red": dict(ic["blue"])}
