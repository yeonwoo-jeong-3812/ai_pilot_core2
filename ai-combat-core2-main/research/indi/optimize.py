"""E4 — PSO 복합 최적화 + 파레토 (paper.md §7-B, 논문 4 방식).

6변수 동시 탐색, 비용 = J/J₀ + γ·A/A₀ (+10 if 한계 실격)
  J : E1 추종 정규화 ISE,  A : 조종면 활동량(평균 |Δu| 에일러론+승강타) — 교범 "신속함과 부드러움"
  (논문 4 의 g_x 는 구조하중. 본 연구의 봉투 위반은 f16fix 에서 기준도 0 이라 파레토를 못 만들어
   활동량으로 대체하고, 위반은 실격 벌점으로 둔다.)
γ 마다 PSO 1회 → 최적해, 그리고 전 평가점의 (J/J₀, A/A₀) 비지배 전선 = 파레토.
filt_hz 는 로그 공간에서 탐색(3–40 Hz).

    python research/indi/optimize.py --smoke                     # 4입자 × 2세대, γ=0.3
    python research/indi/optimize.py --out results/indi/e4.json  # γ∈{0,0.1,0.3,1} × 20입자 × 30세대
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import pmap
from bench import evaluate
from aircombat.control.indi import INDIConfig

# (이름, 하한, 상한, 로그) — paper.md §7-C
BOX = [("k_p", 4.0, 20.0, False), ("k_q", 4.0, 20.0, False), ("filt_hz", 3.0, 40.0, True),
       ("k_att", 2.0, 8.0, False), ("k_ff", 0.0, 1.0, False), ("lam", 0.0, 0.5, False)]
LO = np.array([np.log(b[1]) if b[3] else b[1] for b in BOX])
HI = np.array([np.log(b[2]) if b[3] else b[2] for b in BOX])
DQ_PENALTY = 10.0


def to_cfg(x: np.ndarray) -> dict:
    vals = {b[0]: float(np.exp(v) if b[3] else v) for b, v in zip(BOX, x)}
    return dataclasses.asdict(dataclasses.replace(INDIConfig(), **vals))


def _activity(res: dict) -> float:
    return float(np.mean([r["du_ail"] + r["du_elev"] for r in res["rows"]]))


def _eval(cfg: dict) -> dict:
    res = evaluate(INDIConfig(**cfg))
    return dict(cfg=cfg, J=res["J"], A=_activity(res), dq=res["disqualified"], by_test=res["by_test"])


def pso(gamma: float, ref: dict, n: int, iters: int, seed: int, workers: int, log: list) -> dict:
    """표준 전역 PSO (w 0.7, c1=c2 1.5, 속도 클램프 = 범위 20%). 평가는 세대 단위 병렬."""
    rng = np.random.default_rng(seed)
    span = HI - LO
    x = LO + rng.random((n, len(BOX))) * span
    v = (rng.random((n, len(BOX))) - 0.5) * 0.2 * span

    def cost(e):
        return e["J"] / ref["J"] + gamma * e["A"] / ref["A"] + (DQ_PENALTY if e["dq"] else 0.0)

    pbest, pcost = x.copy(), np.full(n, np.inf)
    gbest, gcost = None, np.inf
    for it in range(iters):
        evals = pmap(_eval, [to_cfg(xi) for xi in x], workers)
        for i, e in enumerate(evals):
            c = cost(e)
            log.append(dict(e, gamma=gamma, iter=it, cost=c))
            if c < pcost[i]:
                pbest[i], pcost[i] = x[i].copy(), c
            if c < gcost:
                gbest, gcost = x[i].copy(), c
        print(f"γ={gamma:<4} iter {it + 1:2d}/{iters}  best cost {gcost:.4f}  {to_cfg(gbest)}", flush=True)
        r1, r2 = rng.random((2, n, len(BOX)))
        v = 0.7 * v + 1.5 * r1 * (pbest - x) + 1.5 * r2 * (gbest - x)
        v = np.clip(v, -0.2 * span, 0.2 * span)
        x = np.clip(x + v, LO, HI)
    return dict(gamma=gamma, cost=float(gcost), cfg=to_cfg(gbest))


def pareto(points: list[dict], ref: dict) -> list[dict]:
    """(J/J₀, A/A₀) 둘 다 최소화 — 실격 제외 비지배 집합."""
    ok = [p for p in points if not p["dq"]]
    front = [p for p in ok if not any(q["J"] <= p["J"] and q["A"] <= p["A"]
                                      and (q["J"] < p["J"] or q["A"] < p["A"]) for q in ok)]
    return sorted([dict(cfg=p["cfg"], J_ratio=p["J"] / ref["J"], A_ratio=p["A"] / ref["A"]) for p in front],
                  key=lambda d: d["J_ratio"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gammas", nargs="+", type=float, default=[0.0, 0.1, 0.3, 1.0])
    ap.add_argument("--particles", type=int, default=20)
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.smoke:
        a.gammas, a.particles, a.iters = [0.3], 4, 2
    ref = _eval(dataclasses.asdict(INDIConfig()))
    print(f"기준 J₀={ref['J']:.4f} A₀={ref['A']:.5f}", flush=True)
    log: list = []
    best = [pso(g, ref, a.particles, a.iters, a.seed + k, a.workers, log) for k, g in enumerate(a.gammas)]
    front = pareto(log + [ref], ref)
    print("파레토 (J/J₀, A/A₀):", [(round(p["J_ratio"], 3), round(p["A_ratio"], 3)) for p in front])
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(dict(ref=ref, best=best, pareto=front, log=log), f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
