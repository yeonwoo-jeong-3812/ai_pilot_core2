"""커스텀 조건·노드 확장(tactics.custom) 검증 — 봉인 게이트·등록·상태 보유·감사."""
import os
import sys
import textwrap
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aircombat.tactics import custom
from aircombat.tactics.context import TacticContext
from aircombat.tactics.dsl import load_agent_yaml

MOD = textwrap.dedent("""
    from aircombat.tactics.custom import custom_condition, custom_node
    from aircombat.tactics.node import Node, Status

    @custom_condition("range_between")
    def range_between(ctx, *, lo=0.0, hi=1e9):
        return lo <= ctx.range_ft <= hi

    @custom_node("tick_counter")
    class TickCounter(Node):
        '''상태 보유 증명용 — arm_after 틱 이후부터 SUCCESS(pure 명령).'''
        def __init__(self, *, arm_after=2):
            self.n = 0
            self.arm_after = int(arm_after)
        def tick(self, ctx):
            self.n += 1
            ctx.trace.append(("tick_counter", self.n))
            if self.n > self.arm_after:
                ctx.set_command("pure", "counter_fire", g_burst=0.8)
                return Status.SUCCESS
            return Status.FAILURE
""")

YAML = textwrap.dedent("""
    agent_name: CustomDemo
    custom_module: my_custom.py
    selector:
      - sequence:
          - condition: {name: range_between, lo: 1000, hi: 2000}
          - custom: {name: tick_counter, arm_after: 2}
      - action: {pursuit: lead, name: fallback}
""")


def ctx(rng=1500.0):
    return TacticContext(ata_deg=10.0, aspect_deg=170.0, range_ft=rng,
                         closure_fps=500.0, kcas=350.0,
                         energy_diff_ft=0.0, alt_gap_ft=0.0)


class TestCustomNodes(unittest.TestCase):
    def setUp(self):
        custom.reset()
        os.environ.pop("AICOMBAT_ALLOW_CUSTOM", None)

    def _write(self, tmp):
        with open(os.path.join(tmp, "my_custom.py"), "w", encoding="utf-8") as f:
            f.write(MOD)
        p = os.path.join(tmp, "agent.yaml")
        with open(p, "w", encoding="utf-8") as f:
            f.write(YAML)
        return p

    def test_seal_switch(self):
        import tempfile
        os.environ["AICOMBAT_ALLOW_CUSTOM"] = "0"    # 봉인 환경 시뮬레이션
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp)
            with self.assertRaises(ValueError):       # 봉인 시 명시 거부
                load_agent_yaml(p)

    def test_roundtrip_state_and_audit(self):
        import tempfile
        os.environ["AICOMBAT_ALLOW_CUSTOM"] = "1"      # 리서치 환경(기본 봉인) 명시 허용
        with tempfile.TemporaryDirectory() as tmp:
            _, root, name, _ = load_agent_yaml(self._write(tmp))
            self.assertEqual(name, "CustomDemo")
            # 틱 1~2: 카운터 미무장 → fallback(lead) / 상태가 인스턴스에 누적
            c1 = ctx(); root.tick(c1)
            self.assertEqual(c1._tactic_name, "fallback")
            c2 = ctx(); root.tick(c2)
            self.assertEqual(c2._tactic_name, "fallback")
            # 틱 3: 무장 → pure 명령 (상태 보유 증명)
            c3 = ctx(); root.tick(c3)
            self.assertEqual(c3._tactic_name, "counter_fire")
            self.assertEqual(c3._pursuit, "pure")
            # 감사: 커스텀 조건이 trace 에 파라미터 병기로 기록
            self.assertTrue(any("range_between" in t[0] for t in c3.trace))
            self.assertIn(("tick_counter", 3), c3.trace)
            # 조건 파라미터 동작: 범위 밖 rng → 커스텀 가지 폴백
            c4 = ctx(rng=5000.0); root.tick(c4)
            self.assertEqual(c4._tactic_name, "fallback")

    def test_unknown_custom_node_rejected(self):
        os.environ["AICOMBAT_ALLOW_CUSTOM"] = "1"
        from aircombat.tactics.dsl import build_node
        with self.assertRaises(KeyError):
            build_node({"custom": {"name": "no_such_node"}})

    def tearDown(self):
        custom.reset()
        os.environ.pop("AICOMBAT_ALLOW_CUSTOM", None)


if __name__ == "__main__":
    unittest.main()
