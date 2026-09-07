"""L1 전술 BT 회귀 — 조건별 전술 선택 / dwell / DSL / Commit·Cooldown / 감사 trace."""
import dataclasses
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.tactics.context import TacticContext
from aircombat.tactics.policy import TacticPolicy
from aircombat.tactics.dsl import build_default, build_from_yaml, build_node
from aircombat.tactics import dsl
from aircombat.tactics.node import Status
from aircombat.tactics import conditions as cond

EXAMPLES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples"))


def ctx(ata=40.0, aspect=40.0, rng=4000.0, closure=50.0, kcas=350.0,
        e_diff=0.0, alt_gap=0.0, hca=0.0, t=0.0, alt=15000.0,
        my_turn=0, foe_turn=0, vs=0.0):
    return TacticContext(ata_deg=ata, aspect_deg=aspect, range_ft=rng,
                         closure_fps=closure, kcas=kcas, energy_diff_ft=e_diff,
                         alt_gap_ft=alt_gap, alt_ft=alt, hca_deg=hca, t_s=t,
                         my_turn_dir=my_turn, foe_turn_dir=foe_turn, vs_fps=vs)


def _decide(c):
    """dwell 무시하고 트리 1회 평가 결과."""
    build_default().tick(c)
    return c._tactic_name


class TestTacticSelection(unittest.TestCase):
    def test_defense_break(self):
        self.assertEqual(_decide(ctx(aspect=170.0)), "break_defense")

    def test_overshoot_lag(self):
        self.assertEqual(_decide(ctx(aspect=30.0, closure=200.0, rng=1500.0)),
                         "lag_reposition")

    def test_extending_rundown(self):
        self.assertEqual(_decide(ctx(aspect=30.0, closure=-40.0, rng=8000.0)),
                         "lead_rundown")

    def test_gun_track(self):
        self.assertEqual(_decide(ctx(aspect=20.0, closure=30.0, rng=2000.0, ata=10.0)),
                         "gun_track")

    def test_lead_pull_nose_far(self):
        self.assertEqual(_decide(ctx(aspect=30.0, closure=20.0, rng=5000.0, ata=90.0)),
                         "lead_pull")

    def test_default_pure(self):
        self.assertEqual(_decide(ctx(aspect=30.0, closure=20.0, rng=4000.0, ata=40.0)),
                         "pure_default")

    def test_priority_defense_over_gun(self):
        # 위협(aspect>120) + 건사거리 동시 → 방어가 우선.
        self.assertEqual(_decide(ctx(aspect=160.0, rng=2000.0, ata=10.0)),
                         "break_defense")


class TestDwell(unittest.TestCase):
    def test_dwell_holds_previous(self):
        pol = TacticPolicy(dwell_s=0.3, dt=0.05)   # 6 tick 유지
        self.assertEqual(pol.tick(ctx(aspect=20.0, rng=2000.0, ata=10.0)).name, "gun_track")
        # 즉시 위협으로 바뀌어도 dwell 동안은 유지
        for _ in range(5):
            cmd = pol.tick(ctx(aspect=170.0))
            self.assertEqual(cmd.name, "gun_track")
        # 6번째 tick 에서 dwell 경과 → 전환
        self.assertEqual(pol.tick(ctx(aspect=170.0)).name, "break_defense")


class TestDSL(unittest.TestCase):
    def test_audit_trace_records_conditions(self):
        c = ctx(aspect=170.0)
        build_default().tick(c)
        self.assertIn(("foe_threat", True), c.trace)

    def test_yaml_matches_default(self):
        path = os.path.join(os.path.dirname(__file__), "..", "config", "tactics.yaml")
        c1 = ctx(aspect=20.0, closure=200.0, rng=1500.0)
        c2 = ctx(aspect=20.0, closure=200.0, rng=1500.0)
        build_from_yaml(path).tick(c1)
        build_default().tick(c2)
        self.assertEqual(c1._tactic_name, c2._tactic_name)   # yaml==default (or yaml 없으면 폴백)


