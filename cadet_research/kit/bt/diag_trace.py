"""하드덱 진단: bt-pilot 하드덱 경기를 같은 시드로 다시 돌려 끝 15초를 추적한다. 읽기 전용 (엔진·상대·원 CSV 안 고침).

  python bt/diag_trace.py            # → bt/out/diag/trace_summary.json, bt/out/diag/traces/*.csv
  python bt/diag_trace.py --f4000    # 반사실 수정 상대(floor 4000) 하드덱 8경기 → bt/out/diag/trace_f4000.json

표본 20 Hz (적 물리 스텝 뒤). 홍 G = −accelerations/n-pilot-z-norm, 리미터 한계 = Pilot.last_flags["g_max"].
분류: (a) 홍 climb(= low_altitude 노드) 작동 후 하드덱, (b) 끝 15초 동안 climb 미작동, (c) 그 밖 (청 하드덱 등).
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
from multiprocessing import Pool

BT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BT)
import make_tree as mt  # noqa: E402
import run_bt  # noqa: E402
from aircombat.engine.factory import load_policy, make_pilot  # noqa: E402
from aircombat.engine.match import Match  # noqa: E402
from aircombat.engine.scenarios import initial_conditions  # noqa: E402

OUT = os.path.join(BT, "out", "diag")
N_GAMES, SEED, LAST_S, G = 20, 20261102, 15.0, 32.174
COLS = ("t", "red_alt", "red_hdot", "red_gamma", "red_kcas", "red_vfps", "red_nz", "red_gmax", "red_node",
        "blue_alt", "blue_node", "red_bank")


def sample(p):
    s = p.state()
    flags = getattr(p, "last_flags", None) or {}
    return (s.alt_ft, -float(s.vel_ned[2]), math.degrees(math.asin(max(-1.0, min(1.0, -s.vel_ned[2] / max(s.v_fps, 1.0))))),
            s.kcas, s.v_fps, -float(p.plant["accelerations/n-pilot-z-norm"]), flags.get("g_max", float("nan")),
            getattr(p._cmd, "name", None) or "none")


def run(row: dict):
    th = mt.normalize({k: row[k] for k in mt.NAMES + ["dummy"]})
    seed = run_bt.derive_seed(row["scenario"], row["seed_salt"])
    me, foe = load_policy(mt.make_tree(th)), load_policy(os.path.join(run_bt.KIT, run_bt.OPPONENT_SETS[row["opponent_set"]][row["opponent"]] if row.get("opponent_set")
                                       else run_bt.OPP_PATHS[row["opponent"]]))
    ic = initial_conditions(row["scenario"], seed=seed)
    blue = make_pilot("Blue", ic["blue"], *me, name="EnergyFighterBT")
    red = make_pilot("Red", ic["red"], *foe, name=row["opponent"])
    log, k, step = [], [0], red.step_physics

    def step_w():
        step()
        k[0] += 1
        if k[0] % 6 == 0:
            r, b = sample(red), sample(blue)
            log.append((k[0] / 120.0, *r, b[0], b[7], math.degrees(red.state().phi)))
    red.step_physics = step_w
    m = Match(blue, red, duration_s=300.0, acmi_path=None, log_hz=0.0,
              acmi_comments=f"scenario={row['scenario']};seed={seed}", overtime_s=0.0)
    r = m.run()
    same = (r.winner == row["winner"] and r.condition == row["end_reason"]
            and round(r.time_s, 4) == float(row["sim_time_s"]))   # CSV 는 소수 4자리 (run_bt._r)
    return dict(row={k: row[k] for k in ("theta_id", "scenario", "opponent", "seed_salt", "winner", "end_reason",
                                         "sim_time_s", "floor_ft")},
                reproduced=same, log=[x for x in log if x[0] >= log[-1][0] - LAST_S])


def classify(g: dict) -> dict:
    log, row = g["log"], g["row"]
    hit = {"blue": "red", "red": "blue"}.get(row["winner"], "both")
    out = dict(hit=hit, n_climb=sum(x[8] == "climb" for x in log))
    if hit != "red":
        return {**out, "cls": "c"}
    if not out["n_climb"]:
        below = [x for x in log if x[1] < 1200.0]
        return {**out, "cls": "b", "nodes_below_1200": sorted({x[8] for x in below})}
    i = max(j for j, x in enumerate(log) if x[8] != "climb") + 1 if any(x[8] != "climb" for x in log) else 0
    a = log[i]                                        # 마지막 연속 climb 구간의 시작 = 작동 시점
    v, gam, gmax = a[5], a[3], a[7]
    nz_max = max(x[6] for x in log[i:])
    def loss(n):
        return float("nan") if n <= 1 else v ** 2 / (G * (n - 1)) * (1 - math.cos(math.radians(min(gam, 0.0))))
    return {**out, "cls": "a", "t_act": a[0], "t_end": log[-1][0], "alt_act": a[1], "gamma_act": gam,
            "kcas_act": a[4], "v_act": v, "gmax_act": gmax, "nz_max_after": nz_max,
            "loss_gmax": loss(gmax), "loss_nzmax": loss(nz_max), "margin": a[1] - 1000.0,
            "blue_alt_act": a[9], "blue_node_act": a[10]}


def f4000():
    """수정 상대도 하드덱을 뚫는 이유: climb 중 뱅크·G·강하각."""
    with open(os.path.join(BT, "out", "bt-diag", "games_diag1.csv"), encoding="utf-8", newline="") as f:
        hd = [r for r in csv.DictReader(f) if r["opponent"].endswith("_f4000")
              and r["end_reason"] == "hard_deck" and r["winner"] == "blue"]
    with Pool(4) as pool:
        games = pool.map(run, random.Random(1).sample(hd, min(8, len(hd))))
    out = []
    for g in games:
        c = classify(g)
        climb = [x for x in g["log"] if x[8] == "climb"]
        out.append({**g["row"], "n_hd_f4000": len(hd), "reproduced": g["reproduced"], **c,
                    "bank_act": climb[-len(climb)][11] if climb else None,
                    "bank_mean_climb": sum(abs(x[11]) for x in climb) / len(climb) if climb else None,
                    "gamma_min_climb": min(x[3] for x in climb) if climb else None,
                    "nz_mean_climb": sum(x[6] for x in climb) / len(climb) if climb else None})
        print(json.dumps(out[-1], ensure_ascii=False, default=str))
    with open(os.path.join(OUT, "trace_f4000.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


def main():
    if "--f4000" in sys.argv:
        return f4000()
    with open(os.path.join(BT, "out", "bt-pilot", "games_original.csv"), encoding="utf-8", newline="") as f:
        hd = [r for r in csv.DictReader(f) if r["end_reason"] == "hard_deck"]
    pick = random.Random(SEED).sample(hd, N_GAMES)
    with Pool(2) as pool:
        games = pool.map(run, pick)
    os.makedirs(os.path.join(OUT, "traces"), exist_ok=True)
    summary = []
    for i, g in enumerate(games):
        with open(os.path.join(OUT, "traces", f"{i:02d}.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(COLS)
            w.writerows(g["log"])
        summary.append({"i": i, **g["row"], "reproduced": g["reproduced"], **classify(g)})
        print(json.dumps(summary[-1], ensure_ascii=False, default=str))
    with open(os.path.join(OUT, "trace_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
