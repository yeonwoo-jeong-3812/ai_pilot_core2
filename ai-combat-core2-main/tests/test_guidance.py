"""BFMGuidance 회귀 — 조준점 / G 조절 / 파워 / 리프트벡터 롤 부호. (JSBSim 불필요)"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.guidance.bfm_guidance import BFMGuidance, AircraftKinematics
from aircombat.guidance.doctrine import Doctrine


class TestGuidance(unittest.TestCase):
    def setUp(self):
        self.g = BFMGuidance()

    def test_aim_point_pursuit(self):
        fp = np.array([1000.0, 0.0, 0.0]); fv = np.array([200.0, 0.0, 0.0])
        np.testing.assert_allclose(self.g._aim_point(fp, fv, "pure"), fp)
        self.assertGreater(self.g._aim_point(fp, fv, "lead")[0], fp[0])   # 앞
        self.assertLess(self.g._aim_point(fp, fv, "lag")[0], fp[0])       # 뒤

    def test_regulate_g_burst_interpolates_envelope(self):
        """g_burst 는 지속↔순간 봉투 사이를 단조 보간한다 (구 max_g 이진 특권 대체)."""
        kw = dict(g_sustained=4.0)
        gs = [self.g._regulate_g(60.0, 350.0, 9.0, b, **kw)[0]
              for b in (0.0, 0.25, 0.5, 0.75, 1.0)]
        self.assertEqual(gs, sorted(gs))                  # 단조 증가
        self.assertAlmostEqual(gs[0], 4.0)                # burst=0 → 지속 봉투 천장
        self.assertAlmostEqual(gs[-1], 9.0 * Doctrine().g_fraction)   # burst=1 → 순간 봉투×g_fraction
        # 어느 burst 에서도 조절 모드다 — "무조건 최대" 탈출구는 없다
        for b in (0.0, 0.5, 1.0):
            self.assertEqual(self.g._regulate_g(60.0, 350.0, 9.0, b, **kw)[1], "regulate")

    def test_regulate_g_full_ata_shapes_aggression(self):
        """g_full_ata_deg 가 작을수록 같은 ATA 에서 더 세게 당긴다."""
        kw = dict(g_sustained=9.0)
        sharp, _ = self.g._regulate_g(30.0, 350.0, 9.0, 1.0, g_full_ata_deg=30.0, **kw)
        blunt, _ = self.g._regulate_g(30.0, 350.0, 9.0, 1.0, g_full_ata_deg=90.0, **kw)
        self.assertGreater(sharp, blunt)

    def test_regulate_g_track_window_opens(self):
        """track 창을 넓히면 burst 가 낮아도 추적 하한 G 가 발동한다."""
        kw = dict(g_sustained=4.0, rng_ft=2400.0, omega_los=0.25, v_fps=600.0)
        _, narrow = self.g._regulate_g(25.0, 350.0, 9.0, 0.0,
                                       track_rng_ft=1000.0, track_ata_deg=10.0, **kw)
        _, wide = self.g._regulate_g(25.0, 350.0, 9.0, 0.0,
                                     track_rng_ft=3000.0, track_ata_deg=30.0, **kw)
        self.assertEqual(narrow, "regulate")
        self.assertEqual(wide, "track_lock")

    def test_regulate_g_proportional_and_cap(self):
        g_lo, _ = self.g._regulate_g(10.0, 350.0, 9.0, 1.0)
        g_hi, _ = self.g._regulate_g(80.0, 350.0, 9.0, 1.0)
        self.assertLess(g_lo, g_hi)                       # ATA↑ → G↑
        self.assertLessEqual(g_hi, 9.0 * Doctrine().g_fraction + 1e-9)   # 명목 상한 = 가용×g_fraction
        self.assertGreaterEqual(g_lo, Doctrine().g_min)

    def test_regulate_g_energy_backoff(self):
        g_norm, _ = self.g._regulate_g(45.0, 350.0, 9.0, False)
        g_slow, mode = self.g._regulate_g(45.0, 250.0, 9.0, False)
        self.assertLess(g_slow, g_norm)                   # 저속 백오프
        self.assertEqual(mode, "energy_backoff")

    def test_power_schedule(self):
        # 캘리브레이션: f16.xml pos=2×cmd → cmd 0.5=MIL, 1.0=full AB, 0.6 은 이미 min-AB
        self.assertEqual(self.g._power(300.0)[0], 1.0)    # 하한 미만 → full AB
        self.assertEqual(self.g._power(350.0)[0], 0.5)    # 대역 유지 = 실 MIL
        self.assertEqual(self.g._power(420.0)[0], 0.2)    # 상한 초과 → MIL 미만 감속

    def test_lift_vector_roll_sign(self):
        # 아군 수평 북향, 표적 우측(E>0) 동일고도 → 우롤(dphi>0).
        me = AircraftKinematics(pos_ned=np.array([0, 0, -15000.0]),
                                vel_ned=np.array([600.0, 0, 0]),
                                phi=0.0, theta=0.0, psi=0.0, v_fps=600.0, kcas=350.0)
        gc = self.g.compute(me, np.array([3000.0, 2000.0, -15000.0]),
                            np.array([600.0, 0, 0]), pursuit="pure")
        self.assertGreater(gc.audit["dphi_deg"], 0.0)     # 우측 표적 → 우롤
        self.assertLessEqual(gc.g_target, gc.audit["g_avail"] + 1e-9)

    def test_g_never_exceeds_limiter(self):
        me = AircraftKinematics(pos_ned=np.array([0, 0, -15000.0]),
                                vel_ned=np.array([300.0, 0, 0]),
                                phi=0.0, theta=0.0, psi=0.0, v_fps=300.0, kcas=200.0)
        # 저속(kcas=200) → 가용 G 작음. g_burst 최대라도 리미터 이하.
        gc = self.g.compute(me, np.array([2000.0, 2000.0, -15000.0]),
                            np.array([300.0, 0, 0]), pursuit="pure", g_burst=1.0)
        self.assertLessEqual(gc.g_target, gc.audit["g_avail"] + 1e-9)
        self.assertLess(gc.audit["g_avail"], 9.0)         # 200 KCAS 는 9G 못 냄


class TestGuidanceVertical(unittest.TestCase):
    """수직 오프셋 + 죽은 setpoint 5종 결선 (§2)."""

    def setUp(self):
        self.g = BFMGuidance()
        self.me = AircraftKinematics(pos_ned=np.array([0.0, 0.0, -15000.0]),
                                     vel_ned=np.array([600.0, 0.0, 0.0]),
                                     phi=0.0, theta=0.0, psi=0.0,
                                     v_fps=600.0, kcas=350.0)

    def test_aim_point_vertical_offset(self):
        fp = np.array([1000.0, 0.0, -15000.0]); fv = np.array([200.0, 0.0, 0.0])
        aim = self.g._aim_point(fp, fv, "pure", aim_above_ft=750.0)
        self.assertAlmostEqual(aim[2], -15750.0)          # NED: 위 = D 감소
        aim_dn = self.g._aim_point(fp, fv, "pure", aim_above_ft=-500.0)
        self.assertAlmostEqual(aim_dn[2], -14500.0)

    def test_aim_point_per_call_overrides(self):
        fp = np.array([1000.0, 0.0, 0.0]); fv = np.array([200.0, 0.0, 0.0])
        lead_far = self.g._aim_point(fp, fv, "lead", lead_time_s=2.0)
        lead_def = self.g._aim_point(fp, fv, "lead")                  # 기본 1.5s
        self.assertAlmostEqual(lead_far[0] - lead_def[0], 100.0)
        lag_far = self.g._aim_point(fp, fv, "lag", lag_dist_ft=2000.0)
        lag_def = self.g._aim_point(fp, fv, "lag")                    # 기본 1500ft
        self.assertAlmostEqual(lag_def[0] - lag_far[0], 500.0)

    def test_limiter_built_from_doctrine(self):
        doc = Doctrine(corner_kcas_lo=300.0, corner_kcas_hi=420.0)
        g = BFMGuidance(doctrine=doc)
        self.assertEqual(g.limiter.cfg.kcas_corner_lo, 300.0)   # 교리=단일 진실
        self.assertEqual(g.limiter.cfg.kcas_corner_hi, 420.0)

    def test_power_entry_ab(self):
        # 원거리(>2×slant_hi=12,000ft) + 진입속도 미달 → AB 가속
        self.assertEqual(self.g._power(400.0, rng_ft=20000.0), (1.0, "AB_entry"))
        # 근거리에선 파이팅 대역 규칙으로 폴백(400>375 → 감속)
        self.assertEqual(self.g._power(400.0, rng_ft=5000.0)[1], "decel")

    def test_power_energy_margin(self):
        # 대역 내: 우위 50kt 미만 → AB, 50–75 는 AB→MIL 선형, 75 이상 → MIL
        self.assertEqual(self.g._power(350.0, adv_kt=30.0), (1.0, "margin_regain"))
        thr_mid, mode_mid = self.g._power(350.0, adv_kt=62.5)
        self.assertAlmostEqual(thr_mid, 0.75)             # 중간점 = AB·MIL 중간
        self.assertEqual(mode_mid, "margin_regain")
        self.assertEqual(self.g._power(350.0, adv_kt=80.0), (0.5, "MIL_hold"))

    def test_power_closure_control(self):
        # 건 접근 closure 조절(4.4.12.1): 후방 반구 + <2,500ft 에서 허용 접근율
        # (900ft 트레일로 수렴하는 깔때기) 초과분만 MIL→idle 비례 컷
        # rng 900ft: allow=0 → closure 150 전부 초과 → idle
        self.assertEqual(self.g._power(400.0, rng_ft=900.0, aspect_deg=40.0,
                                       closure_fps=150.0), (0.0, "closure_ctl"))
        # rng 1650ft: allow=75 → closure 150 중 초과 75 → MIL 절반
        thr_half, mode = self.g._power(400.0, rng_ft=1650.0, aspect_deg=40.0,
                                       closure_fps=150.0)
        self.assertAlmostEqual(thr_half, 0.25)
        self.assertEqual(mode, "closure_ctl")
        # rng 2400ft: allow=150 → closure 150 은 허용 내 → 컷 없음(기존 규칙 decel)
        self.assertEqual(self.g._power(400.0, rng_ft=2400.0, aspect_deg=40.0,
                                       closure_fps=150.0)[1], "decel")
        # 게이트 밖: 전방 반구(aspect>90) / 파이팅 하한 미만 → 기존 규칙
        self.assertEqual(self.g._power(400.0, rng_ft=900.0, aspect_deg=120.0,
                                       closure_fps=150.0)[1], "decel")
        self.assertEqual(self.g._power(300.0, rng_ft=900.0, aspect_deg=40.0,
                                       closure_fps=150.0), (1.0, "AB_accel"))

    def test_regulate_g_track_lock(self):
        # 건 접근 기하(후방·근접·저ATA): LOS 회전율 일치 G 가 하한 — ATA 비례
        # 백오프의 원뿔 직전 평형(획득≠추적)을 깬다. omega 0.3rad/s·V 600fps
        # → n = 0.3×600/32.2×1.15 ≈ 6.4G (ATA 비례로는 15/45×8.1=2.7G)
        g, mode = self.g._regulate_g(15.0, 400.0, 9.0, False, aspect_deg=40.0,
                                     rng_ft=1200.0, omega_los=0.3, v_fps=600.0)
        self.assertEqual(mode, "track_lock")
        self.assertAlmostEqual(g, 0.3 * 600.0 / 32.174 * 1.15, places=2)
        self.assertLessEqual(g, 9.0 * Doctrine().g_fraction + 1e-9)   # g_nom 상한 유지(D6)
        # 기하 밖(원거리)이면 비례 조절 그대로
        g2, mode2 = self.g._regulate_g(15.0, 400.0, 9.0, False, aspect_deg=40.0,
                                       rng_ft=5000.0, omega_los=0.3, v_fps=600.0)
        self.assertEqual(mode2, "regulate")
        self.assertLess(g2, g)

    def test_regulate_g_initial_pull(self):
        # 머지 진입 기하(고aspect·슬랜트 내) → 초기 당김 7G (g_nom 상한 내)
        g, mode = self.g._regulate_g(10.0, 400.0, 9.0, False,
                                     aspect_deg=150.0, rng_ft=5000.0)
        self.assertEqual(mode, "initial_pull")
        self.assertAlmostEqual(g, 7.0)
        # 같은 ATA 라도 기하 밖(원거리)이면 비례 조절 유지
        g2, mode2 = self.g._regulate_g(10.0, 400.0, 9.0, False,
                                       aspect_deg=150.0, rng_ft=20000.0)
        self.assertEqual(mode2, "regulate")
        self.assertLess(g2, g)

    def test_lv_auto_offset_on_entry_geometry(self):
        # 머지 진입 기하(헤드온 접근·슬랜트 내) + L1 미지정 → 자동 +lv_above_ft
        gc = self.g.compute(self.me, np.array([5000.0, 0.0, -15000.0]),
                            np.array([-600.0, 0.0, 0.0]), pursuit="pure",
                            foe_psi=np.pi)   # 대향 기수 (AA 는 BEM 종축 기준)
        self.assertAlmostEqual(gc.audit["aim_above_ft"], Doctrine().lv_above_ft)
        # 진입 기하 아님(적이 같은 방향 비행) → 자동 오프셋 없음
        gc2 = self.g.compute(self.me, np.array([5000.0, 0.0, -15000.0]),
                             np.array([600.0, 0.0, 0.0]), pursuit="pure")
        self.assertAlmostEqual(gc2.audit["aim_above_ft"], 0.0)

    def test_l1_explicit_offset_wins(self):
        # L1 명시값(0 포함)이 교리 자동보다 항상 우선
        gc = self.g.compute(self.me, np.array([5000.0, 0.0, -15000.0]),
                            np.array([-600.0, 0.0, 0.0]), pursuit="pure",
                            aim_above_ft=0.0)
        self.assertAlmostEqual(gc.audit["aim_above_ft"], 0.0)
        gc2 = self.g.compute(self.me, np.array([5000.0, 0.0, -15000.0]),
                             np.array([-600.0, 0.0, 0.0]), pursuit="pure",
                             aim_above_ft=-300.0)
        self.assertAlmostEqual(gc2.audit["aim_above_ft"], -300.0)

    def test_offset_drives_lift_vector(self):
        # 동고도 정면 표적 + 위 오프셋 → 리프트벡터가 위쪽(|dphi| 작음, 배면 아님)
        # 오프셋 0 이고 표적이 정확히 기수 방향이면 dphi 부호 불안정하므로
        # 위 오프셋을 준 경우 조준점이 수평선 위 → -z 성분 우세 → |dphi| < 90°
        gc = self.g.compute(self.me, np.array([3000.0, 0.0, -15000.0]),
                            np.array([600.0, 0.0, 0.0]), pursuit="pure",
                            aim_above_ft=750.0)
        self.assertLess(abs(gc.audit["dphi_deg"]), 90.0)
        # 아래 오프셋 → 조준점이 수평선 아래 → 리프트벡터 반전(|dphi| > 90°)
        gc2 = self.g.compute(self.me, np.array([3000.0, 0.0, -15000.0]),
                             np.array([600.0, 0.0, 0.0]), pursuit="pure",
                             aim_above_ft=-750.0)
        self.assertGreater(abs(gc2.audit["dphi_deg"]), 90.0)

    def test_audit_new_fields(self):
        gc = self.g.compute(self.me, np.array([5000.0, 3000.0, -15000.0]),
                            np.array([500.0, 0.0, 0.0]), pursuit="lead",
                            lead_time_s=1.5)
        for key in ("aim_above_ft", "lead_time_s", "lag_dist_ft",
                    "adv_kt", "entry_phase", "g_mode", "power_mode"):
            self.assertIn(key, gc.audit)
        self.assertAlmostEqual(gc.audit["lead_time_s"], 1.5)
        self.assertAlmostEqual(gc.audit["adv_kt"], (600.0 - 500.0) * 0.592484)


if __name__ == "__main__":
    unittest.main()
