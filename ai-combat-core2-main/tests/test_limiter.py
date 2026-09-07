"""CombinedLimiter 회귀 — 코너 플래토 + AoA→G ∩ 9G."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.control.limiter import CombinedLimiter, LimiterConfig, G_FT_S2


class TestLimiter(unittest.TestCase):
    def setUp(self):
        self.L = CombinedLimiter()

    def test_load_factor_corner_and_struct(self):
        self.assertAlmostEqual(self.L.max_load_factor(330.0), 9.0, places=6)  # 코너서 9G
        self.assertAlmostEqual(self.L.max_load_factor(660.0), 9.0, places=6)  # 고속 구조 포화
        self.assertAlmostEqual(self.L.max_load_factor(165.0), 2.25, places=6)  # 저속 AoA 제한(=9*0.25)

    def test_sustained_below_instantaneous(self):
        """지속 봉투는 순간 봉투 아래 — 고속일수록 격차가 벌어진다."""
        for kcas in (300.0, 350.0, 400.0, 450.0):
            self.assertLess(self.L.sustained_load_factor(kcas),
                            self.L.max_load_factor(kcas), msg=f"{kcas}kt")
        # 350kt 에서 순간 9G / 지속 4.79G — 이 격차가 스틱 포화의 원인이었다
        self.assertAlmostEqual(self.L.sustained_load_factor(350.0), 4.79, places=2)

    def test_sustained_altitude_and_clamping(self):
        """고도가 높을수록 추력이 줄어 지속 G 가 낮다. 표 밖은 양끝값 고정."""
        self.assertLess(self.L.sustained_load_factor(400.0, 25000.0),
                        self.L.sustained_load_factor(400.0, 15000.0))
        self.assertAlmostEqual(self.L.sustained_load_factor(100.0, 15000.0), 3.59, places=2)
        self.assertAlmostEqual(self.L.sustained_load_factor(900.0, 15000.0), 3.68, places=2)
        # 고도 보간: 20,000ft 는 두 곡선 중간
        mid = self.L.sustained_load_factor(350.0, 20000.0)
        self.assertAlmostEqual(mid, 0.5 * (4.79 + 3.86), places=2)

    def test_pitch_rate_matches_g(self):
        v = 590.0  # ~350 kt
        q_max = self.L.max_pitch_rate(v, 350.0)
        self.assertAlmostEqual(q_max, 9.0 * G_FT_S2 / v, places=9)

    def test_omega_clamp_and_flags(self):
        clamped, flags = self.L.limit_omega_sp([0.0, 5.0, 0.0], v_fps=590.0, kcas=350.0)
        self.assertTrue(flags["q_limited"])
        self.assertFalse(flags["p_limited"])
        self.assertAlmostEqual(flags["g_max"], 9.0, places=6)
        self.assertLess(clamped[1], 5.0)   # 클램프됨
        self.assertAlmostEqual(clamped[1], flags["q_max"], places=9)

    def test_negative_g_asymmetric(self):
        self.assertAlmostEqual(self.L.min_load_factor(350.0), -3.0, places=6)   # 고속: 구조 -3G
        self.assertAlmostEqual(self.L.min_load_factor(165.0), -2.25, places=6)  # 저속: 공력이 먼저
        v = 590.0
        clamped, flags = self.L.limit_omega_sp([0.0, -1.0, 0.0], v_fps=v, kcas=350.0)
        self.assertTrue(flags["q_limited"])
        self.assertAlmostEqual(clamped[1], -3.0 * G_FT_S2 / v, places=9)        # -9G 아님
        # 완만한 언로드는 통과 — 음의 G 자체를 막지는 않는다.
        ok, f2 = self.L.limit_omega_sp([0.0, -0.05, 0.0], v_fps=v, kcas=350.0)
        self.assertFalse(f2["q_limited"])
        self.assertAlmostEqual(ok[1], -0.05, places=9)

    def test_gravity_term_in_pitch_rate(self):
        """q = (n − cosφcosθ)·g/V — 수평 정립에서 1G 는 중력이 상쇄한다."""
        v, kcas = 590.0, 350.0
        # 나이프에지(g_lift=0): 종전 그대로 n·g/V.
        self.assertAlmostEqual(self.L.max_pitch_rate(v, kcas, 0.0),
                               9.0 * G_FT_S2 / v, places=9)
        # 수평 정립(g_lift=1): 상한 1G 만큼 좁아지고, 하한도 1G 만큼 내려간다.
        self.assertAlmostEqual(self.L.max_pitch_rate(v, kcas, 1.0),
                               8.0 * G_FT_S2 / v, places=9)
        self.assertAlmostEqual(self.L.min_pitch_rate(v, kcas, 1.0),
                               -4.0 * G_FT_S2 / v, places=9)
        # 배면 수평(g_lift=−1): 반대로 상한이 넓고 하한이 좁다.
        self.assertAlmostEqual(self.L.max_pitch_rate(v, kcas, -1.0),
                               10.0 * G_FT_S2 / v, places=9)
        self.assertAlmostEqual(self.L.min_pitch_rate(v, kcas, -1.0),
                               -2.0 * G_FT_S2 / v, places=9)

    def test_gravity_term_keeps_bounds_ordered(self):
        """g_max < g_lift 인 저속 수평비행에서도 lo ≤ hi 가 깨지지 않아야 한다."""
        # 100 KCAS → g_aero ≈ 0.83G < 1G. 중력항만 빼면 q_max 가 음수가 된다.
        q_hi = self.L.max_pitch_rate(300.0, 100.0, 1.0)
        q_lo = self.L.min_pitch_rate(300.0, 100.0, 1.0)
        self.assertEqual(q_hi, 0.0)
        self.assertLess(q_lo, 0.0)
        clamped, _ = self.L.limit_omega_sp([0.0, 0.5, 0.0], v_fps=300.0,
                                           kcas=100.0, g_lift=1.0)
        self.assertAlmostEqual(clamped[1], 0.0, places=9)

    def test_within_limits_untouched(self):
        # 저G 요청은 그대로 통과.
        clamped, flags = self.L.limit_omega_sp([0.1, 0.05, 0.0], v_fps=590.0, kcas=350.0)
        self.assertFalse(flags["q_limited"])
        np.testing.assert_allclose(clamped, [0.1, 0.05, 0.0])


if __name__ == "__main__":
    unittest.main()
