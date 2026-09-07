"""WeaponEngagementZone 회귀 — 각도 tier·거리 균일 (시간 완화 없음, RULEBOOK §4)."""
import inspect
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.geometry.combat_geometry import CombatGeometry
from aircombat.geometry.wez import WeaponEngagementZone, HealthGauge


def _geo(dist_m, ata_deg=0.0):
    """아군 원점, 적을 북쪽 dist_m 에 두고 **기수(psi)**를 ATA 만큼 틀어 각을 만든다.
    (ATA 는 BEM 종축 기준 — 2026-07-17 전환)"""
    return CombatGeometry(
        p_a=np.array([0, 0, 0.0]), p_t=np.array([dist_m, 0, 0.0]),
        v_a=np.array([200, 0, 0.0]), v_t=np.array([200, 0, 0.0]),
        psi=np.deg2rad(ata_deg))


class TestWEZ(unittest.TestCase):
    def test_in_zone(self):
        g = _geo(300.0, ata_deg=0.0)   # 984ft, 정조준
        self.assertTrue(WeaponEngagementZone.is_in_wez(g))
        self.assertGreater(WeaponEngagementZone.calculate_damage(g, 0.2), 0.0)

    def test_too_far(self):
        g = _geo(1000.0, ata_deg=0.0)  # 3280ft > 3000ft
        self.assertFalse(WeaponEngagementZone.is_in_wez(g))
        self.assertEqual(WeaponEngagementZone.calculate_damage(g, 0.2), 0.0)

    def test_too_close(self):
        g = _geo(100.0, ata_deg=0.0)   # 328ft < 500ft
        self.assertFalse(WeaponEngagementZone.is_in_wez(g))
        self.assertEqual(WeaponEngagementZone.calculate_damage(g, 0.2), 0.0)

    def test_angle_out(self):
        g = _geo(300.0, ata_deg=35.0)  # 거리 OK, 각도 35° ≥ 30° → 밖
        self.assertFalse(WeaponEngagementZone.is_in_wez(g))
        self.assertEqual(WeaponEngagementZone.calculate_damage(g, 0.2), 0.0)

    def test_damage_uniform_in_band(self):
        # 거리계수 없음 — 500–3,000ft 사이면 같은 ATA 에 같은 데미지.
        d_near = WeaponEngagementZone.calculate_damage(_geo(200.0), 1.0)   # 656ft
        d_mid = WeaponEngagementZone.calculate_damage(_geo(457.0), 1.0)    # 1499ft
        d_far = WeaponEngagementZone.calculate_damage(_geo(884.0), 1.0)    # 2900ft
        self.assertAlmostEqual(d_near, d_mid)
        self.assertAlmostEqual(d_mid, d_far)

    def test_health_gauge(self):
        hg = HealthGauge(100.0)
        hg.take_damage(30.0, step=1)
        self.assertEqual(hg.current_health, 70.0)
        self.assertTrue(hg.is_alive())
        hg.take_damage(80.0, step=2)
        self.assertEqual(hg.current_health, 0.0)   # 하한 0
        self.assertFalse(hg.is_alive())


class TestATATiers(unittest.TestCase):
    """각도계단 — ATA<2/10/20/30 → 계수 1.0/0.75/0.5/0.25, ≥30 → 0. 데미지=50×계수×dt."""

    @staticmethod
    def _dps(ata):   # dt=1.0 → 데미지 = 50 × 각도계수
        return WeaponEngagementZone.calculate_damage(_geo(300.0, ata_deg=ata), dt=1.0)

    def test_tier_coefficients(self):
        self.assertAlmostEqual(self._dps(1.0),  50.0)    # <2  → 1.00
        self.assertAlmostEqual(self._dps(5.0),  37.5)    # <10 → 0.75
        self.assertAlmostEqual(self._dps(15.0), 25.0)    # <20 → 0.50
        self.assertAlmostEqual(self._dps(25.0), 12.5)    # <30 → 0.25
        self.assertEqual(self._dps(35.0), 0.0)           # ≥30 → 0

    def test_tier_boundaries_are_strict_less_than(self):
        # 경계는 '미만' — 부동소수 경계 회피 위해 ±0.1 로 검증
        self.assertAlmostEqual(self._dps(1.9),  50.0)
        self.assertAlmostEqual(self._dps(2.1),  37.5)
        self.assertAlmostEqual(self._dps(9.9),  37.5)
        self.assertAlmostEqual(self._dps(10.1), 25.0)
        self.assertAlmostEqual(self._dps(19.9), 25.0)
        self.assertAlmostEqual(self._dps(20.1), 12.5)
        self.assertAlmostEqual(self._dps(29.9), 12.5)
        self.assertAlmostEqual(self._dps(30.1),  0.0)

    def test_no_time_relaxation_param(self):
        # 시간 완화 제거 — calculate_damage/is_in_wez 는 더 이상 t_s 를 받지 않는다.
        self.assertNotIn("t_s", inspect.signature(
            WeaponEngagementZone.calculate_damage).parameters)
        self.assertNotIn("t_s", inspect.signature(
            WeaponEngagementZone.is_in_wez).parameters)


if __name__ == "__main__":
    unittest.main()
