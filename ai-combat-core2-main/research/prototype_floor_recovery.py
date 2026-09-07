"""F-deck 프로토타입 — core2 BFMGuidance 에 **적-무관 하드덱 floor-recovery 채널** 주입.

배경(Phase B STEP1 진단):
  core2 BFMGuidance 의 모든 수직 명령은 적 조준점 기준(aim = foe_pos; aim[2]-=aim_above_ft).
  절대/자기-상대 고도 설정점이 **구조적으로 부재**(GAP-2). 따라서 고속 강하 중 저고도서
  적이 멀리·위에 있으면 적-상대 당김이 floor-priority 회복을 못 만들어 자기-덱 관통.
  → 참가자 BT 층에서 교정 불가(CLIMB 이 climb 으로 실현 안 됨)를 이미 증명.

프로토타입(비-canonical, 승인 불필요): BFMGuidance 를 상속해 compute() 진입 시
  floor 조건(alt < floor_ft AND 강하중)이면 **적 무관** 윙레벨-롤 + 최대당김 + AB 로
  덱 회복을 우선. floor 밖이면 기존 교리 가이던스 그대로(super).

이 파일은 제안(canonical bfm_guidance.py 개선)의 **증거**용 — 덱 손실이 전환되고
  판별셋(headon+neutral) 무회귀임을 수치로 보인 뒤 정본 병합을 승인 요청.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aircombat.fdm.plant import F16Plant
from aircombat.guidance.bfm_guidance import BFMGuidance, GuidanceCommand, THR_AB
from aircombat.guidance.doctrine import Doctrine
from aircombat.control.limiter import G_FT_S2
from aircombat.engine.factory import load_policy, make_pilot
from aircombat.engine.scenarios import initial_conditions

from research import champion_core as C
from research.run_transcribed_match import TranscribedPilot
from research.run_champion_match import MeasMatch


class FloorRecoveryGuidance(BFMGuidance):
    """BFMGuidance + 적-무관 하드덱 floor-recovery 채널.

    floor 조건: alt < floor_ft AND vD > sink_fps (강하중).
    발화 시: dphi=-phi(윙레벨 롤) + q_cmd=최대(리미터까지) + AB. **적 위치 무관.**
    이것이 core2 가이던스에 없는 '비행경로 floor ⊕ 건조준' 분리 채널의 최소 구현.
    """

    def __init__(self, *a, floor_ft: float = 3500.0, sink_fps: float = 0.0, **kw):
        super().__init__(*a, **kw)
        self.floor_ft = float(floor_ft)
        self.sink_fps = float(sink_fps)
        self.floor_ticks = 0

    def compute(self, me, foe_pos_ned, foe_vel_ned, **kw):
        alt_ft = -float(me.pos_ned[2])
        vD = float(me.vel_ned[2])                    # +down = 강하
        if alt_ft < self.floor_ft and vD > self.sink_fps:
            self.floor_ticks += 1
            g_avail = self.limiter.max_load_factor(me.kcas)
            dphi_cmd = -float(me.phi)                 # 윙레벨 (적 무관)
            q_cmd = g_avail * G_FT_S2 / max(me.v_fps, 1.0)   # 최대 당김
            return GuidanceCommand(
                dphi_cmd=dphi_cmd, q_cmd=q_cmd, thrust_cmd=THR_AB,
                g_target=g_avail,
                audit={"floor_recovery": True, "alt_ft": alt_ft, "vD": vD})
        return super().compute(me, foe_pos_ned, foe_vel_ned, **kw)


class PreventiveFloorGuidance(BFMGuidance):
    """예방형 비행경로 floor — 조준점의 **수직 성분만** h_floor 위로 클램프.

    GAP-2 교정: core2 단일 조준점(비행경로⊕건조준)의 **수직 채널을 분리**해 floor 부여.
    aim 의 수평(N,E=적)은 건-추적 위해 보존, 수직(D=고도)만 h_floor 아래로 안 내려가게.
    ⇒ 저/강하 밴딧을 쫓아도 챔프는 덱 아래로 기수-다이브를 커밋하지 않음(교리 하드덱).
    core-live h_star(=max(적_alt, FLOOR)) 의 충실 포트. _aim_point 만 오버라이드(무상태).
    """

    def __init__(self, *a, h_floor_ft: float = 3000.0, **kw):
        super().__init__(*a, **kw)
        self.h_floor_ft = float(h_floor_ft)
        self.floor_ticks = 0

    def _aim_point(self, *a, **kw):
        aim = super()._aim_point(*a, **kw)
        if -aim[2] < self.h_floor_ft:      # 조준 고도 = -aim[2] (NED D)
            aim[2] = -self.h_floor_ft
            self.floor_ticks += 1
        return aim


class PredictiveFloorGuidance(BFMGuidance):
    """예측형 에너지-고도 floor — 현재 궤적이 **실제 하드덱을 관통할지** 물리로 예측해서만
    개입. 정적 고도 클램프(무차별)와 달리 비행경로 급경사·강하속도를 반영해 자기-판별한다.

    발화 판정(무상태, 매 tick):
      pullout_loss = V²/(g·(n-1))·(1-cosγ) · safety   [급강하·고속일수록 큼]
      h_proj = alt - pullout_loss                       [max-G 당김 시 회복 고도]
      if 강하중 and h_proj < HARD_DECK + margin:  덱 관통 예측 → 회복 우선
    발화 시: 적-무관 윙레벨 max-G 당김 + AB (트리거만 예측형, 실행은 회복채널).
    ⇒ 얕은 건-다이브(작은 γ→작은 loss→h_proj 여유)엔 미발화, 뒤집힌 수직 split-S엔 조기발화.
    """
    HARD_DECK = 1000.0

    def __init__(self, *a, margin_ft: float = 1500.0, safety: float = 1.5, **kw):
        super().__init__(*a, **kw)
        self.margin_ft = float(margin_ft)
        self.safety = float(safety)
        self.floor_ticks = 0

    def compute(self, me, foe_pos_ned, foe_vel_ned, **kw):
        alt = -float(me.pos_ned[2])
        vD = float(me.vel_ned[2])                          # +down
        V = max(float(me.v_fps), 1.0)
        vh = float(np.linalg.norm(me.vel_ned[:2]))
        gamma = math.atan2(-vD, max(vh, 1e-6))             # <0 강하
        if vD > 0.0 and gamma < 0.0:
            n = max(self.limiter.max_load_factor(me.kcas) - 1.0, 0.5)
            loss = V * V / (G_FT_S2 * n) * (1.0 - math.cos(gamma)) * self.safety
            if alt - loss < self.HARD_DECK + self.margin_ft:
                self.floor_ticks += 1
                g_avail = self.limiter.max_load_factor(me.kcas)
                return GuidanceCommand(
                    dphi_cmd=-float(me.phi), q_cmd=g_avail * G_FT_S2 / V,
                    thrust_cmd=THR_AB, g_target=g_avail,
                    audit={"pred_floor": True, "alt": alt, "gamma_deg": math.degrees(gamma),
                           "h_proj": alt - loss})
        return super().compute(me, foe_pos_ned, foe_vel_ned, **kw)


def make_pilot_tf(color, ic, clf, guid):
    plant = F16Plant(dt=1.0 / 120.0)
    plant.set_ic(alt_ft=ic["alt"], vc_kts=ic["kcas"], psi_deg=ic["psi"])
    plant["fcs/throttle-cmd-norm"] = 0.85
    plant.trim()
    return TranscribedPilot(plant, clf, off_mode="exact", color=color,
                            init_pos_ned=tuple(ic["pos"]), guidance=guid,
                            name="FloorRec")


def _guid(spec):
    """spec: None=baseline | ('react',floor,sink) | ('prev',h_floor) | ('pred',margin,safety)."""
    if spec is None:
        return BFMGuidance(doctrine=Doctrine())
    if spec[0] == "react":
        return FloorRecoveryGuidance(doctrine=Doctrine(),
                                     floor_ft=spec[1], sink_fps=spec[2])
    if spec[0] == "pred":
        return PredictiveFloorGuidance(doctrine=Doctrine(),
                                       margin_ft=spec[1], safety=spec[2])
    return PreventiveFloorGuidance(doctrine=Doctrine(), h_floor_ft=spec[1])


def run_pairing(scenario, red_yaml, clf, side, spec):
    ic = initial_conditions(scenario)
    red_name = os.path.splitext(os.path.basename(red_yaml))[0]
    if side == "blue":
        blue = make_pilot_tf("Blue", ic["blue"], clf, _guid(spec))
        pol, doc = load_policy(red_yaml)
        red = make_pilot("Red", ic["red"], pol, doc, name=red_name)
        champ = blue
    else:
        pol, doc = load_policy(red_yaml)
        blue = make_pilot("Blue", ic["blue"], pol, doc, name=red_name)
        red = make_pilot_tf("Red", ic["red"], clf, _guid(spec))
        champ = red
    m = MeasMatch(blue, red, duration_s=300.0, acmi_path=None, csv_path=None,
                  log_hz=30.0, wall_limit_s=3600.0)
    res = m.run()
    win = (res.winner == side)
    loss = (res.winner is not None and res.winner != side)
    ft = getattr(getattr(champ, "guid", None), "floor_ticks", 0)
    return res, win, loss, ft


DISCRIM = ["headon", "neutral"]   # sudden_death 폐지(2026-08-01) 후 neutral 로 대체
EXAMPLES = ["examples/energy_fighter.yaml", "redteams/red_attacker.yaml",
            "examples/textbook_headon.yaml", "redteams/red_two_circle.yaml"]


def main():
    clf = C.load_clf()

    print("── 1) 덱 손실 페어링: energy_fighter / headon / red(챔프) ──")
    print(f"  {'설정':<24} {'결과':<6} cond          t     floor틱")
    configs = [
        (None, "baseline(재고)"),
        (("prev", 5000.0), "예방 h_floor=5000(무차별)"),
        (("pred", 500.0, 1.5), "예측 margin=500 s=1.5"),
        (("pred", 1000.0, 1.5), "예측 margin=1000 s=1.5"),
        (("pred", 1500.0, 1.5), "예측 margin=1500 s=1.5"),
        (("pred", 1500.0, 2.0), "예측 margin=1500 s=2.0"),
        (("pred", 2500.0, 1.5), "예측 margin=2500 s=1.5"),
        (("pred", 2500.0, 2.0), "예측 margin=2500 s=2.0"),
    ]
    good = []
    for spec, label in configs:
        res, win, loss, ft = run_pairing("headon", "examples/energy_fighter.yaml",
                                         clf, "red", spec)
        tag = "승" if win else ("패" if loss else "무")
        print(f"  {label:<24} {tag:<6} {res.condition:<12} {res.time_s:4.0f}s  {ft}", flush=True)
        if win and spec is not None:
            good.append((spec, label))

    # 2) 무회귀: 판별셋(headon+neutral × 4상대 × 2사이드 = 16경기) — 전환된 설정만
    print("\n── 2) 판별셋 무회귀 (headon+neutral × examples × 2사이드=16경기) ──")
    check = [(None, "baseline(재고)")] + good
    for spec, label in check:
        W = L = D = 0
        losses = []
        for red in EXAMPLES:
            for sc in DISCRIM:
                for side in ("blue", "red"):
                    res, win, loss, ft = run_pairing(sc, red, clf, side, spec)
                    W += win; L += loss; D += (not win and not loss)
                    if loss:
                        rn = os.path.splitext(os.path.basename(red))[0]
                        losses.append(f"{rn}/{sc}/{side}({res.condition})")
        print(f"  {label:<24} {W}승 {D}무 {L}패  손실={losses}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
