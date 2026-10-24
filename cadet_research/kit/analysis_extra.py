"""추가 실험(ASYM, E3X) 분석. 판정 기준은 ../PREREG_EXTRA.md (실행 전 고정).

  python analysis_extra.py         # → out/extra_report/ 에 보고서·그림·results.json

이 스크립트는 실행 전에 작성했다. 결과를 본 뒤에는 표·그림의 모양만 고친다.
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
import predict as P  # noqa: E402
from analyze import points  # noqa: E402
from experiments import ASYM_CONDS, ASYM_TARGETS, E3X_CONDS, EXPERIMENTS  # noqa: E402

OUTDIR = os.environ.get("EXTRA_OUTDIR", os.path.join(KIT, "out", "extra_report"))
ASYM_GAMES = os.environ.get("ASYM_GAMES", os.path.join(KIT, "out", "asym", "games.csv"))   # 시험용으로만 바꾼다
E3X_GAMES = os.environ.get("E3X_GAMES", os.path.join(KIT, "out", "e3x", "games.csv"))
N_BOOT = 2000
OUT: list[str] = []
RES: dict = {}
KEY = ("blue", "red", "scenario")


def say(s=""):
    print(s)
    OUT.append(s)


def ci(a, level=95.0):
    a = np.asarray(a, float)
    return float(np.percentile(a, (100 - level) / 2)), float(np.percentile(a, 100 - (100 - level) / 2))


def fmt(a, d=2, level=95.0):
    lo, hi = ci(a, level)
    return f"[{lo:+.{d}f}, {hi:+.{d}f}]"


def judge_pts(lo, hi, delta):
    if -delta <= lo and hi <= delta:
        return "차이 없음"
    if lo > delta or hi < -delta:
        return "차이 있음"
    return "판정 불가"


def read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


DELTA_PTS = json.load(open(os.path.join(KIT, "out", "cal", "delta.json"), encoding="utf-8"))["delta_pts"]
DELTA_D = json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))["D"]
MAIN = [r for r in read(os.path.join(KIT, "out", "main", "games.csv")) if r["target"] == ""]
BASE = {(r["salt"],) + tuple(r[k] for k in KEY): r for r in MAIN if r["cond"] == "BASE"}
SEEDS = sorted({r["salt"] for r in MAIN}, key=lambda s: int(s.rsplit("-", 1)[1]))
AG = list(EXPERIMENTS["E2"]["agents"])


def _ceiling():
    """무상관 D 상한 (같은 경기끼리의 비교를 뺀 불편 추정, reanalysis_v2.indep_agreement 와 같음)."""
    dist = collections.defaultdict(collections.Counter)
    for r in MAIN:
        if r["cond"] == "BASE":
            dist[(r["blue"], r["red"], r["scenario"])][(r["winner"], r["condition"])] += 1
    n = len(SEEDS)
    return 1 - float(np.mean([sum(c * (c - 1) for c in cnt.values()) / (n * (n - 1)) for cnt in dist.values()]))


CEIL = _ceiling()


# ---------------------------------------------------------------- ASYM
def asym():
    rows = read(ASYM_GAMES)
    say("## ASYM — 참가자 하나만 열화 (PREREG §2)\n")
    say(f"경기 {len(rows):,} (사전 등록 10,080). 대상 {', '.join(ASYM_TARGETS)}. 짝은 `out/main`의 같은 시드·대진·시나리오 BASE 경기.\n")
    # (조건, 대상, 시드) → 대상 점수 변화, 대상 mae, 대상 승 수 변화, 결과 변화 수
    cell = {}
    for c in ASYM_CONDS:
        for t in ASYM_TARGETS:
            for s in SEEDS:
                gs = [r for r in rows if r["cond"] == c and r["target"] == t and r["salt"] == s]
                bs = [BASE[(s,) + tuple(g[k] for k in KEY)] for g in gs]
                pv, wv = points(gs, AG); pb, wb = points(bs, AG)
                own = lambda g: float(g["blue_mae_q_dps"] if g["blue"] == t else g["red_mae_q_dps"])
                cell[(c, t, s)] = dict(dpts=pv[t] - pb[t], mae=np.mean([own(g) for g in gs]),
                                       mae_base=np.mean([own(b) for b in bs]), dwin=wv[t][0] - wb[t][0],
                                       nwin_base=wb[t][0], n=len(gs),
                                       flips=sum((g["winner"], g["condition"]) != (b["winner"], b["condition"]) for g, b in zip(gs, bs)))
    rng = np.random.default_rng(0)
    boots = [list(rng.choice(SEEDS, len(SEEDS))) for _ in range(N_BOOT)]

    def agg(c, t, seeds, k):
        return float(np.mean([cell[(c, t, s)][k] for s in seeds]))

    level = 100 * (1 - 0.05 / len(ASYM_TARGETS))
    say(f"### A1·A3. 조건 × 대상 점수 변화 (리그 한 바퀴 42경기당, 시드 부트스트랩 {level:.2f} % CI, δ = {DELTA_PTS:.2f}점)\n")
    say("| 조건 | 대상 | 대상 mae BASE → 열화 [°/s] | Δ점수 [CI] | 판정 | Δ승 (경기 42 중) | 결과 변화율 D |")
    say("|---|---|---|---|---|---|---|")
    a1 = {}
    for c in ASYM_CONDS:
        for t in ASYM_TARGETS:
            m = agg(c, t, SEEDS, "dpts")
            bd = [agg(c, t, b, "dpts") for b in boots]
            lo, hi = ci(bd, level)
            j = judge_pts(lo, hi, DELTA_PTS)
            D = sum(cell[(c, t, s)]["flips"] for s in SEEDS) / sum(cell[(c, t, s)]["n"] for s in SEEDS)
            a1[(c, t)] = dict(dpts=m, ci=(lo, hi), judge=j, mae=agg(c, t, SEEDS, "mae"), mae_base=agg(c, t, SEEDS, "mae_base"),
                              dwin=agg(c, t, SEEDS, "dwin"), D=D)
            say(f"| {c} | {t} | {a1[(c, t)]['mae_base']:.2f} → {a1[(c, t)]['mae']:.2f} | {m:+.1f} [{lo:+.1f}, {hi:+.1f}] | {j} | "
                f"{a1[(c, t)]['dwin']:+.2f} | {D:.3f} |")
    sham_ok = all(a1[("SHAM", t)]["judge"] == "차이 없음" for t in ASYM_TARGETS)
    say(f"\nA3 (교정): SHAM에서 대상 3명 모두 \"차이 없음\"인가 → {'예' if sham_ok else '아니오'}\n")

    # A2: Δ점수 = 대상별 절편 + b·mae (SHAM 제외 9조건 × 3대상)
    deg = [c for c in ASYM_CONDS if c != "SHAM"]

    def fit_b(seeds):
        X, y = [], []
        for c in deg:
            for i, t in enumerate(ASYM_TARGETS):
                row = [0.0] * len(ASYM_TARGETS); row[i] = 1.0
                X.append(row + [agg(c, t, seeds, "mae")]); y.append(agg(c, t, seeds, "dpts"))
        coef, *_ = np.linalg.lstsq(np.array(X), np.array(y), rcond=None)
        return coef
    coef = fit_b(SEEDS)
    bb = [fit_b(b)[-1] for b in boots]
    lo, hi = ci(bb)
    verdict = "성립" if hi < 0 else ("반대 방향" if lo > 0 else "성립하지 않음")
    say("### A2 (주). 추종 오차가 클수록 열화된 쪽 점수가 떨어지는가\n")
    say(f"Δ점수 = 대상별 절편 + b·mae, SHAM 제외 9조건 × 대상 3명 = 27점. "
        f"b = {coef[-1]:+.2f}점/(°/s) [{lo:+.2f}, {hi:+.2f}] (95 %, 시드 부트스트랩) → **{verdict}**. "
        f"대상별 절편: " + ", ".join(f"{t} {coef[i]:+.1f}" for i, t in enumerate(ASYM_TARGETS)) + "\n")

    # A4 (탐색): 대상별·원인별 기울기
    say("### A4 (탐색, 판정 없음). 대상별·원인별 기울기\n")
    say("| 묶음 | 기울기 [점/(°/s)] [95 % CI] |")
    say("|---|---|")
    filt = [c for c in deg if c.startswith("F25")]
    a4 = {}
    for t in ASYM_TARGETS:
        f = lambda seeds: np.polyfit([agg(c, t, seeds, "mae") for c in deg], [agg(c, t, seeds, "dpts") for c in deg], 1)[0]
        a4[t] = (f(SEEDS), ci([f(b) for b in boots]))
        say(f"| 대상 {t} (9조건) | {a4[t][0]:+.2f} {fmt([f(b) for b in boots])} |")
    fF = lambda seeds: np.polyfit([agg(c, t, seeds, "mae") for c in filt for t in ASYM_TARGETS],
                                   [agg(c, t, seeds, "dpts") for c in filt for t in ASYM_TARGETS], 1)[0]
    say(f"| 필터·비동기 5조건 (대상 3명 합침) | {fF(SEEDS):+.2f} {fmt([fF(b) for b in boots])} |")
    say("\n| 원인 조건 (필터 외) | 대상별 Δ점수 (mae) |")
    say("|---|---|")
    for c in deg:
        if c in filt:
            continue
        say(f"| {c} | " + ", ".join(f"{t} {a1[(c, t)]['dpts']:+.1f} ({a1[(c, t)]['mae']:.2f})" for t in ASYM_TARGETS) + " |")
    say()
    RES["ASYM"] = dict(n=len(rows), sham_ok=sham_ok, b=float(coef[-1]), b_ci=(lo, hi), verdict=verdict,
                       a1={f"{c}|{t}": v for (c, t), v in a1.items()}, a4={t: dict(slope=v[0], ci=v[1]) for t, v in a4.items()})
    return a1


# ---------------------------------------------------------------- E3X
def e3x():
    say("## E3X — E3 검증 수준 확장 (PREREG §3)\n")
    rows = read(E3X_GAMES)
    say(f"경기 {len(rows):,} (사전 등록 8,064).\n")
    by = collections.defaultdict(list)
    for r in MAIN + rows:
        by[(r["cond"], r["salt"])].append(r)
    e2, e3 = EXPERIMENTS["E2"], EXPERIMENTS["E3"]
    fitc = [c for c in e2["conds"] if c != "BASE"]
    e3c = [c for c in e3["conds"] if c != "BASE"]
    curve = json.load(open(os.path.join(KIT, "out", "main", "curve.json"), encoding="utf-8"))
    P.SHAPE = curve["shape"]
    tol = {"D": DELTA_D, "M": json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))["M"]}
    P.OUT.clear()
    say("### X1. E3X 6조건만 (등록 곡선·등록 판정 규칙)\n")
    P.validate(by, fitc, by, E3X_CONDS, "BASE", SEEDS, SEEDS, AG, tol, "E2 로 적합, E3X 로 검증")
    OUT.extend(P.OUT); P.OUT.clear()
    say("### X2. E3 + E3X 합침 (E3 단독 판정은 바꾸지 않는다)\n")
    P.validate(by, fitc, by, e3c + E3X_CONDS, "BASE", SEEDS, SEEDS, AG, tol, "E2 로 적합, E3 + E3X 로 검증")
    OUT.extend(P.OUT); P.OUT.clear()
    t = P.Table(by, fitc + e3c + E3X_CONDS, "BASE", SEEDS, AG)
    v = t.pick(SEEDS)
    fit_lo, fit_hi = min(v[c][0] for c in fitc), max(v[c][0] for c in fitc)
    say("### X3. 범위 사실 (판정에서 빼지 않는다)\n")
    say(f"| 조건 | mae [°/s] | 적합 범위 {fit_lo:.2f}–{fit_hi:.2f} 안 | D | 무상관 상한 {CEIL:.3f} 위 (보정값, 2026-10-20) |")
    say("|---|---|---|---|---|")
    for c in E3X_CONDS:
        say(f"| {c} | {v[c][0]:.2f} | {'예' if fit_lo <= v[c][0] <= fit_hi else '아니오'} | {v[c][1]:.3f} | {'예' if v[c][1] > CEIL else '아니오'} |")
    say("\n### X4. 원인별 기울기 (E3 + E3X)\n")
    rng = np.random.default_rng(0)
    boots = [t.pick(list(rng.choice(SEEDS, len(SEEDS)))) for _ in range(N_BOOT)]
    say("| 원인 | 조건 수 | mae 범위 | 기울기 [95 % CI] | 등록 기울기 0.0531 대비 |")
    say("|---|---|---|---|---|")
    x4 = {}
    for g in ("kappa", "kq", "sigma_dps", "delay_sync"):
        cs = [c for c in e3c + E3X_CONDS if c.startswith("R_") and P.cause(c) == g]
        sl = lambda vals: np.polyfit([vals[c][0] for c in cs], [vals[c][1] for c in cs], 1)[0]
        b = sl(v); bb = [sl(x) for x in boots]
        x4[g] = (float(b), ci(bb))
        say(f"| {g} | {len(cs)} | {min(v[c][0] for c in cs):.2f}–{max(v[c][0] for c in cs):.2f} | {b:.4f} {fmt(bb, 4)} | {b / 0.0531:.2f}배 |")
    say()
    RES["E3X"] = dict(n=len(rows), points={c: dict(mae=v[c][0], D=v[c][1]) for c in E3X_CONDS},
                      slopes={g: dict(slope=x[0], ci=x[1]) for g, x in x4.items()})


def figures(a1):
    """그림 2장 (결과를 본 뒤 추가한 표현물. 판정과 수치는 위 표와 같다)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    INK, INK2, GRID, SURF, C1, C2, REF = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff", "#2a78d6", "#eb6834", "#8d8c86"
    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": INK2,
                         "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID,
                         "grid.linewidth": 0.6, "savefig.dpi": 200})
    if a1:
        fig, axes = plt.subplots(1, len(ASYM_TARGETS), figsize=(12.0, 3.8), sharey=True)
        filt = [c for c in ASYM_CONDS if c.startswith("F25")]
        other = [c for c in ASYM_CONDS if c not in filt and c != "SHAM"]
        for ax, t in zip(axes, ASYM_TARGETS):
            ax.axhspan(-DELTA_PTS, DELTA_PTS, color=REF, alpha=0.10, lw=0)
            ax.axhline(0, color=INK2, lw=1)
            for cs, col, lab, mk in ((filt, C1, "필터 25 Hz × 비동기 지연 0.5–6틱", "o"), (other, C2, "κ 50, k_q 0.25, σ 6, 동기 16틱", "s")):
                xs = [a1[(c, t)]["mae"] for c in cs]; ys = [a1[(c, t)]["dpts"] for c in cs]
                lo = [a1[(c, t)]["dpts"] - a1[(c, t)]["ci"][0] for c in cs]; hi = [a1[(c, t)]["ci"][1] - a1[(c, t)]["dpts"] for c in cs]
                if cs is filt:
                    ax.plot(xs, ys, color=col, lw=1.5, zorder=2)
                ax.errorbar(xs, ys, yerr=[lo, hi], fmt=mk, color=col, ms=6, mec=SURF, mew=1, elinewidth=1.2, capsize=0,
                            zorder=3, label=lab)
            s = a1[("SHAM", t)]
            ax.errorbar([s["mae"]], [s["dpts"]], yerr=[[s["dpts"] - s["ci"][0]], [s["ci"][1] - s["dpts"]]], fmt="D",
                        color=REF, ms=5, mec=SURF, mew=1, capsize=0, zorder=3, label="SHAM")
            ax.set_title(f"대상 {t}", fontsize=9, color=INK, loc="left")
            ax.set_xlabel("대상 기체의 피치 추종 오차 mae [°/s]")
        axes[0].set_ylabel("대상의 점수 변화 [점/리그 한 바퀴]")
        axes[0].legend(frameon=False, fontsize=7.5, loc="upper left")
        fig.suptitle(f"그림 X-1. 한 기체만 열화했을 때 그 기체의 점수 변화 (선은 98.33 % CI, 회색 띠는 ±δ_점수 {DELTA_PTS:.1f}점)",
                     fontsize=9, color=INK, x=0.01, ha="left")
        fig.tight_layout(); fig.savefig(os.path.join(OUTDIR, "fig_x1_asym.png")); plt.close(fig)
    if "E3X" in RES:
        e2, e3 = EXPERIMENTS["E2"], EXPERIMENTS["E3"]
        fitc = [c for c in e2["conds"] if c != "BASE"]; e3c = [c for c in e3["conds"] if c != "BASE"]
        by = collections.defaultdict(list)
        for r in MAIN:
            by[(r["cond"], r["salt"])].append(r)
        v = P.Table(by, fitc + e3c, "BASE", SEEDS, AG).pick(SEEDS)
        curve = json.load(open(os.path.join(KIT, "out", "main", "curve.json"), encoding="utf-8"))["curve"]["D"]
        fig, ax = plt.subplots(figsize=(6.6, 4.3))
        xs = np.linspace(0, 11, 100)
        ax.plot(xs, curve[0] + curve[1] * xs, color=INK2, lw=2, label="등록 직선 (E2)")
        ax.fill_between(xs, curve[0] + curve[1] * xs - DELTA_D, curve[0] + curve[1] * xs + DELTA_D, color=REF, alpha=0.10, lw=0,
                        label=f"±δ_D {DELTA_D:.3f}")
        ax.scatter([v[c][0] for c in fitc], [v[c][1] for c in fitc], s=22, color=REF, edgecolor=SURF, linewidth=1, zorder=3, label="E2 적합 20조건")
        ax.scatter([v[c][0] for c in e3c], [v[c][1] for c in e3c], s=26, color=C1, edgecolor=SURF, linewidth=1, zorder=4, label="E3 검증 22조건")
        pts = RES["E3X"]["points"]
        ax.scatter([pts[c]["mae"] for c in E3X_CONDS], [pts[c]["D"] for c in E3X_CONDS], s=40, marker="s", color=C2,
                   edgecolor=SURF, linewidth=1.2, zorder=5, label="E3X 넓힌 수준 6조건")
        offs = {"R_kappa_100": (-6, 8), "R_sigma_dps_10": (6, -11), "R_sigma_dps_20": (-6, 8)}
        for c in E3X_CONDS:
            dx, dy = offs.get(c, (5, -3))
            ax.annotate(c.replace("R_", ""), (pts[c]["mae"], pts[c]["D"]), xytext=(dx, dy), textcoords="offset points",
                        fontsize=7.5, color=INK2, ha="right" if dx < 0 else "left")
        ax.axhline(CEIL, color=INK2, lw=1, ls=(0, (4, 3)))
        ax.text(0.2, CEIL + 0.009, f"무상관 상한 D = {CEIL:.3f}", fontsize=8, color=INK2)
        ax.set_xlim(0, 11); ax.set_ylim(0, 0.8)
        ax.set_xlabel("교전 중 피치 추종 오차 mae [°/s]"); ax.set_ylabel("결과 변화율 D")
        ax.legend(frameon=False, fontsize=7.5, loc="upper left")
        ax.set_title("그림 X-2. 넓힌 검증 수준(E3X)과 등록 직선", fontsize=9, color=INK, loc="left")
        fig.tight_layout(); fig.savefig(os.path.join(OUTDIR, "fig_x2_e3x.png")); plt.close(fig)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    say("# 추가 실험 분석 (ASYM, E3X)\n")
    say("판정 기준: `PREREG_EXTRA.md` (실행 전 고정). 결과를 본 뒤 추가한 실험이므로 등록된 E1–E4 판정은 바꾸지 않는다.\n")
    a1 = asym() if os.path.isfile(ASYM_GAMES) else None
    if os.path.isfile(E3X_GAMES):
        e3x()
    figures(a1)
    say("그림: `fig_x1_asym.png`, `fig_x2_e3x.png` (이 폴더)")
    with open(os.path.join(OUTDIR, "report_extra.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")
    with open(os.path.join(OUTDIR, "results.json"), "w", encoding="utf-8") as f:
        json.dump(RES, f, ensure_ascii=False, indent=1, default=float)
    print("보고서: out/extra_report/report_extra.md")


if __name__ == "__main__":
    main()
