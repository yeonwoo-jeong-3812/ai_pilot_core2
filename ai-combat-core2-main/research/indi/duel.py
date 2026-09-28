"""E3 + E5 — 기준(A) vs 튜닝(B) Dogfight 대응 비교, 강건성 조건별 (paper.md §7-B).

blue 트리 고정, blue 의 INDIConfig 만 A/B, red 대항군 5종은 전부 기준 INDI.
같은 (red, 시나리오, 시드, 조건) 에서 A·B 를 각각 치러 대응 차이를 본다.

조건 (논문 2·5, §8-C 실기값):
  nominal   gyro 0.1°/s                 stress    gyro 0.3°/s
  delay30   측정 지연 4틱(33 ms)         delay90   11틱(92 ms)
  g0_lo     G0 × 0.7                     g0_hi     G0 × 1.3
  turb      MIL-SPEC 난류 severity 4     mc        경기마다 G0 × U(0.7,1.3), 난류 0–4 (시드 결정론)

    python research/indi/duel.py --best results/indi/e4.json --gamma 0.3 --out results/indi/e3.json
    python research/indi/duel.py --b k_q=12 filt_hz=6 lam=0.2 --conds nominal delay90 --seeds 1 2
    python research/indi/duel.py --smoke
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import battery, game, pmap, NOMINAL_SIGMA_DPS, REDS, SCENS
from sweep import paired, _points
from aircombat.control.indi import INDIConfig

CONDS = {   # (조건 dict, 자이로 σ, 지연 틱)
    "nominal": ({}, NOMINAL_SIGMA_DPS, 0),
    "stress": ({}, 0.3, 0),
    "delay30": ({}, NOMINAL_SIGMA_DPS, 4),
    "delay90": ({}, NOMINAL_SIGMA_DPS, 11),
    "g0_lo": ({"g0_scale": 0.7}, NOMINAL_SIGMA_DPS, 0),
    "g0_hi": ({"g0_scale": 1.3}, NOMINAL_SIGMA_DPS, 0),
    "turb": ({"turb_severity": 4}, NOMINAL_SIGMA_DPS, 0),
    "mc": (None, NOMINAL_SIGMA_DPS, 0),
}


def _mc_cond(red: str, sc: str, sd: int) -> dict:
    rng = random.Random(f"mc|{red}|{sc}|{sd}")
    return {"g0_scale": rng.uniform(0.7, 1.3), "turb_severity": rng.randint(0, 4)}


def wilson(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return float(c - h), float(c + h)


def _parse_kv(items) -> dict:
    return {k: float(v) for k, v in (s.split("=") for s in items)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--best", help="optimize.py 결과 JSON (B = 해당 γ 최적해)")
    ap.add_argument("--gamma", type=float, default=0.3)
    ap.add_argument("--b", nargs="*", default=[], help="B 설정 직접 지정 key=value (기준 대비 변경분)")
    ap.add_argument("--conds", nargs="+", default=list(CONDS))
    ap.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3, 4])
    ap.add_argument("--reds", nargs="+", default=list(REDS))
    ap.add_argument("--scens", nargs="+", default=list(SCENS))
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    A = dataclasses.asdict(INDIConfig())
    if a.best:
        best = json.load(open(a.best, encoding="utf-8"))["best"]
        B = next(b["cfg"] for b in best if abs(b["gamma"] - a.gamma) < 1e-9)
    else:
        B = dataclasses.asdict(dataclasses.replace(INDIConfig(), **_parse_kv(a.b)))
    if a.smoke:
        a.conds, a.seeds, a.reds, a.scens = ["nominal", "mc"], [1], ["red_prime"], ["headon", "neutral"]
        if not a.best and not a.b:
            B = dataclasses.asdict(dataclasses.replace(INDIConfig(), filt_hz=4.0, lam=0.35))
    bat = battery(tuple(a.seeds), tuple(a.reds), tuple(a.scens))
    print(f"A={A}\nB={B}\n조건 {a.conds} × {len(bat)}경기 × 2 = {len(a.conds) * len(bat) * 2}경기", flush=True)

    jobs = []
    for cname in a.conds:
        cond, sigma, delay = CONDS[cname]
        for cfg in (A, B):
            for r, sc, sd in bat:
                jobs.append((cfg, r, sc, sd, cond if cond is not None else _mc_cond(r, sc, sd), sigma, delay))
    flat = pmap(game, jobs, a.workers)

    out = {}
    n = len(bat)
    for i, cname in enumerate(a.conds):
        ga, gb = flat[2 * i * n:(2 * i + 1) * n], flat[(2 * i + 1) * n:(2 * i + 2) * n]
        s = paired(ga, gb)
        wa, wb = sum(_points(g) for g in ga), sum(_points(g) for g in gb)
        s.update(win_A=wa / n, win_A_ci=wilson(wa, n), win_B=wb / n, win_B_ci=wilson(wb, n),
                 dq_A=int(sum(g["limits_blue"]["disqualified"] for g in ga)),
                 kills_A=int(sum(g["winner"] == "blue" and g["condition"] == "health_zero" for g in ga)),
                 kills_B=int(sum(g["winner"] == "blue" and g["condition"] == "health_zero" for g in gb)))
        out[cname] = dict(summary=s, games_A=ga, games_B=gb)
        print(f"{cname:8} n={n:3d} | 승률 A {s['win_A']:.2f} [{s['win_A_ci'][0]:.2f},{s['win_A_ci'][1]:.2f}]"
              f" B {s['win_B']:.2f} [{s['win_B_ci'][0]:.2f},{s['win_B_ci'][1]:.2f}]"
              f" | Δpts {s['d_points']:+.3f} [{s['d_points_ci'][0]:+.2f},{s['d_points_ci'][1]:+.2f}]"
              f" ΔHP {s['d_hp']:+6.1f} [{s['d_hp_ci'][0]:+.1f},{s['d_hp_ci'][1]:+.1f}]"
              f" | 격추 A {s['kills_A']} B {s['kills_B']} | 한계DQ A {s['dq_A']} B {s['dq']}", flush=True)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(dict(A=A, B=B, battery=bat, conds=out), f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
