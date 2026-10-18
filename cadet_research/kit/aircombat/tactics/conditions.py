"""교리 조건 레지스트리 — BT Condition 노드가 이름으로 참조.

각 조건은 BEM Ch.4 의 상황 판단을 명시적 술어로 표현한다(감사가능).
임계값은 키워드 인자(기본값=교범 setpoint)로 노출되어 YAML 에서
`condition: {name: overshoot_risk, closure_fps: 120, ...}` 로 조정한다 —
함수 시그니처가 파라미터 스펙의 단일 진실(dsl.build_node 가 inspect 로 검증).

파이팅 속도 대역 기본값은 ctx(fighting_kts_lo/hi)에서 가져온다 — pilot 이
per-pilot Doctrine 을 주입하므로 doctrine 개방 시에도 L1/L2 가 같은 대역을 본다
(구 모듈 전역 Doctrine() 은 import 시점 고정이라 오버라이드를 못 봤다).
"""
from __future__ import annotations

from .context import TacticContext


def foe_threat(ctx: TacticContext, *, aspect_deg: float = 120.0) -> bool:
    """적 기수가 나를 향함 — 내가 적 전방에 있다(aspect≈180 = 적 12시에 나). 적이 내 뒤인 수세(HCA 작음)와
    마주 보고 접근하는 헤드온(HCA 큼) 모두 참이다 — 수세만 잡으려면 is_head_on 을 먼저 분리하거나 inverter 로 거른다."""
    return ctx.aspect_deg > aspect_deg


def overshoot_risk(ctx: TacticContext, *, closure_fps: float = 150.0,
                   range_ft: float = 2000.0) -> bool:
    """빠른 접근 + 근거리 → 추월 위험. lag/요요로 물러서야 함(4.4.7.2)."""
    return ctx.closure_fps > closure_fps and ctx.range_ft < range_ft


def foe_extending(ctx: TacticContext, *, closure_fps: float = 0.0,
                  range_ft: float = 6000.0) -> bool:
    """적이 멀어지며 거리 벌림 → max-G 리드 추격(4.4.8.2.1)."""
    return ctx.closure_fps < closure_fps and ctx.range_ft > range_ft


def in_gun_envelope(ctx: TacticContext, *, range_ft: float = 3000.0,
                    ata_deg: float = 30.0) -> bool:
    """건 사거리 + 조준각 근접 → pure/추적."""
    return ctx.range_ft < range_ft and ctx.ata_deg < ata_deg


def nose_far(ctx: TacticContext, *, ata_deg: float = 60.0) -> bool:
    """기수가 적에서 크게 벗어남 → 리드로 기수 당김."""
    return ctx.ata_deg > ata_deg


def energy_advantage(ctx: TacticContext, *, min_ft: float = 0.0) -> bool:
    """비에너지 우세 → 공세 유지 가능."""
    return ctx.energy_diff_ft > min_ft


def low_altitude(ctx: TacticContext, *, floor_ft: float = 4000.0,
                 lookahead_s: float = 0.0) -> bool:
    """하드덱(1,000ft) 근접 — 즉시 회복 필요. 급강하 관성 때문에 대응이 늦으면
    회복해도 하드덱을 뚫는다 → floor_ft 는 넉넉한 여유를 둔다(기본 4,000ft).
    lookahead_s 를 주면 현재 고도 대신 그만큼 뒤의 예상 고도로 판정한다(기본 0=현재 고도).
    고도만 보면 강하각에 따라 여유가 달라진다 — 730fps 강하에서 4,500ft 는 6초뿐인데
    60° 강하 회복에는 4,500ft 가 든다. lookahead_s 는 침하율에 비례해 트리거를
    앞당기므로 수평비행에서는 기본과 동일하게 동작한다."""
    return ctx.alt_ft + ctx.vs_fps * lookahead_s < floor_ft


# ── 신규 8종 (수직/국면 어휘) ────────────────────────────────────────────


def foe_above(ctx: TacticContext, *, min_ft: float = 500.0) -> bool:
    """적이 나보다 위 — 수직 분리 판정(4.4.10). alt_gap_ft 양수=적이 위."""
    return ctx.alt_gap_ft > min_ft


def foe_below(ctx: TacticContext, *, min_ft: float = 500.0) -> bool:
    """적이 나보다 아래 — 요요 정점(재강하 시점) 판정(4.4.6.2.3)."""
    return ctx.alt_gap_ft < -min_ft


def behind_foe(ctx: TacticContext, *, aspect_deg: float = 60.0) -> bool:
    """적 후방 반구(control zone) 점유 — 공세 국면 판정(4.4.6)."""
    return ctx.aspect_deg < aspect_deg


