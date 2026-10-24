"""검토 의견 v1의 권장 재분석 D-6~D-10. 경기를 새로 돌리지 않고 out/{main,gen}/games.csv 만 읽는다.

  python reanalysis_v3.py      # → out/reanalysis_v3/ 에 보고서, 그림, results.json

D-6 대안 예측 변수 (1 − 추종 상관)    D-7 필요한 경기 수    D-8 전술별 기울기 (RQ4)
D-9 부트스트랩 교체 후 재판정 (BCa, 잭나이프 t)    D-10 시드 분할 교차검증
결과를 본 뒤 한 분석이다. 등록된 판정을 바꾸지 않고 사실 보고로만 쓴다.
"""
from __future__ import annotations

import collections
import itertools
import json
import os
import sys

import numpy as np
from scipy.stats import norm, t as tdist

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
import predict as P  # noqa: E402
from experiments import EXPERIMENTS  # noqa: E402

OUTDIR = os.path.join(KIT, "out", "reanalysis_v3")
N_BOOT = 2000
OUT: list[str] = []
RES: dict = {}


def say(s=""):
    print(s)
    OUT.append(s)


def ci(a, q=(2.5, 97.5)):
    lo, hi = np.percentile(np.asarray(a, float), q)
    return float(lo), float(hi)


def fmt(a, d=3):
    lo, hi = ci(a)
    return f"[{lo:+.{d}f}, {hi:+.{d}f}]"


def line(x, y):
    b, a = np.polyfit(np.asarray(x, float), np.asarray(y, float), 1)
    return float(a), float(b)


e2, e3, e4 = EXPERIMENTS["E2"], EXPERIMENTS["E3"], EXPERIMENTS["E4"]
AG = list(e2["agents"])
FIT = [c for c in e2["conds"] if c != "BASE"]
TEST = [c for c in e3["conds"] if c != "BASE"]
ALL = FIT + TEST
GROUPS = collections.defaultdict(list)
for c in TEST:
    GROUPS[P.cause(c)].append(c)
DELTA = json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))["D"]
BY = P.load("main")
SEEDS = P.seeds_of(BY, "main", ALL)
TAB = P.Table(BY, ALL, "BASE", SEEDS, AG)
V = TAB.pick(SEEDS)
rng = np.random.default_rng(0)
BOOTS = [list(rng.choice(SEEDS, len(SEEDS))) for _ in range(N_BOOT)]


# ---------------------------------------------------------------- 조건 × 시드 의 (mae, 1−corr, D) 합계
def per_seed_x(by, conds, seeds, agents):
    """(cond, seed) → (mae 합, 1−corr 합, 수, 뒤집힘 수, 경기 수). 경기마다 양 기체 평균."""
    out = {}
    for c in conds:
        for s in seeds:
            ref = {(g["blue"], g["red"], g["scenario"]): g for g in by[("BASE", s)]}
            gs = [g for g in by[(c, s)] if g["blue"] in agents]
            m = [(float(g["blue_mae_q_dps"]) + float(g["red_mae_q_dps"])) / 2 for g in gs]
            cr = [1 - np.nanmean([float(g["blue_corr_q"]), float(g["red_corr_q"])]) for g in gs]
            cr = [x for x in cr if np.isfinite(x)]
            fl = sum((g["winner"], g["condition"]) != (ref[(g["blue"], g["red"], g["scenario"])]["winner"],
                                                      ref[(g["blue"], g["red"], g["scenario"])]["condition"]) for g in gs)
            out[(c, s)] = (sum(m), sum(cr), len(cr), fl, len(gs))
    return out


def pick_x(px, conds, seeds):
    """→ {cond: (mae, 1−corr, D)}"""
    res = {}
    for c in conds:
        a = [px[(c, s)] for s in seeds]
        res[c] = (sum(x[0] for x in a) / sum(x[4] for x in a), sum(x[1] for x in a) / sum(x[2] for x in a),
                  sum(x[3] for x in a) / sum(x[4] for x in a))
    return res


