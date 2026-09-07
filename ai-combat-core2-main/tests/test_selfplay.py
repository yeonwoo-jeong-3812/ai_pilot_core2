"""Pilot vs Pilot 자가대전 — 성립(완주) + 결정론(2회 실행 일치). JSBSim 필요.

headon 대칭 IC(4NM — 테스트 시간 단축)에서 아키타입 트리 2종으로 30s 교전.
난수 0 + JSBSim 결정론 스텝이므로 두 실행의 결과·최종 상태가 일치해야 한다.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.fdm.plant import F16Plant
from aircombat.engine.pilot import Pilot
from aircombat.engine.match import Match
from aircombat.tactics.policy import TacticPolicy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BLUE_YAML = os.path.join(ROOT, "examples", "starter.yaml")
RED_YAML = os.path.join(ROOT, "redteams", "red_textbook.yaml")
RANGE_FT = 4.0 * 6076.12   # 4NM


def _pilot(color: str, yaml_path: str, pos, psi_deg: float) -> Pilot:
    plant = F16Plant(dt=1.0 / 120.0)
    plant.set_ic(alt_ft=15000.0, vc_kts=350.0, psi_deg=psi_deg)
    plant["fcs/throttle-cmd-norm"] = 0.85
    plant.trim()
    return Pilot(plant, color=color, init_pos_ned=pos,
                 policy=TacticPolicy.from_yaml(yaml_path))


def _run_headon(duration_s: float = 30.0):
    blue = _pilot("Blue", BLUE_YAML, (0.0, 0.0, -15000.0), 0.0)
    red = _pilot("Red", RED_YAML, (RANGE_FT, 0.0, -15000.0), 180.0)
    res = Match(blue, red, duration_s=duration_s, acmi_path=None).run()
    return res, blue.state(), red.state()


class TestSelfPlay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r1, cls.b1, cls.rd1 = _run_headon()
        cls.r2, cls.b2, cls.rd2 = _run_headon()

    def test_completes(self):
        self.assertIn(self.r1.winner, ("blue", "red", "draw"))
        self.assertIn(self.r1.condition, ("health_zero", "hard_deck", "timeout"))
        self.assertGreater(self.r1.time_s, 0.0)

    def test_deterministic_result(self):
        self.assertEqual(self.r1.winner, self.r2.winner)
        self.assertEqual(self.r1.condition, self.r2.condition)
        self.assertAlmostEqual(self.r1.time_s, self.r2.time_s, places=9)
        self.assertAlmostEqual(self.r1.hp_blue, self.r2.hp_blue, places=9)
        self.assertAlmostEqual(self.r1.hp_red, self.r2.hp_red, places=9)

    def test_deterministic_final_states(self):
        np.testing.assert_allclose(self.b1.pos_ned, self.b2.pos_ned, atol=1e-6)
        np.testing.assert_allclose(self.rd1.pos_ned, self.rd2.pos_ned, atol=1e-6)
        self.assertAlmostEqual(self.b1.kcas, self.b2.kcas, places=6)
        self.assertAlmostEqual(self.rd1.kcas, self.rd2.kcas, places=6)

    def test_trees_not_shared_between_pilots(self):
        # Commit/Cooldown 노드가 상태를 가지므로 파일럿별 별도 build 필수
        p1 = TacticPolicy.from_yaml(BLUE_YAML)
        p2 = TacticPolicy.from_yaml(BLUE_YAML)
        self.assertIsNot(p1.root, p2.root)


if __name__ == "__main__":
    unittest.main()