def in_control_zone(ctx: TacticContext, *, range_lo_ft: float = 2000.0,
                    range_hi_ft: float = 3000.0, aspect_deg: float = 30.0,
                    hca_deg: float = 30.0) -> bool:
    """BEM control zone 점유 — 후방 2~3 kft + AA≈0 + HCA 정렬(4.4.6).
    ATA 20~30°는 조건이 아니라 lag 추격의 결과(존 유지 기동이 만드는 기하)."""
    return (range_lo_ft <= ctx.range_ft <= range_hi_ft
            and ctx.aspect_deg < aspect_deg and ctx.hca_deg < hca_deg)


def merged(ctx: TacticContext, *, range_ft: float = 1500.0) -> bool:
    """merge 통과(초근접) — 넥타이/교차 직후 국면(4.4.4)."""
    return ctx.range_ft < range_ft


def one_circle(ctx: TacticContext) -> bool:
    """1-circle flow — 양 기체가 **반대 수평 선회방향**으로 원 하나를 공유(radius fight).
    한쪽이라도 직선이면 False. BEM 4.4.4 flow 정의 — 구 순간 HCA<90 프록시에서
    2026-07-17 교범 정합 전환. 2-circle 은 two_circle 조건(inverter 아님 — 직선 포함 문제)."""
    return (ctx.my_turn_dir != 0 and ctx.foe_turn_dir != 0
            and ctx.my_turn_dir != ctx.foe_turn_dir)


def two_circle(ctx: TacticContext) -> bool:
    """2-circle flow — 양 기체가 **같은 수평 회전방향**(노즈-투-노즈 rate fight).
    한쪽이라도 직선이면 False. BEM 4.4.4. ¬one_circle 과 다름 — inverter 는
    둘 다 직선인 접근 국면까지 참이 되므로 flow 판별에는 이 조건을 쓸 것."""
    return (ctx.my_turn_dir != 0 and ctx.foe_turn_dir != 0
            and ctx.my_turn_dir == ctx.foe_turn_dir)


def closing(ctx: TacticContext, *, min_fps: float = 100.0) -> bool:
    """유의미한 접근율 — 요요 국면 전환(진입/정점) 판정."""
    return ctx.closure_fps > min_fps


def below_fighting_speed(ctx: TacticContext, *,
                         kcas: float | None = None) -> bool:
    """파이팅 속도 하한 미만 — 에너지 회복 필요(4.4.6.2.2). 기본값=교리 fighting_kts_lo."""
    return ctx.kcas < (ctx.fighting_kts_lo if kcas is None else kcas)


def above_fighting_speed(ctx: TacticContext, *,
                         kcas: float | None = None) -> bool:
    """파이팅 속도 상한 초과 — 에너지 여유(전환 기동 가능)(4.4.6.2.2). 기본값=교리 fighting_kts_hi."""
    return ctx.kcas > (ctx.fighting_kts_hi if kcas is None else kcas)


# ── 확장 관측 조건 3종 (2026-08-17) — 기채워진 관측(my_health·vel_*)의 어휘화 ──
# 관측은 2026-07-18 부터 전 참가자 계층에서 채워졌으나 조건 함수가 없어
# custom_module(비공개) 사용자만 읽을 수 있던 비대칭을 해소한다.
# 적 원시 상태(enm_*)는 룰북 §6 정보 정책대로 계속 비노출.


def low_health(ctx: TacticContext, *, hp: float = 40.0) -> bool:
    """내 잔여 HP 가 임계 미만 — 손상 국면 전환(방어 전환·이탈 판단) 판정."""
    return ctx.my_health < hp


def vel_nose_far(ctx: TacticContext, *, vel_ata_deg: float = 60.0) -> bool:
    """내 속도벡터가 적에서 크게 벗어남 — nose_far 의 속도벡터판.
    기수는 표적을 물었는데 비행경로가 흘러나가는 고AoA 드리프트 감지."""
    return ctx.vel_ata_deg > vel_ata_deg


def foe_path_threat(ctx: TacticContext, *, vel_aa_deg: float = 120.0) -> bool:
    """적 속도벡터(비행경로)가 나를 향함 — foe_threat 의 속도벡터판.
    기수 조준(aspect)보다 실제 접근 경로 기반의 위협 판정."""
    return ctx.vel_aa_deg > vel_aa_deg


# ── BFM 국면 3종 (HABFM/OBFM/DBFM 명명 — 저작·설명을 BFM 용어로) ──────────
# aspect/hca 로 조합 가능하나(is_offensive≈behind_foe, is_defensive≈foe_threat),
# 교범 국면 어휘를 BT 에 직접 담고 싶다는 요구(설명가능성)로 얇은 wrapper 제공.