class TestNewConditions(unittest.TestCase):
    def test_vertical_split(self):
        self.assertTrue(cond.foe_above(ctx(alt_gap=800.0)))     # 양수 = 적이 위
        self.assertFalse(cond.foe_above(ctx(alt_gap=200.0)))
        self.assertTrue(cond.foe_below(ctx(alt_gap=-800.0)))
        self.assertFalse(cond.foe_below(ctx(alt_gap=-200.0)))

    def test_phase_predicates(self):
        self.assertTrue(cond.behind_foe(ctx(aspect=30.0)))
        self.assertFalse(cond.behind_foe(ctx(aspect=90.0)))
        self.assertTrue(cond.merged(ctx(rng=1000.0)))
        self.assertTrue(cond.closing(ctx(closure=150.0)))
        self.assertFalse(cond.closing(ctx(closure=50.0)))
        # 1/2-circle flow (BEM 4.4.4): 반대 회전방향 = 1-circle, 같은 방향 = 2-circle
        self.assertTrue(cond.one_circle(ctx(my_turn=1, foe_turn=-1)))
        self.assertFalse(cond.one_circle(ctx(my_turn=1, foe_turn=1)))   # 2-circle
        self.assertFalse(cond.one_circle(ctx(my_turn=1, foe_turn=0)))   # 상대 직선
        self.assertFalse(cond.one_circle(ctx()))                        # 둘 다 직선
        self.assertTrue(cond.two_circle(ctx(my_turn=-1, foe_turn=-1)))
        self.assertFalse(cond.two_circle(ctx(my_turn=1, foe_turn=-1)))  # 1-circle
        self.assertFalse(cond.two_circle(ctx(my_turn=0, foe_turn=1)))   # 내가 직선
        self.assertFalse(cond.two_circle(ctx()))                        # 둘 다 직선

    def test_fighting_band_defaults_from_doctrine(self):
        self.assertTrue(cond.below_fighting_speed(ctx(kcas=300.0)))   # <325
        self.assertFalse(cond.below_fighting_speed(ctx(kcas=350.0)))
        self.assertTrue(cond.above_fighting_speed(ctx(kcas=400.0)))   # >375
        self.assertFalse(cond.above_fighting_speed(ctx(kcas=350.0)))
        # 명시 kcas 는 교리 연동보다 우선(기존 제출물 호환)
        self.assertFalse(cond.below_fighting_speed(ctx(kcas=300.0), kcas=282.0))

    def test_fighting_band_follows_ctx_doctrine(self):
        # doctrine 오버라이드가 ctx 로 주입되면 기본 임계가 함께 이동
        c = ctx(kcas=330.0)
        c = dataclasses.replace(c, fighting_kts_lo=340.0, fighting_kts_hi=390.0)
        self.assertTrue(cond.below_fighting_speed(c))    # 330 < 340
        c2 = dataclasses.replace(ctx(kcas=380.0), fighting_kts_hi=390.0)
        self.assertFalse(cond.above_fighting_speed(c2))  # 380 < 390

    def test_extended_observation_conditions(self):
        # low_health / vel_nose_far / foe_path_threat — 경계 참/거짓 쌍
        low = dataclasses.replace(ctx(), my_health=30.0)
        high = dataclasses.replace(ctx(), my_health=60.0)
        self.assertTrue(cond.low_health(low))                    # 30 < 40
        self.assertFalse(cond.low_health(high))
        self.assertTrue(cond.low_health(high, hp=70.0))          # 임계 오버라이드
        drift = dataclasses.replace(ctx(), vel_ata_deg=80.0)
        aligned = dataclasses.replace(ctx(), vel_ata_deg=20.0)
        self.assertTrue(cond.vel_nose_far(drift))                # 80 > 60
        self.assertFalse(cond.vel_nose_far(aligned))
        inbound = dataclasses.replace(ctx(), vel_aa_deg=160.0)
        outbound = dataclasses.replace(ctx(), vel_aa_deg=40.0)
        self.assertTrue(cond.foe_path_threat(inbound))           # 160 > 120
        self.assertFalse(cond.foe_path_threat(outbound))

    def test_low_altitude(self):
        self.assertTrue(cond.low_altitude(ctx(alt=2000.0)))           # 하드덱 근접
        self.assertFalse(cond.low_altitude(ctx(alt=15000.0)))
        self.assertTrue(cond.low_altitude(ctx(alt=4000.0), floor_ft=4500.0))
        # lookahead 기본 0 → 강하 중이어도 현재 고도만 본다(기존 동작 보존)
        self.assertFalse(cond.low_altitude(ctx(alt=7000.0, vs=-730.0), floor_ft=4500.0))
        # 730fps 강하: 3.5초 뒤 예상 4,445ft → 7,000ft 에서 미리 발동
        self.assertTrue(cond.low_altitude(ctx(alt=7000.0, vs=-730.0),
                                          floor_ft=4500.0, lookahead_s=3.5))
        # 같은 고도라도 수평비행이면 발동 안 함
        self.assertFalse(cond.low_altitude(ctx(alt=7000.0, vs=0.0),
                                           floor_ft=4500.0, lookahead_s=3.5))