PX = per_seed_x(BY, ALL, SEEDS, AG)
VX = pick_x(PX, ALL, SEEDS)
BX = [pick_x(PX, ALL, b) for b in BOOTS]


# ---------------------------------------------------------------- D-6
def d6():
    say("## D-6. 대안 예측 변수: 1 − 추종 상관\n")
    say("`games.csv`의 `*_corr_q`(경기마다 피치 명령과 응답의 상관)로 1 − corr를 만들어 mae와 같은 절차로 비교했다. "
        "E2로 직선을 적합하고 E3를 예측한다. CI는 시드 부트스트랩(표본마다 다시 적합).\n")
    by4 = P.load("gen")
    g4 = [c for c in e4["conds"] if c != "BASE"]
    s4 = P.seeds_of(by4, "gen", g4)
    v4 = pick_x(per_seed_x(by4, g4, s4, list(e4["agents"])), g4, s4)
    res = {}
    say("| 예측 변수 | E2 잔차 RMS | E2 LOO RMS | E3 RMS | E3 평균 \\|오차\\| | E3 평균 오차 [95 % CI] | E4 열화 5조건 평균 오차 | 원인별 기울기 / 적합 기울기 (κ, k_q, σ, 동기, 조합) |")
    say("|---|---|---|---|---|---|---|---|")
    for k, name in ((0, "mae (등록)"), (1, "1 − corr")):
        x = [VX[c][k] for c in FIT]; y = [VX[c][2] for c in FIT]
        a, b = line(x, y)
        rf = np.array(y) - (a + b * np.array(x))
        loo = []
        for i in range(len(FIT)):
            kk = [j for j in range(len(FIT)) if j != i]
            a2, b2 = line([x[j] for j in kk], [y[j] for j in kk])
            loo.append(y[i] - (a2 + b2 * x[i]))
        e = np.array([VX[c][2] - (a + b * VX[c][k]) for c in TEST])
        boot_mean = []
        for bx in BX:
            ab, bb = line([bx[c][k] for c in FIT], [bx[c][2] for c in FIT])
            boot_mean.append(np.mean([bx[c][2] - (ab + bb * bx[c][k]) for c in TEST]))
        e4m = np.mean([v4[c][2] - (a + b * v4[c][k]) for c in g4 if c != "SHAM"])
        ratios = []
        for g in ("kappa", "kq", "sigma_dps", "delay_sync", "조합"):
            bg = line([VX[c][k] for c in GROUPS[g]], [VX[c][2] for c in GROUPS[g]])[1]
            ratios.append(bg / b)
        res[name] = dict(slope=b, intercept=a, fit_rms=float(np.sqrt(np.mean(rf ** 2))), loo=float(np.sqrt(np.mean(np.square(loo)))),
                         e3_rms=float(np.sqrt(np.mean(e ** 2))), e3_mae=float(np.abs(e).mean()), e3_mean=float(e.mean()),
                         e3_mean_ci=ci(boot_mean), e4_mean=float(e4m), cause_ratio=ratios)
        say(f"| {name} | {res[name]['fit_rms']:.4f} | {res[name]['loo']:.4f} | {res[name]['e3_rms']:.4f} | {res[name]['e3_mae']:.4f} | "
            f"{e.mean():+.3f} {fmt(boot_mean)} | {e4m:+.3f} | " + ", ".join(f"{r:.2f}" for r in ratios) + " |")
    say("\n1 − corr의 조건별 값과 mae의 순위 상관: "
        f"{np.corrcoef(np.argsort(np.argsort([VX[c][0] for c in ALL])), np.argsort(np.argsort([VX[c][1] for c in ALL])))[0, 1]:.3f} (42조건)\n")
    RES["D6"] = res


