"""엔진 회귀 — 스크립트 적기 운동학 / WEZ 데미지 / judge / scripted 1v1. (JSBSim 불필요)"""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.engine.state import KinState, ned_to_lonlat
from aircombat.engine.opponents.scripted import ScriptedOpponent
from aircombat.engine.match import Match, _wez_damage, HARD_DECK_FT


def _kin(pos, vel=(600.0, 0, 0), phi=0.0, alt=15000.0, psi=0.0):
    return KinState(pos_ned=np.array(pos, float), vel_ned=np.array(vel, float),
                    phi=phi, theta=0.0, psi=psi, v_fps=600.0, kcas=350.0, alt_ft=alt)


class TestScriptedOpponent(unittest.TestCase):
    def test_turn_changes_heading(self):
        o = ScriptedOpponent(heading_deg=0.0, maneuver="turn", turn_rate_dps=6.0)
        o.step(1.0)
        self.assertAlmostEqual(math.degrees(o.psi), 6.0, places=3)
        self.assertNotEqual(o._bank(), 0.0)          # 선회 → 뱅크

    def test_straight_holds_heading(self):
        o = ScriptedOpponent(heading_deg=0.0, maneuver="straight")
        o.step(1.0)
        self.assertAlmostEqual(math.degrees(o.psi), 0.0, places=6)
        self.assertEqual(o._bank(), 0.0)

    def test_state_interface(self):
        o = ScriptedOpponent(init_pos_ned=(100.0, 0, -15000.0))
        st = o.state()
        self.assertIsInstance(st, KinState)
        self.assertAlmostEqual(st.alt_ft, 15000.0)

    def test_no_synthesized_telemetry(self):
        # 운동학 적기는 조종면이 없다 — 합성값 대신 None(ACMI 조종 속성 미기록).
        o = ScriptedOpponent(maneuver="turn", turn_rate_dps=6.0)
        self.assertIsNone(o.telemetry())


class TestWEZDamage(unittest.TestCase):
    def test_damage_when_tracking(self):
        shooter = _kin((0, 0, -15000.0))
        target = _kin((600.0, 0, -15000.0))          # 600ft 앞(183m, WEZ 내), 정조준
        self.assertGreater(_wez_damage(shooter, target, 1.0 / 120.0)[0], 0.0)

    def test_no_damage_when_far(self):
        shooter = _kin((0, 0, -15000.0))
        target = _kin((4000.0, 0, -15000.0))          # 1219m > 914m
        self.assertEqual(_wez_damage(shooter, target, 1.0 / 120.0)[0], 0.0)

    def test_no_damage_off_angle(self):
        # 기수 동향(ψ=90°), 적은 북쪽 → body ATA 90 (BEM 종축 기준)
        shooter = _kin((0, 0, -15000.0), vel=(0, 600.0, 0), psi=np.pi / 2)
        target = _kin((600.0, 0, -15000.0))
        self.assertEqual(_wez_damage(shooter, target, 1.0 / 120.0)[0], 0.0)


class TestJudgeAndMatch(unittest.TestCase):
    def test_hard_deck_loss(self):
        blue = ScriptedOpponent(init_pos_ned=(0, 0, -15000.0), color="Blue")
        red = ScriptedOpponent(init_pos_ned=(0, 0, -(HARD_DECK_FT - 100.0)), color="Red")  # 하드덱 아래
        m = Match(blue, red, duration_s=1.0, log_hz=0)
        res = m._judge(0.0)
        self.assertIsNotNone(res)
        self.assertEqual(res.winner, "blue")
        self.assertEqual(res.condition, "hard_deck")

    def test_health_zero_loss(self):
        blue = ScriptedOpponent(init_pos_ned=(0, 0, -15000.0), color="Blue")
        red = ScriptedOpponent(init_pos_ned=(0, 0, -15000.0), color="Red")
        m = Match(blue, red, duration_s=1.0, log_hz=0)
        m.hp["red"].current_health = 0.0
        res = m._judge(0.0)
        self.assertEqual(res.winner, "blue")
        self.assertEqual(res.condition, "health_zero")

    def test_scripted_vs_scripted_runs(self):
        # Blue 가 Red 6시 600ft 뒤, 둘 다 직진 → Blue 가 Red 를 WEZ 로 물고 데미지.
        blue = ScriptedOpponent(init_pos_ned=(0, 0, -15000.0), heading_deg=0.0,
                                maneuver="straight", color="Blue")
        red = ScriptedOpponent(init_pos_ned=(600.0, 0, -15000.0), heading_deg=0.0,
                               maneuver="straight", color="Red")
        res = Match(blue, red, duration_s=2.0, log_hz=0).run()
        self.assertLess(res.hp_red, 100.0)            # Red 피격
        self.assertEqual(res.hp_blue, 100.0)          # Blue 무피해

    def test_ned_to_lonlat_roundtrip_sign(self):
        lon, lat, alt_m = ned_to_lonlat(np.array([6076.0, 0.0, -15000.0]))  # 1NM 북
        self.assertGreater(lat, 37.0)                 # 북 → 위도 증가
        self.assertAlmostEqual(alt_m, 15000.0 * 0.3048, places=1)


