"""RQ1 분산분해 (PREREG_BT.md §6.1). games.csv 는 읽기만 한다.

  python bt/analysis/anova.py bt/out/bt-main/games_main_lhs64.csv --out bt/out/analysis

모형: 경기별 Δwez = θ + 기하 + 상대 + θ×기하 + θ×상대 + 기하×상대 + 잔차 (시드 잡음 + θ×기하×상대, 분리 불가).
균형 완전교차 설계라 고정효과 ANOVA 제곱합 비율 η² (항 제곱합 / 전체 제곱합) 를 분산 비율로 쓴다.
불확실성: θ 단위 재표집 부트스트랩 2,000회 (seed 20261108), 백분위 95%. 같은 θ 가 여러 번 뽑히면 뽑힐 때마다 새 이름 (서로 다른 수준).
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from io_utils import read_games  # noqa: E402

TERMS = ("theta", "geometry", "opponent", "theta:geometry", "theta:opponent", "geometry:opponent", "residual")
LABEL = {"theta": "θ", "geometry": "기하", "opponent": "상대", "theta:geometry": "θ×기하", "theta:opponent": "θ×상대",
         "geometry:opponent": "기하×상대", "residual": "잔차 (시드 + θ×기하×상대)"}


def load(path: str) -> pd.DataFrame:
    """read_games 로 읽고 wall_clock 행을 뺀 뒤 dwez = wez_blue − wez_red 열을 붙인다. 뺀 수를 출력한다."""
    df = read_games(path)
    n = int((df.end_reason == "wall_clock").sum())
    if n:
        print(f"wall_clock {n}경기를 뺀다 (CONTRACT §5: 재실행으로 채운 뒤 분석해야 한다 — check_balance 가 막는다)")
    df = df[df.end_reason != "wall_clock"].copy()
    df["dwez"] = df.wez_blue - df.wez_red
    return df


def check_balance(df: pd.DataFrame, n_seeds: int = 4) -> None:
    """모든 θ 가 (기하 3 × 상대 4 × 시드 n_seeds) 칸을 정확히 하나씩 갖는지. 아니면 빠진·겹친 칸 목록과 함께 ValueError."""
    scen, opp = sorted(df.scenario.unique()), sorted(df.opponent.unique())
    seeds = sorted(df.seed_salt.unique())
    if len(scen) != 3 or len(opp) != 4 or len(seeds) != n_seeds:
        raise ValueError(f"수준 수가 다르다: 기하 {len(scen)}, 상대 {len(opp)}, 시드 {len(seeds)} (기대 3, 4, {n_seeds})")
    full = pd.MultiIndex.from_product([sorted(df.theta_id.unique()), scen, opp, seeds],
                                      names=["theta_id", "scenario", "opponent", "seed_salt"])
    counts = df.groupby(["theta_id", "scenario", "opponent", "seed_salt"]).size().reindex(full, fill_value=0)
    missing, dup = list(counts[counts == 0].index), list(counts[counts > 1].index)
    if missing or dup:
        raise ValueError(f"균형이 아니다: 빠진 칸 {len(missing)}개 {missing[:10]}, 겹친 칸 {len(dup)}개 {dup[:10]}")


def _cube(df: pd.DataFrame) -> np.ndarray:
    """Δwez 배열 [θ, 기하, 상대, 시드] (θ 는 등장 순서, 나머지는 정렬)."""
    tids = list(dict.fromkeys(df.theta_id))
    s = df.set_index(["theta_id", "scenario", "opponent", "seed_salt"]).dwez.sort_index()
    shape = (len(tids), df.scenario.nunique(), df.opponent.nunique(), df.seed_salt.nunique())
    return s.reindex(pd.MultiIndex.from_product([tids, *[sorted(df[c].unique()) for c in ("scenario", "opponent", "seed_salt")]])).values.reshape(shape)


def _eta2_cube(y: np.ndarray) -> dict:
    m = y.mean()
    mt, mg, mo = y.mean((1, 2, 3)), y.mean((0, 2, 3)), y.mean((0, 1, 3))
    mtg, mto, mgo = y.mean((2, 3)), y.mean((1, 3)), y.mean((0, 3))
    nt, ng, no, ns = y.shape
    ss = {"theta": ng * no * ns * np.sum((mt - m) ** 2),
          "geometry": nt * no * ns * np.sum((mg - m) ** 2),
          "opponent": nt * ng * ns * np.sum((mo - m) ** 2),
          "theta:geometry": no * ns * np.sum((mtg - mt[:, None] - mg[None, :] + m) ** 2),
          "theta:opponent": ng * ns * np.sum((mto - mt[:, None] - mo[None, :] + m) ** 2),
          "geometry:opponent": nt * ns * np.sum((mgo - mg[:, None] - mo[None, :] + m) ** 2)}
    total = np.sum((y - m) ** 2)
    ss["residual"] = total - sum(ss.values())
    return {k: float(ss[k] / total) for k in TERMS}


def eta2(df: pd.DataFrame) -> dict:
    """항 → η² (합 1). 시작할 때 check_balance."""
    check_balance(df)
    return _eta2_cube(_cube(df))


def resample_thetas(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """θ 를 θ 수만큼 복원추출한 표본. 뽑힐 때마다 새 이름 '<id>#<순번>' → 같은 θ 가 두 번 뽑혀도 서로 다른 수준."""
    tids = list(dict.fromkeys(df.theta_id))
    pick = rng.choice(len(tids), len(tids), replace=True)
    groups = {t: g for t, g in df.groupby("theta_id", sort=False)}
    return pd.concat([groups[tids[i]].assign(theta_id=f"{tids[i]}#{k}") for k, i in enumerate(pick)], ignore_index=True)


def eta2_bootstrap(df: pd.DataFrame, n_boot: int = 2000, seed: int = 20261108) -> pd.DataFrame:
    """열 term, eta2, ci_lo, ci_hi. rng = default_rng(seed) 로 resample_thetas 를 n_boot 번 (배열 색인으로 같은 계산)."""
    check_balance(df)
    y = _cube(df)
    rng = np.random.default_rng(seed)
    nt = y.shape[0]
    boot = np.array([[v for v in _eta2_cube(y[rng.choice(nt, nt, replace=True)]).values()] for _ in range(n_boot)])
    point = _eta2_cube(y)
    return pd.DataFrame({"term": TERMS, "eta2": [point[k] for k in TERMS],
                         "ci_lo": np.percentile(boot, 2.5, 0), "ci_hi": np.percentile(boot, 97.5, 0)})


def plot_eta2(table: pd.DataFrame, path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    x = np.arange(len(table))
    ax.bar(x, table.eta2, color="#4C78A8")
    ax.errorbar(x, table.eta2, yerr=[table.eta2 - table.ci_lo, table.ci_hi - table.eta2], fmt="none", ecolor="black", capsize=3)
    ax.set_xticks(x, [LABEL[t] for t in table.term], rotation=20, ha="right")
    ax.set_ylabel("η² (분산 비율)")
    ax.set_title("RQ1 Δwez 분산분해 (95% CI, θ 부트스트랩 2,000회)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def to_md(table: pd.DataFrame, title: str, n_theta: int, n_games: int) -> str:
    L = [f"# {title}", "", f"θ {n_theta}개, {n_games}경기. 1차 지표 Δwez = wez_blue − wez_red. PREREG_BT.md §6.1.", "",
         "| 항 | η² | 95% CI |", "|---|---|---|"]
    L += [f"| {LABEL[r.term]} | {r.eta2:.3f} | ({r.ci_lo:.3f}, {r.ci_hi:.3f}) |" for r in table.itertuples()]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("games")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="rq1_eta2")
    ap.add_argument("--title", default="RQ1 분산분해")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    df = load(a.games)
    t = eta2_bootstrap(df)
    t.to_csv(os.path.join(a.out, f"{a.name}.csv"), index=False)
    open(os.path.join(a.out, f"{a.name}.md"), "w", encoding="utf-8", newline="\n").write(to_md(t, a.title, df.theta_id.nunique(), len(df)))
    plot_eta2(t, os.path.join(a.out, f"{a.name}.png"))
    print(t.to_string(index=False))


if __name__ == "__main__":
    main()
