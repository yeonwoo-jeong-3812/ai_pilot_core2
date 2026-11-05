"""확인 단계 비교 (PREREG_BT.md §6.4, RQ3 조건부). games.csv 는 읽기만 한다.

  python bt/analysis/confirm.py bt/out/bt-confirm/games.csv --baseline <theta_id> --out bt/out/analysis

후보 θ − 기준 θ 의 짝 차이 Δwez (같은 기하·상대·시드끼리). 짝 차이에 대한 t 분포 (자유도 n − 1).
"낫다" = Holm 보정 후 단측 유의 (α 0.05) 이고 95% CI 하한 > 0. "실질적으로 낫다" = 여기에 점추정 ≥ 0.5 s.
동등성 = ±0.5 s TOST (α 0.05). 보조 지표 (승률, 체력 차) 짝 차이 평균은 서술용.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anova import load  # noqa: E402

CELL = ["scenario", "opponent", "seed_salt"]


def paired(df: pd.DataFrame, baseline_id: str) -> pd.DataFrame:
    """후보 θ × 셀마다 한 행: theta_id, 셀, d_dwez, d_win, d_hp (후보 − 기준). 짝이 안 맞으면 ValueError."""
    df = df.assign(win=(df.winner == "blue").astype(float), hp=df.hp_blue_raw - df.hp_red_raw)
    base = df[df.theta_id == baseline_id].set_index(CELL)
    if base.empty:
        raise ValueError(f"기준 θ {baseline_id} 가 없다")
    if base.index.duplicated().any():
        raise ValueError("기준 θ 에 겹친 셀이 있다")
    out = []
    for tid, g in df[df.theta_id != baseline_id].groupby("theta_id", sort=False):
        g = g.set_index(CELL)
        if g.index.duplicated().any() or set(g.index) != set(base.index):
            raise ValueError(f"θ {tid} 의 셀이 기준 θ 와 짝이 맞지 않는다 (후보 {len(g)}칸, 기준 {len(base)}칸)")
        b = base.loc[g.index]
        out.append(pd.DataFrame({"theta_id": tid, **{c: g.index.get_level_values(c) for c in CELL},
                                 "d_dwez": g.dwez.values - b.dwez.values, "d_win": g.win.values - b.win.values,
                                 "d_hp": g.hp.values - b.hp.values}))
    return pd.concat(out, ignore_index=True)


def holm(p: np.ndarray) -> np.ndarray:
    """Holm 보정 p 값 (단조성 유지)."""
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    run = 0.0
    for k, i in enumerate(order):
        run = max(run, min(1.0, (m - k) * p[i]))
        adj[i] = run
    return adj


def compare(df: pd.DataFrame, baseline_id: str, alpha: float = 0.05, mid: float = 0.5) -> pd.DataFrame:
    pr = paired(df, baseline_id)
    rows = []
    for tid, g in pr.groupby("theta_id", sort=False):
        d = g.d_dwez.values
        n, m, se = len(d), d.mean(), d.std(ddof=1) / np.sqrt(len(d))
        tq = stats.t.ppf(0.975, n - 1)
        p1 = stats.t.sf(m / se, n - 1)                                            # 단측 (후보 > 기준)
        p_tost = max(stats.t.sf((m + mid) / se, n - 1), stats.t.cdf((m - mid) / se, n - 1))
        rows.append(dict(theta_id=tid, n=n, mean=m, ci_lo=m - tq * se, ci_hi=m + tq * se, p_one_sided=p1, p_tost=p_tost,
                         win_diff=g.d_win.mean(), hp_diff=g.d_hp.mean()))
    t = pd.DataFrame(rows)
    t["p_holm"] = holm(t.p_one_sided.values)
    t["better"] = (t.p_holm < alpha) & (t.ci_lo > 0)
    t["practically_better"] = t.better & (t["mean"] >= mid)
    t["equivalent"] = t.p_tost < alpha
    return t[["theta_id", "n", "mean", "ci_lo", "ci_hi", "p_one_sided", "p_holm", "better", "practically_better",
              "p_tost", "equivalent", "win_diff", "hp_diff"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("games")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t = compare(load(a.games), a.baseline)
    t.to_csv(os.path.join(a.out, "confirm.csv"), index=False)
    L = ["# 확인 단계 (PREREG_BT.md §6.4)", "", "| θ | n | Δwez 평균 [s] (95% CI) | 단측 p | Holm p | 낫다 | 실질적 | TOST p | 동등 | Δ승률 | Δ체력 |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {r.theta_id} | {r.n} | {r.mean:+.3f} ({r.ci_lo:+.3f}, {r.ci_hi:+.3f}) | {r.p_one_sided:.3g} | {r.p_holm:.3g} | {r.better} "
          f"| {r.practically_better} | {r.p_tost:.3g} | {r.equivalent} | {r.win_diff:+.3f} | {r.hp_diff:+.1f} |" for r in t.itertuples()]
    open(os.path.join(a.out, "confirm.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    print(t.to_string(index=False))


if __name__ == "__main__":
    main()
