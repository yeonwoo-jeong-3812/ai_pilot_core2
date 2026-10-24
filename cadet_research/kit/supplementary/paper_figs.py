"""논문 그림 3·4·6·7 (초안 v2). 기존 자료만 읽는다(경기 0판).

  python paper_figs.py   # → paper_figs/fig3_curve.png, fig4_error_type.png, fig6_configs.png, fig7_asym.png

색: dataviz 기본 범주 팔레트 1–4번을 순서대로 쓰고(파랑 #2a78d6, 주황 #eb6834, 청록 #1baf7a, 노랑 #eda100),
색만으로 구분하지 않도록 표식 모양도 함께 바꾼다. 글자는 본문색(#0b0b0b·#52514e)으로 쓴다.
"""
import collections
import csv
import json
import os
import re
import sys

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
os.chdir(KIT)
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import predict as P  # noqa: E402
from experiments import EXPERIMENTS  # noqa: E402

OUT = os.path.join(HERE, "paper_figs")
os.makedirs(OUT, exist_ok=True)
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.family": ["Malgun Gothic", "DejaVu Sans"], "axes.unicode_minus": False, "font.size": 9,
                     "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.facecolor": SURF, "figure.facecolor": "white", "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 2})
AG = list(EXPERIMENTS["E2"]["agents"])
FIT = [c for c in EXPERIMENTS["E2"]["conds"] if c != "BASE"]
A_REG, B_REG = 0.14380045578818365, 0.05309285306453424


def read(p):
    return list(csv.DictReader(open(p, encoding="utf-8")))


def table(path, conds, extra=None):
    by = collections.defaultdict(list)
    for p in [path] + (extra or []):
        for r in read(p):
            if r["target"] == "":
                by[(r["cond"], r["salt"])].append(r)
    seeds = sorted({s for (c, s) in by if c in conds}, key=lambda x: int(x.rsplit("-", 1)[1]))
    t = P.Table(by, conds, "BASE", seeds, AG)
    return t, seeds


def mark(ax, x, y, kind, label=None):
    style = {"osc": dict(marker="o", color=C1), "slug": dict(marker="^", color=C2)}[kind]
    ax.scatter(x, y, s=46, edgecolors="white", linewidths=1.5, zorder=4, label=label, **style)


# ---------------------------------------------------------------- 그림 3
def fig3():
    t, seeds = table(os.path.join(KIT, "out", "main", "games.csv"), FIT)
    v = t.pick(seeds)
    rng = np.random.default_rng(0)
    xs = np.linspace(0, 11, 100)
    lines = []
    for _ in range(500):
        vb = t.pick(list(rng.choice(seeds, len(seeds))))
        b, a = np.polyfit([vb[c][0] for c in FIT], [vb[c][1] for c in FIT], 1)
        lines.append(a + b * xs)
    lo, hi = np.percentile(lines, [2.5, 97.5], axis=0)
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.6), gridspec_kw={"width_ratios": [2.2, 1]})
    ax.fill_between(xs, lo, hi, color=C1, alpha=0.15, linewidth=0)
    ax.plot(xs, A_REG + B_REG * xs, color=C1, label="등록 직선 D = 0.144 + 0.053·mae")
    for f, mk in (("25", "o"), ("12", "s"), ("5", "D")):
        cs = [c for c in FIT if c.startswith(f"F{f}_")]
        ax.scatter([v[c][0] for c in cs], [v[c][1] for c in cs], marker=mk, s=40, color=C1, edgecolors="white", linewidths=1.3,
                   zorder=4, label=f"필터 {f} Hz × 지연")
    ax.axhline(0.460, color=INK2, linestyle="--", linewidth=1)
    ax.text(0.2, 0.47, "무상관 상한 0.460", color=INK2, fontsize=8)
    ax.set_xlabel("교전 중 피치 추종 오차 mae [°/s]")
    ax.set_ylabel("결과 변화율 D")
    ax.set_title("(a) 적합 집합 20조건 (원래 구성)", loc="left", fontsize=9, color=INK)
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    names = ["등록 직선\n(mae 사용)", "상수\n(약한 열화 평균)", "상수\n(E2 절편)"]
    vals = [0.041, 0.068, 0.074]
    bars = ax2.bar(range(3), vals, color=[C1, "#b5b3ad", "#b5b3ad"], width=0.6, edgecolor="white", linewidth=2)
    for i, val in enumerate(vals):
        ax2.text(i, val + 0.002, f"{val:.3f}", ha="center", fontsize=8, color=INK)
    ax2.set_xticks(range(3)); ax2.set_xticklabels(names, fontsize=7.5)
    ax2.set_ylabel("처음 보는 원인 22조건의 예측 RMS")
    ax2.set_title("(b) 기준선 대비 (기술 점수 0.44)", loc="left", fontsize=9, color=INK)
    ax2.grid(axis="x", visible=False)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig3_curve.png"), dpi=200)