class _FaultyOpponent(ScriptedOpponent):
    """참가자 트리 예외를 흉내내는 스텁 — L1 tick 에서 폭발."""
    def tactic_step(self, foe):
        raise ValueError("participant tree error")


class TestCompetitionJudge(unittest.TestCase):
    """대회 판정 계층 (Phase 1.1): 실속 / DISQUALIFY / wall-clock."""

    @staticmethod
    def _apart(**red_kw):
        # 동서 6,000ft 분리·둘 다 직진 북향 → WEZ 데미지 없음(판정만 격리 검증)
        blue = ScriptedOpponent(init_pos_ned=(0, 0, -15000.0), heading_deg=0.0,
                                maneuver="straight", color="Blue")
        red = ScriptedOpponent(init_pos_ned=(0, 6000.0, -15000.0), heading_deg=0.0,
                               maneuver="straight", color="Red", **red_kw)
        return blue, red

    def test_stall_cumulative_10s_loss(self):
        blue, red = self._apart(speed_kts=70.0)       # kcas ≈ 94.5 < 100
        res = Match(blue, red, duration_s=15.0, log_hz=0).run()
        self.assertEqual((res.winner, res.condition), ("blue", "stall"))
        self.assertAlmostEqual(res.time_s, 10.0, delta=0.1)

    def test_bt_exception_disqualifies_owner(self):
        blue, red = self._apart()
        red = _FaultyOpponent(init_pos_ned=(0, 6000.0, -15000.0), heading_deg=0.0,
                              maneuver="straight", color="Red")
        res = Match(blue, red, duration_s=5.0, log_hz=0).run()
        self.assertEqual((res.winner, res.condition), ("blue", "disqualified"))

    def test_wall_clock_guard_draws(self):
        blue, red = self._apart()
        res = Match(blue, red, duration_s=5.0, log_hz=0, wall_limit_s=0.0).run()
        self.assertEqual((res.winner, res.condition), ("draw", "wall_clock"))

    def test_no_contact_timeout_is_double_loss(self):
        # 6,000ft 분리 유지 → 건 사거리(3,000ft) 미진입 → 무접촉 = 쌍방 패
        blue, red = self._apart()
        res = Match(blue, red, duration_s=2.0, log_hz=0).run()
        self.assertEqual((res.winner, res.condition), ("draw", "no_contact"))

    def test_in_range_without_damage_is_also_no_contact(self):
        # 2,000ft 병렬 비행 — 사거리 안이지만 서로 ATA 90° 라 피해 0.
        # 사거리 스침만으로는 교전 성립이 아니다(피해 0 만료 = 쌍방 패, 2026-08-01).
        blue = ScriptedOpponent(init_pos_ned=(0, 0, -15000.0), heading_deg=0.0,
                                maneuver="straight", color="Blue")
        red = ScriptedOpponent(init_pos_ned=(0, 2000.0, -15000.0), heading_deg=0.0,
                               maneuver="straight", color="Red")
        res = Match(blue, red, duration_s=2.0, log_hz=0).run()
        self.assertEqual((res.hp_blue, res.hp_red), (100.0, 100.0))   # 무피해
        self.assertEqual((res.winner, res.condition), ("draw", "no_contact"))


if __name__ == "__main__":
    unittest.main()
