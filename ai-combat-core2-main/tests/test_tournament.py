"""리그·랭킹 회귀 — D8 순위 키, 스왑 미러 집계, 결정론. (JSBSim 매치 실행 포함)"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.engine.tournament import (Standing, run_league, _record, GameResult,
                                         LEAGUE_SCENARIOS)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EX = os.path.join(ROOT, "examples")


class TestRankKey(unittest.TestCase):
    def test_points_then_hpdiff_then_kills_then_order(self):
        # 승점 우선
        hi = Standing("a", 0, wins=2, games=2, hp_diff_total=-50)
        lo = Standing("b", 1, wins=1, draws=1, games=2, hp_diff_total=99)
        self.assertGreater(hi.rank_key(), lo.rank_key())
        # 동점 → 평균 HP 득실차
        x = Standing("x", 0, wins=1, draws=1, games=2, hp_diff_total=20)
        y = Standing("y", 1, wins=1, draws=1, games=2, hp_diff_total=10)
        self.assertGreater(x.rank_key(), y.rank_key())
        # 그다음 격추승, 마지막 등록순서(먼저 등록=상위)
        p = Standing("p", 0, wins=1, draws=1, games=2, hp_diff_total=10, kill_wins=1)
        q = Standing("q", 1, wins=1, draws=1, games=2, hp_diff_total=10, kill_wins=1)
        self.assertGreater(p.rank_key(), q.rank_key())   # order 0 < 1


class TestRecord(unittest.TestCase):
    def test_swap_symmetry_and_killwin(self):
        st = {"A": Standing("A", 0), "B": Standing("B", 1)}
        _record(st, GameResult("headon", "A", "B", "A", "health_zero", 80.0, 0.0))
        self.assertEqual((st["A"].wins, st["A"].kill_wins), (1, 1))
        self.assertEqual((st["B"].losses, st["B"].kill_wins), (1, 0))
        self.assertEqual(st["A"].hp_diff_total, 80.0)
        self.assertEqual(st["B"].hp_diff_total, -80.0)

    def test_timeout_win_not_killwin(self):
        st = {"A": Standing("A", 0), "B": Standing("B", 1)}
        _record(st, GameResult("headon", "A", "B", "B", "timeout", 40.0, 55.0))
        self.assertEqual(st["B"].wins, 1)
        self.assertEqual(st["B"].kill_wins, 0)

    def test_no_contact_is_double_loss_not_draw(self):
        # 도주가 무승부 1점을 벌면 격추패보다 이득이 된다 → 쌍방 0점이어야 한다
        st = {"A": Standing("A", 0), "B": Standing("B", 1)}
        _record(st, GameResult("headon", "A", "B", "draw", "no_contact", 100.0, 100.0))
        for s in st.values():
            self.assertEqual((s.losses, s.draws, s.wins), (1, 0, 0))
            self.assertEqual(s.pts, 0)
            self.assertEqual(s.hp_diff_total, 0.0)


class TestLeagueRun(unittest.TestCase):
    def test_two_agent_league_deterministic(self):
        agents = {"starter": os.path.join(EX, "starter.yaml"),
                  "textbook": os.path.join(EX, "textbook.yaml")}
        # 1 시나리오로 축소 (속도) — 스왑 = 2경기
        r1, g1 = run_league(agents, scenarios=("headon",))
        r2, g2 = run_league(agents, scenarios=("headon",))
        self.assertEqual(len(g1), 2)
        self.assertEqual([s.name for s in r1], [s.name for s in r2])   # 결정론
        # 스왑 미러: 각 팀 2경기
        for s in r1:
            self.assertEqual(s.games, 2)
        # 총 승/무/패 균형 (제로섬)
        self.assertEqual(sum(s.wins for s in r1), sum(s.losses for s in r1))


if __name__ == "__main__":
    unittest.main()
