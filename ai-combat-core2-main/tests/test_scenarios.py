"""시나리오 IC 회귀 — 결정론 시드 / 진영 스왑 / BEM 국면 커버리지. (JSBSim 불필요)"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.engine.scenarios import (SCENARIOS, initial_conditions, swap_sides,
                                        _ALT_RANGE_FT, _SPEED_JITTER_KCAS)


# duel 도입 이전 코드에서 뜬 골든값 — 회귀 감시용 (수정 금지).
GOLDEN_HEADON_7 = {"blue_psi": 9.056068382391224, "red_psi": 182.15292025840137,
                   "blue_kcas": 332.8974514667017, "red_kcas": 344.62755667650345,
                   "alt": 13942.996588998974}


class TestScenarios(unittest.TestCase):
    def test_bem_phase_coverage(self):
        # OBFM/DBFM/HABFM + 중립 머지를 전부 가진다 (부분-교리 트리 배제)
        for name in ("headon", "perch_offense", "perch_defense", "neutral"):
            self.assertIn(name, SCENARIOS)

    def test_league_set_is_playable(self):
        # 리그/서버 배터리 세트의 전 시나리오가 유효 IC 를 낸다 (neutral 포함)
        from aircombat.engine.tournament import LEAGUE_SCENARIOS
        for name in LEAGUE_SCENARIOS:
            ic = initial_conditions(name, seed=1)
            self.assertEqual(set(ic), {"blue", "red"})
            self.assertNotEqual(ic["blue"]["pos"], ic["red"]["pos"])

    def test_neutral_is_role_symmetric(self):
        # 중립 머지 — 양측 기하가 대칭이라 스왑 미러 없이 1경기로 공정
        ic = initial_conditions("neutral")
        self.assertEqual(ic["blue"]["kcas"], ic["red"]["kcas"])
        self.assertEqual(ic["blue"]["alt"], ic["red"]["alt"])
        self.assertEqual(ic["blue"]["pos"][1], -ic["red"]["pos"][1])

    def test_seed_deterministic(self):
        a = initial_conditions("headon", seed=42)
        b = initial_conditions("headon", seed=42)
        c = initial_conditions("headon", seed=43)
        self.assertEqual(a, b)          # 같은 시드 = 같은 IC
        self.assertNotEqual(a, c)       # 다른 시드 = 다른 IC

    def test_no_seed_is_baseline(self):
        ic = initial_conditions("headon")
        self.assertEqual(ic["blue"]["alt"], 15000.0)
        self.assertEqual(ic["blue"]["kcas"], 350.0)
        self.assertEqual(ic["red"]["psi"], 180.0)

    def test_jitter_within_published_bounds(self):
        # 지터 분포는 룰북 공지 범위 안 — 시드 다수로 확인
        base = initial_conditions("headon")
        for seed in range(30):
            ic = initial_conditions("headon", seed=seed)
            for side in ("blue", "red"):
                s = ic[side]
                self.assertTrue(_ALT_RANGE_FT[0] <= s["alt"] <= _ALT_RANGE_FT[1])
                self.assertLessEqual(abs(s["kcas"] - base[side]["kcas"]),
                                     _SPEED_JITTER_KCAS)
                self.assertAlmostEqual(-s["pos"][2], s["alt"])   # D = -alt 일관

    def test_jitter_preserves_designed_speed_advantage(self):
        # 회귀: 지터가 절대 재추첨이면 perch 의 +100kt 공격자 우위가 지워진다
        # (실제로 지워져 공격자가 WEZ 접근 실패 → 무접촉 타임아웃이 났다)
        nominal = 100.0     # perch_offense 기본 IC 의 blue−red 속도차
        for seed in range(30):
            ic = initial_conditions("perch_offense", seed=seed)
            dv = ic["blue"]["kcas"] - ic["red"]["kcas"]
            self.assertGreater(dv, 0.0, f"seed={seed}: 공격자가 더 느리다 (dV={dv:+.0f})")
            self.assertLessEqual(abs(dv - nominal), 2 * _SPEED_JITTER_KCAS)

    def test_swap_is_involution(self):
        ic = initial_conditions("perch_offense", seed=7)
        self.assertEqual(swap_sides(swap_sides(ic)), ic)
        self.assertEqual(swap_sides(ic)["blue"], ic["red"])

    def test_perch_defense_is_swapped_offense(self):
        off = initial_conditions("perch_offense")
        dfn = initial_conditions("perch_defense")
        self.assertEqual(dfn, swap_sides(off))

    def test_duel_is_mirror_symmetric(self):
        # duel — 시드가 붙어도 방위·속도가 양측 동일 → 180° 회전 대칭 (조준 우위 0).
        # 스왑 없는 단판(현장 결선)에서 진영이 승부를 가르지 않게 하는 것이 목적이다.
        for seed in range(50):
            ic = initial_conditions("duel", seed=seed)
            db = (ic["blue"]["psi"] - 0.0 + 180.0) % 360.0 - 180.0
            dr = (ic["red"]["psi"] - 180.0 + 180.0) % 360.0 - 180.0
            self.assertAlmostEqual(db, dr, places=9, msg=f"seed={seed} 방위 비대칭")
            self.assertEqual(ic["blue"]["kcas"], ic["red"]["kcas"])
            self.assertEqual(ic["blue"]["alt"], ic["red"]["alt"])
            self.assertEqual(ic["blue"]["pos"][0], 0.0)   # blue 는 원점, red 는 정북

    def test_duel_does_not_disturb_existing_seeds(self):
        # duel 추가로 기존 시나리오의 난수 추첨 순서가 밀리면 리더보드가 재현되지 않는다.
        # 골든값은 duel 도입 **이전** 코드에서 뜬 것 (seed=7).
        ic = initial_conditions("headon", seed=7)
        self.assertAlmostEqual(ic["blue"]["psi"], GOLDEN_HEADON_7["blue_psi"], places=9)
        self.assertAlmostEqual(ic["red"]["psi"], GOLDEN_HEADON_7["red_psi"], places=9)
        self.assertAlmostEqual(ic["blue"]["kcas"], GOLDEN_HEADON_7["blue_kcas"], places=9)
        self.assertAlmostEqual(ic["red"]["kcas"], GOLDEN_HEADON_7["red_kcas"], places=9)
        self.assertAlmostEqual(ic["blue"]["alt"], GOLDEN_HEADON_7["alt"], places=9)

    def test_unknown_scenario_rejected(self):
        with self.assertRaises(ValueError):
            initial_conditions("nope")


if __name__ == "__main__":
    unittest.main()
