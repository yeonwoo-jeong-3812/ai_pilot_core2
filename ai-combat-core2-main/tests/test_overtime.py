"""오버타임 회귀 — 진입 조건 / 완화 WEZ / 타이브레이크. (JSBSim 불필요)

규칙 원본은 RULEBOOK 「오버타임」. 현장 단판(브래킷)만 켜고, 정규 300초에 승자가
안 나온 경우(무접촉 또는 HP 완전 동률)에만 120초를 더 뛴다.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.engine.state import KinState
from aircombat.engine.match import Match, _wez_damage
from aircombat.geometry.wez import WeaponEngagementZone
from aircombat.geometry.combat_geometry import CombatGeometry
from aircombat.geometry.units import feet_to_meters
from aircombat.tactics.conditions import CONDITIONS
from aircombat.tactics.context import TacticContext


class _Stub:
    """Match 가 전투원에게 요구하는 표면 중 판정에 쓰이는 것만 (고도·OT 플래그)."""
    def __init__(self, alt_ft=15000.0):
        self.overtime = False
        self._st = KinState(pos_ned=np.array([0.0, 0.0, -alt_ft]),
                            vel_ned=np.array([600.0, 0.0, 0.0]), phi=0.0, theta=0.0,
                            psi=0.0, v_fps=600.0, kcas=350.0, alt_ft=alt_ft)

    def state(self):
        return self._st


def _match(overtime_s=120.0):
    return Match(_Stub(), _Stub(), duration_s=300.0, overtime_s=overtime_s)


def _geo(dist_m, ata_deg=0.0):
    """shooter 원점·기수 북향, target 을 ATA 만큼 틀어 dist_m 앞에 둔다."""
    a = np.radians(ata_deg)
    tgt = np.array([dist_m * np.cos(a), dist_m * np.sin(a), 0.0])
    return CombatGeometry(np.zeros(3), tgt, np.array([180.0, 0, 0]),
                          np.array([180.0, 0, 0]), 0.0, 0.0, 0.0, 0.0, 0.0)


class TestOvertimeEntry(unittest.TestCase):
    """① 정규 만료 시 승자 미결정이면 OT 진입, 결정되면 즉시 종료."""

    def test_no_contact_enters_overtime(self):
        m = _match()
        self.assertIsNone(m._regulation_expiry(300.0))   # 양측 만피 = 무접촉

    def test_exact_tie_enters_overtime(self):
        m = _match()
        m.hp["blue"].take_damage(30.0, 0)
        m.hp["red"].take_damage(30.0, 0)
        self.assertIsNone(m._regulation_expiry(300.0))

    def test_hp_lead_ends_at_regulation(self):
        m = _match()
        m.hp["red"].take_damage(30.0, 0)
        r = m._regulation_expiry(300.0)
        self.assertIsNotNone(r)
        self.assertEqual((r.winner, r.condition), ("blue", "timeout"))

    def test_disabled_keeps_no_contact_rule(self):
        """OT 비활성(훈련센터·리그)에서는 무접촉이 그대로 쌍방 패다."""
        m = _match(overtime_s=0.0)
        r = m._expiry_result(300.0)
        self.assertEqual((r.winner, r.condition), ("draw", "no_contact"))
        self.assertFalse(r.overtime)

    def test_begin_overtime_flags_combatants(self):
        m = _match()
        m._begin_overtime(None, 300.0)
        self.assertTrue(m.overtime)
        self.assertTrue(m.blue.overtime and m.red.overtime)


class TestOvertimeWez(unittest.TestCase):
    """OT 완화 WEZ — 사거리 6,000ft / 원뿔 45°. 정규에서는 0 이던 기하가 유효해진다."""

    def test_range_relaxed(self):
        g = _geo(feet_to_meters(4500))                    # 3,000 < 4,500 < 6,000 ft
        self.assertEqual(WeaponEngagementZone.calculate_damage(g, 1.0), 0.0)
        self.assertGreater(WeaponEngagementZone.calculate_damage(g, 1.0, overtime=True), 0.0)

    def test_cone_relaxed(self):
        g = _geo(feet_to_meters(1500), ata_deg=40.0)      # 30° < 40° < 45°
        self.assertEqual(WeaponEngagementZone.calculate_damage(g, 1.0), 0.0)
        self.assertGreater(WeaponEngagementZone.calculate_damage(g, 1.0, overtime=True), 0.0)

    def test_beyond_overtime_cone_still_zero(self):
        g = _geo(feet_to_meters(1500), ata_deg=50.0)
        self.assertEqual(WeaponEngagementZone.calculate_damage(g, 1.0, overtime=True), 0.0)

    def test_inner_tiers_unchanged(self):
        """계단은 그대로 — 최외곽 tier 만 45°까지 늘렸다."""
        g = _geo(feet_to_meters(1500), ata_deg=1.0)
        self.assertAlmostEqual(WeaponEngagementZone.calculate_damage(g, 1.0),
                               WeaponEngagementZone.calculate_damage(g, 1.0, overtime=True))

    def test_min_range_penalty_kept(self):
        g = _geo(feet_to_meters(300))                     # 과접근은 OT 에서도 0
        self.assertEqual(WeaponEngagementZone.calculate_damage(g, 1.0, overtime=True), 0.0)


class TestOvertimeJudging(unittest.TestCase):
    """② OT 중 격추는 그대로 health_zero(격추승). ③ 만료 동률은 타이브레이크."""

    def test_kill_in_overtime_is_health_zero(self):
        m = _match()
        m._begin_overtime(None, 300.0)
        m.hp["red"].take_damage(100.0, 0)
        r = m._judge(360.0)
        self.assertEqual((r.winner, r.condition), ("blue", "health_zero"))
        self.assertTrue(r.overtime)

    def test_expiry_hp_lead_wins(self):
        m = _match()
        m._begin_overtime(None, 300.0)
        m.hp["blue"].take_damage(10.0, 0)
        r = m._expiry_result(420.0)
        self.assertEqual((r.winner, r.condition), ("red", "overtime"))

    def test_tiebreak_by_aim_time(self):
        m = _match()
        m._begin_overtime(None, 300.0)
        m.hp["blue"].take_damage(20.0, 0)
        m.hp["red"].take_damage(20.0, 0)          # HP 동률
        m._wez_time = {"blue": 3.0, "red": 1.5}
        r = m._expiry_result(420.0)
        self.assertEqual((r.winner, r.condition), ("blue", "overtime"))
        self.assertEqual(r.wez_time["blue"], 3.0)

    def test_tiebreak_falls_through_to_mean_ata(self):
        """무접촉 OT 는 조준 시간이 0=0 이라 평균 ATA 가 판별한다."""
        m = _match()
        m._begin_overtime(None, 300.0)
        m._ata_sum = {"blue": 40.0 * 100, "red": 90.0 * 100}
        m._ata_n = 100
        r = m._expiry_result(420.0)
        self.assertEqual((r.winner, r.condition), ("blue", "overtime"))

    def test_identical_trees_remain_draw(self):
        """모든 지표가 같으면 draw — 시드 승계는 엔진이 아니라 운영 규칙이다."""
        m = _match()
        m._begin_overtime(None, 300.0)
        m._ata_sum = {"blue": 50.0, "red": 50.0}
        m._ata_n = 1
        self.assertEqual(m._tiebreak(), "draw")


class TestOvertimeObservation(unittest.TestCase):
    """트리는 경과 시간을 못 본다 — in_overtime 이 유일한 OT 인지 경로."""

    def test_condition_registered(self):
        self.assertIn("in_overtime", CONDITIONS)

    def test_reads_context(self):
        fn = CONDITIONS["in_overtime"]
        base = dict(ata_deg=0.0, aspect_deg=0.0, range_ft=1000.0, closure_fps=0.0,
                    kcas=350.0, energy_diff_ft=0.0, alt_gap_ft=0.0)
        self.assertFalse(fn(TacticContext(**base)))
        self.assertTrue(fn(TacticContext(**base, overtime=True)))


if __name__ == "__main__":
    unittest.main()