class TestDSLValidation(unittest.TestCase):
    def test_condition_param_override(self):
        node = build_node({"condition": {"name": "overshoot_risk",
                                         "closure_fps": 120, "range_ft": 2500}})
        c = ctx(closure=130.0, rng=2300.0)
        self.assertIs(node.tick(c), Status.SUCCESS)     # 완화된 임계값으로 참
        c2 = ctx(closure=130.0, rng=2300.0)
        self.assertIs(build_node({"condition": "overshoot_risk"}).tick(c2),
                      Status.FAILURE)                   # 기본 임계값(150/2000)으론 거짓

    def test_condition_unknown_param_raises(self):
        with self.assertRaises(ValueError):
            build_node({"condition": {"name": "overshoot_risk", "closure_fpss": 120}})

    def test_action_unknown_key_raises(self):
        with self.assertRaises(ValueError):
            build_node({"action": {"pursuit": "lag", "aim_abov_ft": 750}})   # 오타

    def test_action_bad_pursuit_raises(self):
        with self.assertRaises(ValueError):
            build_node({"action": {"pursuit": "chase"}})

    def test_example_attacker_yoyo(self):
        # attacker 는 2026-08-01 redteams/red_attacker.yaml 로 이동(예선 상대 비공개화)
        root = build_from_yaml(os.path.join(EXAMPLES_DIR, "..", "redteams", "red_attacker.yaml"))
        # 요요 국면1 게이트: 후방 반구(behind_foe<90) + 추적 중 추월(160fps/2200ft)
        c = ctx(aspect=30.0, closure=200.0, rng=2000.0)
        root.tick(c)
        self.assertEqual(c._tactic_name, "yoyo_up")     # 요요 가지가 발동
        self.assertEqual(c._aim_above_ft, 750.0)
        # 헤드온 머지(고aspect)에선 요요 오발동 없음 — 사격 창 보존
        c2 = ctx(aspect=170.0, closure=1000.0, rng=2000.0)
        root.tick(c2)
        self.assertNotIn(c2._tactic_name, ("yoyo_up", "yoyo_down"))


