"""경기 하나를 다시 돌려 끝나기 전 N초 동안 양쪽 트리가 실행한 action(노드 이름)을 구간으로 찍는다. 읽기 전용.

  python bt/trace_match.py --scenario neutral --opponent A2_GunTracker_00 --seed-salt bt-smoke-0
  python bt/trace_match.py ... --theta bt/thetas/validation.csv --row 1 --last 15

결과는 run_bt.play 와 같은 경기다 (같은 시드·같은 조립). 노드 이름은 Pilot._cmd.name (dwell 히스테리시스 뒤 실제 명령).
"""
from __future__ import annotations

import argparse
import os
import sys

BT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BT)
import make_tree as mt  # noqa: E402
import run_bt  # noqa: E402
from aircombat.engine.factory import load_policy, make_pilot  # noqa: E402
from aircombat.engine.match import Match  # noqa: E402
from aircombat.engine.scenarios import initial_conditions  # noqa: E402


def trace(job: dict, every: int = 6):
    """(결과, 표본 목록). 표본 = (t, 청 노드, 청 고도, 청 KCAS, 적 노드, 적 고도, 적 KCAS), 20 Hz."""
    me, foe = load_policy(job["tree"]), load_policy(os.path.join(run_bt.KIT, run_bt.OPPONENT_SETS[job["opponent_set"]][job["opponent"]]))
    ic = initial_conditions(job["scenario"], seed=job["seed"])
    blue = make_pilot("Blue", ic["blue"], *me, name="EnergyFighterBT")
    red = make_pilot("Red", ic["red"], *foe, name=job["opponent"])
    log, k, step = [], [0], red.step_physics

    def step_w():                      # 적 물리 스텝 뒤 = 한 틱이 끝난 뒤
        step()
        k[0] += 1
        if k[0] % every == 0:
            b, r = blue.state(), red.state()
            log.append((k[0] / 120.0, blue._cmd.name, b.alt_ft, b.kcas, red._cmd.name, r.alt_ft, r.kcas))
    red.step_physics = step_w
    m = Match(blue, red, duration_s=300.0, acmi_path=None, log_hz=0.0,
              acmi_comments=f"scenario={job['scenario']};seed={job['seed']}", overtime_s=0.0)
    return m.run(), log


def segments(log, last_s):
    """끝 last_s 초를 (청 노드, 적 노드)가 같은 구간으로 묶는다."""
    t_end = log[-1][0]
    seg = []
    for x in (x for x in log if x[0] >= t_end - last_s):
        if seg and seg[-1]["b"] == x[1] and seg[-1]["r"] == x[4]:
            seg[-1]["end"] = x
        else:
            seg.append(dict(b=x[1], r=x[4], start=x, end=x))
    return seg


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", required=True, choices=run_bt.SCENARIOS)
    ap.add_argument("--opponent", required=True, choices=list(run_bt.OPPONENTS))
    ap.add_argument("--seed-salt", required=True)
    ap.add_argument("--theta", default=os.path.join(BT, "thetas", "baseline.csv"))
    ap.add_argument("--row", type=int, default=0)
    ap.add_argument("--opponents", default=run_bt.DEFAULT_SET, choices=list(run_bt.OPPONENT_SETS))
    ap.add_argument("--last", type=float, default=10.0, help="끝나기 전 몇 초")
    a = ap.parse_args()
    th = run_bt.read_thetas(a.theta)[a.row]
    seed = run_bt.derive_seed(a.scenario, a.seed_salt)
    r, log = trace(dict(tree=mt.make_tree(th), scenario=a.scenario, opponent=a.opponent, opponent_set=a.opponents, seed=seed))
    print(f"{a.scenario} / {a.opponent} / {a.seed_salt}: {r.winner} {r.condition} t={r.time_s:.2f}s "
          f"HP {r.hp_blue:.1f}/{r.hp_red:.1f}")
    print("| 구간 [s] | 청 노드 | 청 고도 ft (KCAS) | 적 노드 | 적 고도 ft (KCAS) |")
    print("|---|---|---|---|---|")
    for s in segments(log, a.last):
        b0, b1 = s["start"], s["end"]
        print(f"| {b0[0]:.2f}–{b1[0]:.2f} | {s['b']} | {b0[2]:.0f}→{b1[2]:.0f} ({b1[3]:.0f}) "
              f"| {s['r']} | {b0[5]:.0f}→{b1[5]:.0f} ({b1[6]:.0f}) |")


if __name__ == "__main__":
    main()