# ---------------------------------------------------------------- D-7
def d7():
    say("## D-7. 조건의 mae를 재는 데 필요한 경기 수\n")
    say("조건 하나에서 경기 n판을 무작위로 뽑아(비복원) 그 n판의 평균 mae로 D를 예측했을 때, 1,344판 전체의 mae로 "
        "예측한 값과의 차이 |b·(mae_n − mae_전체)|가 95 % 확률로 목표 안에 드는 가장 작은 n을 구했다(조건마다 2,000번 추출, "
        f"b = {line([V[c][0] for c in FIT], [V[c][1] for c in FIT])[1]:.4f}).\n")
    b = line([V[c][0] for c in FIT], [V[c][1] for c in FIT])[1]
    games = collections.defaultdict(list)
    for c in ALL:
        for s in SEEDS:
            for g in BY[(c, s)]:
                games[c].append((float(g["blue_mae_q_dps"]) + float(g["red_mae_q_dps"])) / 2)
    ns = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200]
    r7 = np.random.default_rng(7)
    need = {0.02: {}, 0.01: {}}
    for c in ALL:
        arr = np.array(games[c]); full = arr.mean()
        p95 = {}
        for n in ns:
            idx = np.array([r7.choice(len(arr), n, replace=False) for _ in range(2000)])
            p95[n] = float(np.percentile(np.abs(b * (arr[idx].mean(1) - full)), 95))
        for tgt in need:
            need[tgt][c] = next((n for n in ns if p95[n] <= tgt), f">{ns[-1]}")
    say("| 목표 (D 단위) | 필요한 경기 수: 중앙값 | 범위 (42조건) | mae가 작은 조건(< 1 °/s) | mae가 큰 조건(≥ 4 °/s) |")
    say("|---|---|---|---|---|")
    res = {}
    over = ns[-1] + 1                                   # ">200" 을 201 로 두고 표시만 ">200" 으로

    def num(v):
        return v if isinstance(v, int) else over

    def rng_(xs):
        lo, hi = min(map(num, xs)), max(map(num, xs))
        show = lambda n: f">{ns[-1]}" if n == over else str(n)
        return f"{show(lo)}–{show(hi)}"
    for tgt, d in need.items():
        vals = [num(v) for v in d.values()]
        lo_c = [d[c] for c in ALL if V[c][0] < 1]; hi_c = [d[c] for c in ALL if V[c][0] >= 4]
        med = int(np.median(vals))
        say(f"| ±{tgt} | {med if med != over else f'>{ns[-1]}'} | {rng_(list(d.values()))} | {rng_(lo_c)} | {rng_(hi_c)} |")
        res[str(tgt)] = d
    say("\n**주의**: 이것은 mae를 재는 오차만이다. 곡선 자체의 예측 오차(E3 평균 |오차| 0.034)가 그보다 크므로, "
        "\"수십 경기로 D를 ±0.03–0.05 정도로 가늠한다\"까지만 말할 수 있다(v1 §9-4와 같은 결론).\n")
    RES["D7"] = res