class TestCommit(unittest.TestCase):
    SPEC = {"commit": {"name": "yoyo", "duration_s": 4.0, "cooldown_s": 3.0,
                       "child": {"sequence": [
                           {"condition": {"name": "closing", "min_fps": 100}},
                           {"action": {"pursuit": "lag", "name": "yoyo_up",
                                       "aim_above_ft": 750}}]}}}

    def test_latch_and_replay(self):
        node = build_node(self.SPEC)
        c = ctx(closure=150.0, t=0.0)
        self.assertIs(node.tick(c), Status.SUCCESS)
        self.assertIn(("commit:yoyo", "latch"), c.trace)
        # 래치 중 조건 이탈 → 직전 명령 리플레이(기동 중단 없음)
        c2 = ctx(closure=0.0, t=1.0)
        self.assertIs(node.tick(c2), Status.SUCCESS)
        self.assertEqual(c2._tactic_name, "yoyo_up")
        self.assertEqual(c2._aim_above_ft, 750.0)
        self.assertIn(("commit:yoyo", "replay"), c2.trace)

    def test_expiry_then_cooldown_then_relatch(self):
        node = build_node(self.SPEC)
        node.tick(ctx(closure=150.0, t=0.0))                      # latch @0
        # 만료(t>=4) → 쿨다운 3s: 조건 참이어도 재진입 차단
        c = ctx(closure=150.0, t=4.5)
        self.assertIs(node.tick(c), Status.FAILURE)
        self.assertIn(("commit:yoyo", "cooldown"), c.trace)
        # 쿨다운 종료(4.0 만료시각 + 이후 tick 시각 기준) → 재래치
        c2 = ctx(closure=150.0, t=8.0)
        self.assertIs(node.tick(c2), Status.SUCCESS)
        self.assertIn(("commit:yoyo", "latch"), c2.trace)

    def test_preemption_by_tree_placement(self):
        # 상위 방어 브랜치가 commit 을 건너뛰고(preempt), 해제되면 잔여 래치로 복귀
        tree = build_node({"selector": [
            {"sequence": [{"condition": "foe_threat"},
                          {"action": {"pursuit": "lag", "g_burst": 0.8, "name": "break"}}]},
            self.SPEC,
            {"action": {"pursuit": "pure", "name": "fallback"}}]})
        c = ctx(closure=150.0, t=0.0)
        tree.tick(c)
        self.assertEqual(c._tactic_name, "yoyo_up")               # latch @0
        c = ctx(aspect=170.0, closure=150.0, t=1.0)
        tree.tick(c)
        self.assertEqual(c._tactic_name, "break")                 # 방어가 선점
        c = ctx(closure=0.0, t=2.0)
        tree.tick(c)
        self.assertEqual(c._tactic_name, "yoyo_up")               # 잔여 래치 복귀(리플레이)
        c = ctx(closure=0.0, t=5.0)                               # t0=0 + 4s 만료
        tree.tick(c)
        self.assertEqual(c._tactic_name, "fallback")              # 쿨다운 → 폴백


class TestCooldown(unittest.TestCase):
    SPEC = {"cooldown": {"wait_s": 5.0, "name": "recover",
                         "child": {"sequence": [
                             {"condition": "below_fighting_speed"},
                             {"action": {"pursuit": "lag", "name": "recover"}}]}}}

    def test_continuous_success_passes_then_blocks_after_end(self):
        node = build_node(self.SPEC)
        self.assertIs(node.tick(ctx(kcas=300.0, t=0.0)), Status.SUCCESS)
        self.assertIs(node.tick(ctx(kcas=300.0, t=1.0)), Status.SUCCESS)  # 활동 지속 통과
        self.assertIs(node.tick(ctx(kcas=360.0, t=2.0)), Status.FAILURE)  # 종료 → 쿨다운 개시
        self.assertIs(node.tick(ctx(kcas=300.0, t=3.0)), Status.FAILURE)  # 재진입 차단
        c = ctx(kcas=300.0, t=3.5)
        node.tick(c)
        self.assertIn(("cooldown:recover", "blocked"), c.trace)
        self.assertIs(node.tick(ctx(kcas=300.0, t=7.5)), Status.SUCCESS)  # 2.0+5.0 경과


