"""서버 계약 어댑터(bridge) 회귀 — V1 계약 필드·derive_seed 값 호환·DQ·결정론."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.bridge import (CompetitionMatch, CompetitionResult, derive_seed,
                              _ranked_healths)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STARTER = os.path.join(ROOT, "examples", "starter.yaml")


class TestDeriveSeed(unittest.TestCase):
    def test_value_compatible_with_v1(self):
        # V1 src/match/seeding.py 알고리즘(SHA-256 앞 4바이트 big-endian) 핀 값.
        # 이 값이 깨지면 기존 매치 재현성이 깨진다 — 절대 변경 금지.
        self.assertEqual(derive_seed("match-123"), 3032468703)
        self.assertEqual(derive_seed("550e8400-e29b-41d4-a716-446655440000"),
                         1695734796)
        self.assertEqual(derive_seed("a", "b"), 2410811126)

    def test_range_and_stability(self):
        s = derive_seed("x")
        self.assertEqual(s, derive_seed("x"))
        self.assertTrue(0 <= s < 2 ** 32)
        self.assertNotEqual(derive_seed("a", "b"), derive_seed("ab"))  # 구분자 효과


class TestRankedHealths(unittest.TestCase):
    def test_forfeit_zeroes_loser(self):
        for cond in ("hard_deck", "stall", "disqualified"):
            self.assertEqual(_ranked_healths("tree1", cond, 90.0, 70.0), (90.0, 0.0))
            self.assertEqual(_ranked_healths("tree2", cond, 90.0, 70.0), (0.0, 70.0))

    def test_timeout_and_draw_keep_actual(self):
        self.assertEqual(_ranked_healths("tree1", "timeout", 90.0, 70.0), (90.0, 70.0))
        self.assertEqual(_ranked_healths("draw", "wall_clock", 90.0, 70.0), (90.0, 70.0))
        self.assertEqual(_ranked_healths("draw", "hard_deck", 50.0, 60.0), (50.0, 60.0))


class TestCompetitionMatch(unittest.TestCase):
    def test_contract_shape_and_determinism(self):
        kw = dict(tree1_file=STARTER, tree2_file=STARTER,
                  tree1_name="t1", tree2_name="t2",
                  seed=derive_seed("match-123"), scenario="headon", duration_s=2.0)
        r1 = CompetitionMatch(**kw).run()
        r2 = CompetitionMatch(**kw).run()
        self.assertIsInstance(r1, CompetitionResult)
        self.assertIn(r1.winner, ("tree1", "tree2", "draw"))
        self.assertIsInstance(r1.total_steps, int)
        self.assertIsInstance(r1.tree1_health, float)
        # 결정론: wall-clock(duration_seconds) 제외 전 필드 일치
        self.assertEqual(
            (r1.winner, r1.condition, r1.total_steps, r1.tree1_health, r1.tree2_health),
            (r2.winner, r2.condition, r2.total_steps, r2.tree1_health, r2.tree2_health))

    def test_missing_file_is_dq_not_error(self):
        r = CompetitionMatch(tree1_file="no/such/agent.yaml",
                             tree2_file=STARTER, duration_s=2.0).run()
        self.assertEqual((r.winner, r.condition), ("tree2", "disqualified"))
        self.assertEqual(r.tree1_health, 0.0)   # D8: 판정패 HP 0
        self.assertEqual(r.total_steps, 0)      # 교전 없음

    def test_invalid_yaml_is_dq(self):
        f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False,
                                        encoding="utf-8")
        f.write("selector:\n  - action: {pursuit: pure, warp_drive: 1}\n")
        f.close()
        try:
            r = CompetitionMatch(tree1_file=STARTER, tree2_file=f.name,
                                 duration_s=2.0).run()
            self.assertEqual((r.winner, r.condition), ("tree1", "disqualified"))
            self.assertEqual(r.tree2_health, 0.0)
        finally:
            os.unlink(f.name)

    def test_v1_max_steps_alias(self):
        # V1 계약: max_steps(20Hz env step) → duration 환산 (1500 = 75s)
        m = CompetitionMatch(tree1_file=STARTER, tree2_file=STARTER,
                             config_name="1v1/NoWeapon/bt_vs_bt", max_steps=1500)
        self.assertEqual(m.duration_s, 75.0)


if __name__ == "__main__":
    unittest.main()
