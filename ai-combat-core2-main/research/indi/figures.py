"""논문 그림 4종 → results/indi/fig/*.png (300 dpi, 인쇄용 라이트 모드).

  fig1_pareto        E4 전 평가점 (J/J$_0$, A/A$_0$) + 비지배 전선 + 기준·선택해
  fig2_winrate       조건별 승률(Wilson 95% CI) — 기준 vs γ=0 vs γ=0.3 (E3 명목 + E5 7조건)
  fig3_delay         측정 지연에 따른 ΔG 더블릿 추종 ISE (E1 벤치, 로그 축) — 지연 강건성 메커니즘
  fig4_sensitivity   E2 단일 변수: 윗줄 추종 J/J₀, 아랫줄 Δ승점(부트스트랩 95% CI)

색: 범주 슬롯 1 파랑 #2a78d6 (γ=0), 슬롯 2 주황 #eb6834 (γ=0.3) — dataviz validate_palette PASS
(CVD ΔE 24.7). 기준은 중립 회색(비교 기준선, 범주 슬롯 아님).

    python research/indi/figures.py
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duel import wilson
from sweep import _points, LEVELS, BASE

RES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "results", "indi"))
FIG = os.path.join(RES, "fig")
C_G0, C_G03, C_BASE = "#2a78d6", "#eb6834", "#8a8985"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"
LABEL = {"A": "기준 INDI", "g0": "튜닝 γ=0 (성능형)", "g0.3": "튜닝 γ=0.3 (절충형)"}
COLOR = {"A": C_BASE, "g0": C_G0, "g0.3": C_G03}

plt.rcParams.update({
    "font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 9,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF,
    "axes.facecolor": SURF, "legend.frameon": False, "savefig.dpi": 300, "savefig.bbox": "tight",
})


def _load(name):
    return json.load(open(os.path.join(RES, name), encoding="utf-8"))


def _save(fig, name):
    os.makedirs(FIG, exist_ok=True)
    fig.savefig(os.path.join(FIG, name + ".png"))
    plt.close(fig)
    print("saved", name)


def fig1_pareto():
    d = _load("e4.json")
    j0, a0 = d["ref"]["J"], d["ref"]["A"]
    J = np.array([e["J"] / j0 for e in d["log"]])
    A = np.array([e["A"] / a0 for e in d["log"]])
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    ax.scatter(A, J, s=8, color=C_BASE, alpha=0.25, linewidths=0, label=f"PSO 평가점 (n={len(J)})")
    front = sorted(d["pareto"], key=lambda p: p["A_ratio"])
    ax.plot([p["A_ratio"] for p in front], [p["J_ratio"] for p in front], color=INK, lw=2,
            label="파레토 전선")
    ax.scatter([1], [1], s=60, color=C_BASE, edgecolor=SURF, linewidth=2, zorder=5)
    ax.annotate("기준 INDI", (1, 1), xytext=(-8, 8), textcoords="offset points", ha="right", color=INK)
    for g, key in ((0.0, "g0"), (0.3, "g0.3")):
        e = min((e for e in d["log"] if e["gamma"] == g), key=lambda e: e["cost"])
        x, y = e["A"] / a0, e["J"] / j0
        ax.scatter([x], [y], s=60, color=COLOR[key], edgecolor=SURF, linewidth=2, zorder=6)
        ax.annotate(LABEL[key], (x, y), xytext=(10, -4) if key == "g0" else (6, 12),
                    textcoords="offset points", color=INK, va="center")
    ax.set_xlabel("조종면 활동량 A / A$_0$ (낮을수록 부드러움)")
    ax.set_ylabel("추종 오차 J / J$_0$ (낮을수록 정확)")
    ax.set_ylim(0.85, 1.6)
    ax.set_xlim(0, 1.3)
    ax.set_title("그림 1. E4 복합 최적화 — 추종 오차 대 조종 부드러움", loc="left", color=INK)
    ax.legend(loc="upper right")
    _save(fig, "fig1_pareto")


def fig2_winrate():
    e3, e5 = _load("e3_nominal.json"), _load("e5.json")
    conds = [("nominal", "명목", e3)] + [(c, lab, e5) for c, lab in (
        ("stress", "잡음 0.3°/s"), ("delay30", "지연 33 ms"), ("delay90", "지연 92 ms"),
        ("g0_lo", "G0 ×0.7"), ("g0_hi", "G0 ×1.3"), ("turb", "난류"), ("mc", "몬테카를로"))]
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    off = {"A": -0.22, "g0": 0.0, "g0.3": 0.22}
    for i, (c, lab, src) in enumerate(conds):
        block = src["conds"][c]
        for key in ("A", "g0", "g0.3"):
            games = block["games_A"] if key == "A" else block[key]["games"]
            k, n = sum(_points(g) for g in games), len(games)
            lo, hi = wilson(k, n)
            y = len(conds) - 1 - i + off[key]
            ax.plot([lo, hi], [y, y], color=COLOR[key], lw=2, solid_capstyle="round")
            ax.scatter([k / n], [y], s=36, color=COLOR[key], edgecolor=SURF, linewidth=1.5, zorder=5,
                       label=LABEL[key] if i == 0 else None)
    ax.axvline(0.5, color=INK2, lw=1, ls=(0, (3, 3)))
    ax.set_yticks(range(len(conds)))
    ax.set_yticklabels([lab for _, lab, _ in conds][::-1])
    ax.set_xlim(0.2, 1.0)
    ax.set_xlabel("승률 (승 1 · 무 0.5 · 패 0), Wilson 95% 신뢰구간")
    ax.grid(axis="y", visible=False)
    ax.set_title("그림 2. 평가 조건별 교전 승률 (E3 명목 n=325, E5 조건별 n=100)", loc="left", color=INK)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3)
    _save(fig, "fig2_winrate")


def _delay_bench():
    """지연별 벤치 — 무거우므로 results/indi/delay_bench.json 에 캐시."""
    path = os.path.join(RES, "delay_bench.json")
    if os.path.isfile(path):
        return json.load(open(path, encoding="utf-8"))
    from runner import pmap
    jobs = [(k, dly) for dly in (0, 4, 11) for k in ("A", "g0", "g0.3")]
    rows = pmap(_delay_job, jobs, 3)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    return rows


def _delay_job(job):
    from bench import evaluate
    from aircombat.control.indi import INDIConfig, SensorConfig
    key, dly = job
    e4 = _load("e4.json")
    cfg = INDIConfig() if key == "A" else INDIConfig(**next(
        b["cfg"] for b in e4["best"] if abs(b["gamma"] - (0.0 if key == "g0" else 0.3)) < 1e-9))
    r = evaluate(cfg, SensorConfig("gyro", 0.1, dly))
    return dict(key=key, delay_ticks=dly, J=r["J"], by_test=r["by_test"])


def fig3_delay():
    rows = _delay_bench()
    fig, ax = plt.subplots(figsize=(4.8, 3.4))
    for key in ("A", "g0", "g0.3"):
        pts = sorted((r["delay_ticks"] / 120 * 1000, r["by_test"]["q_dbl"]) for r in rows if r["key"] == key)
        x, y = zip(*pts)
        ax.plot(x, y, color=COLOR[key], lw=2, marker="o", ms=6, mec=SURF, mew=1.5, label=LABEL[key])
        ax.annotate(f"{y[-1]:.1f}", (x[-1], y[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", color=INK2)
    ax.set_yscale("log")
    ax.set_yticks([0.1, 0.3, 1, 3, 10])
    ax.set_yticklabels(["0.1", "0.3", "1", "3", "10"])
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_xticks([0, 33, 92])
    ax.set_xlabel("각속도 측정 지연 [ms] (실기 30–90 ms)")
    ax.set_ylabel("ΔG 더블릿 정규화 ISE (로그)")
    ax.set_title("그림 3. 측정 지연 대 피치 추종 오차 (E1 벤치)", loc="left", color=INK)
    ax.legend(loc="lower right")
    _save(fig, "fig3_delay")


def fig4_sensitivity():
    d = _load("e2.json")
    names = {"k_p": "k_p [1/s]", "k_q": "k_q [1/s]", "filt_hz": "f_c [Hz]", "k_att": "k_att [1/s]",
             "k_ff": "k_ff", "lam": "λ"}
    base = next(r for r in d["rows"] if r["var"] == "baseline")
    fig, axes = plt.subplots(2, 6, figsize=(11, 4.2), sharey="row")
    for j, var in enumerate(LEVELS):
        pts = [(getattr(BASE, var), 1.0, base["duel"])] + \
              [(r["value"], r["J_ratio"], r["duel"]) for r in d["rows"] if r["var"] == var]
        pts.sort(key=lambda t: t[0])
        x = [p[0] for p in pts]
        top, bot = axes[0, j], axes[1, j]
        top.plot(x, [p[1] for p in pts], color=C_G0, lw=2, marker="o", ms=5, mec=SURF, mew=1)
        clip = [(p[0], p[1]) for p in pts if p[1] >= 3.0]
        if clip:
            top.scatter(*zip(*clip), marker="^", s=40, color=C_G0, zorder=5)
        top.axhline(1.0, color=INK2, lw=1, ls=(0, (3, 3)))
        top.set_title(names[var], color=INK, fontsize=9)
        dp = [p[2]["d_points"] for p in pts]
        lo = [p[2]["d_points"] - p[2]["d_points_ci"][0] if p[2]["n"] and p[2]["d_points_ci"][0] == p[2]["d_points_ci"][0] else 0 for p in pts]
        hi = [p[2]["d_points_ci"][1] - p[2]["d_points"] if p[2]["n"] and p[2]["d_points_ci"][1] == p[2]["d_points_ci"][1] else 0 for p in pts]
        bot.errorbar(x, dp, yerr=[lo, hi], color=C_G0, lw=2, marker="o", ms=5, mec=SURF, mew=1,
                     capsize=0, elinewidth=1.5)
        bot.axhline(0.0, color=INK2, lw=1, ls=(0, (3, 3)))
        if var == "filt_hz":
            top.set_xscale("log"); bot.set_xscale("log")
            for a in (top, bot):
                a.set_xticks([3, 6, 12, 25, 40]); a.set_xticklabels(["3", "6", "12", "25", "40"])
                a.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    axes[0, 0].set_ylabel("추종 J / J$_0$")
    axes[1, 0].set_ylabel("Δ승점 (95% CI)")
    fig.suptitle("그림 4. E2 단일 변수 민감도 — 윗줄 추종 오차(▲ 발산, 3.0 절단), 아랫줄 교전 Δ승점(수준별 n=50); 나머지 변수는 기준값 고정", x=0.01, ha="left", color=INK)
    fig.tight_layout()
    _save(fig, "fig4_sensitivity")


if __name__ == "__main__":
    fig1_pareto()
    fig2_winrate()
    fig3_delay()
    fig4_sensitivity()