# ---------------------------------------------------------------- D-8
def d8():
    say("## D-8. 전술별 기울기 (RQ4)\n")
    say("참가자마다 리그 한 바퀴 점수 변화 Δ점수(같은 시드의 BASE 대비)를 조건의 mae에 회귀했다. 대칭 열화라 모든 기체가 "
        "같이 나빠진 상태에서 누가 상대적으로 득·실을 보는지를 잰다. 기울기는 조건 사이의 변화만 보므로, BASE 한 번의 "
        "우연(평균으로의 회귀)은 절편에 흡수된다. CI는 시드 부트스트랩.\n")
    res = {}
    for label, conds in (("E2 필터·비동기 20조건 (mae 0.19–10.57)", FIT), ("E2 + E3 42조건", ALL)):
        say(f"### {label}\n")
        say("| 참가자 | BASE 점수 (한 바퀴) | 기울기 [점/(°/s)] [95 % CI] | 판정 | mae 6 °/s 이상 조건의 평균 Δ점수 |")
        say("|---|---|---|---|---|")

        def slopes(seeds):
            d = {c: np.mean([TAB.v[(c, s)][3] for s in seeds], axis=0) for c in conds}
            x = [np.mean([TAB.v[(c, s)][0] for s in seeds]) for c in conds]
            return [line(x, [d[c][i] for c in conds])[1] for i in range(len(AG))]
        b0 = slopes(SEEDS)
        bb = np.array([slopes(b) for b in BOOTS])
        base_pts = {a: np.mean([P.points([g for g in BY[("BASE", s)]], AG)[0][a] for s in SEEDS]) for a in AG}
        big = [c for c in conds if V[c][0] >= 6]
        order = np.argsort(b0)
        r = {}
        for i in order:
            lo, hi = ci(bb[:, i])
            j = "잃음" if hi < 0 else ("얻음" if lo > 0 else "판별 안 됨")
            bigd = np.mean([np.mean([TAB.v[(c, s)][3][i] for s in SEEDS]) for c in big]) if big else float("nan")
            r[AG[i]] = dict(slope=b0[i], ci=(lo, hi), judge=j, base=base_pts[AG[i]], big=float(bigd))
            say(f"| {AG[i]} | {base_pts[AG[i]]:.1f} | {b0[i]:+.2f} [{lo:+.2f}, {hi:+.2f}] | {j} | {bigd:+.1f} ({len(big)}조건) |")
        rho = np.corrcoef(np.argsort(np.argsort([base_pts[a] for a in AG])), np.argsort(np.argsort(b0)))[0, 1]
        say(f"\nBASE 점수 순위와 기울기 순위의 상관: {rho:+.2f} (음수면 강한 전술일수록 열화에서 더 잃는다)\n")
        res[label] = dict(per_agent=r, rank_corr_base_vs_slope=float(rho))
    say("전술을 \"정밀 조준형\"과 \"단순 추적형\"으로 나누는 기준은 참가자 파일에 없다. RQ4의 가설 판정에는 그 분류를 "
        "연구자가 먼저 정해야 한다. 위 표는 분류 없이 참가자별 기울기만 보고한다.\n")
    RES["D8"] = res


# ---------------------------------------------------------------- D-9
def group_err(vals, g):
    a, b = line([vals[c][0] for c in FIT], [vals[c][1] for c in FIT])
    cs = TEST if g == "전체" else GROUPS[g]
    return float(np.mean([vals[c][1] - (a + b * vals[c][0]) for c in cs]))


def judge(lo, hi):
    if -DELTA <= lo and hi <= DELTA:
        return "예측 성공"
    if lo > DELTA or hi < -DELTA:
        return "예측 실패"
    return "판정 불가"


