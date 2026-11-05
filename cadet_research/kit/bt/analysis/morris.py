"""RQ2 Morris μ*·μ·σ (PREREG_BT.md §6.2) + 중요 판정 (PREREG_BT_DEVIATIONS.md #3). games.csv 는 읽기만 한다.

  python bt/analysis/morris.py bt/out/bt-main/games_main_morris_r16.csv --design bt/thetas/main_morris_r16.csv --out bt/out/analysis

- 단계 (궤적 t, 바뀐 파라미터 i) 마다 셀별 짝 차이 d_c = y(다음 θ, c) − y(이전 θ, c). EE = mean(d_c) / Δ (정규화 단위).
- μ* = mean|EE|, μ = mean EE, σ = std EE (궤적 16개). 부트스트랩: 궤적 재표집 2,000회 (seed 20261108), 백분위 95%.
- 잡음 기준선: 각 단계 d_c 부호를 독립적으로 무작위로 뒤집어 μ* 를 다시 계산 2,000회 (seed 20261108), 파라미터별 95백분위.
- 중요 = 관측 μ* 부트스트랩 95% CI 하한 > 그 파라미터의 잡음 기준선. 기하별은 셀 16개로 같은 방식.
- 기하별 비교: 한 번 뽑은 궤적 묶음으로 세 기하를 함께 계산 (차이 CI 가 짝을 이룸). "다르다" = 한 기하 중요·다른 기하 중요 아님이고
  두 기하 μ* 차이 95% CI 가 0 을 포함하지 않음. 기하 쌍 Spearman 순위 상관 (서술용, 부트스트랩 CI).
"""
from __future__ import annotations

import argparse
import itertools
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anova import load  # noqa: E402
from io_utils import read_design  # noqa: E402

BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BT)
import make_tree as mt  # noqa: E402

PARAMS = [p["name"] for p in mt.PARAMS] + ["dummy"]
BOUNDS = {p["name"]: (float(p["lo"]), float(p["hi"])) for p in mt.PARAMS + [mt.DUMMY]}
CELL = ["scenario", "opponent", "seed_salt"]
B, SEED = 2000, 20261108


def theta_means(games_df: pd.DataFrame, design_path: str, by_geometry: bool = False) -> pd.DataFrame:
    """θ 마다 (by_geometry 면 θ·기하마다) 평균 Δwez 를 설계 파일 (read_design) 에 붙인다."""
    d = read_design(design_path)
    keys = ["theta_id", "scenario"] if by_geometry else ["theta_id"]
    m = games_df.groupby(keys).dwez.mean().rename("y").reset_index()
    return d.merge(m, on="theta_id", how="left")


def step_diffs(games_df: pd.DataFrame, design_path: str, scenario: str | None = None) -> list:
    """단계마다 (trajectory, param, d, delta). d = 셀별 짝 차이 배열 (두 θ 에 같은 셀 순서), delta = 정규화 단위 변화량."""
    g = games_df if scenario is None else games_df[games_df.scenario == scenario]
    piv = g.pivot_table(index="theta_id", columns=CELL, values="dwez", aggfunc="first")
    if piv.isna().any().any():
        raise ValueError("셀이 빠진 θ 가 있다 (균형 아님)")
    d = read_design(design_path).sort_values(["trajectory", "step"])
    out = []
    for tr, b in d.groupby("trajectory"):
        b = b.reset_index(drop=True)
        for k in range(len(b) - 1):
            a, c = b.iloc[k], b.iloc[k + 1]
            changed = [p for p in PARAMS if a[p] != c[p]]
            if len(changed) != 1:
                raise ValueError(f"궤적 {tr} 단계 {k}: 바뀐 요인이 {len(changed)}개")
            p = changed[0]
            lo, hi = BOUNDS[p]
            out.append((int(tr), p, piv.loc[c.theta_id].values - piv.loc[a.theta_id].values, (c[p] - a[p]) / (hi - lo)))
    return out


def elementary_effects(steps: list) -> pd.DataFrame:
    return pd.DataFrame([(t, p, d.mean() / dl) for t, p, d, dl in steps], columns=["trajectory", "param", "ee"])


def indices(ee: pd.DataFrame) -> pd.DataFrame:
    g = ee.groupby("param").ee
    return pd.DataFrame({"mu_star": g.apply(lambda x: x.abs().mean()), "mu": g.mean(), "sigma": g.std(ddof=0)}).reindex(PARAMS)


