"""CombatGeometry 회귀 — 알려진 기하(head-on / 6시 추적)의 ATA/AA/HCA."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.geometry.combat_geometry import CombatGeometry


class TestCombatGeometry(unittest.TestCase):
    def test_head_on(self):
        # 아군 북향, 적 1km 북쪽에서 남향으로 마주봄 (수평). 자세 = 속도 방향(AoA 0).
        g = CombatGeometry(p_a=np.array([0, 0, 0.0]), p_t=np.array([1000, 0, 0.0]),
                           v_a=np.array([200, 0, 0.0]), v_t=np.array([-200, 0, 0.0]),
                           psi_t=np.pi)
        self.assertAlmostEqual(g.ata_deg(), 0.0, places=3)    # 적이 정면
        self.assertAlmostEqual(g.aa_deg(), 180.0, places=3)   # 적이 날 정면조준(위협)
        self.assertAlmostEqual(g.hca_deg(), 180.0, places=3)  # 정면 대치
        self.assertGreater(g.closure_rate(), 0.0)             # 접근 중

    def test_six_oclock_tracking(self):
        # 아군이 적 500m 뒤, 둘 다 북향 (아군이 적 6시).
        g = CombatGeometry(p_a=np.array([0, 0, 0.0]), p_t=np.array([500, 0, 0.0]),
                           v_a=np.array([200, 0, 0.0]), v_t=np.array([200, 0, 0.0]))
        self.assertAlmostEqual(g.ata_deg(), 0.0, places=3)   # 적이 정면
        self.assertAlmostEqual(g.aa_deg(), 0.0, places=3)    # 아군이 적 6시(유리)
        self.assertAlmostEqual(g.hca_deg(), 0.0, places=3)   # 동일 침로

    def test_beam(self):
        # 적이 아군 우측 90°(빔). 아군 북향, 적은 동쪽 500m에서 북향.
        g = CombatGeometry(p_a=np.array([0, 0, 0.0]), p_t=np.array([0, 500, 0.0]),
                           v_a=np.array([200, 0, 0.0]), v_t=np.array([200, 0, 0.0]))
        self.assertAlmostEqual(g.ata_deg(), 90.0, places=3)

    def test_ata_is_boresight_not_velocity(self):
        # BEM §4.8.2.4: ATA 는 기수(boresight) 기준 — 속도벡터가 아님.
        # 수평 북향 비행 중 기수만 10° 상향(AoA 10°), 적은 같은 고도 정면.
        aoa = np.deg2rad(10.0)
        g = CombatGeometry(p_a=np.array([0, 0, 0.0]), p_t=np.array([1000, 0, 0.0]),
                           v_a=np.array([200, 0, 0.0]), v_t=np.array([-200, 0, 0.0]),
                           theta=aoa, psi_t=np.pi)
        self.assertAlmostEqual(g.ata_deg(), 10.0, places=3)   # 구(속도 기준)라면 0

    def test_aa_is_target_axis_not_velocity(self):
        # BEM §4.8.2.3: AA 는 적 종축 기준. 적이 헤딩만 30° 튼 채(축) 북쪽으로
        # 표류(속도)하는 합성 상황 — 축 기준이면 30°.
        g = CombatGeometry(p_a=np.array([-500, 0, 0.0]), p_t=np.array([0, 0, 0.0]),
                           v_a=np.array([200, 0, 0.0]), v_t=np.array([200, 0, 0.0]),
                           psi_t=np.deg2rad(30.0))
        self.assertAlmostEqual(g.aa_deg(), 30.0, places=3)    # 구(속도 기준)라면 0

    def test_hca_is_axes_angle(self):
        # BEM §4.3.3.3: HCA 는 양 기체 종축 사이 각.
        g = CombatGeometry(p_a=np.array([0, 0, 0.0]), p_t=np.array([1000, 0, 0.0]),
                           v_a=np.array([200, 0, 0.0]), v_t=np.array([200, 0, 0.0]),
                           psi=np.deg2rad(20.0), psi_t=np.deg2rad(-25.0))
        self.assertAlmostEqual(g.hca_deg(), 45.0, places=3)


class TestRollOff(unittest.TestCase):
    """RollOff = 표적 롤오프 각(body-frame). +우롤, 정면·위=0, 우측=90, 아래=±180."""

    @staticmethod
    def _g(p_t, roll=0.0, theta=0.0, psi=0.0):
        return CombatGeometry(p_a=np.array([0, 0, 0.0]), p_t=np.array(p_t, float),
                              v_a=np.array([200, 0, 0.0]), v_t=np.array([200, 0, 0.0]),
                              roll=roll, theta=theta, psi=psi)

    def test_target_right_is_plus90(self):
        # 수평 북향, 적 동쪽(우측) → 우롤 90° 필요
        self.assertAlmostEqual(self._g([0, 500, 0]).rolloff_deg(), 90.0, places=2)

    def test_target_left_is_minus90(self):
        self.assertAlmostEqual(self._g([0, -500, 0]).rolloff_deg(), -90.0, places=2)

    def test_target_above_is_zero(self):
        # 적 바로 위(NED Down 음수) → 이미 당김면(리프트벡터↑) → 0
        self.assertAlmostEqual(self._g([0, 0, -500]).rolloff_deg(), 0.0, places=2)

    def test_target_below_is_180(self):
        self.assertAlmostEqual(abs(self._g([0, 0, 500]).rolloff_deg()), 180.0, places=2)

    def test_roll_folds_into_pull_plane(self):
        # 이미 우로 90° 롤 → 우측 표적이 당김면에 들어옴 → RollOff 0 (자세 반영 확인)
        self.assertAlmostEqual(self._g([0, 500, 0], roll=np.pi / 2).rolloff_deg(), 0.0, places=2)

    def test_heading_east_target_ahead_is_zero(self):
        # 기수 동향(ψ=90°, 속도도 동쪽), 적이 기수 방향(동쪽) → 정면·수평 → 0
        # (구 정의는 북향 전제라 이 경우 왜곡됐다 — 자세 기반 교정 확인)
        g = CombatGeometry(p_a=np.array([0, 0, 0.0]), p_t=np.array([0, 500, 0.0]),
                           v_a=np.array([0, 200, 0.0]), v_t=np.array([0, 200, 0.0]),
                           psi=np.pi / 2)
        self.assertAlmostEqual(g.ata_deg(), 0.0, places=2)   # 기수 방향 = 정면
        self.assertAlmostEqual(g.rolloff_deg(), 0.0, places=2)   # 정면 → 롤오프 0

    def test_heading_east_target_left_is_minus90(self):
        # 기수 동향, 적이 북쪽(기수 기준 좌측) → 좌롤 −90° (헤딩 반영 확인)
        g = CombatGeometry(p_a=np.array([0, 0, 0.0]), p_t=np.array([500, 0, 0.0]),
                           v_a=np.array([0, 200, 0.0]), v_t=np.array([0, 200, 0.0]),
                           psi=np.pi / 2)
        self.assertAlmostEqual(g.rolloff_deg(), -90.0, places=2)


if __name__ == "__main__":
    unittest.main()
