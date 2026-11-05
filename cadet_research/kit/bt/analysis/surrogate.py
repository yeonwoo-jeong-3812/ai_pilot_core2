"""대리모델 (PREREG_BT.md §6.3). games.csv 는 읽기만 한다.

  python bt/analysis/surrogate.py bt/out/bt-main/games_main_lhs64.csv bt/out/bt-main/games_main_morris_r16.csv \\
      --designs bt/thetas/main_lhs64.csv bt/thetas/main_morris_r16.csv --out bt/out/analysis

HistGradientBoostingRegressor (random_state 20261108, 나머지 기본값). 입력 θ (10개 + 더미), 출력 θ 별 48경기 평균 Δwez.
떼어 두기 (집단 단위): rng = default_rng(20261108) → Morris 궤적 rng.choice(16, 3) 의 θ 36개 → LHS 행 rng.choice(64, 13) → 49 θ.
떼어 둔 데이터 R² ≥ 0.5 일 때만 SHAP (TreeExplainer) 을 결과로 보고한다.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anova import load  # noqa: E402
from io_utils import read_design  # noqa: E402
from morris import PARAMS  # noqa: E402

SEED, R2_MIN = 20261108, 0.5


def theta_table(games_df: pd.DataFrame, design_paths) -> pd.DataFrame:
    m = games_df.groupby("theta_id").dwez.mean().rename("y")
    parts = []
    for p in design_paths:
        d = read_design(p)
        d["design"] = "morris" if "trajectory" in d.columns else "lhs"
        d["row"] = range(len(d))
        if "trajectory" not in d.columns:
            d["trajectory"] = np.nan
        parts.append(d[PARAMS + ["theta_id", "design", "row", "trajectory"]])
    tt = pd.concat(parts, ignore_index=True)
    tt["y"] = tt.theta_id.map(m)
    return tt


def holdout_split(tt: pd.DataFrame, seed: int = SEED):
    rng = np.random.default_rng(seed)
    trajs = {int(t) for t in rng.choice(16, 3, replace=False)}
    rows = set(int(r) for r in rng.choice(64, 13, replace=False))
    test = (tt.design.eq("morris") & tt.trajectory.isin(trajs)) | (tt.design.eq("lhs") & tt.row.isin(rows))
    return list(tt.theta_id[~test]), list(tt.theta_id[test]), sorted(trajs)


def fit_holdout(tt: pd.DataFrame, seed: int = SEED) -> dict:
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import r2_score
    tr, te, trajs = holdout_split(tt, seed)
    a, b = tt.set_index("theta_id").loc[tr], tt.set_index("theta_id").loc[te]
    model = HistGradientBoostingRegressor(random_state=seed).fit(a[PARAMS], a.y)
    return dict(model=model, r2_holdout=float(r2_score(b.y, model.predict(b[PARAMS]))), train_ids=tr, test_ids=te,
                test_trajectories=trajs)


def shap_report(fit: dict, tt: pd.DataFrame, out_dir: str) -> bool:
    if fit["r2_holdout"] < R2_MIN:
        return False
    import shap
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    X = tt[PARAMS]
    sv = shap.TreeExplainer(fit["model"]).shap_values(X)
    pd.DataFrame(sv, columns=PARAMS).assign(theta_id=tt.theta_id.values).to_csv(os.path.join(out_dir, "surrogate_shap.csv"), index=False)
    shap.summary_plot(sv, X, show=False)
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "surrogate_shap.png"), dpi=150)
    plt.close()
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("games", nargs="+")
    ap.add_argument("--designs", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    df = pd.concat([load(g) for g in a.games], ignore_index=True)
    tt = theta_table(df, a.designs)
    fit = fit_holdout(tt)
    shown = shap_report(fit, tt, a.out)
    L = ["# 대리모델 (PREREG_BT.md §6.3)", "", f"θ {len(tt)}개 (학습 {len(fit['train_ids'])}, 떼어 둠 {len(fit['test_ids'])}; 떼어 둔 Morris 궤적 {fit['test_trajectories']}).",
         f"떼어 둔 데이터 R² = **{fit['r2_holdout']:.3f}** (기준 ≥ {R2_MIN}) → SHAP {'보고' if shown else '보고하지 않음'}.", ""]
    if shown:
        sv = pd.read_csv(os.path.join(a.out, "surrogate_shap.csv"))
        imp = sv[PARAMS].abs().mean().sort_values(ascending=False)
        L += ["| 파라미터 | mean\\|SHAP\\| [s] |", "|---|---|"] + [f"| {p} | {v:.3f} |" for p, v in imp.items()]
    open(os.path.join(a.out, "surrogate.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