class TestPolicyClock(unittest.TestCase):
    def test_clock_injected_and_accumulates(self):
        pol = TacticPolicy(dt=0.05)
        c1 = ctx()
        pol.tick(c1)
        self.assertEqual(c1.t_s, 0.0)
        c2 = ctx()
        pol.tick(c2)
        self.assertAlmostEqual(c2.t_s, 0.05)

    def test_command_carries_geometry_fields(self):
        pol = TacticPolicy(root=build_node(
            {"action": {"pursuit": "lag", "name": "y", "aim_above_ft": 750,
                        "lead_time_s": 1.5, "lag_dist_ft": 2000}}), dwell_s=0.0)
        cmd = pol.tick(ctx())
        self.assertEqual((cmd.aim_above_ft, cmd.lead_time_s, cmd.lag_dist_ft),
                         (750.0, 1.5, 2000.0))

    def test_command_carries_g_regulation_fields(self):
        """2026-08-24 개방 — 조절층 노브가 TacticCommand 까지 흐른다."""
        pol = TacticPolicy(root=build_node(
            {"action": {"pursuit": "lead", "name": "g", "g_burst": 0.6,
                        "g_full_ata_deg": 35, "track_rng_ft": 2800,
                        "track_ata_deg": 25}}), dwell_s=0.0)
        cmd = pol.tick(ctx())
        self.assertEqual((cmd.g_burst, cmd.g_full_ata_deg,
                          cmd.track_rng_ft, cmd.track_ata_deg),
                         (0.6, 35.0, 2800.0, 25.0))


class TestActionBounds(unittest.TestCase):
    """액션 숫자 파라미터 범위 강제 (dsl._ACTION_BOUNDS) + max_g 폐지."""

    def test_max_g_rejected_with_migration_hint(self):
        with self.assertRaises(ValueError) as cm:
            build_node({"action": {"pursuit": "lead", "max_g": True}})
        self.assertIn("g_burst", str(cm.exception))      # 무엇으로 바꿀지 알려준다

    def test_out_of_range_rejected(self):
        for key, bad in (("g_burst", 1.5), ("g_full_ata_deg", 5.0),
                         ("track_rng_ft", 50.0), ("track_ata_deg", 90.0),
                         ("lead_time_s", 30.0), ("aim_above_ft", 99999.0)):
            with self.subTest(key=key):
                with self.assertRaises(ValueError) as cm:
                    build_node({"action": {"pursuit": "lead", key: bad}})
                self.assertIn(key, str(cm.exception))

    def test_bounds_are_inclusive(self):
        for key, (lo, hi) in dsl._ACTION_BOUNDS.items():
            with self.subTest(key=key):
                build_node({"action": {"pursuit": "lead", key: lo}})
                build_node({"action": {"pursuit": "lead", key: hi}})

    def test_all_errors_reported_at_once(self):
        """한 필드씩 고쳐 재제출하는 왕복을 없앤다 (doctrine 과 동일 철학)."""
        with self.assertRaises(ValueError) as cm:
            build_node({"action": {"pursuit": "lead", "g_burst": 2.0,
                                   "track_ata_deg": 99.0}})
        msg = str(cm.exception)
        self.assertIn("g_burst", msg)
        self.assertIn("track_ata_deg", msg)

    def test_bool_rejected_for_numeric_keys(self):
        """YAML 1.1 의 no/off 함정 — g_burst: no 가 0.0 으로 통과하면 안 된다."""
        with self.assertRaises(ValueError):
            build_node({"action": {"pursuit": "lead", "g_burst": False}})


class TestObservationPolicy(unittest.TestCase):
    def test_foe_health_not_observable(self):
        """룰북 정보 정책: 적 HP·적 데미지는 BT 관측(TacticContext)에 노출되지 않는다."""
        fields = {f.name for f in dataclasses.fields(TacticContext)}
        self.assertNotIn("foe_health", fields)
        self.assertFalse({f for f in fields if f.startswith("foe_damage")})


if __name__ == "__main__":
    unittest.main()
