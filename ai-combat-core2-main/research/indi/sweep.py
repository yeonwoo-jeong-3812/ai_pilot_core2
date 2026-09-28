"""E2 — 단일 변수 민감도 (paper.md §7-B, 논문 2 VI-F 방식).

변수 6개 × 5수준, 나머지는 기준값 고정. 수준마다:
  bench : E1 추종 J / J_기준 (실격 = 3.0 절단, 논문 2 의 300%)
  duel  : blue 만 변경, red 전원 기준 INDI. 같은 (red, 시나리오, 시드) 의 기준 경기와 **대응 차이**
          Δ승점(승 1·무 0.5·패 0), ΔHP차(hp_blue − hp_red), 부트스트랩 95% CI. 한계 실격 수.

    python research/indi/sweep.py --smoke                       # k_q 2수준 × 소형 배터리
    python research/indi/sweep.py --out results/e2.json         # 전체 (≈ 1–2 h, 8코어)
    python research/indi/sweep.py --vars filt_hz lam --seeds 1 2 3
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import battery, game, pmap, NOMINAL_SIGMA_DPS, REDS, SCENS
from bench import evaluate
from aircombat.control.indi import INDIConfig

BASE = INDIConfig()
LEVELS = {   # paper.md §7-C 범위. 게인은 기준 대비 비율, filt_hz 로그 간격, k_ff·λ 절대값
    "k_p": [BASE.k_p * m for m in (0.5, 0.75, 1.0, 1.5, 2.0)],
    "k_q": [BASE.k_q * m for m in (0.5, 0.75, 1.0, 1.5, 2.0)],
    "filt_hz": [3.0, 6.0, 12.0, 25.0, 40.0],
    "k_att": [BASE.k_att * m for m in (0.5, 0.75, 1.0, 1.5, 2.0)],
    "k_ff": [0.0, 0.25, 0.5, 0.75, 1.0],
    "lam": [0.0, 0.1, 0.2, 0.3, 0.5],
}
CLAMP = 3.0


def _points(r: dict) -> float:
    return 1.0 if r["winner"] == "blue" else (0.5 if r["winner"] == "draw" else 0.0)


def _boot_ci(x: np.ndarray, n: int = 2000, seed: int = 0) -> tuple[float, float]:
    if len(x) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    m = rng.choice(x, (n, len(x))).mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def paired(base_games: list[dict], games: list[dict]) -> dict:
    """같은 순서(battery)의 기준·변경 경기 → 대응 차이 요약."""
    dp = np.array([_points(g) - _points(b) for b, g in zip(base_games, games)])
    dh = np.array([(g["hp_blue"] - g["hp_red"]) - (b["hp_blue"] - b["hp_red"])
                   for b, g in zip(base_games, games)])
    return dict(n=len(dp), d_points=float(dp.mean()), d_points_ci=_boot_ci(dp),
                d_hp=float(dh.mean()), d_hp_ci=_boot_ci(dh),
                win_rate=float(np.mean([_points(g) for g in games])),
                dq=int(sum(g["limits_blue"]["disqualified"] for g in games)),
                nz_max=float(max(g["limits_blue"]["nz_max"] for g in games)))


def _bench_job(cfg_dict):
    return evaluate(INDIConfig(**cfg_dict))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vars", nargs="+", default=list(LEVELS))
    ap.add_argument("--seeds", nargs="+", type=int, default=[1, 2])
    ap.add_argument("--reds", nargs="+", default=list(REDS))
    ap.add_argument("--scens", nargs="+", default=list(SCENS))
    ap.add_argument("--no-duel", action="store_true", help="추종 벤치만")
    ap.add_argument("--smoke", action="store_true", help="k_q ×0.5·×2, red 1종 × 시나리오 2 × 시드 1")
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--out")
    a = ap.parse_args()
    levels = {v: LEVELS[v] for v in a.vars}
    if a.smoke:
        levels = {"k_q": [BASE.k_q * 0.5, BASE.k_q * 2.0]}
        a.reds, a.scens, a.seeds = ["red_prime"], ["headon", "neutral"], [1]

    cfgs = [dataclasses.asdict(BASE)] + [dataclasses.asdict(dataclasses.replace(BASE, **{v: x}))
                                         for v, xs in levels.items() for x in xs
                                         if x != getattr(BASE, v)]
    bat = battery(tuple(a.seeds), tuple(a.reds), tuple(a.scens))
    print(f"configs {len(cfgs)} (기준 포함) · bench {len(cfgs)} · duel {0 if a.no_duel else len(cfgs) * len(bat)} 경기",
          flush=True)

    benches = pmap(_bench_job, cfgs, a.workers)
    duels = None
    if not a.no_duel:
        jobs = [(c, r, sc, sd, {}, NOMINAL_SIGMA_DPS, 0) for c in cfgs for r, sc, sd in bat]
        flat = pmap(game, jobs, a.workers)
        duels = [flat[i * len(bat):(i + 1) * len(bat)] for i in range(len(cfgs))]

    j0 = benches[0]["J"]
    rows = []
    for i, (c, b) in enumerate(zip(cfgs, benches)):
        var = next((v for v in levels if c[v] != getattr(BASE, v)), "baseline")
        row = dict(var=var, value=c[var] if var != "baseline" else None, cfg=c,
                   J=b["J"], J_ratio=CLAMP if b["disqualified"] else min(CLAMP, b["J"] / j0),
                   bench_dq=b["disqualified"], by_test=b["by_test"])
        if duels is not None:
            row["duel"] = paired(duels[0], duels[i])
        rows.append(row)
        d = row.get("duel", {})
        print(f"{var:8} {str(row['value']):>6} | J {row['J']:.4f} ratio {row['J_ratio']:.3f} dq {b['disqualified']}"
              + (f" | Δpts {d['d_points']:+.3f} [{d['d_points_ci'][0]:+.2f},{d['d_points_ci'][1]:+.2f}]"
                 f" ΔHP {d['d_hp']:+6.1f} win {d['win_rate']:.2f} limDQ {d['dq']} nzmax {d['nz_max']:.2f}" if d else ""),
              flush=True)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(dict(battery=bat, sigma_dps=NOMINAL_SIGMA_DPS, rows=rows,
                           games=duels), f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
