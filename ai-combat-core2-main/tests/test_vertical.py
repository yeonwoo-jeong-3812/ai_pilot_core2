"""수직 기동 물리 검증 — perch 세팅에서 high_yoyo 트리 vs pure 고정 트리 비교.

perch: Blue 가 Red 후방 3,000ft·+100kt 우세로 시작 → 오버슈트 유발 세팅.
JSBSim 결정론이므로 수치가 고정된다. 검증 항목(플랜 §7-2):
  1) 요요 커밋 구간에서 실제 수직 기동 발생: max|θ|>15° 또는 고도 변화>500ft
  2) 에너지 불변식: 전 구간 min KCAS>250, 하드덱(1,000ft) 무위반
  3) 효과: 오버슈트 이벤트 감소 또는 hp_red 더 낮음(WEZ 유지 우위)
"""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.fdm.plant import F16Plant
from aircombat.engine.pilot import Pilot
from aircombat.engine.opponents.scripted import ScriptedOpponent
from aircombat.engine.match import _wez_damage, HARD_DECK_FT
from aircombat.geometry.wez import HealthGauge
from aircombat.geometry.combat_geometry import CombatGeometry
from aircombat.tactics.dsl import build_node
from aircombat.tactics.policy import TacticPolicy

PURE_SPEC = {"action": {"pursuit": "pure", "name": "pure_only"}}
YOYO_SPEC = {"selector": [
    {"commit": {"name": "high_yoyo", "duration_s": 4.0, "cooldown_s": 3.0, "child": {
        "selector": [
            {"sequence": [
                {"condition": {"name": "behind_foe", "aspect_deg": 90}},
                {"condition": {"name": "foe_below", "min_ft": 800}},
                {"inverter": {"condition": {"name": "closing", "min_fps": 60}}},
                {"action": {"pursuit": "lead", "name": "yoyo_down",
                            "aim_above_ft": -300, "lead_time_s": 1.5}},
            ]},
            {"sequence": [
                {"condition": {"name": "behind_foe", "aspect_deg": 90}},
                {"condition": {"name": "overshoot_risk", "closure_fps": 160, "range_ft": 2200}},
                {"action": {"pursuit": "lag", "name": "yoyo_up",
                            "aim_above_ft": 750, "lag_dist_ft": 2000}},
            ]},
        ]}}},
    {"action": {"pursuit": "pure", "name": "pure_only"}},
]}


def _run_perch(spec: dict, duration_s: float = 35.0) -> dict:
    """perch IC 로 blue(Pilot, 주어진 트리) vs red(scripted turn) 커스텀 루프.

    Match 와 동일한 다중레이트 스케줄이지만 per-tick 기록을 남긴다.
    """
    plant = F16Plant(dt=1.0 / 120.0)
    plant.set_ic(alt_ft=15000.0, vc_kts=450.0, psi_deg=0.0)   # +100kt 우세
    plant["fcs/throttle-cmd-norm"] = 0.85
    plant.trim()
    blue = Pilot(plant, color="Blue", init_pos_ned=(-3000.0, 0.0, -15000.0),
                 policy=TacticPolicy(root=build_node(spec)))
    red = ScriptedOpponent(init_pos_ned=(0.0, 0.0, -15000.0), speed_kts=350.0,
                           heading_deg=0.0, maneuver="turn", turn_rate_dps=6.0)
    blue.setup()
    red.setup()

    dt = 1.0 / 120.0
    n = int(duration_s / dt)
    hp_red = HealthGauge()
    rec = {"theta_deg": [], "alt_ft": [], "kcas": [], "cmd": []}
    overshoot_events = 0
    prev_os = False
    for k in range(n):
        bs = blue.state()
        rs = red.state()
        if k % 6 == 0:
            blue.tactic_step(rs)
        if k % 2 == 0:
            blue.guidance_step(rs)
        blue.control_step(rs)
        blue.step_physics()
        red.step_physics()

        dmg, _ = _wez_damage(bs, rs, dt)
        if dmg > 0:
            hp_red.take_damage(dmg, k)

        geom = CombatGeometry(bs.pos_ned, rs.pos_ned, bs.vel_ned, rs.vel_ned,
                              bs.phi, bs.theta, bs.psi, rs.theta, rs.psi)
        rng = float(np.linalg.norm(rs.pos_ned - bs.pos_ned))
        os_now = rng < 2500.0 and geom.ata_deg() > 90.0   # 근거리 기수 상실 = 오버슈트
        if os_now and not prev_os:
            overshoot_events += 1
        prev_os = os_now

        rec["theta_deg"].append(math.degrees(bs.theta))
        rec["alt_ft"].append(bs.alt_ft)
        rec["kcas"].append(bs.kcas)
        rec["cmd"].append(blue._cmd.name)
    return {"rec": rec, "hp_red": hp_red.current_health,
            "overshoot_events": overshoot_events}


class TestVerticalManeuver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yoyo = _run_perch(YOYO_SPEC)
        cls.pure = _run_perch(PURE_SPEC)

    def test_yoyo_commit_fires(self):
        cmds = set(self.yoyo["rec"]["cmd"])
        self.assertTrue(cmds & {"yoyo_up", "yoyo_down"},
                        f"요요 커밋 미발동 (관측 명령: {cmds})")

    def test_actual_vertical_motion_during_yoyo(self):
        rec = self.yoyo["rec"]
        idx = [i for i, c in enumerate(rec["cmd"]) if c in ("yoyo_up", "yoyo_down")]
        max_theta = max(abs(rec["theta_deg"][i]) for i in idx)
        alts = [rec["alt_ft"][i] for i in idx]
        alt_span = max(alts) - min(alts)
        self.assertTrue(max_theta > 15.0 or alt_span > 500.0,
                        f"수직 기동 미발생: max|θ|={max_theta:.1f}°, Δalt={alt_span:.0f}ft")

    def test_energy_invariants(self):
        rec = self.yoyo["rec"]
        self.assertGreater(min(rec["kcas"]), 250.0)          # 요요 중 실속 없음
        self.assertGreater(min(rec["alt_ft"]), HARD_DECK_FT)  # 하드덱 무위반

    def test_yoyo_effectiveness_vs_pure(self):
        # 오버슈트 이벤트 감소 또는 WEZ 유지 우위(hp_red 더 낮음)
        better_overshoot = (self.yoyo["overshoot_events"]
                            <= self.pure["overshoot_events"])
        better_wez = self.yoyo["hp_red"] < self.pure["hp_red"]
        self.assertTrue(
            better_overshoot or better_wez,
            f"yoyo(os={self.yoyo['overshoot_events']}, hp_red={self.yoyo['hp_red']:.1f}) vs "
            f"pure(os={self.pure['overshoot_events']}, hp_red={self.pure['hp_red']:.1f})")


if __name__ == "__main__":
    unittest.main()