def d9():
    say("## D-9. 부트스트랩 교체 후 재판정\n")
    say("등록 판정과 같은 통계량(원인별 평균 예측 오차, E2 재적합 포함)에 세 가지 구간을 비교했다. "
        "(1) 퍼센타일 부트스트랩(등록 방식), (2) BCa(가속도는 시드 하나씩 빼는 잭나이프 8회), "
        "(3) 잭나이프 t 구간(자유도 7). 시드 8개 군집에서 (1)이 좁게 나오는 경향을 (2)·(3)으로 확인한다.\n")
    bvals = [TAB.pick(b) for b in BOOTS]
    jvals = [TAB.pick([s for s in SEEDS if s != x]) for x in SEEDS]
    say("| 묶음 | 평균 오차 | 퍼센타일 95 % | 판정 | BCa 95 % | 판정 | 잭나이프 t 95 % | 판정 | 퍼센타일 대비 폭 (BCa, t) |")
    say("|---|---|---|---|---|---|---|---|---|")
    res = {}
    for g in list(sorted(GROUPS)) + ["전체"]:
        th = group_err(V, g)
        bt = np.array([group_err(v, g) for v in bvals])
        p_lo, p_hi = ci(bt)
        jk = np.array([group_err(v, g) for v in jvals])
        jm = jk.mean()
        a = np.sum((jm - jk) ** 3) / (6 * np.sum((jm - jk) ** 2) ** 1.5) if np.sum((jm - jk) ** 2) > 0 else 0.0
        z0 = norm.ppf(np.clip(np.mean(bt < th), 1e-6, 1 - 1e-6))
        q = [norm.cdf(z0 + (z0 + z) / (1 - a * (z0 + z))) * 100 for z in (norm.ppf(0.025), norm.ppf(0.975))]
        b_lo, b_hi = np.percentile(bt, q)
        se = np.sqrt((len(SEEDS) - 1) / len(SEEDS) * np.sum((jk - jm) ** 2))
        t_lo, t_hi = th - tdist.ppf(0.975, len(SEEDS) - 1) * se, th + tdist.ppf(0.975, len(SEEDS) - 1) * se
        w = p_hi - p_lo
        res[g] = dict(theta=th, pct=(p_lo, p_hi), bca=(float(b_lo), float(b_hi)), jack_t=(float(t_lo), float(t_hi)),
                      judge=(judge(p_lo, p_hi), judge(b_lo, b_hi), judge(t_lo, t_hi)))
        name = {"kappa": "κ", "kq": "k_q", "sigma_dps": "σ", "delay_sync": "동기 지연"}.get(g, g)
        say(f"| {name} | {th:+.3f} | [{p_lo:+.3f}, {p_hi:+.3f}] | {res[g]['judge'][0]} | [{b_lo:+.3f}, {b_hi:+.3f}] | "
            f"{res[g]['judge'][1]} | [{t_lo:+.3f}, {t_hi:+.3f}] | {res[g]['judge'][2]} | {(b_hi - b_lo) / w:.2f}, {(t_hi - t_lo) / w:.2f} |")
    changed = [g for g, r in res.items() if len(set(r["judge"])) > 1]
    say(f"\n판정이 방식에 따라 달라지는 묶음: {', '.join(changed) if changed else '없음'}.\n")
    # 조건 하나씩 (등록 보고서의 조건별 CI) 도 같은 방식으로
    say("조건 하나씩 보면 (등록 보고서에서 경계에 있던 두 조건):\n")
    say("| 조건 | 오차 | 퍼센타일 95 % | BCa 95 % | 잭나이프 t 95 % |")
    say("|---|---|---|---|---|")
    for c in ("R_kq_0.25", "R_kappa_50"):
        f = lambda vals: vals[c][1] - (lambda ab: ab[0] + ab[1] * vals[c][0])(line([vals[x][0] for x in FIT], [vals[x][1] for x in FIT]))
        th = f(V); bt = np.array([f(v) for v in bvals]); jk = np.array([f(v) for v in jvals]); jm = jk.mean()
        a = np.sum((jm - jk) ** 3) / (6 * np.sum((jm - jk) ** 2) ** 1.5)
        z0 = norm.ppf(np.clip(np.mean(bt < th), 1e-6, 1 - 1e-6))
        q = [norm.cdf(z0 + (z0 + z) / (1 - a * (z0 + z))) * 100 for z in (norm.ppf(0.025), norm.ppf(0.975))]
        se = np.sqrt((len(SEEDS) - 1) / len(SEEDS) * np.sum((jk - jm) ** 2)); tq = tdist.ppf(0.975, len(SEEDS) - 1)
        p = ci(bt); bq = np.percentile(bt, q)
        say(f"| {c} | {th:+.3f} | [{p[0]:+.3f}, {p[1]:+.3f}] | [{bq[0]:+.3f}, {bq[1]:+.3f}] | [{th - tq * se:+.3f}, {th + tq * se:+.3f}] |")
    say()
    RES["D9"] = res


