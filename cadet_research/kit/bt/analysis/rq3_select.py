"""RQ3 후보 θ 선택 (PREREG_BT.md §1, §6.4 + PREREG_BT_DEVIATIONS.md #7). games.csv 는 읽기만 한다.

  python bt/analysis/rq3_select.py      # cadet_research/kit/ 에서 → bt/thetas/confirm_candidates.csv

- 기준 θ: bt/thetas/baseline.csv.
- 관측 최고 θ 1개: bt-main θ 256개 중 48경기 평균 Δwez 최대, 동률이면 승률 높은 쪽.
- 대리모델 예측 최고 θ 2개: HistGradientBoostingRegressor (random_state 20261108, 나머지 기본값) 를 θ 256개 전체로 학습하고,
  designs.lhs(10000, seed=20261108) 후보에서 예측값이 가장 큰 2개. 반복 탐색·최적화는 하지 않는다.
"""
from __future__ import annotations

import csv
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BT = os.path.dirname(HERE)
sys.path[:0] = [HERE, BT]
import designs  # noqa: E402
import make_tree as mt  # noqa: E402
import run_bt  # noqa: E402
from anova import load  # noqa: E402
from morris import PARAMS  # noqa: E402
from surrogate import SEED, theta_table  # noqa: E402

GAMES = [os.path.join(BT, "out", "bt-main", f) for f in ("games_main_lhs64.csv", "games_main_morris_r16.csv")]
DESIGNS = [os.path.join(BT, "thetas", f) for f in ("main_lhs64.csv", "main_morris_r16.csv")]
OUT = os.path.join(BT, "thetas", "confirm_candidates.csv")
N_POOL = 10000


def select():
    from sklearn.ensemble import HistGradientBoostingRegressor
    df = pd.concat([load(g) for g in GAMES], ignore_index=True)
    tt = theta_table(df, DESIGNS)
    win = df.assign(win=(df.winner == "blue").astype(float)).groupby("theta_id").win.mean()
    tt["win"] = tt.theta_id.map(win)
    best = tt.sort_values(["y", "win"], ascending=False).iloc[0]
    model = HistGradientBoostingRegressor(random_state=SEED).fit(tt[PARAMS], tt.y)
    pool = pd.DataFrame(designs.lhs(N_POOL, SEED))
    pool["pred"] = model.predict(pool[PARAMS])
    top = pool.sort_values("pred", ascending=False).head(2)
    base = mt.normalize({**mt.BASE, "dummy": mt.DUMMY["base"]})
    rows = [dict(role="baseline", **base, note="bt/thetas/baseline.csv"),
            dict(role="observed_best", **{p: float(best[p]) for p in PARAMS},
                 note=f"bt-main 평균 Δwez {best.y:+.3f} s, 승률 {best.win:.3f}, theta_id {best.theta_id}")]
    rows += [dict(role=f"surrogate_top{k + 1}", **{p: float(r[p]) for p in PARAMS}, note=f"예측 Δwez {r.pred:+.3f} s (LHS 후보 {N_POOL})")
             for k, (_, r) in enumerate(top.iterrows())]
    return rows


def main():
    rows = select()
    cols = mt.NAMES + ["dummy"]
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows({k: repr(float(r[k])) for k in cols} for r in rows)
    for r in rows:
        print(r["role"], mt.theta_id({k: r[k] for k in cols}), r["note"])
    print("→", OUT)


if __name__ == "__main__":
    main()
