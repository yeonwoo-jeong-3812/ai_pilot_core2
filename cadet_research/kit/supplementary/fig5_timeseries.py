"""그림 5: 같은 추종 오차, 다른 응답 — 둔한 형(κ 100)과 진동형(σ 6)의 피치 명령·응답 시계열 (서술, 판정 없음).

  python supplementary/fig5_timeseries.py          # 3경기 재생(약 1분). 원자료와 같은 경기일 때만 fig5_timeseries.csv, fig5_output.md, 그림을 쓴다
  python supplementary/fig5_timeseries.py --plot   # 재생 없이 저장된 시계열로 그림만

조건: BASE, R_kappa_100(둔한 형, P3 조건 mae 1.64), R_sigma_dps_6(진동형, 1.62). 둘 다 P4 T-D의 유형 대비에 쓴 조건이고
그 대비 조건(둔한 κ 50·100, 진동형 F25_D0.5·F5_D2·σ 6) 중 조건 mae가 가장 가까운 짝이다.
경기 선택 규칙(결과를 보지 않음): P3 재생 자료(main-0, neutral, 56대진)에서 세 조건 모두 청 기체가 60 s 이상 비행한 대진 중,
청 기체의 경기 mae가 두 조건 평균(p3_output.md)에 가장 가까운 대진 하나.
재생은 P3와 같은 기록 방식(p3_timeseries.apply_logged)을 쓰고, 먼저 원자료와 같은 경기인지 확인한다(승자·종료 사유·HP·mae).
엔진·키트 파일은 고치지 않는다. 확증 판정에 쓰지 않는 그림용 재생이다.
"""
from __future__ import annotations

import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p3_timeseries as T  # noqa: E402  (KIT 로 chdir, run.apply_knobs 에 기록 래퍼를 건다)

KIT = T.KIT
CONDS = {"BASE": "기준(열화 없음)", "R_kappa_100": "둔한 형: κ 100", "R_sigma_dps_6": "진동형: σ 6 °/s"}
COND_MAE = {"R_kappa_100": 1.64, "R_sigma_dps_6": 1.62}        # p3_output.md 조건 평균
CSV_OUT = os.path.join(HERE, "fig5_timeseries.csv")
MD_OUT = os.path.join(HERE, "fig5_output.md")
FIG = os.path.join(HERE, "paper_figs", "fig5_timeseries.png")
MIN_TICKS = int(60 * T.FS)


def pick():
    rows = [r for r in T.read(T.OUT) if r["cond"] in CONDS]
    by = {}
    for r in rows:
        by.setdefault((r["blue"], r["red"]), {})[r["cond"]] = r
    best = None
    for key, d in by.items():
        if len(d) < 3 or any(int(d[c]["blue_n"]) < MIN_TICKS for c in CONDS):
            continue
        score = sum(abs(float(d[c]["blue_mae"]) - m) / m for c, m in COND_MAE.items())
        if best is None or score < best[0]:
            best = (score, key)
    return best[1]


def original(cond, blue, red):
    src = "e3x" if cond == "R_kappa_100" else "main"
    for r in csv.DictReader(open(os.path.join(KIT, "out", src, "games.csv"), encoding="utf-8")):
        if (r["cond"], r["target"], r["blue"], r["red"], r["scenario"], r["salt"]) == (cond, "", blue, red, "neutral", "main-0"):
            return r
    raise KeyError(cond)


def replay(blue, red):
    js = [j for j in T.jobs() if j["cond"] in CONDS and j["blue"] == blue and j["red"] == red]
    series, checks = {}, []
    for j in js:
        T.REC.clear()
        r = T.run.play(j)
        rec = np.array(T.REC["Blue"])
        o = original(j["cond"], blue, red)
        same = (r["winner"] == o["winner"] and r["condition"] == o["condition"]
                and abs(r["hp_blue"] - float(o["hp_blue"])) < 1e-6 and abs(r["hp_red"] - float(o["hp_red"])) < 1e-6
                and abs(r["blue_mae_q_dps"] - float(o["blue_mae_q_dps"])) < 1e-4
                and abs(r["red_mae_q_dps"] - float(o["red_mae_q_dps"])) < 1e-4)
        checks.append((j["cond"], same, r["winner"], r["condition"], r["blue_mae_q_dps"], len(rec) / T.FS))
        series[j["cond"]] = rec
    return series, checks


def save(series):
    with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cond", "t_s", "q_cmd_dps", "q_dps", "elev_norm"])
        for c, rec in series.items():
            for i, row in enumerate(rec):
                w.writerow([c, round(i / T.FS, 4), round(row[0], 4), round(row[1], 4), round(row[2], 5)])