# ---------------------------------------------------------------- 그림 4
def fig4():
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.5), sharey=True)
    # (a) P4 새 시드, 원래 구성, κ
    t, seeds = table(os.path.join(KIT, "out", "rep", "games.csv"), ["R_kappa_50", "R_kappa_100", "F25_D0.5", "F5_D2", "R_sigma_dps_6"])
    v = t.pick(seeds)
    xs = np.linspace(0, 3, 50)
    ax = axes[0]
    ax.plot(xs, A_REG + B_REG * xs, color=INK2, linewidth=1.5, label="기준 직선")
    mark(ax, [v[c][0] for c in ("F25_D0.5", "F5_D2", "R_sigma_dps_6")], [v[c][1] for c in ("F25_D0.5", "F5_D2", "R_sigma_dps_6")], "osc", "진동형")
    mark(ax, [v[c][0] for c in ("R_kappa_50", "R_kappa_100")], [v[c][1] for c in ("R_kappa_50", "R_kappa_100")], "slug", "둔한 형")
    for c, lab in (("R_kappa_50", "κ 50"), ("R_kappa_100", "κ 100")):
        ax.annotate(lab, (v[c][0], v[c][1]), xytext=(6, 2), textcoords="offset points", fontsize=8, color=INK)
    ax.set_title("(a) 원래 구성, 새 시드\n잔차 차이 +0.060", loc="left", fontsize=9, color=INK)
    # (b) P7 실제형, κ
    p7 = json.load(open(os.path.join(HERE, "p7_results.json"), encoding="utf-8"))["conds"]
    dl = ["F25_D2", "F25_D4", "F25_D6", "F25_D8", "F25_D10", "F25_D12"]
    b7, a7 = np.polyfit([p7[c]["mae"] for c in dl], [p7[c]["D"] for c in dl], 1)
    ax = axes[1]
    xs = np.linspace(0, 15, 50)
    ax.plot(xs, a7 + b7 * xs, color=INK2, linewidth=1.5)
    mark(ax, [p7[c]["mae"] for c in dl], [p7[c]["D"] for c in dl], "osc")
    xs = np.linspace(0, 6, 50)
    mark(ax, [p7[c]["mae"] for c in ("R_kappa_25", "R_kappa_50")], [p7[c]["D"] for c in ("R_kappa_25", "R_kappa_50")], "slug")
    for c, lab, off in (("R_kappa_25", "κ 25", (-12, -15)), ("R_kappa_50", "κ 50", (6, 2))):
        ax.annotate(lab, (p7[c]["mae"], p7[c]["D"]), xytext=off, textcoords="offset points", fontsize=8, color=INK)
    ax.set_title("(b) 실제형 구성\n잔차 차이 +0.172", loc="left", fontsize=9, color=INK)
    # (c) P8 실제형, κ 아님, 새 시드
    p8 = json.load(open(os.path.join(HERE, "p8_results.json"), encoding="utf-8"))
    cd = p8["conds"]
    a8, b8 = p8["line"]
    ax = axes[2]
    ax.plot(xs, a8 + b8 * xs, color=INK2, linewidth=1.5)
    mark(ax, [cd[c][0] for c in ("F25_D6", "F25_D8")], [cd[c][1] for c in ("F25_D6", "F25_D8")], "osc")
    mark(ax, [cd[c][0] for c in ("CMD48", "R_kq_0.25")], [cd[c][1] for c in ("CMD48", "R_kq_0.25")], "slug")
    for c, lab, off in (("CMD48", "명령 지연 0.4 s", (7, -6)), ("R_kq_0.25", "k_q 0.25", (6, 2))):
        ax.annotate(lab, (cd[c][0], cd[c][1]), xytext=off, textcoords="offset points", fontsize=8, color=INK)
    ax.set_title("(c) 실제형, κ가 아닌 원인, 새 시드\n잔차 차이 +0.330", loc="left", fontsize=9, color=INK)
    for ax in axes:
        ax.set_xlabel("mae [°/s]")
    axes[0].set_ylabel("결과 변화율 D")
    axes[0].legend(fontsize=7.5, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig4_error_type.png"), dpi=200)


# ---------------------------------------------------------------- 그림 6
def fig6():
    t, seeds = table(os.path.join(KIT, "out", "main", "games.csv"), FIT)
    v = t.pick(seeds)
    p7 = json.load(open(os.path.join(HERE, "p7_results.json"), encoding="utf-8"))["conds"]
    dl = ["F25_D2", "F25_D4", "F25_D6", "F25_D8", "F25_D10", "F25_D12"]
    b7, a7 = np.polyfit([p7[c]["mae"] for c in dl], [p7[c]["D"] for c in dl], 1)
    fig, ax = plt.subplots(figsize=(5.6, 3.7))
    xs = np.linspace(0, 15, 100)
    ax.plot(xs[xs <= 10.6], (A_REG + B_REG * xs)[xs <= 10.6], color=C1, label="원래 구성 (기울기 0.053)")
    ax.scatter([v[c][0] for c in FIT], [v[c][1] for c in FIT], marker="o", s=34, color=C1, edgecolors="white", linewidths=1.2, zorder=4)
    ax.plot(xs, a7 + b7 * xs, color=C3, label="실제형 구성 (기울기 0.022)")
    ax.scatter([p7[c]["mae"] for c in dl], [p7[c]["D"] for c in dl], marker="s", s=38, color=C3, edgecolors="white", linewidths=1.2, zorder=4)
    for c, lab, off in (("F25_D4", "2·4틱", (9, -3)), ("F25_D8", "8틱", (6, -13)), ("F25_D12", "12틱", (-10, -15))):
        ax.annotate(lab, (p7[c]["mae"], p7[c]["D"]), xytext=off, textcoords="offset points", fontsize=7.5, color=INK2)
    ax.axvspan(4.4, 5.0, color=GRID, alpha=0.8, zorder=0)
    ax.text(10.6, 0.235, "음영: 같은 mae ≈ 4.7에서\nD 0.39(원래) 대 0.26(실제형)", fontsize=7.5, color=INK2)
    ax.set_xlabel("mae [°/s]"); ax.set_ylabel("결과 변화율 D")
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig6_configs.png"), dpi=200)


# ---------------------------------------------------------------- 그림 7
def fig7():
    txt = open(os.path.join(KIT, "out", "extra_report", "report_extra.md"), encoding="utf-8").read()
    orig = collections.defaultdict(dict)
    for m in re.finditer(r"^\| (SHAM|F25_D[\d.]+) \| (GunTracker|Extender) \| ([\d.]+) → ([\d.]+) \| ([+-][\d.]+) \[([+-][\d.]+), ([+-][\d.]+)\]", txt, re.M):
        c, t, m0, m1, d, lo, hi = m.groups()
        orig[t][c] = (float(m1), float(d), float(lo), float(hi))
    real = json.load(open(os.path.join(HERE, "p9c_results.json"), encoding="utf-8"))
    rtxt = open(os.path.join(HERE, "p9c_output.md"), encoding="utf-8").read()
    rci = {}
    for m in re.finditer(r"^\| (GunTracker|Extender) \| (F25_D\d+) \| ([\d.]+) \| ([+-][\d.]+) \[([+-][\d.]+), ([+-][\d.]+)\]", rtxt, re.M):
        t, c, mae, d, lo, hi = m.groups()
        rci[(t, c)] = (float(mae), float(d), float(lo), float(hi))
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.6), sharey=True)
    for ax, t in zip(axes, ("GunTracker", "Extender")):
        ax.axhspan(-11.1, 11.1, color=GRID, alpha=0.6, zorder=0)
        ax.axhline(0, color=INK2, linewidth=0.8)
        o = sorted((v for c, v in orig[t].items() if c != "SHAM"), key=lambda x: x[0])
        ax.errorbar([x[0] for x in o], [x[1] for x in o], yerr=[[x[1] - x[2] for x in o], [x[3] - x[1] for x in o]],
                    color=C1, marker="o", markersize=6, markeredgecolor="white", capsize=0, elinewidth=1.2, label="원래 구성 (지연 0.5–6틱)")
        r = sorted((v for (tt, c), v in rci.items() if tt == t), key=lambda x: x[0])
        ax.errorbar([x[0] for x in r], [x[1] for x in r], yerr=[[x[1] - x[2] for x in r], [x[3] - x[1] for x in r]],
                    color=C3, marker="s", markersize=6, markeredgecolor="white", capsize=0, elinewidth=1.2, label="실제형 구성 (지연 6–12틱)")
        ax.set_title(f"열화한 기체: {t}", loc="left", fontsize=9, color=INK)
        ax.set_xlabel("열화한 기체의 mae [°/s]")
    axes[0].set_ylabel("그 기체의 Δ점수 (리그 한 바퀴, 98.33 % 구간)")
    axes[0].text(9.0, 12.5, "실용 기준 ±11.1점", fontsize=7.5, color=INK2)
    axes[0].legend(fontsize=7.5, frameon=False, loc="upper left", bbox_to_anchor=(0, 0.92))
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig7_asym.png"), dpi=200)


if __name__ == "__main__":
    fig3(); fig4(); fig6(); fig7()
    print("done", os.listdir(OUT))
