"""절전 때문에 wall_clock(120 s 안전장치)으로 잘린 경기만 다시 돌려 따로 저장한다. 원자료 games.csv 는 건드리지 않는다.
그 다음 잘린 판을 다시 돈 결과로 바꿔 끼운 자료로 E3 판정과 E4 보조 계산을 다시 해 본다 (민감도 분석)."""
import csv
import multiprocessing as mp
import os
import sys

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # kit/supplementary → kit
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
os.chdir(KIT)
import run  # noqa: E402
from experiments import AGENTS_MAIN, AGENTS_E4, EXPERIMENTS  # noqa: E402

KEY = ("cond", "target", "blue", "red", "scenario", "salt")


def jobs_for(d, agents):
    rows = list(csv.DictReader(open(os.path.join(KIT, "out", d, "games.csv"), encoding="utf-8")))
    bad = [r for r in rows if r["condition"] == "wall_clock"]
    return rows, bad, [dict({k: r[k] for k in KEY}, blue_path=agents[r["blue"]], red_path=agents[r["red"]]) for r in bad]


def main():
    out = {}
    for d, agents in (("main", AGENTS_MAIN), ("gen", AGENTS_E4)):
        rows, bad, jobs = jobs_for(d, agents)
        path = os.path.join(OUT, f"rerun_wallclock_{d}.csv")
        if os.path.isfile(path) and "--replay" not in sys.argv:      # 이미 다시 돈 결과가 있으면 그대로 쓴다
            got = {tuple(r[k] for k in KEY): r for r in csv.DictReader(open(path, encoding="utf-8"))}
            new = [got[tuple(o[k] for k in KEY)] for o in bad]
            print(f"{d}: 저장된 재실행 결과 {len(new)}판을 쓴다 ({os.path.basename(path)}). 다시 돌리려면 --replay")
        else:
            with mp.Pool(14) as pool:
                new = pool.map(run.play, jobs, chunksize=1)
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=run.FIELDS)
                w.writeheader()
                w.writerows(new)
            print(f"{d}: 다시 돈 {len(new)}판 → {os.path.basename(path)}")
        for o, n in zip(bad, new):
            print(f"   {o['cond']} {o['blue']} vs {o['red']} {o['scenario']} {o['salt']}: "
                  f"wall_clock/draw → {n['condition']}/{n['winner']} (wall {n['wall_s']} s)")
        fixed = {tuple(n[k] for k in KEY): n for n in new}
        out[d] = [{k: str(v) for k, v in fixed.get(tuple(r[k] for k in KEY), r).items()} for r in rows]
    return out


def analyse(data):
    import collections
    import predict as P
    tol = {"D": 0.07857142857142854, "M": 5.212499999999999}

    def by_of(rows):
        by = collections.defaultdict(list)
        for r in rows:
            if r["target"] == "":
                by[(r["cond"], r["salt"])].append(r)
        return by
    e2, e3, e4 = EXPERIMENTS["E2"], EXPERIMENTS["E3"], EXPERIMENTS["E4"]
    fitc = [c for c in e2["conds"] if c != "BASE"]
    testc = [c for c in e3["conds"] if c != "BASE"]
    by = by_of(data["main"])
    s = P.seeds_of(by, "main", fitc)
    P.SHAPE = "linear"
    print("\n=== E3 다시 판정 (잘린 판을 바꿔 끼운 자료) ===")
    P.validate(by, fitc, by, testc, "BASE", s, s, list(e2["agents"]), tol, "E2 로 적합, E3 로 검증 (보정)")
    by4 = by_of(data["gen"])
    tc4 = [c for c in e4["conds"] if c != "BASE"]
    s4 = P.seeds_of(by4, "gen", tc4)
    tf = P.Table(by, fitc, "BASE", s, list(e2["agents"]))
    tt = P.Table(by4, tc4, "BASE", s4, list(e4["agents"]))
    curve, vt = P.fit(tf.pick(s), fitc), tt.pick(s4)
    rng = np.random.default_rng(0)
    deg = [c for c in tc4 if c != "SHAM"]
    bD = []
    for _ in range(P.N_BOOT):
        cb = P.fit(tf.pick(list(rng.choice(s, len(s)))), fitc)
        vb = tt.pick(list(rng.choice(s4, len(s4))))
        bD.append(np.mean([vb[c][1] - P.pred(cb, "D", vb[c][0]) for c in deg]))
    print("\n=== E4 (보정) ===")
    for c in tc4:
        print(f"{c}: mae {vt[c][0]:.2f}, D {vt[c][1]:.3f}, 예측 {P.pred(curve, 'D', vt[c][0]):.3f}, "
              f"오차 {vt[c][1] - P.pred(curve, 'D', vt[c][0]):+.3f}")
    lo, hi = np.percentile(bD, [2.5, 97.5])
    print(f"열화 5조건 평균 {np.mean(bD):+.3f} [{lo:+.3f}, {hi:+.3f}] → {P.judge(lo, hi, tol['D'])}")


if __name__ == "__main__":
    analyse(main())
