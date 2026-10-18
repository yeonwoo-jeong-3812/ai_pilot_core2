"""원인 무관성 점검: 열화 원인이 달라도 추종 오차가 같으면 교전 결과 변화도 같은가.

  python route.py      # out/feas2 의 DOSE(필터·비동기 지연) + ROUTE(κ, k_q, 잡음, 동기 지연)

기준 곡선은 필터·비동기 지연 조건으로만 맞춘다(y = a + b·mae, 최소제곱).
다른 원인의 조건이 그 곡선에서 얼마나 벗어나는지(잔차)를 보고, 잔차가 필터·지연 조건끼리의 흩어짐보다 큰지 비교한다.
결과 변화 지표 두 개:
  D = 1 − 경기 일치율 (기준 F25_D0 과 승자·종료 사유가 다른 경기의 비율)
  M = 참가자별 |Δ점수| 평균 [점/리그 한 바퀴]
"""
from __future__ import annotations

import collections
import csv
import json
import os
import sys

import numpy as np
from scipy.stats import spearmanr

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
from analyze import points  # noqa: E402
from experiments import EXPERIMENTS, ROUTE  # noqa: E402

OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def main():
    agents = list(EXPERIMENTS["DOSE"]["agents"])
    conds = set(EXPERIMENTS["DOSE"]["conds"]) | set(EXPERIMENTS["ROUTE"]["conds"])
    with open(os.path.join(KIT, "out", "feas2", "games.csv"), encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["cond"] in conds]
    by = collections.defaultdict(list)
    for r in rows:
        by[r["cond"]].append(r)
    salts = sorted({r["salt"] for r in rows})
    key = lambda g: (g["blue"], g["red"], g["scenario"], g["salt"])
    ref = "F25_D0"
    refg = {key(g): g for g in by[ref]}

    def salt_pts(c):
        return np.array([[points([g for g in by[c] if g["salt"] == s], agents)[0][a] for a in agents]
                         for s in salts], float)

    ref_pts = salt_pts(ref)

    def measure(c):
        gs = by[c]
        D = 1 - np.mean([(g["winner"], g["condition"]) == (refg[key(g)]["winner"], refg[key(g)]["condition"])
                         for g in gs])
        M = float(np.abs((salt_pts(c) - ref_pts).mean(0)).mean())
        mae = float(np.mean([float(g[k]) for g in gs for k in ("blue_mae_q_dps", "red_mae_q_dps")]))
        return mae, float(D), M

    pts = []
    for c in sorted(by):
        if c == ref:
            continue
        if c.startswith("F"):
            route = f"필터 {c.split('_')[0][1:]} Hz + 비동기 지연"
        elif c == "SHAM":
            route = "SHAM"
        else:
            route = c[2:].rsplit("_", 1)[0]       # "R_sigma_dps_1" -> "sigma_dps"
        mae, D, M = measure(c)
        pts.append(dict(cond=c, route=route, mae=mae, D=D, M=M, base=c.startswith("F")))
    base = [p for p in pts if p["base"]]
    say("# 원인 무관성 점검 (탐색 데이터, 시드 2개)\n")
    say(f"기준 조건 {ref}. 기준 곡선은 필터·비동기 지연 {len(base)}개 조건으로 맞췄다.\n")
    say("| 지표 | 기준 곡선 | 필터·지연 조건의 잔차 RMS | Spearman ρ (전체 조건, mae 대 지표) |")
    say("|---|---|---|---|")
    fit = {}
    for y in ("D", "M"):
        b, a = np.polyfit([p["mae"] for p in base], [p[y] for p in base], 1)
        fit[y] = (a, b)
        rms = float(np.sqrt(np.mean([(p[y] - (a + b * p["mae"])) ** 2 for p in base])))
        fit[y + "_rms"] = rms
        rho = spearmanr([p["mae"] for p in pts], [p[y] for p in pts]).statistic
        say(f"| {y} | {y} = {a:.3f} + {b:.3f}·mae | {rms:.3f} | {rho:.3f} |")
    say()
    say("## 다른 원인의 조건 (잔차 = 실제 − 기준 곡선 예측, 괄호는 잔차 / 필터·지연 잔차 RMS)\n")
    say("| 조건 | 원인 | 추종 오차 [°/s] | D | D 잔차 | M [점] | M 잔차 |")
    say("|---|---|---|---|---|---|---|")
    for p in pts:
        if p["base"]:
            continue
        rd = p["D"] - (fit["D"][0] + fit["D"][1] * p["mae"])
        rm = p["M"] - (fit["M"][0] + fit["M"][1] * p["mae"])
        p["rD"], p["rM"] = rd, rm
        say(f"| {p['cond']} | {p['route']} | {p['mae']:.2f} | {p['D']:.3f} | {rd:+.3f} ({rd / fit['D_rms']:+.1f}) | "
            f"{p['M']:.2f} | {rm:+.2f} ({rm / fit['M_rms']:+.1f}) |")
    say()
    for r in ROUTE:
        ps = [p for p in pts if p["route"] == r]
        say(f"{r}: 평균 D 잔차 {np.mean([p['rD'] for p in ps]):+.3f}, 평균 M 잔차 {np.mean([p['rM'] for p in ps]):+.2f}")
    with open(os.path.join(KIT, "out", "feas2", "report_ROUTE.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")
    with open(os.path.join(KIT, "out", "feas2", "route_points.json"), "w", encoding="utf-8") as f:
        json.dump(pts, f, ensure_ascii=False, indent=1)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    groups = collections.OrderedDict()
    for p in pts:
        groups.setdefault(p["route"], []).append(p)
    marks = dict(zip(groups, "osD^v<>Px*"))
    for i, (y, lab) in enumerate((("D", "D = 1 - 경기 일치율"), ("M", "M = 평균 |Δ점수| [점]"))):
        for g, ps in groups.items():
            ax[i].scatter([p["mae"] for p in ps], [p[y] for p in ps], marker=marks[g], label=g, s=28)
        xs = np.linspace(0, max(p["mae"] for p in pts), 50)
        ax[i].plot(xs, fit[y][0] + fit[y][1] * xs, "k--", lw=0.8, label="기준 곡선 (필터·지연)")
        ax[i].set_xlabel("교전 중 피치 추종 오차 [°/s]"); ax[i].set_ylabel(lab)
    ax[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(KIT, "out", "feas2", "route.png"), dpi=130)
    print("그림:", os.path.join(KIT, "out", "feas2", "route.png"))


if __name__ == "__main__":
    main()
