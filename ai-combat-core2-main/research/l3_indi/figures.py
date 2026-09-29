"""논문 그림 생성 — 실험이 끝날 때마다 바로 돌린다 (개정 A27 보조).

규칙 (데이터 시각화 규약)
  · 축은 하나. 단위가 다른 양을 한 축에 겹치지 않는다 → λ 곡선은 **3 단 패널**(x 공유)로 낸다.
  · 색은 고정 순서로 배정하고 돌려쓰지 않는다. 색맹·흑백 인쇄 대비로 **선 모양과 마커를 2 차 부호**로 같이 쓴다.
  · 계열이 2 개 이상이면 범례를 항상 넣고, 직접 라벨은 선택적으로만 단다.
  · 격자·축은 눈에 덜 띄게, 데이터가 가장 진하게.

사용: python research/l3_indi/figures.py --all
      python research/l3_indi/figures.py --only share,transfer
출력: research/l3_indi/figures/<이름>.pdf (+ .png)
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO                          # noqa: E402

OUT_DIR = os.path.join(HERE, "figures")

# 고정 색 순서 (검증 통과: 명도대 · 채도 하한 · 색맹 인접쌍 ΔE 9.1 · 정상시야 ΔE 19.6)
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK, INK2, MUTED = "#1a1a19", "#4a4a47", "#8a8a85"
# 흑백 인쇄·색맹 대비용 2 차 부호
LS = ["-", "--", "-.", ":", (0, (3, 1, 1, 1))]
MK = ["o", "s", "^", "D", "v"]


def setup():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    for cand in ("Malgun Gothic", "NanumGothic", "AppleGothic", "Noto Sans KR"):
        if cand in have:
            plt.rcParams["font.family"] = cand
            break
    else:
        print("  ! 한글 폰트를 찾지 못했다 — 라벨이 깨질 수 있다")
    plt.rcParams.update({
        "axes.unicode_minus": False, "figure.dpi": 140, "savefig.dpi": 300,
        "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
        "xtick.color": INK2, "ytick.color": INK2, "axes.titlesize": 11,
        "axes.labelsize": 10, "legend.fontsize": 9, "legend.frameon": False,
        "grid.color": "#e6e6e2", "grid.linewidth": 0.8, "axes.axisbelow": True,
        "savefig.bbox": "tight", "figure.facecolor": "white",
    })
    os.makedirs(OUT_DIR, exist_ok=True)
    return plt


def save(plt, fig, name):
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT_DIR, f"{name}.{ext}"))
    plt.close(fig)
    print("  ->", os.path.join("research", "l3_indi", "figures", name + ".pdf"))


def newest(pattern):
    hits = sorted(glob.glob(os.path.join(REPO, pattern)), key=os.path.getmtime)
    return hits[-1] if hits else None


def load_csv(path, str_cols=()):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        d = dict(r)
        for k, v in r.items():
            if k in str_cols:
                continue
            try:
                d[k] = float(v)
            except (TypeError, ValueError):
                d[k] = float("nan")
        rows.append(d)
    return rows


def boot_ci(d, n=4000, seed=20260920):
    d = np.asarray([x for x in d if np.isfinite(x)], float)
    if len(d) < 3:
        return (np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    m = np.median(d[rng.integers(0, len(d), size=(n, len(d)))], axis=1)
    return float(np.median(d)), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


# ======================================================================================
# 1. λ 곡선 — 3 단 패널 (추종 오차 / 조준 이득 / 에너지 대가)
# ======================================================================================
def fig_lambda(plt):
    """대표 그림 — x(λ)만 공유하는 5 단 패널. 단위가 다른 양을 한 축에 겹치지 않는다.

    ① 추종 오차 ② 조준(짝 차이) ③ 에너지(짝 차이) ④ 명령·응답 상관 ⑤ 진동 비율.
    추종 상실 경계(A29-2: 상관 < 0.7)를 다섯 패널 전체에 수직선으로 긋는다.
    """
    path = newest("results/paper/lamsweep/*/runs.csv")
    if not path:
        print("  (건너뜀) λ 스윕 결과가 아직 없다")
        return
    rows = load_csv(path, str_cols=("setting", "geom", "enemy", "kind", "flow_intent"))
    rows = [r for r in rows if r.get("excluded", 0) < 1]
    lams = sorted({r["lam_q"] for r in rows})
    hi = [l for l in lams if l >= 1.0]
    lo = [l for l in lams if l < 1.0]
    key = lambda r: (r["kcas"], r["geom"], r["enemy"])
    ref = {key(r): r for r in rows if r["lam_q"] == 1.0}

    def med(col, lam):
        v = [r[col] for r in rows if r["lam_q"] == lam and np.isfinite(r.get(col, np.nan))]
        return float(np.median(v)) if v else np.nan

    def paired(col, lam):
        d = [r[col] - ref[key(r)][col] for r in rows if r["lam_q"] == lam and key(r) in ref
             and np.isfinite(r.get(col, np.nan)) and np.isfinite(ref[key(r)].get(col, np.nan))]
        return boot_ci(d)

    def osc(lam):
        R = [r for r in rows if r["lam_q"] == lam]
        return 100.0 * sum(1 for r in R if r.get("oscillating", 0) >= 1) / max(len(R), 1)

    # 추종 상실 경계 (A29-2)
    bnd = next((l for l in hi if min(med("corr_early", l), med("corr_late", l)) < 0.7), np.nan)

    fig, axes = plt.subplots(5, 1, figsize=(6.4, 12.4), sharex=True)

    # ① 추종 오차
    ax = axes[0]
    ax.plot(hi, [med("J_q", l) for l in hi], LS[0], color=C[0], marker=MK[0], markersize=5,
            linewidth=2, label="λ ≥ 1 (제어효율 과대추정)")
    if lo:
        ax.plot(lo, [med("J_q", l) for l in lo], LS[1], color=C[1], marker=MK[1], markersize=5,
                linewidth=2, label="λ < 1 (과소추정)")
    ax.legend(loc="upper left", fontsize=8.5)
    ax.set_ylabel("① 추종 오차 $J_q$")
    ax.text(0.99, 0.06, "클수록 명령을 못 따라감", transform=ax.transAxes, fontsize=8,
            color=MUTED, ha="right")

    # ② 조준 (짝 차이) / ③ 에너지 (짝 차이)
    for i, (col, ylab, note) in enumerate(
            (("ata_min", "② 조준: ATA 최소 차이 [°]", "아래 = 기수를 더 가깝게"),
             ("dkcas", "③ 에너지: ΔKCAS 차이 [kt]", "아래 = 속도를 더 잃음")), start=1):
        ax = axes[i]
        m, l_, h_ = zip(*[paired(col, x) for x in hi])
        ax.fill_between(hi, l_, h_, color=C[0], alpha=0.15, linewidth=0)
        ax.plot(hi, m, LS[0], color=C[0], marker=MK[0], markersize=5, linewidth=2)
        if lo:
            m2, l2, h2 = zip(*[paired(col, x) for x in lo])
            ax.fill_between(lo, l2, h2, color=C[1], alpha=0.15, linewidth=0)
            ax.plot(lo, m2, LS[1], color=C[1], marker=MK[1], markersize=5, linewidth=2)
        ax.axhline(0, color=MUTED, linewidth=0.8)
        if col == "ata_min":                       # 등가 한계 띠
            ax.axhspan(-2.0, 2.0, color=MUTED, alpha=0.13, linewidth=0)
            ax.text(lams[0], -2.0, " 등가 한계 ±2.0°", fontsize=7.5, color=INK2, va="top")
        ax.set_ylabel(ylab)
        ax.text(0.01, 0.06, note, transform=ax.transAxes, fontsize=8, color=MUTED)

    # ④ 명령·응답 상관
    ax = axes[3]
    for k, (col, lab) in enumerate((("corr_early", "전반 [1, 15) s"), ("corr_late", "후반 [15, 25] s"))):
        ax.plot(hi, [med(col, l) for l in hi], LS[k], color=C[k], marker=MK[k], markersize=5,
                linewidth=2, label=lab)
    ax.axhline(0.7, color=C[3], linestyle=":", linewidth=1.6)
    ax.text(lams[0], 0.7, " 추종 상실 기준 r = 0.7", fontsize=8, color=C[3], ha="left", va="bottom")
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("④ 명령·응답 상관 r")
    ax.legend(loc="lower left")

    # ⑤ 진동 비율
    ax = axes[4]
    ax.plot(hi, [osc(l) for l in hi], LS[0], color=C[0], marker=MK[0], markersize=5, linewidth=2)
    if lo:
        ax.plot(lo, [osc(l) for l in lo], LS[1], color=C[1], marker=MK[1], markersize=5, linewidth=2)
    ax.set_ylim(0, None)
    ax.set_ylabel("⑤ 진동 판정 비율 [%]")
    ax.set_xlabel("제어효율 모델 오차 λ = $G_{model}/G_{true}$ (피치 축, 로그 눈금)")

    for i, ax in enumerate(axes):
        ax.set_xscale("log")
        ax.grid(True, which="both")
        if np.isfinite(bnd):
            ax.axvline(bnd, color=C[3], linestyle="--", linewidth=1.8, zorder=0)
            if i == 0:
                ax.annotate(f"추종 상실 경계 λ = {bnd:g}", xy=(bnd, 0.55),
                            xycoords=("data", "axes fraction"), xytext=(-8, 0),
                            textcoords="offset points", color=C[3], fontsize=9,
                            ha="right", va="center")
    axes[0].set_title("λ 를 키우면 조준은 좋아지지만, 어느 지점부터는 명령 추종을 잃는다", pad=12)
    fig.subplots_adjust(hspace=0.16)
    save(plt, fig, "fig_lambda_curves")


# ======================================================================================
# 2. 에너지 대 조준 맞교환
# ======================================================================================
def fig_tradeoff(plt):
    path = newest("results/paper/lamsweep/*/runs.csv") or newest("results/paper/rq3/*/runs.csv")
    rows = load_csv(path, str_cols=("setting", "geom", "enemy", "kind", "flow_intent"))
    rows = [r for r in rows if r.get("kind") == "P" and r.get("excluded", 0) < 1]
    key = "lam_q" if "lam_q" in rows[0] else "setting"
    groups = sorted({r[key] for r in rows}, key=lambda x: (isinstance(x, str), x))
    ref = [r for r in rows if (r[key] == 1.0 if key == "lam_q" else r[key] == "S2")]
    base_ata = np.median([r["ata_min"] for r in ref])
    base_kc = np.median([r["dkcas"] for r in ref])
    fig, ax = plt.subplots(figsize=(6.0, 4.6))
    xs, ys, labs = [], [], []
    for g in groups:
        sub = [r for r in rows if r[key] == g]
        xs.append(np.median([r["dkcas"] for r in sub]) - base_kc)
        ys.append(np.median([r["ata_min"] for r in sub]) - base_ata)
        labs.append(f"λ {g:g}" if key == "lam_q" else str(g))
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.axvline(0, color=MUTED, linewidth=0.8)
    ax.plot(xs, ys, "-", color=MUTED, linewidth=1, zorder=1)
    ax.scatter(xs, ys, s=52, color=C[0], zorder=2, edgecolor="white", linewidth=1.2)
    for x, y, t in zip(xs, ys, labs):
        ax.annotate(t, (x, y), textcoords="offset points", xytext=(6, 5), fontsize=8, color=INK2)
    ax.set_xlabel("에너지 대가: 기준 대비 ΔKCAS 차이 [kt]  (왼쪽 = 속도를 더 잃음)")
    ax.set_ylabel("조준 이득: 기준 대비 ATA 최소 차이 [°]\n(아래 = 기수를 더 가깝게)")
    ax.set_title("조준을 얻고 에너지를 내주는 맞교환", pad=10)
    ax.grid(True)
    save(plt, fig, "fig_tradeoff")


# ======================================================================================
# 3. 축별 물리 한계 몫 대 제어기 몫
# ======================================================================================
def fig_share(plt):
    path = newest("results/paper/ideal_share/*/runs.csv")
    rows = load_csv(path, str_cols=("man",))
    mans = ["M1_0.7", "M1_0.8", "M1_0.9", "M3_0.7", "M3_0.9", "M2a", "M2b"]
    prim = lambda m: "q" if m.startswith("M1") else "p"
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    y = np.arange(len(mans))
    phys, ctrl = [], []
    for m in mans:
        R = [r for r in rows if r["man"] == m]
        a = prim(m)
        s = np.median([r[f"Jideal_{a}"] / r[f"J_{a}"] for r in R]) * 100
        s = min(s, 100.0)                        # 100% 초과 칸은 상한 처리 (보고서 주석 참조)
        phys.append(s)
        ctrl.append(100 - s)
    ax.barh(y, phys, color=C[0], height=0.62, label="물리 한계 몫 (어떤 제어기도 못 피함)")
    ax.barh(y, ctrl, left=np.array(phys) + 0.6, color=C[1], height=0.62,
            label="제어기 몫 (설계로 줄일 수 있음)")
    for i, (p, c) in enumerate(zip(phys, ctrl)):
        ax.text(p / 2, i, f"{p:.0f}%", ha="center", va="center", color="white", fontsize=9)
        if c > 8:
            ax.text(p + 0.6 + c / 2, i, f"{c:.0f}%", ha="center", va="center", color="white", fontsize=9)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{m}  ({'피치' if prim(m) == 'q' else '롤'})" for m in mans])
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("전체 추종 오차에서 차지하는 비율 [%]")
    ax.set_title("축에 따라 제어기가 손댈 수 있는 몫이 다르다", pad=10)
    ax.legend(loc="lower right")
    ax.grid(True, axis="x")
    save(plt, fig, "fig_physical_share")


# ======================================================================================
# 4. 유도 유무 대조 (개루프 vs 폐루프)
# ======================================================================================
def fig_guidance(plt):
    path = newest("results/paper/rq3/*/runs.csv")
    rows = load_csv(path, str_cols=("setting", "geom", "enemy", "kind", "flow_intent"))
    rows = [r for r in rows if r.get("excluded", 0) < 1]
    sets = ["S3", "S4", "S1p", "S5"]
    arms = [("A", "유도 없음 (개루프 당김)"), ("P", "유도 있음 (추격)")]
    fig, ax = plt.subplots(figsize=(6.2, 4.4))
    for k, (kind, label) in enumerate(arms):
        med, lo, hi = [], [], []
        for s in sets:
            by = {(r["kcas"], r["geom"], r["enemy"]): r for r in rows
                  if r["kind"] == kind and r["setting"] == "S2"}
            d = []
            for key, ref in by.items():
                o = next((r for r in rows if r["kind"] == kind and r["setting"] == s
                          and (r["kcas"], r["geom"], r["enemy"]) == key), None)
                if o is not None and np.isfinite(o["ata_min"]) and np.isfinite(ref["ata_min"]):
                    d.append(o["ata_min"] - ref["ata_min"])
            m, l, h = boot_ci(d)
            med.append(m); lo.append(l); hi.append(h)
        x = np.arange(len(sets)) + (k - 0.5) * 0.22
        ax.errorbar(x, med, yerr=[np.array(med) - np.array(lo), np.array(hi) - np.array(med)],
                    fmt=MK[k], color=C[k], markersize=7, capsize=4, linewidth=2, label=label)
    ax.axhline(0, color=MUTED, linewidth=1)
    ax.set_xticks(np.arange(len(sets)))
    ax.set_xticklabels(sets)
    ax.set_xlabel("설정 (기준 S2 대비)")
    ax.set_ylabel("ATA 최소 차이 [°]  (아래 = 기수를 더 가깝게)")
    ax.set_title("유도 루프가 없으면 내부 루프 차이가 밖으로 나오지 않는다", pad=10)
    ax.legend(loc="lower left")
    ax.grid(True, axis="y")
    save(plt, fig, "fig_guidance_contrast")


# ======================================================================================
# 5. 안정 경계 (RQ2 λ_s)
# ======================================================================================
def fig_stability(plt):
    path = newest("results/paper/rq2/*/blocks.csv")
    rows = load_csv(path, str_cols=("axis", "man", "metric", "setting", "lam_s_status",
                                    "lam_s_hi_status"))
    rows = [r for r in rows if r["fbw"] == 0 and r["axis"] == "all"]
    sets = sorted({r["setting"] for r in rows})
    vals = [[r["lam_s"] for r in rows if r["setting"] == s and np.isfinite(r["lam_s"])] for s in sets]
    keep = [(s, v) for s, v in zip(sets, vals) if len(v) >= 5]
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    bp = ax.boxplot([v for _, v in keep], orientation="vertical", widths=0.55, patch_artist=True,
                    medianprops=dict(color=INK, linewidth=2), whiskerprops=dict(color=MUTED),
                    capprops=dict(color=MUTED), flierprops=dict(marker=".", markersize=4,
                                                                markerfacecolor=MUTED,
                                                                markeredgecolor="none"))
    for patch in bp["boxes"]:
        patch.set(facecolor=C[0], alpha=0.25, edgecolor=C[0], linewidth=1.5)
    ax.axhline(0.5, color=C[1], linestyle="--", linewidth=1.5)
    ax.text(len(keep) + 0.45, 0.5, "이론 수렴 조건\nλ > 0.5", color=C[1], fontsize=8, va="center")
    ax.set_xticklabels([s for s, _ in keep], rotation=30, ha="right")
    ax.set_ylabel("안정 경계 $λ_s$  (이 값 아래로 내려가면 흔들림)")
    ax.set_xlabel("INDI 설정")
    ax.set_title("게인을 올리면 모델 오차를 견디는 폭이 줄어든다", pad=10)
    ax.grid(True, axis="y")
    save(plt, fig, "fig_stability_boundary")


# ======================================================================================
# 6. T 층 → M 층 전이 산점도
# ======================================================================================
def fig_transfer(plt):
    path = newest("results/paper/lamsweep/*/runs.csv") or newest("results/paper/rq3/*/runs.csv")
    rows = load_csv(path, str_cols=("setting", "geom", "enemy", "kind", "flow_intent"))
    rows = [r for r in rows if r.get("kind") == "P" and r.get("excluded", 0) < 1]
    by = {(r["setting"], r["kcas"], r["geom"], r["enemy"]): r for r in rows}
    dt, dm = [], []
    for (s, kc, g, e), r in by.items():
        ref = by.get(("S2", kc, g, e)) if "S2" in {k[0] for k in by} else None
        if ref is None or r is ref:
            continue
        if np.isfinite(r["ata_min"]) and np.isfinite(ref["ata_min"]):
            dt.append(r["J_q"] - ref["J_q"])
            dm.append(r["ata_min"] - ref["ata_min"])
    if len(dt) < 5:
        print("  (건너뜀) 전이 산점도: 짝이 부족하다")
        return
    from l3_indi import metrics as M
    fit = M.transfer_fit(dt, dm)
    fig, ax = plt.subplots(figsize=(6.0, 4.6))
    ax.scatter(dt, dm, s=22, color=C[0], alpha=0.55, edgecolor="none")
    xs = np.linspace(min(dt), max(dt), 100)
    ax.plot(xs, fit["a_linear"] * xs, LS[0], color=C[1], linewidth=2,
            label=f"선형 적합 (기울기 {fit['a_linear']:+.1f}°/ΔJ)")
    if fit.get("verdict") == "threshold" and fit.get("x0") is not None:
        ax.plot(xs, fit["a_hinge"] * np.maximum(0, xs - fit["x0"]), LS[1], color=C[2],
                linewidth=2, label=f"임계형 적합 (x₀ = {fit['x0']:.2f})")
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.axvline(0, color=MUTED, linewidth=0.8)
    ax.set_xlabel("T 층: 추종 오차 차이 ΔJ_q  (기준 대비)")
    ax.set_ylabel("M 층: ATA 최소 차이 [°]  (기준 대비)")
    ax.set_title(f"추종 오차가 조준으로 전이되는 모양 — 판정 {fit['verdict']}", pad=10)
    ax.legend(loc="upper right")
    ax.grid(True)
    save(plt, fig, "fig_transfer")


# ======================================================================================
# 7. 과응답 파형 — 메커니즘을 눈으로 보이는 그림 (제안 추가분)
# ======================================================================================
def fig_waveform(plt):
    """같은 λ 가 두 과제에서 정반대로 보이는 것을 한 장에 담는다.

    (위) 고정 계단 명령: λ 가 크면 **뒤처진다**.
    (아래) 유도 폐루프(명령이 계속 바뀜): 같은 λ 가 **명령 추종을 잃는다**.
      측정: 명령·응답 상관이 λ=1 에서 1.00 인데 λ=25 에서는 0.33(전반)·0.46(후반)이고,
      후반 10 s 평균 명령 2.26 °/s 에 실제 15.71 °/s — 명령의 7 배를 스스로 당긴다.
    """
    import contextlib
    import io as _io
    import json as _json
    from l3_indi.harness import Condition, Params, Uncertainty, build, run
    from l3_indi.design import capability
    from l3_indi.evaluate import maneuver_by_name
    from l3_indi import rq3

    cond = Condition(14000.0, 350.0)
    fig, axes = plt.subplots(2, 1, figsize=(6.6, 7.0))

    # (a) 합성 계단 명령
    man = maneuver_by_name("M1_0.9", capability(cond))
    ax = axes[0]
    for k, (lam, label) in enumerate(((1.0, "λ = 1 (기준)"), (25.0, "λ = 25"))):
        with contextlib.redirect_stdout(_io.StringIO()):
            ts = run(build(cond, Params(), Uncertainty(g0_row_scale=(1.0, lam, 1.0))), man)
        if k == 0:
            ax.plot(ts["t"], np.rad2deg(ts["sp_q"]), color=INK, linewidth=2.2, label="명령 $q_{sp}$")
        ax.plot(ts["t"], np.rad2deg(ts["q"]), LS[k + 1], color=C[k], linewidth=1.8, label=label)
    ax.set_xlim(0, 8.0)
    ax.set_ylabel("피치율 [°/s]")
    ax.set_title("(가) 고정 계단 명령 — λ 가 크면 **뒤처진다**".replace("**", ""), pad=8)
    ax.legend(loc="lower right")
    ax.grid(True)

    # (b) 유도 폐루프 (명령이 매 순간 바뀐다)
    gj = os.path.join(REPO, "results", "paper", "rq3_geom", "10c98be2cd", "geometries.json")
    ax = axes[1]
    if os.path.isfile(gj):
        g = {x["id"]: x for x in _json.load(open(gj, encoding="utf-8"))}["G1"]
        job = {"kcas": 350.0, "geom": "G1", "enemy": "E1", "kind": "P", "bank0": g["bank_deg"],
               "dur": rq3.DUR_GUIDED, "_geom": g}
        for k, (name, lam) in enumerate((("λ = 1 (기준)", 1.0), ("λ = 25", 25.0))):
            red = rq3.cached_track(job)
            man2 = rq3.PursuitScript(red, duration_s=rq3.DUR_GUIDED)
            blue = rq3.fly(cond, man2, (1.0, 1.0, 1.0), 25.0, lam)
            if k == 0:
                ax.plot(blue["t"], np.rad2deg(blue["sp_q"]), color=INK, linewidth=2.0,
                        label="명령 $q_{sp}$")
            ax.plot(blue["t"], np.rad2deg(blue["q"]), LS[k + 1], color=C[k], linewidth=1.6,
                    label=name)
        ax.set_xlim(0, rq3.DUR_GUIDED)
        ax.legend(loc="upper left", ncol=3)
    ax.set_xlabel("시간 [s]")
    ax.set_ylabel("피치율 [°/s]")
    ax.set_title("(나) 유도 폐루프 — 같은 λ 가 명령 추종을 잃고 스스로 당긴다", pad=8)
    ax.grid(True)
    fig.suptitle("λ 를 키우면 증분 루프가 느려진다 — 계단 명령에서는 지연, 폐루프에서는 추종 상실",
                 y=0.99, fontsize=11)
    fig.subplots_adjust(hspace=0.32)
    save(plt, fig, "fig_lag_vs_oscillation")


# ======================================================================================
# 8. 사슬 — 명령 실현(1 순위) → 조준(2 순위) → 교전 결과(3 순위)  [개정 A35 §7]
# ======================================================================================
def fig_chain(plt):
    """확증 실행의 설정별 짝 차이를 3 단으로 나란히. 1 순위 크기로 정렬한다.

    왼쪽 칸만 판정 대상이고(δ 띠를 그린다), 가운데·오른쪽은 관찰이다.
    """
    path = newest("results/paper/dogfight_confirm/*/runs.csv")
    if not path:
        raise FileNotFoundError("확증 실행 결과가 없다 (results/paper/dogfight_confirm/*/runs.csv)")
    STR = ("match_id", "setting_name", "family", "variable", "level", "red", "red_path",
           "blue_policy", "scenario", "salt", "winner", "condition", "turb", "turb_side",
           "indi_side")
    rows = load_csv(path, STR)
    key = lambda r: (r["scenario"], r["red"], r["salt"])
    base = {key(r): r for r in rows if r["setting_name"] == "BASE"}
    names = [s for s in dict.fromkeys(r["setting_name"] for r in rows) if s != "BASE"]

    def diff(name, col, scale=1.0):
        d = [scale * (r[col] - base[key(r)][col]) for r in rows
             if r["setting_name"] == name and key(r) in base
             and np.isfinite(r[col]) and np.isfinite(base[key(r)][col])]
        d = np.asarray(d, float)
        if len(d) < 3:
            return (np.nan, np.nan, np.nan)
        rng = np.random.default_rng(20260929)
        m = np.mean(d[rng.integers(0, len(d), size=(4000, len(d)))], axis=1)
        return float(np.mean(d)), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))

    # A33 봉투 게이트: 기준 대비 초과 비율의 CI 하한 > 0
    exc = lambda r: float(r["nz_max"] > 9.0 or r["nz_min"] < -3.0 or r["alpha_max_deg"] > 30.0)
    def flagged(name):
        d = np.asarray([exc(r) - exc(base[key(r)]) for r in rows
                        if r["setting_name"] == name and key(r) in base], float)
        rng = np.random.default_rng(20260925)
        m = np.mean(d[rng.integers(0, len(d), size=(4000, len(d)))], axis=1)
        return float(np.percentile(m, 2.5)) > 0

    P = [("명령 실현 (1 순위, 판정 대상)", "reach63_q", 1.0, "도달 비율 차 [지령 계단 중]", 0.03125),
         ("조준 (2 순위, 관찰)", "frac_ata30_blue", 1.0, "ATA ≤ 30° 시간 비율 차", None),
         ("교전 결과 (3 순위, 관찰)", "blue_pts", 100.0 / 3.0, "승률 차 [%p]", None)]
    V = {(n, c): diff(n, c, s) for n in names for _, c, s, _, _ in P}
    order = sorted(names, key=lambda n: V[(n, "reach63_q")][0])
    flag = {n: flagged(n) for n in order}
    y = np.arange(len(order))

    fig, axes = plt.subplots(1, 3, figsize=(11.2, 7.4), sharey=True)
    for ax, (title, col, sc, xlab, delta) in zip(axes, P):
        if delta is not None:
            ax.axvspan(-delta, delta, color=C[2], alpha=0.13, lw=0)
        ax.axvline(0, color=MUTED, lw=0.9, zorder=1)
        for i, n in enumerate(order):
            m, lo, hi = V[(n, col)]
            ax.plot([lo, hi], [i, i], color=INK2, lw=1.4, solid_capstyle="round", zorder=2)
            ax.plot([m], [i], marker=MK[1] if flag[n] else MK[0], ms=5.5, zorder=3,
                    color=C[1] if flag[n] else C[0], mec="white", mew=0.7)
        ax.set_title(title, pad=8)
        ax.set_xlabel(xlab)
        ax.grid(axis="x")
        ax.set_axisbelow(True)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(order, fontsize=8)
    axes[0].set_ylim(-0.8, len(order) - 0.2)
    from matplotlib.patches import Patch
    h = [Patch(facecolor=C[2], alpha=0.13, label="등가 한계 δ = ±0.03125 (왼쪽 칸만 판정한다)"),
         plt.Line2D([], [], ls="", marker=MK[0], color=C[0], ms=5.5, label="봉투 게이트 통과"),
         plt.Line2D([], [], ls="", marker=MK[1], color=C[1], ms=5.5, label="F-16 성능 초과 (기준 대비)"),
         plt.Line2D([], [], color=INK2, lw=1.4, label="짝 차이 평균의 95% CI")]
    fig.legend(handles=h, loc="lower center", ncol=4, fontsize=8.5,
               bbox_to_anchor=(0.5, -0.005))
    fig.suptitle("INDI 파라미터의 짝 차이: 명령 실현도 순으로 정렬 (확증 실행 4,480 경기)",
                 y=0.985, fontsize=12)
    fig.tight_layout(rect=(0, 0.035, 1, 0.96))
    save(plt, fig, "chain")


FIGS = {"lambda": fig_lambda, "tradeoff": fig_tradeoff, "share": fig_share,
        "guidance": fig_guidance, "stability": fig_stability, "transfer": fig_transfer,
        "waveform": fig_waveform, "chain": fig_chain}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only", default=None, help="쉼표로 구분한 그림 이름")
    args = ap.parse_args()
    names = list(FIGS) if args.all or not args.only else [s.strip() for s in args.only.split(",")]
    plt = setup()
    for n in names:
        if n not in FIGS:
            print("  ? 알 수 없는 그림:", n)
            continue
        print(f"[{n}]")
        try:
            FIGS[n](plt)
        except Exception as e:                       # 한 장이 실패해도 나머지는 계속
            print(f"  ! 실패: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
