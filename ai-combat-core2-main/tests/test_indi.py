"""INDI 회귀 — 동기화 LPF DC이득, 그리고 합성 플랜트 정상상태 rate 추종.

tmp/f16_bfm_control_architecture.md §5.1: 합성 플랜트(G 40% 오차 + 교차결합 +
외란)에서도 정상상태 rate RMS ~0.06°/s. 여기서는 넉넉한 상한으로 회귀만 가둔다.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.control.indi import SecondOrderLPF, INDIRateController


class TestLPF(unittest.TestCase):
    def test_dc_gain_unity(self):
        f = SecondOrderLPF(cutoff_hz=20.0, sample_rate_hz=200.0, n_channels=3)
        y = None
        for _ in range(400):
            y = f(np.array([1.0, -2.0, 0.5]))
        np.testing.assert_allclose(y, [1.0, -2.0, 0.5], atol=1e-6)  # 상수 입력 → 상수 통과


class TestINDISyntheticPlant(unittest.TestCase):
    def test_steady_state_rate_tracking(self):
        dt = 1.0 / 200.0
        # 실제 제어효과 (대각 지배 + 교차결합)
        G_true = np.array([[25.0, 0.0, 3.0],
                           [0.5, -8.0, 0.2],
                           [1.2, 0.0, -1.6]])
        G0 = 1.4 * G_true            # 식별 40% 오차
        dist = np.array([0.5, -0.3, 0.2])  # 외란 각가속도 [rad/s^2]

        ctl = INDIRateController(dt, G0, qbar_ref=1.0, k_rate=(8.0, 8.0, 6.0),
                                 filt_hz=25.0)
        ctl.reset(u0=(0, 0, 0), omega0=(0, 0, 0))

        omega = np.zeros(3)
        omega_dot = np.zeros(3)
        omega_sp = np.array([0.2, 0.1, -0.05])  # 일정 rate 지령
        err2 = np.zeros(3)
        n = 3000
        tail = 500
        for i in range(n):
            u = ctl.update(omega, omega_sp, qbar=1.0, ang_accel=omega_dot)
            omega_dot = G_true @ u + dist
            omega = omega + omega_dot * dt
            if i >= n - tail:
                err2 += (omega_sp - omega) ** 2
        rms_dps = np.rad2deg(np.sqrt(err2 / tail))
        # 40% 모델오차 + 외란에도 정상상태 rate 오차가 작아야 한다.
        self.assertTrue(np.all(rms_dps < 0.5),
                        msg="steady-state RMS too high: %s deg/s" % rms_dps)


if __name__ == "__main__":
    unittest.main()
