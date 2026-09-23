"""INDI 연구 노브(INDIConfig: k_ff·λ) + 교범 해석 G 봉투(envelope="manual") 회귀.

근거: paper.md §6(봉투)·§7-C(변수). 기본값은 기존 동작과 비트 동일해야 한다.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.control.indi import INDIConfig, INDIRateController
from aircombat.control.limiter import CombinedLimiter, LimiterConfig

DT = 1.0 / 120.0
G_TRUE = np.array([[25.0, 0.0, 3.0],
                   [0.5, -8.0, 0.2],
                   [1.2, 0.0, -1.6]])


def _run(sp_fn, n=1200, **kw):
    """합성 플랜트 폐루프 → (각 스텝 omega_sp, omega, u) 배열."""
    ctl = INDIRateController(DT, G_TRUE, qbar_ref=1.0, k_rate=(9.0, 9.0, 6.0),
                             filt_hz=25.0, **kw)
    ctl.reset()
    omega = np.zeros(3); omega_dot = np.zeros(3)
    sps, ws, us = [], [], []
    for i in range(n):
        sp = sp_fn(i * DT)
        u = ctl.update(omega, sp, qbar=1.0, ang_accel=omega_dot)
        omega_dot = G_TRUE @ u
        omega = omega + omega_dot * DT
        sps.append(sp); ws.append(omega.copy()); us.append(u)
    return np.array(sps), np.array(ws), np.array(us)


class TestINDIConfig(unittest.TestCase):
    def test_defaults_match_legacy_hardcode(self):
        c = INDIConfig()
        self.assertEqual((c.k_p, c.k_q, c.k_r, c.filt_hz, c.k_att, c.k_ff, c.lam),
                         (9.0, 9.0, 6.0, 25.0, 4.0, 0.0, 0.0))

    def test_zero_knobs_bit_identical(self):
        step = lambda t: np.array([0.2, 0.1, -0.05])
        a = _run(step, n=300)
        b = _run(step, n=300, k_ff=0.0, lam=0.0)
        for x, y in zip(a, b):
            np.testing.assert_array_equal(x, y)

    def test_feedforward_reduces_ramp_lag(self):
        ramp = lambda t: np.array([0.3 * t, 0.1 * t, 0.0])   # rad/s 램프 지령
        sp0, w0, _ = _run(ramp)
        sp1, w1, _ = _run(ramp, k_ff=1.0)
        lag0 = np.abs(sp0 - w0)[-200:, :2].mean()
        lag1 = np.abs(sp1 - w1)[-200:, :2].mean()
        self.assertLess(lag1, 0.5 * lag0)

    def test_lambda_scales_increment_per_channel(self):
        # 대각 G 에서 LM 채널별 스케일 → 증분이 정확히 1/(1+λ) (채널 효과 크기와 무관).
        G = np.diag([25.0, -8.0, -1.6])
        du = []
        for lam in (0.0, 0.5):
            c = INDIRateController(DT, G, qbar_ref=1.0, k_rate=(9.0, 9.0, 6.0), lam=lam)
            c.reset()
            du.append(c.update(np.zeros(3), np.array([0.2, 0.1, -0.05]), qbar=1.0,
                               ang_accel=np.zeros(3)))
        np.testing.assert_allclose(du[1], du[0] / 1.5, rtol=1e-12)

    def test_lambda_still_converges_all_channels(self):
        # 단일 tr(GᵀG) 스케일은 약한 yaw 채널이 여기서 수렴 실패했다(회귀 방지).
        step = lambda t: np.array([0.2, 0.1, -0.05])
        _, w, _ = _run(step, n=1200, lam=0.3)
        np.testing.assert_allclose(w[-1], step(0), atol=2e-3)


class TestManualEnvelope(unittest.TestCase):
    def setUp(self):
        self.man = CombinedLimiter(LimiterConfig(envelope="manual"))
        self.plat = CombinedLimiter(LimiterConfig())

    def test_breakpoints(self):
        g = self.man.max_load_factor
        self.assertAlmostEqual(g(0.0), 0.0)
        self.assertAlmostEqual(g(330.0), 6.75)
        self.assertAlmostEqual(g(350.0), 9.0 * 350 / 440)      # 7.16 ≈ 교범 EEGS 7.3G@350
        self.assertAlmostEqual(g(440.0), 9.0)
        self.assertAlmostEqual(g(600.0), 9.0)
        self.assertAlmostEqual(g(165.0), 6.75 / 4)             # 330 이하 ∝ V²

    def test_continuous_and_monotone(self):
        v = np.linspace(0, 600, 6001)
        g = np.array([self.man.max_load_factor(x) for x in v])
        self.assertTrue(np.all(np.diff(g) >= -1e-12))
        self.assertLess(np.abs(np.diff(g)).max(), 0.01)       # 꺾임점에서 점프 없음

    def test_never_more_lenient_than_platform(self):
        for v in range(0, 601, 5):
            self.assertLessEqual(self.man.max_load_factor(v),
                                 self.plat.max_load_factor(v) + 1e-12)
            self.assertGreaterEqual(self.man.min_load_factor(v),
                                    self.plat.min_load_factor(v) - 1e-12)

    def test_ignores_doctrine_corner_override(self):
        wide = CombinedLimiter(LimiterConfig(kcas_corner_lo=440.0, envelope="manual"))
        self.assertAlmostEqual(wide.max_load_factor(350.0), self.man.max_load_factor(350.0))

    def test_platform_default_unchanged(self):
        self.assertAlmostEqual(self.plat.max_load_factor(330.0), 9.0)

    def test_rejects_unknown_envelope(self):
        with self.assertRaises(ValueError):
            CombinedLimiter(LimiterConfig(envelope="bogus"))


if __name__ == "__main__":
    unittest.main()
