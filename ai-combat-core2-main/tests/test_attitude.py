"""QuaternionAttitudeShim 회귀 — 부호/영오차/특이점(θ≈90°) 없음."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.control.attitude import (
    euler_to_quat, quat_to_euler, QuaternionAttitudeShim,
)


class TestQuaternionShim(unittest.TestCase):
    def test_euler_quat_roundtrip(self):
        for e in [(0.3, -0.5, 1.2), (0.0, 0.0, 0.0), (-1.0, 0.8, -2.5)]:
            q = euler_to_quat(*e)
            q2 = euler_to_quat(*quat_to_euler(q))
            self.assertTrue(np.allclose(q, q2, atol=1e-9) or
                            np.allclose(q, -q2, atol=1e-9))

    def test_roll_error_gives_positive_p(self):
        shim = QuaternionAttitudeShim(k_att=4.5, rate_limit_dps=(500, 500, 500))
        w = shim.rate_setpoint(euler_to_quat(0, 0, 0),
                               euler_to_quat(np.deg2rad(30), 0, 0), r_cur=0.0)
        self.assertGreater(w[0], 0.5)          # +roll 지령
        self.assertLess(abs(w[1]), 1e-6)
        self.assertLess(abs(w[2]), 1e-6)

    def test_zero_error(self):
        shim = QuaternionAttitudeShim()
        q = euler_to_quat(0.5, 0.3, 1.0)
        np.testing.assert_allclose(shim.rate_setpoint(q, q, 0.0), [0, 0, 0], atol=1e-9)

    def test_shortest_path_qneg(self):
        # q 와 -q 는 같은 자세 → ω_sp 동일(≈0).
        shim = QuaternionAttitudeShim(rate_limit_dps=(500, 500, 500))
        q = euler_to_quat(0.2, 0.1, 0.0)
        np.testing.assert_allclose(shim.rate_setpoint(q, -q, 0.0), [0, 0, 0], atol=1e-9)

    def test_no_singularity_near_vertical(self):
        # θ≈90°(수직)에서 작은 피치 스텝 → 유한·유계 ω (gimbal lock 없음).
        shim = QuaternionAttitudeShim(rate_limit_dps=(500, 500, 500))
        w = shim.rate_setpoint(euler_to_quat(0, np.deg2rad(89.0), 0.3),
                               euler_to_quat(0, np.deg2rad(90.0), 0.3), r_cur=0.0)
        self.assertTrue(np.all(np.isfinite(w)))
        self.assertLess(np.linalg.norm(w), 10.0)


if __name__ == "__main__":
    unittest.main()