def load():
    series = {}
    for r in csv.DictReader(open(CSV_OUT, encoding="utf-8")):
        series.setdefault(r["cond"], []).append((float(r["t_s"]), float(r["q_cmd_dps"]), float(r["q_dps"])))
    return {c: np.array(v) for c, v in series.items()}


def plot(series, title_pair):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": ["Malgun Gothic", "DejaVu Sans"], "axes.unicode_minus": False, "font.size": 9})
    INK, INK2, GRID, CMD = "#2b2b2b", "#6b6b6b", "#e6e6e3", "#9a9893"
    COL = {"BASE": "#2b2b2b", "R_kappa_100": "#eb6834", "R_sigma_dps_6": "#2a78d6"}
    T0, T1, Z0, Z1 = 0.0, 60.0, 20.0, 26.0
    fig = plt.figure(figsize=(7.2, 6.4))
    gs = fig.add_gridspec(3, 2, width_ratios=[3.2, 1.2], hspace=0.45, wspace=0.18)
    for i, c in enumerate(CONDS):
        s = series[c]
        t, cmd, q = s[:, 0], s[:, 1], s[:, 2]
        mae_all = float(np.mean(np.abs(cmd - q)))
        for k, (a, b) in enumerate(((T0, T1), (Z0, Z1))):
            ax = fig.add_subplot(gs[i, k])
            m = (t >= a) & (t <= b)
            ax.plot(t[m], cmd[m], color=CMD, lw=2.0, label="피치 각속도 명령")
            ax.plot(t[m], q[m], color=COL[c], lw=1.2, label="실제 피치 각속도")
            ax.set_xlim(a, b)
            ax.grid(color=GRID, lw=0.6); ax.set_axisbelow(True)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
            ax.tick_params(colors=INK2, labelsize=8)
            if k == 0:
                ax.set_title(f"{CONDS[c]}   (이 경기 청 기체 mae {mae_all:.2f} °/s)", loc="left", fontsize=9, color=INK)
                ax.set_ylabel("°/s", color=INK2)
                ax.axvspan(Z0, Z1, color="#f2f1ee", zorder=0)
            else:
                ax.set_title(f"확대 {Z0:.0f}–{Z1:.0f} s", loc="left", fontsize=8, color=INK2)
            if i == 2:
                ax.set_xlabel("경기 시간 [s]", color=INK2)
    fig.suptitle(f"같은 크기의 추종 오차, 다른 모양 — {title_pair} (main-0, 중립 시나리오, 청 기체)", x=0.01, ha="left",
                 fontsize=9.5, color=INK)
    from matplotlib.lines import Line2D
    fig.legend([Line2D([], [], color=CMD, lw=2.0), Line2D([], [], color=INK, lw=1.2)],
               ["피치 각속도 명령", "실제 피치 각속도 (색은 조건)"], loc="upper left", bbox_to_anchor=(0.01, 0.955),
               ncol=2, frameon=False, fontsize=8)
    os.makedirs(os.path.dirname(FIG), exist_ok=True)
    fig.savefig(FIG, dpi=200, bbox_inches="tight")


def main():
    if "--plot" in sys.argv:
        blue, red = open(MD_OUT, encoding="utf-8").read().split("대진: ")[1].split("\n")[0].split(" 대 ")
        plot(load(), f"{blue} 대 {red}")
        return
    blue, red = pick()
    series, checks = replay(blue, red)
    L = ["# 그림 5 재생 기록 (서술, 판정 없음)\n",
         f"대진: {blue} 대 {red}",
         "",
         "시드 main-0, 시나리오 neutral, 기록 대상은 청 기체. 선택 규칙과 조건은 `fig5_timeseries.py` 머리말.\n",
         "| 조건 | 원자료와 같은 경기 | 승자 | 종료 사유 | 청 기체 mae [°/s] | 청 기체 비행 시간 [s] |",
         "|---|---|---|---|---|---|"]
    for c, same, w, cond, mae, dur in checks:
        L.append(f"| {c} | {'예' if same else '**아니오**'} | {w} | {cond} | {mae:.3f} | {dur:.1f} |")
    L.append("")
    L.append("조건 평균(`p3_output.md`): κ 100 mae 1.64·D 0.332, σ 6 mae 1.62·D 0.261. "
             "그림은 한 경기의 예시이며, 유형 효과의 근거는 P4·P7·P8의 사전 등록 대비다.")
    print("\n".join(L))
    if not all(x[1] for x in checks):
        # 다른 PC 등에서 원자료와 다른 경기가 나오면 저장된 시계열·기록·그림을 덮어쓰지 않는다
        print("원자료와 다른 경기가 있어 아무 파일도 쓰지 않는다.")
        return
    save(series)
    open(MD_OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    plot(load(), f"{blue} 대 {red}")        # 저장한 (t, 명령, 응답) 열로 그린다
    print("그림:", FIG)


if __name__ == "__main__":
    main()
