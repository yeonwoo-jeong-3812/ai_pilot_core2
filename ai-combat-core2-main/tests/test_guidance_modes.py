"""L2 가이드 국면 모드(stable·control_zone) + BFM 국면 조건 — 파일럿 피드백 라운드.

핵심 수용 기준:
  · stable    : 저표적(아래) 헤드온에서 배면 롤 무발생(|dphi|<90°, 클램프 ≤75°).
  · control_zone: 파워가 접근율을 목표 거리로 수렴(존 체류), 근접+접근 시 lag 편향(오버슈트 방지).
  · mode=None : 기존 거동 불변(회귀는 test_guidance 가 커버; 여기선 audit['mode'] 추가만 확인).
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.guidance.bfm_guidance import (
    BFMGuidance, AircraftKinematics, STABLE_BANK_MAX, CZ_RANGE_FT, THR_MIL)
from aircombat.tactics import conditions as cond
from aircombat.tactics.context import TacticContext


def _me():
    return AircraftKinematics(pos_ned=np.array([0.0, 0.0, -15000.0]),
                              vel_ned=np.array([600.0, 0.0, 0.0]),
                              phi=0.0, theta=0.0, psi=0.0, v_fps=600.0, kcas=350.0)


class TestStableMode(unittest.TestCase):
    """포인팅 추적 — 수평 우선 롤(정면=수평 복귀) + 부호있는 pitch(위/아래 모두)."""

    def setUp(self):
        self.g = BFMGuidance()

    def test_frontal_target_wings_level(self):
        """정면·동고도 표적 → 목표 뱅크 0(수평 복귀), pitch ≈ 0 (노즈온 유지)."""
        foe = np.array([3000.0, 0.0, -15000.0]); fv = np.array([600.0, 0.0, 0.0])
        gc = self.g.compute(_me(), foe, fv, pursuit="pure", mode="stable")
        self.assertLess(abs(gc.audit["dphi_deg"]), 5.0)   # 수평 복귀(배면 아님)
        self.assertLess(abs(gc.q_cmd), 0.05)              # 정면 → pitch 거의 0

    def test_low_target_pitches_down(self):
        """저표적 → **부호있는 pitch 로 기수를 내린다**(q_cmd<0). 구 stable 의 핵심 결함 해소.
        (기본 모드는 항상 상향 당김이라 저표적서 ATA null 실패했다 — 대비.)"""
        foe = np.array([3000.0, 0.0, -14250.0]); fv = np.array([600.0, 0.0, 0.0])  # 750ft 아래
        stable = self.g.compute(_me(), foe, fv, pursuit="pure", mode="stable")
        default = self.g.compute(_me(), foe, fv, pursuit="pure")
        self.assertLess(stable.q_cmd, 0.0)        # stable = 기수 내림(추적)
        self.assertGreater(default.q_cmd, 0.0)    # 기본 = 상향 당김(저표적 놓침)
        self.assertLessEqual(abs(stable.audit["dphi_deg"]),
                             np.degrees(STABLE_BANK_MAX) + 1e-6)   # 배면 무발생(뱅크 상한)

    def test_high_target_pitches_up(self):
        """고표적 → 기수 올림(q_cmd>0)."""
        foe = np.array([3000.0, 0.0, -15750.0]); fv = np.array([600.0, 0.0, 0.0])  # 750ft 위
        gc = self.g.compute(_me(), foe, fv, pursuit="pure", mode="stable")
        self.assertGreater(gc.q_cmd, 0.0)

    def test_lateral_target_banks_bounded(self):
        """우측 표적 → 우로 목표 뱅크(부분), 상한 STABLE_BANK_MAX 준수."""
        foe = np.array([3000.0, 2000.0, -15000.0]); fv = np.array([600.0, 0.0, 0.0])
        gc = self.g.compute(_me(), foe, fv, pursuit="pure", mode="stable")
        self.assertGreater(gc.audit["dphi_deg"], 5.0)     # 우롤
        self.assertLessEqual(gc.audit["dphi_deg"], np.degrees(STABLE_BANK_MAX) + 1e-6)
        self.assertEqual(gc.audit["g_mode"], "stable_track")


class TestControlZoneMode(unittest.TestCase):
    def setUp(self):
        self.g = BFMGuidance()

    def test_power_holds_zone(self):
        """접근율 조절기: 목표거리·닫힘0 → MIL, 근접+빠른접근 → 컷, 원거리 → 증추."""
        thr_hold, mode = self.g._control_zone_power(CZ_RANGE_FT, 0.0)
        self.assertAlmostEqual(thr_hold, THR_MIL, places=3)
        self.assertEqual(mode, "control_zone")
        thr_close, _ = self.g._control_zone_power(800.0, 150.0)     # 근접+빠른접근
        self.assertLess(thr_close, THR_MIL)                         # 파워 컷
        thr_far, _ = self.g._control_zone_power(4000.0, 0.0)        # 멀고 안 붙음
        self.assertGreater(thr_far, THR_MIL)                        # 붙이려 증추

    def test_lag_bias_prevents_overshoot(self):
        """근접+접근이면 control_zone 이 lag 로 편향(적기 앞 이탈 방지)."""
        foe = np.array([1500.0, 0.0, -15000.0]); fv = np.array([400.0, 0.0, 0.0])  # 접근중
        cz = self.g.compute(_me(), foe, fv, pursuit="pure", mode="control_zone")
        self.assertEqual(cz.audit["pursuit"], "lag")
        # 멀리 벌어지면(접근 아님) 입력 pursuit 유지
        foe_far = np.array([6000.0, 0.0, -15000.0]); fv_open = np.array([700.0, 0.0, 0.0])
        cz2 = self.g.compute(_me(), foe_far, fv_open, pursuit="pure", mode="control_zone")
        self.assertEqual(cz2.audit["pursuit"], "pure")

    def test_suppresses_auto_lv_offset(self):
        """머지 진입 기하라도 control_zone/stable 은 자동 LV 오프셋 억제(0)."""
        foe = np.array([5000.0, 0.0, -15000.0]); fv = np.array([-600.0, 0.0, 0.0])  # 대향
        base = self.g.compute(_me(), foe, fv, pursuit="pure", foe_psi=np.pi)
        self.assertGreater(base.audit["aim_above_ft"], 0.0)         # 기본은 자동 +LV
        for m in ("stable", "control_zone"):
            gc = self.g.compute(_me(), foe, fv, pursuit="pure", mode=m, foe_psi=np.pi)
            self.assertAlmostEqual(gc.audit["aim_above_ft"], 0.0)


class TestCzRangeOverride(unittest.TestCase):
    """cz_range_ft 오버라이드 — BEM CZ(2,000~3,000 ft)를 L1 액션 키로 표현."""

    def setUp(self):
        self.g = BFMGuidance()

    def test_power_setpoint_follows_override(self):
        """오버라이드 1,500 ft: 그 거리·닫힘0 → MIL 유지; 미지정(기본 2,500)이면 같은 거리서 증추."""
        thr_hold, _ = self.g._control_zone_power(1500.0, 0.0, cz_range_ft=1500.0)
        self.assertAlmostEqual(thr_hold, THR_MIL, places=3)
        thr_default, _ = self.g._control_zone_power(1500.0, 0.0)   # 기본 2,500 → 벌리려 감속
        self.assertLess(thr_default, THR_MIL)

    def test_lag_trip_scales_with_override(self):
        """lag 편향 트립도 setpoint 비례: 2,500 ft 접근중은 기본(트립 3,000 안)에선 lag,
        오버라이드 1,000(트립 1,200 밖)에선 pure."""
        foe = np.array([2500.0, 0.0, -15000.0]); fv = np.array([400.0, 0.0, 0.0])
        base = self.g.compute(_me(), foe, fv, pursuit="pure", mode="control_zone")
        self.assertEqual(base.audit["pursuit"], "lag")
        over = self.g.compute(_me(), foe, fv, pursuit="pure", mode="control_zone",
                              cz_range_ft=1000.0)
        self.assertEqual(over.audit["pursuit"], "pure")

    def test_default_unchanged(self):
        """cz_range_ft=None 은 기존 거동과 동일(하위호환)."""
        thr_a, _ = self.g._control_zone_power(CZ_RANGE_FT, 0.0)
        thr_b, _ = self.g._control_zone_power(CZ_RANGE_FT, 0.0, cz_range_ft=None)
        self.assertEqual(thr_a, thr_b)


class TestInControlZoneCondition(unittest.TestCase):
    """in_control_zone 경계값 — BEM CZ 기하(2~3 kft, AA<30, HCA<30)."""

    @staticmethod
    def _ctx(rng=2500.0, aspect=10.0, hca=10.0):
        return TacticContext(ata_deg=25.0, aspect_deg=aspect, range_ft=rng,
                             closure_fps=0.0, kcas=350.0, energy_diff_ft=0.0,
                             alt_gap_ft=0.0, hca_deg=hca)

    def test_range_band(self):
        self.assertFalse(cond.in_control_zone(self._ctx(rng=1999.0)))
        self.assertTrue(cond.in_control_zone(self._ctx(rng=2000.0)))
        self.assertTrue(cond.in_control_zone(self._ctx(rng=3000.0)))
        self.assertFalse(cond.in_control_zone(self._ctx(rng=3001.0)))

    def test_angle_gates(self):
        self.assertFalse(cond.in_control_zone(self._ctx(aspect=35.0)))   # AA 이탈
        self.assertFalse(cond.in_control_zone(self._ctx(hca=35.0)))      # HCA 이탈
        self.assertTrue(cond.in_control_zone(self._ctx(aspect=29.0, hca=29.0)))

    def test_registered_and_yaml_parses(self):
        self.assertIn("in_control_zone", cond.CONDITIONS)
        from aircombat.tactics.dsl import load_agent_yaml
        path = os.path.join(os.path.dirname(__file__), "..",
                            "examples", "textbook_headon.yaml")
        _, root, name, _ = load_agent_yaml(path)
        self.assertEqual(name, "TextbookHeadon")
        self.assertIsNotNone(root)


class TestAuditMode(unittest.TestCase):
    def test_mode_in_audit(self):
        g = BFMGuidance()
        foe = np.array([3000.0, 0.0, -15000.0]); fv = np.array([600.0, 0.0, 0.0])
        self.assertEqual(g.compute(_me(), foe, fv).audit["mode"], "-")
        self.assertEqual(g.compute(_me(), foe, fv, mode="stable").audit["mode"], "stable")


class TestBFMPhaseConditions(unittest.TestCase):
    """HABFM/OBFM/DBFM 진리표 — aspect/hca 기반 명명 wrapper."""

    @staticmethod
    def _ctx(aspect=90.0, hca=90.0):
        return TacticContext(ata_deg=20.0, aspect_deg=aspect, range_ft=3000.0,
                             closure_fps=100.0, kcas=350.0, energy_diff_ft=0.0,
                             alt_gap_ft=0.0, hca_deg=hca)

    def test_head_on(self):
        self.assertTrue(cond.is_head_on(self._ctx(hca=170.0)))     # 대향
        self.assertFalse(cond.is_head_on(self._ctx(hca=90.0)))

    def test_offensive(self):
        self.assertTrue(cond.is_offensive(self._ctx(aspect=30.0)))  # 내가 적 후미
        self.assertFalse(cond.is_offensive(self._ctx(aspect=150.0)))

    def test_defensive(self):
        self.assertTrue(cond.is_defensive(self._ctx(aspect=150.0)))  # 적이 내 후미
        self.assertFalse(cond.is_defensive(self._ctx(aspect=30.0)))

    def test_registered_in_dsl(self):
        for name in ("is_head_on", "is_offensive", "is_defensive"):
            self.assertIn(name, cond.CONDITIONS)


if __name__ == "__main__":
    unittest.main()