def is_head_on(ctx: TacticContext, *, hca_deg: float = 150.0) -> bool:
    """HABFM — 종축이 대향(HCA 고, BEM Angle-Off): 머지/헤드온 국면(4.4.4). 안정 노즈온 추적 대상."""
    return ctx.hca_deg > hca_deg


def is_offensive(ctx: TacticContext, *, aspect_deg: float = 60.0) -> bool:
    """OBFM — 내가 적 후미(aspect 낮음): 공세 국면(4.4.6). control zone 유지 대상."""
    return ctx.aspect_deg < aspect_deg


def is_defensive(ctx: TacticContext, *, aspect_deg: float = 120.0) -> bool:
    """DBFM — aspect 높음(내가 적 기수 전방): 방어 국면(4.4.9). 브레이크/역전 대상. foe_threat 와 같은 판정이라
    헤드온(HCA 큼)에서도 참이다 — 적이 내 후미인 수세만 잡으려면 is_head_on 을 먼저 분리하거나 inverter 로 거른다."""
    return ctx.aspect_deg > aspect_deg


def in_overtime(ctx: TacticContext) -> bool:
    """오버타임 구간 — 2026-10 오버타임 폐지로 대회 경기에서는 항상 False.

    기존 제출물이 검증에서 떨어지지 않게 조건 이름만 남겼다(삭제하면 이 조건을 쓴
    트리가 미지 어휘로 실격된다). 엔진의 OT 경로(`Match(overtime_s=…)`, run_match
    --overtime)는 연구용으로 남아 있고, 그때만 참이 된다.
    """
    return ctx.overtime


# ── 적 기체 상태 (2026-09-08) ──────────────────────────────────────────
# 관측(enm_*)은 2026-07-18 부터 ctx 에 채워지고 있었으나 조건 어휘가 없었고,
# custom_module 은 대회에서 봉인이라(tactics/custom.py) 참가자는 읽을 방법이
# 없었다. "적이 이렇게 움직이면 나는 이렇게" 를 짤 수 있게 넷을 연다.
# 선회방향은 one_circle/two_circle 이, 적 기수각은 foe_threat(aspect)·
# foe_path_threat 가 이미 덮으므로 추가하지 않는다.

def foe_climbing(ctx: TacticContext, *, min_fps: float = 50.0) -> bool:
    """적이 상승 중 — 수직 전개 진입(요요·상승 분리) 판정. 임계는 상승률 [fps]."""
    return ctx.enm_vs_fps > min_fps


def foe_diving(ctx: TacticContext, *, min_fps: float = 50.0) -> bool:
    """적이 강하 중 — 하드덱으로 몰거나 재강하 정점을 잡을 국면 판정. 임계는 강하율 [fps]."""
    return ctx.enm_vs_fps < -min_fps


def foe_banked(ctx: TacticContext, *, min_deg: float = 45.0) -> bool:
    """적이 뱅크 중 = 선회 중 — 선회 진입 시점 판정(뱅크가 선회율보다 먼저 선다).

    부호 없는 판정이다. 좌·우 구분이 필요하면 one_circle/two_circle 을 쓸 것.
    """
    return abs(ctx.enm_phi_deg) > min_deg


def foe_faster(ctx: TacticContext, *, min_kt: float = 25.0) -> bool:
    """적이 나보다 빠름 [KCAS 차] — 속도만의 비교.

    energy_advantage 는 고도까지 포함한 비에너지 비교라 "적이 높지만 느린" 상황을
    구분하지 못한다. 순수 속도 우열이 필요할 때 쓴다.
    """
    return (ctx.enm_kcas - ctx.kcas) > min_kt


CONDITIONS = {
    "foe_threat": foe_threat,
    "overshoot_risk": overshoot_risk,
    "foe_extending": foe_extending,
    "in_gun_envelope": in_gun_envelope,
    "nose_far": nose_far,
    "energy_advantage": energy_advantage,
    "low_altitude": low_altitude,
    "foe_above": foe_above,
    "foe_below": foe_below,
    "behind_foe": behind_foe,
    "in_control_zone": in_control_zone,
    "merged": merged,
    "one_circle": one_circle,
    "two_circle": two_circle,
    "closing": closing,
    "below_fighting_speed": below_fighting_speed,
    "above_fighting_speed": above_fighting_speed,
    "low_health": low_health,
    "vel_nose_far": vel_nose_far,
    "foe_path_threat": foe_path_threat,
    "is_head_on": is_head_on,
    "is_offensive": is_offensive,
    "is_defensive": is_defensive,
    "in_overtime": in_overtime,
    "foe_climbing": foe_climbing,
    "foe_diving": foe_diving,
    "foe_banked": foe_banked,
    "foe_faster": foe_faster,
}
