"""용량-반응 분석: 지연 × 필터가 추종과 교전 결과에 주는 영향을 무차원 지연 x = τ·f_c 위에서 본다.

  python dose.py               # out/feas2/games.csv → out/feas2/report_DOSE.md, dose.png
  python dose.py --prefix X    # 다른 시드 접두어

질문 세 가지:
  1. 필터 세 개의 곡선이 x 축에서 한 곡선으로 겹치는가 (붕괴가 τ·f_c 로 정해지는가)
  2. 추종과 교전 결과가 같은 x 에서 꺾이는가 (분절 회귀의 분절점)
  3. 그 분절점이 교전을 보기 전에 벤치로 정한 예측(out/margin/bench_summary.json)과 맞는가
교전 결과 지표 M = 참가자별 |Δ점수| 의 평균 (같은 필터의 지연 0 대비, 리그 한 바퀴당).
"""
from __future__ import annotations

import collections
import csv
import json
import os
import sys

import numpy as np

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
from analyze import points, END_CAUSES  # noqa: E402
from experiments import EXPERIMENTS, DOSE_FILTERS, DOSE_DELAYS  # noqa: E402

DT = 1.0 / 120.0
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def hinge_fit(x, y):
    """y = a + b·max(0, x − x0). x0 격자 탐색. 반환 (x0, a, b, sse, 직선 sse)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    best = None
    for x0 in np.linspace(x.min(), np.percentile(x, 90), 400):
        X = np.c_[np.ones_like(x), np.maximum(0, x - x0)]
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        sse = float(np.sum((X @ coef - y) ** 2))
        if best is None or sse < best[3]:
            best = (float(x0), float(coef[0]), float(coef[1]), sse)
    Xl = np.c_[np.ones_like(x), x]
    cl, *_ = np.linalg.lstsq(Xl, y, rcond=None)
    return best + (float(np.sum((Xl @ cl - y) ** 2)),)


def main():
    prefix = sys.argv[sys.argv.index("--prefix") + 1] if "--prefix" in sys.argv else "feas2"
    exp = EXPERIMENTS["DOSE"]
    agents = list(exp["agents"])
    path = os.path.join(KIT, "out", prefix, "games.csv")
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["cond"] in exp["conds"]]
    by = collections.defaultdict(list)
    for r in rows:
        by[r["cond"]].append(r)
    salts = sorted({r["salt"] for r in rows})
    key = lambda g: (g["blue"], g["red"], g["scenario"], g["salt"])

    def salt_pts(c):
        return np.array([[points([g for g in by[c] if g["salt"] == s], agents)[0][a] for a in agents]
                         for s in salts], float)

    def cell(c, ref):
        d = (salt_pts(c) - salt_pts(ref)).mean(0)          # 참가자별 평균 Δ점수
        refg = {key(g): g for g in by[ref]}
        agree = np.mean([(g["winner"], g["condition"]) == (refg[key(g)]["winner"], refg[key(g)]["condition"])
                         for g in by[c]])
        mae = np.mean([float(g[k]) for g in by[c] for k in ("blue_mae_q_dps", "red_mae_q_dps")])
        corr = np.nanmean([float(g[k]) for g in by[c] for k in ("blue_corr_q", "red_corr_q")])
        ends = collections.Counter(g["condition"] for g in by[c])
        return d, agree, mae, corr, ends

    say("# DOSE 보고서 (탐색 데이터, 판정 없음)\n")
    say(f"경기 {len(rows)}, 시드 {len(salts)}개 {salts}, 참가자 {len(agents)}명. "
        "x = τ·f_c (τ = 지연 [s], f_c = 필터 [Hz]). M = 참가자별 |Δ점수| 평균 [점/리그 한 바퀴], 기준은 같은 필터의 지연 0.\n")
    d_s, a_s, *_ = cell("SHAM", "F25_D0")
    say(f"잡음 바닥 (SHAM vs F25_D0): M = {np.abs(d_s).mean():.2f}, 경기 일치율 {a_s:.3f}\n")

    table = []
    for fc in DOSE_FILTERS:
        ref = f"F{fc:g}_D0"
        for dl in DOSE_DELAYS:
            c = f"F{fc:g}_D{dl:g}"
            if c not in by:
                continue
            d, agree, mae, corr, ends = cell(c, ref)
            n = len(by[c])
            table.append(dict(fc=fc, delay=dl, x=dl * DT * fc, M=float(np.abs(d).mean()),
                              maxd=float(np.abs(d).max()), agree=float(agree), mae=float(mae),
                              corr=float(corr), hard=ends["hard_deck"] / n, kill=ends["health_zero"] / n,
                              d={a: float(v) for a, v in zip(agents, d)}))
    # 필터 25 Hz 지연 0 대비 F12/F5 지연 0 의 점수 차 (필터 자체의 영향)
    for fc in DOSE_FILTERS[1:]:
        d, agree, *_ = cell(f"F{fc:g}_D0", "F25_D0")
        say(f"필터 자체의 영향 F{fc:g}_D0 vs F25_D0: M = {np.abs(d).mean():.2f}, 경기 일치율 {agree:.3f}")
    say()

    say("## 1. 조건별 결과\n")
    say("| 필터 [Hz] | 지연 [틱] | x = τ·f_c | 피치 추종 오차 [°/s] | 추종 상관 | M [점] | 최대 \\|Δ점수\\| | 경기 일치율 | 격추 비율 | 저고도 이탈 비율 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for t in table:
        say(f"| {t['fc']:g} | {t['delay']:g} | {t['x']:.3f} | {t['mae']:.2f} | {t['corr']:.3f} | {t['M']:.2f} | "
            f"{t['maxd']:.1f} | {t['agree']:.3f} | {t['kill']:.2f} | {t['hard']:.2f} |")
    say()

    say("## 2. 분절 회귀 (y = a + b·max(0, x − x₀))\n")
    say("| 지표 | 묶음 | x₀ | 분절 SSE / 직선 SSE |")
    say("|---|---|---|---|")
    fits = {}
    for name, ylab in (("mae", "추종 오차"), ("M", "교전 M")):
        for grp in ("전체",) + DOSE_FILTERS:
            ts = table if grp == "전체" else [t for t in table if t["fc"] == grp]
            x0, a, b, sse, sse_lin = hinge_fit([t["x"] for t in ts], [t[name] for t in ts])
            fits[(name, grp)] = x0
            say(f"| {ylab} | {grp if grp == '전체' else f'{grp:g} Hz'} | {x0:.3f} | {sse / max(sse_lin, 1e-12):.2f} |")
    say()
    bench = os.path.join(KIT, "out", "margin", "bench_summary.json")
    if os.path.isfile(bench):
        bs = [b for b in json.load(open(bench, encoding="utf-8")) if b["fc"] in DOSE_FILTERS and b["crit_ticks"]]
        xs = [b["crit_ticks"] * DT * b["fc"] for b in bs]
        say(f"벤치 사전 예측 (교전 전, 필터 {', '.join(f'{f:g}' for f in DOSE_FILTERS)} Hz × 비행점 3곳): "
            f"임계 x = {min(xs):.3f} – {max(xs):.3f}, 중앙값 {np.median(xs):.3f}\n")

    say("## 3. 참가자별 Δ점수 (붕괴 뒤 방향이 전술마다 다른가)\n")
    say("| 조건 | " + " | ".join(agents) + " |")
    say("|---|" + "---|" * len(agents))
    for t in table:
        if t["delay"] in (1.0, 2.0, 4.0, 6.0):
            say(f"| F{t['fc']:g}_D{t['delay']:g} | " + " | ".join(f"{t['d'][a]:+.1f}" for a in agents) + " |")
    say()

    with open(os.path.join(KIT, "out", prefix, "report_DOSE.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")
    with open(os.path.join(KIT, "out", prefix, "dose_table.json"), "w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, indent=1)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
    for fc, mk in zip(DOSE_FILTERS, "osD"):
        ts = [t for t in table if t["fc"] == fc]
        for i, (k, lab) in enumerate((("mae", "피치 추종 오차 [°/s]"), ("M", "M = 평균 |Δ점수| [점]"),
                                      ("agree", "경기 일치율"))):
            ax[i].plot([t["x"] for t in ts], [t[k] for t in ts], marker=mk, label=f"{fc:g} Hz")
            ax[i].set_xlabel("x = τ·f_c"); ax[i].set_ylabel(lab)
    if os.path.isfile(bench):
        for a in ax:
            a.axvspan(min(xs), max(xs), color="0.85", zorder=0, label="벤치 예측 범위")
    ax[1].axhline(np.abs(d_s).mean(), ls="--", c="k", lw=0.8, label="SHAM 바닥")
    ax[2].axhline(a_s, ls="--", c="k", lw=0.8)
    ax[0].legend(fontsize=8); ax[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(KIT, "out", prefix, "dose.png"), dpi=130)
    print("그림:", os.path.join(KIT, "out", prefix, "dose.png"))


if __name__ == "__main__":
    main()
