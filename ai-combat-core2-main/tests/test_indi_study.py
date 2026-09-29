"""INDI 연구 노브(INDIConfig: k_ff·λ) + 교범 해석 G 봉투(envelope="manual") 회귀.

근거: paper.md §6(봉투)·§7-C(변수). 기본값은 기존 동작과 비트 동일해야 한다.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.control.indi import INDIConfig, INDIRateController, RateSensor, SensorConfig
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


class TestRateSensor(unittest.TestCase):
    PQR = np.array([0.1, -0.2, 0.05]); ACC = np.array([1.0, 2.0, 3.0])

    def test_truth_passthrough(self):
        pqr, acc = RateSensor()(self.PQR, self.ACC)
        np.testing.assert_array_equal(pqr, self.PQR)
        np.testing.assert_array_equal(acc, self.ACC)

    def test_gyro_noise_deterministic_and_sized(self):
        cfg = SensorConfig(kind="gyro", gyro_sigma_dps=0.5, seed=7)
        a, b, c = RateSensor(cfg), RateSensor(cfg), RateSensor(cfg, salt=1)
        xa = np.array([a(self.PQR, self.ACC)[0] for _ in range(4000)])
        xb = np.array([b(self.PQR, self.ACC)[0] for _ in range(4000)])
        xc = np.array([c(self.PQR, self.ACC)[0] for _ in range(4000)])
        np.testing.assert_array_equal(xa, xb)                 # 같은 seed·salt = 같은 잡음열
        self.assertFalse(np.array_equal(xa, xc))              # 측(salt)별로 다름
        std = np.rad2deg((xa - self.PQR).std(axis=0))
        np.testing.assert_allclose(std, 0.5, rtol=0.05)
        self.assertIsNone(a(self.PQR, self.ACC)[1])           # 각가속도는 INDI 차분 추정

    def test_delay_ticks(self):
        s = RateSensor(SensorConfig(delay_ticks=3))
        out = [s(np.full(3, float(k)), np.zeros(3))[0][0] for k in range(8)]
        self.assertEqual(out, [0, 0, 0, 0, 1, 2, 3, 4])

    def test_rejects_unknown_kind(self):
        with self.assertRaises(ValueError):
            RateSensor(SensorConfig(kind="lidar"))


class TestF16FixModel(unittest.TestCase):
    """연구용 f16fix: 롤 명령이 대칭 양력을 만들지 않고, 롤 성능은 원본과 같다."""

    @staticmethod
    def _aileron_only(model, ail):
        from aircombat.fdm.plant import F16Plant
        p = F16Plant(dt=1.0 / 120.0, model=model)
        p.set_ic(alt_ft=5000.0, vc_kts=400.0)
        p["fcs/throttle-cmd-norm"] = 0.85
        p.trim()
        p["fcs/aileron-cmd-norm"] = ail
        nz = []
        for _ in range(36):
            p.step(1)
            nz.append(p["accelerations/Nz"])
        return min(nz), max(nz), p["velocities/p-rad_sec"]

    def test_no_roll_induced_lift_and_symmetric(self):
        lo_r, hi_r, p_r = self._aileron_only("f16fix", 1.0)
        lo_l, hi_l, p_l = self._aileron_only("f16fix", -1.0)
        for lo, hi in ((lo_r, hi_r), (lo_l, hi_l)):
            self.assertLess(hi - lo, 0.1)                       # 원본은 +3G/−3G 급변
        self.assertAlmostEqual(p_r, -p_l, delta=np.radians(0.5))

    def test_stock_model_still_has_defect(self):
        # 원본은 건드리지 않았다(플랫폼 물리 불변) — 결함이 그대로 재현돼야 한다.
        lo, hi, _ = self._aileron_only("f16", -1.0)
        self.assertGreater(hi, 3.0)


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

    def test_nz_protect_off_ignores_nz(self):
        a, fa = self.man.limit_omega_sp([0.0, 0.3, 0.0], 700.0, 400.0, 1.0)
        b, fb = self.man.limit_omega_sp([0.0, 0.3, 0.0], 700.0, 400.0, 1.0, nz=12.0)
        np.testing.assert_array_equal(a, b)
        self.assertFalse(fb["nz_limited"])

    def test_nz_protect_cuts_q_on_predicted_overshoot(self):
        L = CombinedLimiter(LimiterConfig(envelope="manual", nz_protect=True))
        free, _ = L.limit_omega_sp([0.0, 0.3, 0.0], 700.0, 400.0, 1.0, nz=5.0)
        cut, f = L.limit_omega_sp([0.0, 0.3, 0.0], 700.0, 400.0, 1.0, nz=7.6)  # 급상승 → 예측 초과
        self.assertTrue(f["nz_limited"])
        self.assertLess(cut[1], free[1])

    def test_nz_protect_negative_side(self):
        L = CombinedLimiter(LimiterConfig(envelope="manual", nz_protect=True))
        L.limit_omega_sp([0.0, -0.3, 0.0], 700.0, 400.0, 1.0, nz=-1.0)
        cut, f = L.limit_omega_sp([0.0, -0.3, 0.0], 700.0, 400.0, 1.0, nz=-2.5)
        self.assertTrue(f["nz_limited"])
        self.assertGreater(cut[1], -0.3)

    def test_rejects_unknown_envelope(self):
        with self.assertRaises(ValueError):
            CombinedLimiter(LimiterConfig(envelope="bogus"))


if __name__ == "__main__":
    unittest.main()


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "research", "indi")))


class TestStudyDrivers(unittest.TestCase):
    """E2·E3·E4 드라이버의 순수 함수 (JSBSim 불필요)."""

    def test_pareto_keeps_only_nondominated(self):
        from optimize import pareto
        ref = dict(J=1.0, A=1.0)
        pts = [dict(cfg=i, J=j, A=a, dq=dq) for i, (j, a, dq) in
               enumerate([(1.0, 1.0, False), (0.9, 0.5, False), (0.8, 0.9, False),
                          (0.95, 0.6, False), (0.1, 0.1, True)])]
        front = pareto(pts, ref)
        self.assertEqual([p["cfg"] for p in front], [2, 1])     # 실격(0.1,0.1)·지배된 점 제외

    def test_pso_box_round_trip_log_axis(self):
        from optimize import to_cfg, LO, HI
        lo, hi = to_cfg(LO), to_cfg(HI)
        self.assertAlmostEqual(lo["filt_hz"], 3.0)
        self.assertAlmostEqual(hi["filt_hz"], 40.0)
        self.assertEqual((lo["k_r"], hi["k_r"]), (6.0, 6.0))    # k_r 은 탐색 대상 아님

    def test_wilson_interval(self):
        from duel import wilson
        lo, hi = wilson(50, 100)
        self.assertAlmostEqual(lo, 0.4038, places=3)
        self.assertAlmostEqual(hi, 0.5962, places=3)

    def test_mc_condition_deterministic(self):
        from duel import _mc_cond
        a, b = _mc_cond("red_prime", "headon", 3), _mc_cond("red_prime", "headon", 3)
        self.assertEqual(a, b)
        self.assertTrue(0.7 <= a["g0_scale"] <= 1.3 and 0 <= a["turb_severity"] <= 4)

    def test_paired_difference(self):
        from sweep import paired
        lim = {"disqualified": False, "nz_max": 5.0}
        g = lambda w, hb, hr: dict(winner=w, hp_blue=hb, hp_red=hr, limits_blue=lim)
        s = paired([g("red", 10, 60), g("draw", 50, 50)], [g("blue", 70, 0), g("draw", 50, 50)])
        self.assertAlmostEqual(s["d_points"], 0.5)              # (1−0 + 0.5−0.5)/2
        self.assertAlmostEqual(s["d_hp"], 60.0)                 # ((70−0)−(10−60) + 0)/2


class TestCombatLag(unittest.TestCase):
    def test_lag_recovers_known_delay(self):
        from combat import CombatMonitor
        rng = np.random.default_rng(0)
        x = np.convolve(rng.standard_normal(3000), np.ones(20) / 20, mode="same")
        y = np.r_[np.zeros(10), x[:-10]]                     # 10틱(83.3 ms) 지연된 응답
        self.assertAlmostEqual(CombatMonitor._lag_ms(x, y, 1 / 120), 10 / 120 * 1000, places=6)


class TestHolm(unittest.TestCase):
    def test_holm_matches_textbook(self):
        from analyze import holm
        # p = [0.01, 0.04, 0.03, 0.005] → 정렬 0.005·0.01·0.03·0.04 → ×4,×3,×2,×1 → 0.02,0.03,0.06,0.06(단조)
        np.testing.assert_allclose(holm([0.01, 0.04, 0.03, 0.005]), [0.03, 0.06, 0.06, 0.02])
