"""champion_core — core-live 챔프(FullUnifiedPolicy) 결정-수학의 자립 추출본.

목적: core-live 42/42 챔프를 core2 엔진 위에서 **틱-충실하게** 측정하기 위한 이식.
core-live 원본은 exp_e54_bc_distill 을 통해 guidance/match/lqr/autopilot/scenarios 등
연구스택 전체를 import 하므로 core2 프로세스에 직접 넣으면 JSBSim·모듈명(guidance/match)
충돌이 발생한다. 그래서 **결정에 필요한 순수-수학만** 축자 추출한다(numpy + joblib 만 의존).

원본 대응(축자 복사, 심볼 로컬 해소):
  · situation_cost.py         → _sig/_hca/_es/es_diff/wez_margin/_energy_norm/memberships/their_margin/value
  · exp_e54_bc_distill.py     → featurize/featurize_s, HARD_DECK, _apply_vmax, DIVE_FPS/HOLD, AA_EXTEND
  · exp_e53_integrated_17.py  → WEZ/RECV_CLOS/RECV_AA/OS_CLOS/OS_DIST 상수
  · d2_cost_unified_policy.py → s_off/base_tactic/D2CostUnifiedPolicy
  · full_unified_policy.py    → FullUnifiedPolicy
  · tactic.py                 → Tactic (IntEnum, clf 클래스명과 일치)
  · engine/obs.py             → reconstruct_obs (compute_obs 의 BFM 기하 공식만, plant 대신 KinState)

★ 충실도 주의:
  1) reconstruct_obs 는 core2 (me,foe) KinState 를 core-live compute_obs 규약으로 변환한다.
     검증: d=foe.pos_ned-me.pos_ned 의 down성분 = me_alt-foe_alt = core-live d_d 와 부호·크기 동일
     (core2 pos_ned[2]=D=-alt). 속도는 동일 JSBSim 속성. ata/aa/closure 완전 동일.
  2) closure_kts 는 core-live 정확 상수(FT_S_TO_KNOT=1/(1852/(3600·0.3048)))를 써야 트리 학습분포와 일치.
     core2 state.FT_S_TO_KT=0.592484(근사)는 쓰지 않는다.
  3) _apply_vmax: 원본은 guidance.V_MAX_KTS 전역을 SMART_DIVE 시 540 으로 올린다(dive sprint).
     core2 엔진엔 대응 knob 이 없어 여기선 항등(GAP-3: SMART_DIVE sprint 미반영) — 측정이 비용을 드러낸다.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

# ── 단위 상수 (core-live constants.py 정확값) ──────────────────────────────
KNOT_TO_FT_S = 1852.0 / (3600.0 * 0.3048)   # = 1.6878098524...  kts → ft/s
FT_S_TO_KNOT = 1.0 / KNOT_TO_FT_S           # = 0.5924838...    ft/s → kts

# ── 게임/트리거 상수 (exp_e53/e54 원본) ────────────────────────────────────
WEZ = 3000.0                # exp_e53 WEZ (거리 게이트)
RECV_CLOS = 50.0            # exp_e53 NME_RECV_CLOS 기본
RECV_AA = 90.0             # exp_e53 NME_RECV_AA 기본
OS_CLOS = 60.0             # exp_e53 NME_OS_CLOS 기본
OS_DIST = 3800.0           # exp_e53 NME_OS_DIST 기본
DIVE_FPS = 80.0            # 적 강하율 > 이 값 = 다이브 onset 후보
DIVE_HOLD = 1.5            # 지속시간(s)
AA_EXTEND = 50.0           # latch extend-gate: aa>이 각 = 적 도주(D2 시그니처)
HARD_DECK = 1300.0         # e54 v2 추락방지 최소선

# situation_cost 게임규칙 상수
WEZ_ATA_DEG = 12.0
WEZ_MIN_FT, WEZ_MAX_FT = 500.0, 3000.0
_G = 32.174
_KT2FPS = 1.68781


# ── Tactic enum (tactic.py 축자 복사 — clf 클래스명과 일치해야 함) ──────────
class Tactic(IntEnum):
    LEAD_PURSUIT          = 0
    PURE_PURSUIT          = 1
    LAG_PURSUIT           = 2
    LAG_DISPLACEMENT_ROLL = 3
    GUN_TRACK             = 4
    ONE_CIRCLE            = 5
    TWO_CIRCLE            = 6
    SCISSORS              = 7
    HIGH_YOYO             = 8
    LOW_YOYO              = 9
    BREAK_TURN            = 10
    EXTENSION             = 11
    LEVEL_FLIGHT          = 12
    CLIMB                 = 13
    HEADON                = 14
    ADAPTIVE              = 15
    VERTICAL_PURSUIT      = 16
    TIGHT_TURN            = 17
    LEAD_TURN             = 18
    ETM_TRACK             = 19
    SMART_DIVE            = 20


T = Tactic


# ── Observation (챔프가 읽는 12 필드만) ────────────────────────────────────
@dataclass
class Obs:
    ego_alt_ft: float
    enm_alt_ft: float
    ego_vc_kts: float
    enm_vc_kts: float
    distance_ft: float
    ata_deg: float
    aa_deg: float
    closure_kts: float
    enm_theta_deg: float
    ego_psi_deg: float
    enm_psi_deg: float
    alt_gap_ft: float
    # 롤 축(루프38) — 기존 어휘는 각도(ata·aa)와 거리·고도차뿐이라 **LOS 기준 롤
    # 방향**이 통째로 빠져 있었다. 방어 기동에서 브레이크를 어느 쪽으로 걸지는
    # "공격자가 내 당김면(리프트벡터 면) 기준 어디에 있나"로 결정되므로, 이 축이
    # 없으면 방어 국면은 원리적으로 학습될 수 없다.
    rolloff_deg: float = 0.0      # 적을 내 당김면에 올리려면 얼마나 롤해야 하나 (+우/−좌)
    enm_rolloff_deg: float = 0.0  # 적 입장에서 나를 올리려면 — 적의 당김면 기준 내 위치


def _rolloff(los, ac) -> float:
    """NED LOS 단위벡터 → 기체 body frame 롤오프 각 [deg]. +우롤 / −좌롤.

    표적이 기수 정면이거나 바로 위면 0, 우측 90°, 바로 아래 ±180°.
    보어사이트에서는 롤오프가 정의되지 않으므로(어느 롤이든 표적이 기수에 머묾) 0.
    """
    phi, th, psi = float(ac.phi), float(ac.theta), float(ac.psi)
    cp, sp = math.cos(phi), math.sin(phi)
    ct, st = math.cos(th), math.sin(th)
    cy, sy = math.cos(psi), math.sin(psi)
    y = ((sp * st * cy - cp * sy) * los[0] + (sp * st * sy + cp * cy) * los[1]
         + (sp * ct) * los[2])
    z = ((cp * st * cy + sp * sy) * los[0] + (cp * st * sy - sp * cy) * los[1]
         + (cp * ct) * los[2])
    if abs(y) < 1e-9 and abs(z) < 1e-9:
        return 0.0
    return (math.degrees(math.atan2(y, -z)) + 180.0) % 360.0 - 180.0


def reconstruct_obs(me, foe) -> Obs:
    """core2 KinState (me, foe) → core-live compute_obs 규약 Obs.

    me, foe: aircombat.engine.state.KinState (pos_ned/vel_ned ft·fps, phi/theta/psi rad,
             kcas, alt_ft). core-live compute_obs 의 BFM 기하 공식을 그대로 적용.
    """
    d = foe.pos_ned - me.pos_ned                 # ego→enm 벡터 (NED, ft)
    d_n, d_e, d_d = float(d[0]), float(d[1]), float(d[2])
    distance = math.sqrt(d_n**2 + d_e**2 + d_d**2)

    e_vn, e_ve, e_vd = (float(me.vel_ned[0]), float(me.vel_ned[1]), float(me.vel_ned[2]))
    o_vn, o_ve, o_vd = (float(foe.vel_ned[0]), float(foe.vel_ned[1]), float(foe.vel_ned[2]))
    ego_speed = math.sqrt(e_vn**2 + e_ve**2 + e_vd**2) + 1e-9
    enm_speed = math.sqrt(o_vn**2 + o_ve**2 + o_vd**2) + 1e-9

    # ATA: ego velocity 와 ego→enm 사이 각 (0=조준)
    proj_ego = (d_n*e_vn + d_e*e_ve + d_d*e_vd) / (distance*ego_speed + 1e-9)
    ata = math.degrees(math.acos(max(-1.0, min(1.0, proj_ego))))
    # AA: enm velocity 와 ego→enm 사이 각 (head-on→180, 적6시→0)
    proj_enm = (d_n*o_vn + d_e*o_ve + d_d*o_vd) / (distance*enm_speed + 1e-9)
    aa = math.degrees(math.acos(max(-1.0, min(1.0, proj_enm))))
    # closure: 상대속도 LOS 성분, +접근
    rel_vn, rel_ve, rel_vd = o_vn - e_vn, o_ve - e_ve, o_vd - e_vd
    closure_fps = -(rel_vn*d_n + rel_ve*d_e + rel_vd*d_d) / (distance + 1e-9)
    closure_kts = closure_fps * FT_S_TO_KNOT

    # 롤오프: NED LOS 를 각자의 body frame 으로 돌려 atan2(y, −z).
    # combat_geometry.rolloff_deg 와 같은 정의(항공 3-2-1 C_bn) — 조준 오프셋 없는 순수 LOS 판.
    inv = 1.0 / (distance + 1e-9)
    los = (d_n * inv, d_e * inv, d_d * inv)
    return Obs(
        rolloff_deg=_rolloff(los, me),
        # 적 기준으로는 LOS 가 반대 방향(적→나)
        enm_rolloff_deg=_rolloff((-los[0], -los[1], -los[2]), foe),
        ego_alt_ft=float(me.alt_ft), enm_alt_ft=float(foe.alt_ft),
        ego_vc_kts=float(me.kcas), enm_vc_kts=float(foe.kcas),
        distance_ft=distance, ata_deg=ata, aa_deg=aa, closure_kts=closure_kts,
        enm_theta_deg=math.degrees(float(foe.theta)),
        ego_psi_deg=math.degrees(float(me.psi)) % 360.0,
        enm_psi_deg=math.degrees(float(foe.psi)) % 360.0,
        alt_gap_ft=float(me.alt_ft) - float(foe.alt_ft),
    )


# ── situation_cost (축자 복사) ─────────────────────────────────────────────
def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def _hca(o) -> float:
    return abs(((o.ego_psi_deg - o.enm_psi_deg) + 180.0) % 360.0 - 180.0)


def _es(alt_ft: float, vc_kts: float) -> float:
    return alt_ft + (vc_kts * _KT2FPS) ** 2 / (2.0 * _G)


def es_diff(o) -> float:
    return _es(o.ego_alt_ft, o.ego_vc_kts) - _es(o.enm_alt_ft, o.enm_vc_kts)


def wez_margin(o) -> float:
    ang = max(0.0, 1.0 - o.ata_deg / 60.0)
    if o.distance_ft <= WEZ_MIN_FT:
        rng = o.distance_ft / WEZ_MIN_FT
    elif o.distance_ft <= WEZ_MAX_FT:
        rng = 1.0
    else:
        rng = max(0.0, 1.0 - (o.distance_ft - WEZ_MAX_FT) / 6000.0)
    return ang * rng


def _energy_norm(o) -> float:
    return math.tanh(es_diff(o) / 6000.0)


def memberships(o) -> dict:
    ata, aa, hca = o.ata_deg, o.aa_deg, _hca(o)
    e = _energy_norm(o)
    w = {
        "DEFENSIVE": _sig((aa - 110.0) / 20.0),
        "OFFENSIVE": _sig((35.0 - ata) / 15.0) * _sig((90.0 - aa) / 30.0),
        "TWO_CIRCLE": _sig((hca - 90.0) / 30.0) * _sig((e + 0.0) / 0.4) * _sig((ata - 20.0) / 20.0),
        "ONE_CIRCLE": _sig((hca - 60.0) / 30.0) * _sig((-e + 0.0) / 0.4) * _sig((ata - 20.0) / 20.0),
    }
    s = sum(w.values())
    w["NEUTRAL"] = max(0.0, 1.0 - s)
    tot = sum(w.values()) + 1e-9
    return {k: v / tot for k, v in w.items()}


def their_margin(o) -> float:
    ang = max(0.0, (o.aa_deg - 110.0) / 70.0)
    rng = 1.0 if o.distance_ft <= WEZ_MAX_FT else max(0.0, 1.0 - (o.distance_ft - WEZ_MAX_FT) / 6000.0)
    return max(0.0, min(1.0, ang)) * rng


def value(o) -> float:
    return wez_margin(o) - their_margin(o) + 0.3 * _energy_norm(o)


# ── featurize (exp_e54 축자 복사) ──────────────────────────────────────────
def featurize(o):
    m = memberships(o)
    return [
        m["DEFENSIVE"], m["OFFENSIVE"], m["TWO_CIRCLE"], m["ONE_CIRCLE"], m["NEUTRAL"],
        value(o), wez_margin(o), their_margin(o),
        o.ata_deg, o.aa_deg, _hca(o), o.distance_ft, o.closure_kts, es_diff(o),
        o.ego_alt_ft, o.enm_alt_ft, o.alt_gap_ft,
    ]


def featurize_s(o, dive_run):
    return featurize(o) + [dive_run]


def _apply_vmax(t):
    """GAP-3: core-live 는 SMART_DIVE 시 guidance.V_MAX_KTS=540 sprint. core2 엔진엔 대응 knob 없음 → 항등."""
    return t


# ── cost 정책 (d2_cost_unified_policy 축자 복사) ───────────────────────────
sig = _sig
THETA, LAMBDA, S_SHARP = 0.4, 0.999, 0.05


def s_off(o, S=S_SHARP, yoyo=False):
    off = {
        T.GUN_TRACK:   4.0 * sig((WEZ - o.distance_ft)/S) * sig((20.0 - o.ata_deg)/S),
        T.LAG_PURSUIT: 2.0 * sig((o.closure_kts - OS_CLOS)/S) * sig((OS_DIST - o.distance_ft)/S) * sig((30.0 - o.ata_deg)/S) * sig((60.0 - o.aa_deg)/S),
        T.HEADON:      1.5 * sig((o.closure_kts - RECV_CLOS)/S) * sig((o.aa_deg - RECV_AA)/S),
        T.SMART_DIVE:  1.0,
    }
    if yoyo:
        off[T.HIGH_YOYO] = 3.0 * sig((o.closure_kts - 350.0)/S) * sig((5000.0 - o.distance_ft)/S) * sig((40.0 - o.ata_deg)/S)
    return off


def base_tactic(o, clf, dr=0.0):
    b = T[clf.predict([featurize_s(o, dr)])[0]]
    hca, ata, clos = _hca(o), o.ata_deg, o.closure_kts
    w_circ = sig((hca - 90.0)/30.0); w_ext = sig((-clos - 25.0)/30.0) * sig((ata - 30.0)/20.0)
    if w_circ > 0.6 and w_circ >= w_ext: return T.GUN_TRACK if ata < 30 else T.LEAD_TURN
    if w_ext > 0.6:                       return T.GUN_TRACK if ata < 30 else T.LEAD_TURN
    return b


class D2CostUnifiedPolicy:
    def __init__(self, clf, decay=LAMBDA, thr=THETA, S=S_SHARP, yoyo=False):
        self.clf, self.decay, self.thr, self.S, self.yoyo = clf, decay, thr, S, yoyo
        self.run = 0.0; self.c = 0.0

    def sel(self, o):
        climb = o.enm_vc_kts * 1.68781 * math.sin(math.radians(o.enm_theta_deg))
        if climb < -DIVE_FPS:       self.run += 0.1
        elif self.c <= self.thr:    self.run = 0.0
        fire = (self.run >= DIVE_HOLD and o.aa_deg > AA_EXTEND)
        self.c = 1.0 if fire else self.decay * self.c

        if o.ego_alt_ft < HARD_DECK:  return _apply_vmax(T.CLIMB)
        gw = sig((self.c - self.thr)/0.05)
        off = s_off(o, self.S, self.yoyo)
        b = base_tactic(o, self.clf, min(self.run, DIVE_HOLD))
        cand = set(off) | {b, T.LEAD_TURN}
        V = lambda a: gw * off.get(a, 0.0) + (1.0 - gw) * (1.0 if a == b else 0.0)
        return _apply_vmax(max(cand, key=V))


# ── FullUnifiedPolicy (full_unified_policy 축자 복사) ──────────────────────
class FullUnifiedPolicy:
    def __init__(self, clf):
        self.inner = D2CostUnifiedPolicy(clf)
        self.hist = []
        self.run = 0.0
        self.armed = False
        self.kill = False
        self.base = None

    def sel(self, o):
        return self.decide(o)[1]

    def decide(self, o):
        base = self.inner.sel(o)
        self.base = base
        a, d, a2 = o.ego_alt_ft, o.distance_ft, o.enm_alt_ft
        preva = self.hist[-1][0] if self.hist else a
        dalt = (a - preva) / 0.1
        dop = (len(self.hist) >= 10 and d > self.hist[-10][1])
        perch = a - a2
        pred = (dalt < -30.0 and o.aa_deg < 35.0
                and dop and o.ata_deg < 90.0 and perch > 150.0)
        self.hist.append((a, d))
        self.run = self.run + 0.1 if pred else 0.0

        enm_climb = o.enm_vc_kts * 1.68781 * math.sin(math.radians(o.enm_theta_deg))
        if not self.armed and self.run >= 2.0 and enm_climb < -DIVE_FPS:
            self.armed = True

        if not self.armed:
            if base == T.HEADON and a < 4500.0 and d < 7000.0:
                return "deck_suppress", _apply_vmax(T.PURE_PURSUIT)
            return "core", base

        if a < 1300.0:
            return "empty_dive", _apply_vmax(T.CLIMB)
        if not self.kill and (d < 3500.0 or (o.aa_deg > 150.0 and d < 4500.0)):
            self.kill = True
        if self.kill and d > 12000.0:
            self.kill = False
        if not self.kill:
            return "empty_dive", _apply_vmax(T.BREAK_TURN)
        if d < 3000.0 and o.ata_deg < 20.0:
            return "empty_dive", _apply_vmax(T.GUN_TRACK)
        if o.aa_deg < 90.0 and d > 2000.0:
            return "empty_dive", _apply_vmax(T.SMART_DIVE)
        return "empty_dive", _apply_vmax(T.LEAD_TURN)


def load_clf(path: str | None = None):
    """증류트리 clf 로드. 기본 = research/models (자립화 — core-live 의존 제거)."""
    import joblib
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "models",
                            "e54_tree_v3_d2lc.joblib")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"clf 미발견: {path}")
    return joblib.load(path)["clf"]