def _boot_draws(trajs, n_boot, seed):
    rng = np.random.default_rng(seed)
    return [rng.choice(trajs, len(trajs), replace=True) for _ in range(n_boot)]


def _mu_star_boot(ee: pd.DataFrame, draws) -> np.ndarray:
    piv = ee.pivot(index="trajectory", columns="param", values="ee").reindex(columns=PARAMS).abs()
    return np.array([piv.loc[dr].mean().values for dr in draws])


def bootstrap(ee: pd.DataFrame, n_boot: int = B, seed: int = SEED, draws=None) -> pd.DataFrame:
    draws = draws if draws is not None else _boot_draws(sorted(ee.trajectory.unique()), n_boot, seed)
    bs = _mu_star_boot(ee, draws)
    t = indices(ee)
    t["mu_star_lo"], t["mu_star_hi"] = np.percentile(bs, 2.5, 0), np.percentile(bs, 97.5, 0)
    return t[["mu_star", "mu_star_lo", "mu_star_hi", "mu", "sigma"]]


def noise_floor(steps: list, n_null: int = B, seed: int = SEED) -> dict:
    """파라미터 → μ* 귀무 분포 (d_c 부호 독립 뒤집기) 의 95백분위."""
    rng = np.random.default_rng(seed)
    D = np.stack([d for _, _, d, _ in steps])                      # 단계 × 셀
    dl = np.array([x for _, _, _, x in steps])
    par = np.array([p for _, p, _, _ in steps])
    null = np.empty((n_null, len(PARAMS)))
    for r in range(n_null):
        ee = np.abs((D * rng.choice([-1.0, 1.0], D.shape)).mean(1) / dl)
        null[r] = [ee[par == p].mean() for p in PARAMS]
    return dict(zip(PARAMS, np.percentile(null, 95, 0)))


def important(boot: pd.DataFrame, floor: dict) -> dict:
    return {p: bool(boot.loc[p, "mu_star_lo"] > floor[p]) for p in boot.index}


def analyze(games_df: pd.DataFrame, design_path: str, scenario: str | None = None, draws=None) -> dict:
    st = step_diffs(games_df, design_path, scenario)
    ee = elementary_effects(st)
    boot = bootstrap(ee, draws=draws)
    floor = noise_floor(st)
    imp = important(boot, floor)
    boot["noise_floor"] = [floor[p] for p in boot.index]
    boot["important"] = [imp[p] for p in boot.index]
    dummy_zero = all(np.all(d == 0) for _, p, d, _ in st if p == "dummy")
    return dict(steps=st, ee=ee, table=boot, important=imp, dummy_exact_zero=dummy_zero)


def geometry_compare(games_df: pd.DataFrame, design_path: str, n_boot: int = B, seed: int = SEED) -> dict:
    geos = sorted(games_df.scenario.unique())
    trajs = sorted(read_design(design_path).trajectory.unique())
    draws = _boot_draws(trajs, n_boot, seed)                         # 세 기하가 같은 궤적 묶음을 쓴다
    res = {g: analyze(games_df, design_path, g, draws) for g in geos}
    bs = {g: _mu_star_boot(res[g]["ee"], draws) for g in geos}
    pairs = []
    for a, b in itertools.combinations(geos, 2):
        ta, tb = res[a]["table"], res[b]["table"]
        rho = stats.spearmanr(ta.mu_star, tb.mu_star).correlation
        rb = [stats.spearmanr(x, y).correlation for x, y in zip(bs[a], bs[b])]
        diff = bs[a] - bs[b]
        lo, hi = np.percentile(diff, 2.5, 0), np.percentile(diff, 97.5, 0)
        for i, p in enumerate(PARAMS):
            pairs.append(dict(geo_a=a, geo_b=b, param=p, mu_star_a=ta.mu_star[p], mu_star_b=tb.mu_star[p],
                              diff=ta.mu_star[p] - tb.mu_star[p], diff_lo=lo[i], diff_hi=hi[i],
                              imp_a=res[a]["important"][p], imp_b=res[b]["important"][p],
                              differs=(res[a]["important"][p] != res[b]["important"][p]) and not (lo[i] <= 0 <= hi[i]),
                              spearman=rho, spearman_lo=np.nanpercentile(rb, 2.5), spearman_hi=np.nanpercentile(rb, 97.5)))
    return dict(by_geometry=res, pairs=pd.DataFrame(pairs))