# ---------------------------------------------------------------- D-10
def d10():
    say("## D-10. 시드 분할 교차검증\n")
    say("시드 8개를 4+4로 나누는 35가지와 그 반대 방향(합 70가지)마다, 절반 A의 E2 조건으로 직선을 적합하고 "
        "겹치지 않는 절반 B의 E3 조건을 예측한다(mae와 D 모두 B에서 잰다). \"처음 보는 원인\"이면서 "
        "\"처음 보는 시드\"인 예측이다. 같은 절차로 B의 E2 조건도 예측해, 시드만 바뀔 때의 오차를 함께 낸다.\n")
    splits = [sa for sa in itertools.combinations(SEEDS, 4)]
    rows = collections.defaultdict(list)
    for sa in splits:
        sb = [s for s in SEEDS if s not in sa]
        va, vb = TAB.pick(list(sa)), TAB.pick(sb)
        a, b = line([va[c][0] for c in FIT], [va[c][1] for c in FIT])
        e3e = {c: vb[c][1] - (a + b * vb[c][0]) for c in TEST}
        e2e = [vb[c][1] - (a + b * vb[c][0]) for c in FIT]
        rows["E3 RMS"].append(np.sqrt(np.mean(np.square(list(e3e.values())))))
        rows["E3 평균 오차"].append(np.mean(list(e3e.values())))
        rows["E2 (시드만 바뀜) RMS"].append(np.sqrt(np.mean(np.square(e2e))))
        rows["기울기 (A)"].append(b)
        for g, cs in GROUPS.items():
            rows[f"원인:{g}"].append(np.mean([e3e[c] for c in cs]))
    say(f"| 지표 | 분할 {len(splits)}가지의 중앙값 | 2.5–97.5 백분위 | \\|값\\| ≤ δ_D 인 분할 비율 |")
    say("|---|---|---|---|")
    res = {}
    for k, v in rows.items():
        v = np.array(v)
        frac = f"{np.mean(np.abs(v) <= DELTA):.2f}" if k.startswith(("원인", "E3 평균")) else "—"
        say(f"| {k} | {np.median(v):+.4f} | [{np.percentile(v, 2.5):+.4f}, {np.percentile(v, 97.5):+.4f}] | {frac} |")
        res[k] = dict(median=float(np.median(v)), p025=float(np.percentile(v, 2.5)), p975=float(np.percentile(v, 97.5)))
    say(f"\n참고: 시드 8개 전체로 한 등록 예측의 E3 RMS는 "
        f"{np.sqrt(np.mean([(V[c][1] - (lambda ab: ab[0] + ab[1] * V[c][0])(line([V[x][0] for x in FIT], [V[x][1] for x in FIT]))) ** 2 for c in TEST])):.4f}.\n")
    RES["D10"] = res


# ---------------------------------------------------------------- 그림 (D-8)
def figure_d8():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    INK, INK2, GRID, C1 = "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"
    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": INK2,
                         "xtick.color": INK2, "ytick.color": INK2, "savefig.dpi": 200})
    r = RES["D8"]["E2 필터·비동기 20조건 (mae 0.19–10.57)"]["per_agent"]
    names = sorted(r, key=lambda a: r[a]["slope"])
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    ax.axvline(0, color=INK2, lw=1)
    for i, a in enumerate(names):
        lo, hi = r[a]["ci"]
        ax.plot([lo, hi], [i, i], color=C1, lw=2, solid_capstyle="round")
        ax.scatter([r[a]["slope"]], [i], s=40, color=C1, edgecolor="white", linewidth=1.2, zorder=3)
        ax.text(hi + 0.08, i, f"{r[a]['slope']:+.2f}", va="center", fontsize=8, color=INK2)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels([f"{a} (BASE {r[a]['base']:.0f}점)" for a in names])
    ax.set_xlabel("점수 변화의 기울기 [점/(°/s)], 리그 한 바퀴당")
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_title("그림 D-8. 전술별 기울기 (E2 대칭 열화 20조건, 선은 95 % CI)", fontsize=9, color=INK, loc="left")
    fig.tight_layout(); fig.savefig(os.path.join(OUTDIR, "fig_d8_agent_slopes.png")); plt.close(fig)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    say("# 검토 의견 v1 권장 재분석 (D-6~D-10)\n")
    say(f"원자료: `out/main`, `out/gen`의 games.csv. 경기를 새로 돌리지 않았다. δ_D = {DELTA:.3f}. "
        "결과를 본 뒤 한 분석이며 등록된 판정을 바꾸지 않는다.\n")
    d6(); d7(); d8(); d9(); d10()
    figure_d8()
    say("그림: `fig_d8_agent_slopes.png` (이 폴더)")
    with open(os.path.join(OUTDIR, "report_reanalysis_v3.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")
    with open(os.path.join(OUTDIR, "results.json"), "w", encoding="utf-8") as f:
        json.dump(RES, f, ensure_ascii=False, indent=1, default=float)
    print("보고서: out/reanalysis_v3/report_reanalysis_v3.md")


if __name__ == "__main__":
    main()
