"""Summarise games.csv: fidelity, standings, ranking agreement vs BASE.

  python cadet_research/feasibility/analyze.py cadet_research/feasibility/out/games.csv
"""
import csv
import collections
import itertools
import sys

import numpy as np
from scipy.stats import kendalltau

rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
by = collections.defaultdict(list)
for r in rows:
    by[r["cond"]].append(r)
conds = [c for c in ("BASE", "SHAM", "FILT10", "NOISE0.3", "ASYNC2", "KAPPA8", "KAPPA25") if c in by]


def standings(games):
    pts, wdl = collections.Counter(), collections.defaultdict(lambda: [0, 0, 0])
    for g in games:
        a, b = g["blue"], g["red"]
        if g["condition"] == "no_contact":
            wdl[a][2] += 1; wdl[b][2] += 1
        elif g["winner"] == "draw":
            pts[a] += 1; pts[b] += 1; wdl[a][1] += 1; wdl[b][1] += 1
        else:
            lo = b if g["winner"] == a else a
            pts[g["winner"]] += 3; wdl[g["winner"]][0] += 1; wdl[lo][2] += 1
    return pts, wdl


def key(g):
    return (g["blue"], g["red"], g["scenario"], g["salt"])


base = {key(g): g for g in by["BASE"]}
agents = sorted({g["blue"] for g in rows})
base_pts, _ = standings(by["BASE"])
print("cond      games  W/D/L(all agents)  corr_q  mae_q[dps]  same_winner  tau_vs_BASE  ranking")
for c in conds:
    gs = by[c]
    pts, wdl = standings(gs)
    tot = np.sum([wdl[a] for a in agents], axis=0) // 1
    corr = np.nanmean([float(g["blue_corr_q"]) for g in gs if g["blue_corr_q"] not in ("", "nan")])
    mae = np.mean([float(g["blue_mae_q_dps"]) for g in gs])
    same = np.mean([g["winner"] == base[key(g)]["winner"] and g["condition"] == base[key(g)]["condition"]
                    for g in gs])
    tau = kendalltau([base_pts[a] for a in agents], [pts[a] for a in agents]).statistic
    rank = sorted(agents, key=lambda a: -pts[a])
    print(f"{c:9s} {len(gs):5d}  {tot[0]:4d}/{tot[1]:3d}/{tot[2]:4d}       {corr:.3f}   {mae:6.2f}      "
          f"{same:.3f}       {tau:+.2f}     " + " > ".join(f"{a}({pts[a]})" for a in rank))

# per-salt ranking stability: tau of each salt's ranking vs BASE same salt (spread = noise)
print("\nper-salt tau vs BASE (same salt)")
salts = sorted({g["salt"] for g in rows})
for c in conds:
    taus = []
    for s in salts:
        p0, _ = standings([g for g in by["BASE"] if g["salt"] == s])
        p1, _ = standings([g for g in by[c] if g["salt"] == s])
        taus.append(kendalltau([p0[a] for a in agents], [p1[a] for a in agents]).statistic)
    print(f"{c:9s} " + " ".join(f"{t:+.2f}" for t in taus) + f"   mean {np.nanmean(taus):+.2f}")

# head-to-head pair outcome flips vs BASE, by pair (where does the ranking move?)
print("\npair net points (row agent vs column agent, summed over scenarios/salts/sides)")
for c in ("BASE", "KAPPA25"):
    if c not in by:
        continue
    net = collections.Counter()
    for g in by[c]:
        if g["condition"] == "no_contact" or g["winner"] == "draw":
            continue
        lo = g["red"] if g["winner"] == g["blue"] else g["blue"]
        net[(g["winner"], lo)] += 1
    print(c)
    for a, b in itertools.combinations(agents, 2):
        print(f"  {a:13s} vs {b:13s} {net[(a, b)]:2d}-{net[(b, a)]:2d}")