def plot_mu_sigma(boot: pd.DataFrame, path: str, title: str = "Morris μ*–σ") -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    for p, r in boot.iterrows():
        c = "#D62728" if r.important else ("#7F7F7F" if p == "dummy" else "#4C78A8")
        ax.errorbar(r.mu_star, r.sigma, xerr=[[r.mu_star - r.mu_star_lo], [r.mu_star_hi - r.mu_star]], fmt="o", color=c, capsize=3)
        ax.annotate(p, (r.mu_star, r.sigma), textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax.set_xlabel("μ* (95% CI)")
    ax.set_ylabel("σ")
    ax.set_title(title + " (빨강 = 중요)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_geometry_rank(result: dict, path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    geos = list(result["by_geometry"])
    fig, ax = plt.subplots(figsize=(7, 4))
    w = 0.8 / len(geos)
    x = np.arange(len(PARAMS))
    for k, g in enumerate(geos):
        t = result["by_geometry"][g]["table"]
        ax.bar(x + k * w, t.mu_star, w, label=g, yerr=[t.mu_star - t.mu_star_lo, t.mu_star_hi - t.mu_star], capsize=2)
    ax.set_xticks(x + w, PARAMS, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("μ* (95% CI)")
    ax.set_title("기하별 Morris μ*")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _md_table(t: pd.DataFrame) -> list:
    L = ["| 파라미터 | μ* | 95% CI | 잡음 기준선 | μ | σ | 중요 |", "|---|---|---|---|---|---|---|"]
    for p, r in t.sort_values("mu_star", ascending=False).iterrows():
        L.append(f"| {p} | {r.mu_star:.3f} | ({r.mu_star_lo:.3f}, {r.mu_star_hi:.3f}) | {r.noise_floor:.3f} | {r.mu:+.3f} | {r.sigma:.3f} | {'**중요**' if r.important else '—'} |")
    return L


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("games")
    ap.add_argument("--design", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    df = load(a.games)
    allr = analyze(df, a.design)
    geo = geometry_compare(df, a.design)
    allr["table"].to_csv(os.path.join(a.out, "morris.csv"))
    geo["pairs"].to_csv(os.path.join(a.out, "morris_geometry_pairs.csv"), index=False)
    L = ["# RQ2 Morris (전체, 셀 48개)", "", f"θ {df.theta_id.nunique()}개, {len(df)}경기. 중요 판정은 PREREG_BT_DEVIATIONS.md #3.", "",
         f"더미 단계 셀별 차이가 모두 정확히 0 (재현성 확인): **{allr['dummy_exact_zero']}**", ""] + _md_table(allr["table"])
    open(os.path.join(a.out, "morris.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    G = ["# RQ2 기하별 Morris (셀 16개)", ""]
    for g, r in geo["by_geometry"].items():
        G += [f"## {g}", ""] + _md_table(r["table"]) + [""]
    pr = geo["pairs"]
    G += ["## 기하 쌍 비교", "", "| 기하 A | 기하 B | Spearman ρ (95% CI) |", "|---|---|---|"]
    for (a_, b_), s in pr.groupby(["geo_a", "geo_b"]):
        G.append(f"| {a_} | {b_} | {s.spearman.iloc[0]:.2f} ({s.spearman_lo.iloc[0]:.2f}, {s.spearman_hi.iloc[0]:.2f}) |")
    G += ["", "\"기하별로 다르다\" 판정된 (파라미터, 기하 쌍):", ""]
    dd = pr[pr.differs]
    G += [f"- {r.param}: {r.geo_a} {'중요' if r.imp_a else '중요 아님'} vs {r.geo_b} {'중요' if r.imp_b else '중요 아님'}, "
          f"μ* 차이 {r.diff:+.3f} ({r.diff_lo:+.3f}, {r.diff_hi:+.3f})" for r in dd.itertuples()] or ["- 없음"]
    open(os.path.join(a.out, "morris_geometry.md"), "w", encoding="utf-8", newline="\n").write("\n".join(G) + "\n")
    plot_mu_sigma(allr["table"], os.path.join(a.out, "morris_mu_sigma.png"))
    plot_geometry_rank(geo, os.path.join(a.out, "morris_geometry.png"))
    print("\n".join(L))


if __name__ == "__main__":
    main()
