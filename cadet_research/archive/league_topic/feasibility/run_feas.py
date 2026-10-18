"""Feasibility: does the tactic ranking survive INDI setting changes?

Injects the student INDI knobs (kappa, filter, gyro noise, async delay) into core2's
Pilot after setup, then plays a small round-robin league per condition.

  python cadet_research/feasibility/run_feas.py --procs 20 --out cadet_research/feasibility/out
  python cadet_research/feasibility/run_feas.py --selfcheck
"""
from __future__ import annotations

import argparse
import collections
import csv
import itertools
import os
import sys
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from aircombat.bridge import CompetitionMatch, derive_seed  # noqa: E402
from aircombat.control.indi import SecondOrderLPF  # noqa: E402
from aircombat.engine import pilot as pilot_mod  # noqa: E402

AGENTS = {
    "PurePursuer": "roster/A1_PurePursuer_00.yaml",
    "GunTracker": "roster/A2_GunTracker_00.yaml",
    "LagAngler": "roster/A3_LagAngler_00.yaml",
    "EnergyFighter": "roster/B1_EnergyFighter_00.yaml",
    "Extender": "roster/B2_Extender_00.yaml",
    "RedPrime": "redteams/red_prime.yaml",
}
SCENARIOS = ("headon", "perch_offense", "neutral")

# name -> INDI changes. Applied to BOTH aircraft unless side="blue".
CONDITIONS = {
    "BASE": {},
    "SHAM": {"kappa": 1.000001},
    "FILT10": {"filt_hz": 10.0},
    "NOISE0.3": {"sigma_dps": 0.3},
    "ASYNC2": {"delay": 2},
    "KAPPA8": {"kappa": 8.0},
    "KAPPA25": {"kappa": 25.0},
}

CFG: dict = {}          # active condition in this process
TRACE: list = []        # per-pilot command/response sums, filled during a match
_orig_setup = pilot_mod.Pilot.setup


def _patched_setup(self):
    _orig_setup(self)
    if CFG.get("side", "both") == "blue" and self.color != "Blue":
        return self
    indi = self.indi
    if "kappa" in CFG:                       # G_model / G_true on the pitch row
        indi.G0[1, :] *= CFG["kappa"]
    if "filt_hz" in CFG:
        fs = 1.0 / indi.dt
        for name in ("f_acc", "f_act", "f_rate"):
            setattr(indi, name, SecondOrderLPF(CFG["filt_hz"], fs, 3))
        indi._primed = False
    sigma = np.radians(CFG.get("sigma_dps", 0.0))
    delay = int(CFG.get("delay", 0))
    rng = np.random.default_rng(derive_seed(CFG.get("seed", 0), self.color))
    buf = collections.deque(maxlen=delay + 1)
    stats = {"color": self.color, "n": 0, "sx": 0.0, "sy": 0.0, "sxx": 0.0,
             "syy": 0.0, "sxy": 0.0, "abs_err": 0.0}
    TRACE.append(stats)
    raw_update = indi.update

    def update(omega, omega_sp, qbar, ang_accel=None, **kw):
        omega = np.asarray(omega, float)
        q_true, q_cmd = float(omega[1]), float(omega_sp[1])
        meas = omega + (rng.normal(0.0, sigma, 3) if sigma > 0 else 0.0)
        buf.append((meas, np.asarray(ang_accel, float)))
        meas_d, acc_d = buf[0]               # async: measurement late, u_prev current
        x, y = np.degrees(q_cmd), np.degrees(q_true)
        stats["n"] += 1; stats["sx"] += x; stats["sy"] += y
        stats["sxx"] += x * x; stats["syy"] += y * y; stats["sxy"] += x * y
        stats["abs_err"] += abs(x - y)
        return raw_update(meas_d, omega_sp, qbar, ang_accel=acc_d, **kw)

    indi.update = update
    return self


pilot_mod.Pilot.setup = _patched_setup


def _corr(s):
    n = s["n"]
    if n < 2:
        return float("nan")
    cov = s["sxy"] / n - (s["sx"] / n) * (s["sy"] / n)
    vx = s["sxx"] / n - (s["sx"] / n) ** 2
    vy = s["syy"] / n - (s["sy"] / n) ** 2
    return cov / np.sqrt(vx * vy) if vx > 0 and vy > 0 else float("nan")


def play(job):
    cond, a, b, scen, salt = job
    CFG.clear(); CFG.update(CONDITIONS[cond]); CFG["seed"] = (cond, a, b, scen, salt)
    TRACE.clear()
    seed = derive_seed(scen, salt)
    t0 = time.time()
    r = CompetitionMatch(os.path.join(ROOT, AGENTS[a]), os.path.join(ROOT, AGENTS[b]),
                         a, b, seed=seed, scenario=scen).run()
    blue = next((s for s in TRACE if s["color"] == "Blue"), None)
    return {"cond": cond, "blue": a, "red": b, "scenario": scen, "salt": salt,
            "winner": {"tree1": a, "tree2": b, "draw": "draw"}[r.winner],
            "condition": r.condition, "hp_blue": round(r.tree1_health, 2),
            "hp_red": round(r.tree2_health, 2),
            "blue_corr_q": round(_corr(blue), 4) if blue else "",
            "blue_mae_q_dps": round(blue["abs_err"] / max(blue["n"], 1), 4) if blue else "",
            "wall_s": round(time.time() - t0, 1)}


def jobs(conds, salts):
    for cond in conds:
        for salt in salts:
            for a, b in itertools.combinations(AGENTS, 2):
                for scen in SCENARIOS:
                    yield (cond, a, b, scen, salt)
                    yield (cond, b, a, scen, salt)


def selfcheck():
    j = ("BASE", "PurePursuer", "Extender", "neutral", "s0")
    r1, r2 = play(j), play(j)
    keys = ("winner", "condition", "hp_blue", "hp_red", "blue_corr_q")
    assert all(r1[k] == r2[k] for k in keys), (r1, r2)
    print("deterministic OK:", {k: r1[k] for k in keys}, "wall", r1["wall_s"], "s")
    rk = play(("KAPPA25",) + j[1:])
    print("KAPPA25        :", {k: rk[k] for k in keys})
    assert rk["blue_corr_q"] != r1["blue_corr_q"], "kappa injection had no effect"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--procs", type=int, default=20)
    ap.add_argument("--salts", type=int, default=1)
    ap.add_argument("--conds", default=",".join(CONDITIONS))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "out"))
    args = ap.parse_args()
    if args.selfcheck:
        return selfcheck()
    import multiprocessing as mp
    os.makedirs(args.out, exist_ok=True)
    todo = list(jobs(args.conds.split(","), [f"feas-{i}" for i in range(args.salts)]))
    path = os.path.join(args.out, "games.csv")
    t0 = time.time()
    with mp.Pool(args.procs) as pool, open(path, "w", newline="") as f:
        w = None
        for i, row in enumerate(pool.imap_unordered(play, todo, chunksize=1), 1):
            if w is None:
                w = csv.DictWriter(f, fieldnames=list(row)); w.writeheader()
            w.writerow(row); f.flush()
            if i % 50 == 0:
                print(f"{i}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    print("wrote", path, len(todo), "games", f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
