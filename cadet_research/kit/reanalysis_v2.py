"""검토 의견 v1(`../FEEDBACK_FOR_CADET_v1.md`)의 필수 재분석 D-1~D-5.

경기를 새로 돌리지 않는다. `out/{main,gen,feas3,cal}/games.csv` 만 읽고, 기존 분석기(`predict.py`)의 정의를
그대로 가져다 쓴다. 등록 파일(`tolerance.json`, `curve.json`)은 읽기만 한다.

  python reanalysis_v2.py      # → out/reanalysis_v2/ 에 보고서, 그림 3장, results.json

D-1 원인별 기울기와 세 모형 비교   D-2 겹치는 mae 구간 비교   D-3 차분(ΔD) 모형
D-4 무상관 상한 표시와 범위 구분    D-5 경기 수준 분석(순환성)
결과를 본 뒤 하는 분석이다. 등록된 판정을 바꾸지 않고, 사실 보고로만 쓴다.
"""
from __future__ import annotations

import collections
import itertools
import json
import os
import sys

import numpy as np

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
import predict as P  # noqa: E402
from experiments import EXPERIMENTS, V_FIT  # noqa: E402

OUTDIR = os.path.join(KIT, "out", "reanalysis_v2")
N_BOOT = 2000
OUT: list[str] = []
RES: dict = {}
CAUSE_KO = {"필터·비동기": "필터·비동기 (적합)", "kappa": "κ", "kq": "k_q", "sigma_dps": "σ (잡음)",
            "delay_sync": "동기 지연", "조합": "조합"}


def say(s=""):
    print(s)
    OUT.append(s)


def level(c):
    return float(c.rsplit("_", 1)[1])


def line(x, y):
    b, a = np.polyfit(np.asarray(x, float), np.asarray(y, float), 1)
    return float(a), float(b)


def ci(a, q=(2.5, 97.5)):
    lo, hi = np.percentile(np.asarray(a, float), q)
    return float(lo), float(hi)


def fmt_ci(a, d=4):
    lo, hi = ci(a)
    return f"[{lo:.{d}f}, {hi:.{d}f}]"


# ---------------------------------------------------------------- 자료
e2, e3, e4 = EXPERIMENTS["E2"], EXPERIMENTS["E3"], EXPERIMENTS["E4"]
AG = list(e2["agents"])
FIT = [c for c in e2["conds"] if c != "BASE"]
TEST = [c for c in e3["conds"] if c != "BASE"]
ALL = FIT + TEST
GROUPS = {"필터·비동기": FIT}
for c in TEST:
    GROUPS.setdefault(P.cause(c), []).append(c)
TOL = json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))
DELTA = TOL["D"]

BY = P.load("main")
SEEDS = P.seeds_of(BY, "main", ALL)
TAB = P.Table(BY, ALL, "BASE", SEEDS, AG)
V = TAB.pick(SEEDS)
rng = np.random.default_rng(0)
BOOT = [TAB.pick(list(rng.choice(SEEDS, len(SEEDS)))) for _ in range(N_BOOT)]

BY4 = P.load("gen")
G4 = [c for c in e4["conds"] if c != "BASE"]
S4 = P.seeds_of(BY4, "gen", G4)
TAB4 = P.Table(BY4, G4, "BASE", S4, list(e4["agents"]))
V4 = TAB4.pick(S4)
BOOT4 = [TAB4.pick(list(rng.choice(S4, len(S4)))) for _ in range(N_BOOT)]

BY3 = P.load("feas3")
S3 = P.seeds_of(BY3, "feas3", V_FIT)
TAB3 = P.Table(BY3, V_FIT, "BASE", S3, list(EXPERIMENTS["SIG"]["agents"]))
V3 = TAB3.pick(S3)
BOOT3 = [TAB3.pick(list(rng.choice(S3, len(S3)))) for _ in range(N_BOOT)]


def xy(vals, conds):
    return [vals[c][0] for c in conds], [vals[c][1] for c in conds]


A0, B0 = line(*xy(V, FIT))                           # 등록 곡선 (= curve.json)
B0_BOOT = [line(*xy(v, FIT))[1] for v in BOOT]


# ---------------------------------------------------------------- D-1
def d1():
    say("## D-1. 원인별 기울기와 세 모형 비교\n")
    say(f"조건 단위 (mae, D)는 `predict.py`의 `Table.pick`으로 만들었다(시드 {len(SEEDS)}개 × 시나리오 3개 × 참가자 "
        f"{len(AG)}명, 조건당 1,344경기). CI는 시드 부트스트랩 {N_BOOT}회이고, 표본마다 모든 묶음을 다시 적합한다"
        "(같은 재표본을 모든 묶음에 쓰므로 묶음끼리의 차이도 짝지어 비교된다).\n")
    say("| 묶음 | 조건 수 | mae 범위 [°/s] | 기울기 [95 % CI] | 적합 대비 | 기울기 − 적합 기울기 [95 % CI] | 절편 [95 % CI] |")
    say("|---|---|---|---|---|---|---|")
    res = {}
    for g, cs in GROUPS.items():
        a, b = line(*xy(V, cs))
        bb = [line(*xy(v, cs)) for v in BOOT]
        slopes = [x[1] for x in bb]
        diff = [s - s0 for s, s0 in zip(slopes, B0_BOOT)]
        x = [V[c][0] for c in cs]
        res[g] = dict(n=len(cs), slope=b, slope_ci=ci(slopes), intercept=a, intercept_ci=ci([x[0] for x in bb]),
                      diff_ci=ci(diff), mae_range=(min(x), max(x)))
        ratio = "—" if g == "필터·비동기" else f"{b / B0:.2f}배"
        dcell = "—" if g == "필터·비동기" else f"{b - B0:+.4f} {fmt_ci(diff)}"
        say(f"| {CAUSE_KO[g]} | {len(cs)} | {min(x):.2f}–{max(x):.2f} | {b:.4f} {fmt_ci(slopes)} | {ratio} | {dcell} | "
            f"{a:.3f} {fmt_ci([x[0] for x in bb], 3)} |")
    excl = [g for g in res if g != "필터·비동기" and (res[g]["diff_ci"][0] > 0 or res[g]["diff_ci"][1] < 0)]
    say(f"\n적합 기울기 {B0:.4f} {fmt_ci(B0_BOOT)}. 기울기 차이의 CI가 0을 포함하지 않는 묶음: "
        f"{len(excl)}/5 ({', '.join(CAUSE_KO[g] for g in excl)}).\n")

    # 42조건 풀링 세 모형
    names = list(GROUPS)
    cond_g = {c: g for g, cs in GROUPS.items() for c in cs}
    x = np.array([V[c][0] for c in ALL]); y = np.array([V[c][1] for c in ALL])
    gi = np.array([names.index(cond_g[c]) for c in ALL])

    def design(kind, xx, gg):
        if kind == "common":
            return np.column_stack([np.ones_like(xx), xx])
        dum = np.eye(len(names))[gg]
        if kind == "intercepts":
            return np.column_stack([dum, xx])
        return np.column_stack([dum, dum * xx[:, None]])

    say("42조건(적합 20 + 검증 22) 풀링 모형 비교. LOO는 조건 하나씩 빼고 다시 적합한 예측 오차다. "
        "조건들이 시드를 공유하므로 독립 표본을 가정하는 검정(F 검정 등)은 하지 않았다.\n")
    say("| 모형 | 모수 | 잔차 RMS | LOO RMS | AIC |")
    say("|---|---|---|---|---|")
    models = {}
    for kind, label in (("common", "공통 직선"), ("intercepts", "원인별 절편 + 공통 기울기"), ("lines", "원인별 직선")):
        X = design(kind, x, gi)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        r = y - X @ coef
        loo = []
        for i in range(len(y)):
            k = np.arange(len(y)) != i
            c2, *_ = np.linalg.lstsq(X[k], y[k], rcond=None)
            loo.append(y[i] - X[i] @ c2)
        rss = float(np.sum(r ** 2)); p = X.shape[1]
        aic = len(y) * np.log(rss / len(y)) + 2 * p
        models[label] = dict(params=p, rms=float(np.sqrt(rss / len(y))), loo=float(np.sqrt(np.mean(np.square(loo)))), aic=float(aic))
        say(f"| {label} | {p} | {models[label]['rms']:.4f} | {models[label]['loo']:.4f} | {aic:.1f} |")
    say()
    RES["D1"] = dict(groups=res, fit_slope=B0, fit_slope_ci=ci(B0_BOOT), models=models)


# ---------------------------------------------------------------- D-2
def d2():
    say("## D-2. 겹치는 mae 구간에서의 기울기 비교\n")
    say("규칙(실행 전에 정함): 원인 묶음의 mae 범위를 양쪽으로 0.05 °/s 넓힌 구간 안의 적합(필터·비동기) 조건만 뽑는다. "
        "뽑힌 적합 조건이 3개 미만이거나 그 mae 폭이 0.3 °/s 미만이면 기울기를 정할 수 없으므로 \"비교 불가\"로 둔다.\n")
    say("| 원인 묶음 | 원인 기울기 | 겹치는 구간의 적합 조건 | 적합 기울기 (그 구간) | 비 | 차이 [95 % CI] |")
    say("|---|---|---|---|---|---|")
    res = {}
    for g, cs in GROUPS.items():
        if g == "필터·비동기":
            continue
        lo, hi = min(V[c][0] for c in cs) - 0.05, max(V[c][0] for c in cs) + 0.05
        fsel = [c for c in FIT if lo <= V[c][0] <= hi]
        span = (max(V[c][0] for c in fsel) - min(V[c][0] for c in fsel)) if fsel else 0.0
        bc = line(*xy(V, cs))[1]
        fl = ", ".join(f"{c}({V[c][0]:.2f})" for c in fsel) or "없음"
        if len(fsel) < 3 or span < 0.3:
            say(f"| {CAUSE_KO[g]} | {bc:.4f} | {fl} | 비교 불가 (조건 {len(fsel)}개, mae 폭 {span:.2f}) | — | — |")
            res[g] = dict(comparable=False, fit_conds=fsel)
            continue
        bf = line(*xy(V, fsel))[1]
        diff = [line(*xy(v, cs))[1] - line(*xy(v, fsel))[1] for v in BOOT]
        say(f"| {CAUSE_KO[g]} | {bc:.4f} | {fl} | {bf:.4f} | {bc / bf:.2f}배 | {bc - bf:+.4f} {fmt_ci(diff)} |")
        res[g] = dict(comparable=True, fit_conds=fsel, cause_slope=bc, fit_slope_local=bf, diff_ci=ci(diff))
    say()
    RES["D2"] = res


# ---------------------------------------------------------------- D-3
def pair_errors(vals, pairs, b):
    """pairs: (i, j) 는 mae_i ≤ mae_j 로 정렬. 오차 = 실제 ΔD − b·Δmae."""
    return np.array([(vals[j][1] - vals[i][1]) - b * (vals[j][0] - vals[i][0]) for i, j in pairs])


def oriented(vals, pairs):
    return [(i, j) if vals[i][0] <= vals[j][0] else (j, i) for i, j in pairs]


def d3():
    say("## D-3. 차분(ΔD) 모형\n")
    say(f"예측: ΔD = b·Δmae, b는 E2에서 등록한 기울기 {B0:.4f}. 쌍은 mae가 작은 쪽 → 큰 쪽으로 놓는다(Δmae ≥ 0). "
        "오차 = 실제 ΔD − 예측 ΔD. 양수면 실제 변화가 예측보다 크다. "
        "부트스트랩마다 b를 E2에서 다시 적합하고 D와 mae도 다시 계산한다.\n")
    single = [c for c in TEST if c.startswith("R_")]
    by_cause = collections.defaultdict(list)
    for c in single:
        by_cause[P.cause(c)].append(c)
    sets = {}
    for g, cs in by_cause.items():
        cs = sorted(cs, key=level)
        sets[f"원인 안 인접 수준: {CAUSE_KO[g]}"] = list(zip(cs, cs[1:]))
    sets["원인 안 인접 수준: 전체"] = [p for k, v in sets.items() for p in v]
    sets["원인 안 모든 쌍"] = [p for cs in by_cause.values() for p in itertools.combinations(cs, 2)]
    sets["원인 간 교차 쌍 (단일 원인 18조건)"] = [(a, b) for a, b in itertools.combinations(single, 2) if P.cause(a) != P.cause(b)]
    say("| 쌍 묶음 | 쌍 수 | 평균 Δmae | 평균 실제 ΔD | 평균 예측 ΔD | 평균 오차 [95 % CI] | 평균 \\|오차\\| [95 % CI] | RMS | \\|오차\\| ≤ δ_D 비율 | 최대 \\|오차\\| |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    res = {}
    for name, pairs in sets.items():
        pr = oriented(V, pairs)
        e = pair_errors(V, pr, B0)
        dm = np.mean([V[j][0] - V[i][0] for i, j in pr]); dd = np.mean([V[j][1] - V[i][1] for i, j in pr])
        be = [pair_errors(v, pr, b) for v, b in zip(BOOT, B0_BOOT)]
        mean_b = [x.mean() for x in be]; abs_b = [np.abs(x).mean() for x in be]
        res[name] = dict(n=len(pr), mean=float(e.mean()), mean_ci=ci(mean_b), mean_abs=float(np.abs(e).mean()),
                         mean_abs_ci=ci(abs_b), rms=float(np.sqrt(np.mean(e ** 2))), within=float(np.mean(np.abs(e) <= DELTA)),
                         max_abs=float(np.abs(e).max()))
        say(f"| {name} | {len(pr)} | {dm:.2f} | {dd:+.3f} | {B0 * dm:+.3f} | {e.mean():+.3f} {fmt_ci(mean_b, 3)} | "
            f"{np.abs(e).mean():.3f} {fmt_ci(abs_b, 3)} | {res[name]['rms']:.3f} | {res[name]['within']:.2f} | {np.abs(e).max():.3f} |")
    abs_e3 = np.array([V[c][1] - (A0 + B0 * V[c][0]) for c in TEST])
    say(f"\n참고: 절대 D 예측(등록 판정)의 E3 22조건 평균 |오차| {np.abs(abs_e3).mean():.3f}, RMS {np.sqrt(np.mean(abs_e3 ** 2)):.3f}.\n")

    say("원인 안 인접 수준 쌍을 하나씩 보면 (실제 ΔD / 예측 ΔD가 그 구간의 실제 기울기 / 등록 기울기다):\n")
    say("| 쌍 | Δmae | 실제 ΔD | 예측 ΔD | 오차 | 실제 / 예측 |")
    say("|---|---|---|---|---|---|")
    for i, j in oriented(V, sets["원인 안 인접 수준: 전체"]):
        dm, dd = V[j][0] - V[i][0], V[j][1] - V[i][1]
        ratio = f"{dd / (B0 * dm):.1f}" if dm > 0.02 else "— (Δmae < 0.02)"
        say(f"| {i} → {j} | {dm:.2f} | {dd:+.3f} | {B0 * dm:+.3f} | {dd - B0 * dm:+.3f} | {ratio} |")
    say()

    # E4: 열화끼리의 쌍과 SHAM 이 낀 쌍
    deg = [c for c in G4 if c != "SHAM"]
    say("E4 (참가자 12종, 시드 4개)에 같은 b를 적용한다. E2 시드와 E4 시드를 따로 재표본한다.\n")
    say("| 쌍 묶음 | 쌍 수 | 평균 오차 [95 % CI] | 평균 \\|오차\\| | 최대 \\|오차\\| |")
    say("|---|---|---|---|---|")
    e4res = {}
    for name, pairs in (("열화끼리 (SHAM 제외 5조건)", list(itertools.combinations(deg, 2))),
                        ("SHAM ↔ 열화", [("SHAM", c) for c in deg])):
        pr = oriented(V4, pairs)
        e = pair_errors(V4, pr, B0)
        mb = [pair_errors(v4, pr, b).mean() for v4, b in zip(BOOT4, B0_BOOT)]
        e4res[name] = dict(n=len(pr), mean=float(e.mean()), mean_ci=ci(mb), mean_abs=float(np.abs(e).mean()), max_abs=float(np.abs(e).max()))
        say(f"| {name} | {len(pr)} | {e.mean():+.3f} {fmt_ci(mb, 3)} | {np.abs(e).mean():.3f} | {np.abs(e).max():.3f} |")
    abs4 = {c: V4[c][1] - (A0 + B0 * V4[c][0]) for c in G4}
    say(f"\n참고: 절대 D 예측의 E4 오차는 SHAM {abs4['SHAM']:+.3f}, 열화 5조건 평균 {np.mean([abs4[c] for c in deg]):+.3f}.\n")

    # 기울기 재현성
    say("기울기 재현성 (각 데이터셋 안에서 따로 적합, 시드 부트스트랩 CI):\n")
    say("| 데이터셋 | 적합 조건 | 시드 | 기울기 [95 % CI] | 절편 |")
    say("|---|---|---|---|---|")
    rep = {}
    rows = [("main (E2)", V, FIT, BOOT, len(SEEDS)), ("feas3 (SIG 적합 10조건)", V3, V_FIT, BOOT3, len(S3)),
            ("gen (E4 열화 5조건)", V4, deg, BOOT4, len(S4)), ("gen (E4 SHAM 포함 6조건)", V4, G4, BOOT4, len(S4))]
    for name, vals, cs, boot, ns in rows:
        a, b = line(*xy(vals, cs)); bs = [line(*xy(v, cs))[1] for v in boot]
        rep[name] = dict(slope=b, slope_ci=ci(bs), intercept=a)
        say(f"| {name} | {len(cs)} | {ns} | {b:.4f} {fmt_ci(bs)} | {a:.3f} |")
    say()
    RES["D3"] = dict(e3_pairs=res, e4_pairs=e4res, reproducibility=rep)


# ---------------------------------------------------------------- D-4
def indep_agreement(by, seeds):
    """무상관 기준 일치율. 반환 (보정값, plug-in 값).
    plug-in Σp̂² 는 analyze.section_agreement 와 같은 정의인데, 한 경기가 자기 자신과 일치하는 경우를 포함해 위로 치우친다.
    보정값은 같은 경기끼리의 비교를 뺀 불편 추정 Σc(c−1)/(n(n−1)) (2026-10-20, 패널 검토 P0)."""
    base = [g for s in seeds for g in by[("BASE", s)]]
    dist = collections.defaultdict(collections.Counter)
    for g in base:
        dist[(g["blue"], g["red"], g["scenario"])][(g["winner"], g["condition"])] += 1
    n = len(seeds)
    plug = float(np.mean([sum((c / n) ** 2 for c in dist[(g["blue"], g["red"], g["scenario"])].values()) for g in base]))
    unb = float(np.mean([sum(c * (c - 1) for c in cnt.values()) / (n * (n - 1)) for cnt in dist.values()]))
    return unb, plug


def d4():
    say("## D-4. 무상관 상한과 범위 구분\n")
    say("무상관 기준 = 변형 경기의 결과를 같은 대진·시나리오의 BASE 결과 분포에서 독립으로 뽑았을 때 기대되는 일치율"
        ". D = 1 − 일치율이므로 D 상한 = 1 − 무상관 기준이다. "
        "**2026-10-20 정정 (패널 검토 P0)**: 처음 판은 `analyze.py` 4절과 같은 plug-in 값(Σp̂²)을 썼는데, 한 경기가 자기 자신과 "
        "일치하는 경우를 포함해 위로 치우친다. 같은 경기끼리의 비교를 뺀 불편 추정으로 바로잡았다(괄호 안이 이전 값). "
        "상한 위의 조건은 개별 경기의 짝이 사라지고 대진별 결과 분포가 이동한 구간이다(\"무정보\"가 아니다). "
        "등록 판정 규칙은 바꾸지 않고 사실로만 적는다.\n")
    cal_by = P.load("cal")
    rows = [("E1 (cal)", cal_by, P.seeds_of(cal_by, "cal", ["SHAM"]), None),
            ("E2·E3 (main)", BY, SEEDS, None), ("E4 (gen)", BY4, S4, None)]
    say("| 실험 | 무상관 기준 일치율 (이전 plug-in) | D 상한 (이전) | 상한 위 조건 |")
    say("|---|---|---|---|")
    res = {}
    for name, by, seeds, _ in rows:
        ref, plug = indep_agreement(by, seeds)
        if name.startswith("E2"):
            above_f = [c for c in FIT if V[c][1] > 1 - ref]
            above_t = [c for c in TEST if V[c][1] > 1 - ref]
            note = f"적합 {len(above_f)}/{len(FIT)} ({', '.join(above_f)}), 검증 {len(above_t)}/{len(TEST)}"
            res["main"] = dict(ref=ref, ceiling=1 - ref, above_fit=above_f, above_test=above_t)
        elif name.startswith("E4"):
            above = [c for c in G4 if V4[c][1] > 1 - ref - 1e-9]
            note = f"{len(above)}/{len(G4)} ({', '.join(f'{c} {V4[c][1]:.3f}' for c in above)}; 상한과 같은 값 포함)"
            res["gen"] = dict(ref=ref, ceiling=1 - ref, above=above)
        else:
            note = "— (SHAM만)"
            res["cal"] = dict(ref=ref, ceiling=1 - ref)
        say(f"| {name} | {ref:.3f} ({plug:.3f}) | {1 - ref:.3f} ({1 - plug:.3f}) | {note} |")
    mx = max(V[c][1] for c in TEST)
    say(f"\n검증 22조건의 D는 최대 {mx:.3f}로 모두 상한 아래에 있다. 등록 기울기를 정한 적합 20조건 가운데 "
        f"{len(res['main']['above_fit'])}개는 상한 위에 있다. 그림 3·4에 상한을 가로선으로 넣었다.\n")
    RES["D4"] = res


# ---------------------------------------------------------------- D-5
def logistic_fe(y, x, cond_idx, n_cond, beta0=None, iters=25):
    """flip ~ 조건 고정효과 + β·mae. 뉴턴법. 반환 (β, 계수 전체)."""
    X = np.column_stack([np.eye(n_cond)[cond_idx], x])
    w = np.zeros(X.shape[1]) if beta0 is None else beta0.copy()
    for _ in range(iters):
        eta = X @ w
        p = 1 / (1 + np.exp(-eta))
        g = X.T @ (y - p)
        H = (X * (p * (1 - p))[:, None]).T @ X + 1e-9 * np.eye(X.shape[1])
        step = np.linalg.solve(H, g)
        w += step
        if np.max(np.abs(step)) < 1e-8:
            break
    return float(w[-1]), w


def d5():
    say("## D-5. 경기 수준 분석 (순환성)\n")
    say("경기 하나마다 mae(양 기체 평균)와 뒤집힘(같은 대진·시나리오·시드의 BASE와 승자 또는 종료 사유가 다름, "
        "0/1)을 만든다. 대상은 E2·E3의 열화 42조건 전부다.\n")
    games = []
    for c in ALL:
        for s in SEEDS:
            ref = {(g["blue"], g["red"], g["scenario"]): g for g in BY[("BASE", s)]}
            for g in BY[(c, s)]:
                r = ref[(g["blue"], g["red"], g["scenario"])]
                games.append((c, s, (float(g["blue_mae_q_dps"]) + float(g["red_mae_q_dps"])) / 2,
                              float((g["winner"], g["condition"]) != (r["winner"], r["condition"]))))
    cidx = {c: i for i, c in enumerate(ALL)}
    ci_ = np.array([cidx[g[0]] for g in games]); sd = np.array([g[1] for g in games])
    m = np.array([g[2] for g in games]); f = np.array([g[3] for g in games])
    mu_m = np.bincount(ci_, m) / np.bincount(ci_); mu_f = np.bincount(ci_, f) / np.bincount(ci_)
    mc, fc = m - mu_m[ci_], f - mu_f[ci_]
    r_within = float(np.corrcoef(mc, fc)[0, 1])
    r_between = float(np.corrcoef(mu_m, mu_f)[0, 1])
    lpm_within = float(np.sum(mc * fc) / np.sum(mc * mc))
    # 조건 안 사분위
    q = np.zeros(len(m), int)
    for i in range(len(ALL)):
        k = np.where(ci_ == i)[0]
        rank = np.argsort(np.argsort(m[k], kind="stable"), kind="stable")
        q[k] = np.minimum(4 * rank // len(k), 3)
    qrate = [float(f[q == j].mean()) for j in range(4)]
    qmae = [float(mc[q == j].mean()) for j in range(4)]
    # 시드 군집 부트스트랩: 조건 안 상관, 선형확률 기울기, 로지스틱 β
    beta, w_full = logistic_fe(f, m, ci_, len(ALL))
    seed_rows = {s: np.where(sd == s)[0] for s in SEEDS}
    rb = []; lb = []; bb = []
    rng5 = np.random.default_rng(5)
    for _ in range(1000):
        idx = np.concatenate([seed_rows[s] for s in rng5.choice(SEEDS, len(SEEDS))])
        cc, mm, ff = ci_[idx], m[idx], f[idx]
        cnt = np.bincount(cc, minlength=len(ALL))
        mum = np.bincount(cc, mm, minlength=len(ALL)) / cnt; muf = np.bincount(cc, ff, minlength=len(ALL)) / cnt
        a_, b_ = mm - mum[cc], ff - muf[cc]
        rb.append(np.corrcoef(a_, b_)[0, 1]); lb.append(np.sum(a_ * b_) / np.sum(a_ * a_))
        bb.append(logistic_fe(ff, mm, cc, len(ALL), beta0=w_full, iters=6)[0])
    say(f"경기 수 {len(games):,} (42조건 × 1,344).\n")
    say("| 수준 | 상관 [95 % CI] | 뒤집힘 확률 기울기 [/(°/s)] |")
    say("|---|---|---|")
    say(f"| 조건 안 (조건 평균을 뺀 경기 수준) | {r_within:.3f} {fmt_ci(rb, 3)} | {lpm_within:.4f} {fmt_ci(lb)} |")
    say(f"| 조건 간 (42조건 평균) | {r_between:.3f} | {B0:.4f} (등록 곡선, 적합 20조건) |")
    say(f"\n조건 안 mae 사분위별 뒤집힘률 (사분위마다 조건 평균 대비 mae 편차의 평균):\n")
    say("| 사분위 | 1 (조건 안에서 mae가 가장 낮은 25 %) | 2 | 3 | 4 (가장 높은 25 %) |")
    say("|---|---|---|---|---|")
    say("| 뒤집힘률 | " + " | ".join(f"{r:.3f}" for r in qrate) + " |")
    say("| mae 편차 [°/s] | " + " | ".join(f"{x:+.2f}" for x in qmae) + " |")
    say(f"\n로지스틱 회귀 (뒤집힘 ~ 조건 고정효과 42개 + β·mae, 시드 군집 부트스트랩 1,000회): "
        f"β = {beta:.4f} {fmt_ci(bb)}, 오즈비 {np.exp(beta):.3f}/(°/s) {fmt_ci(np.exp(bb), 3)}.\n")

    # 같은 경기 설정(대진·시나리오·시드)끼리: 조건 + 경기 설정 이중 고정효과 선형확률 모형
    keys = {}
    gkey = []
    for c in ALL:
        for s in SEEDS:
            for g in BY[(c, s)]:
                gkey.append((g["blue"], g["red"], g["scenario"], s))
    kidx = np.array([keys.setdefault(k, len(keys)) for k in gkey], int)

    def twoway(yv, xv, a_idx, b_idx, na, nb, iters=200):
        yv, xv = yv.copy(), xv.copy()
        ca, cb = np.bincount(a_idx, minlength=na), np.bincount(b_idx, minlength=nb)
        for _ in range(iters):
            for idx, cnt, n in ((a_idx, ca, na), (b_idx, cb, nb)):
                yv -= (np.bincount(idx, yv, minlength=n) / cnt)[idx]
                xv -= (np.bincount(idx, xv, minlength=n) / cnt)[idx]
        return float(np.sum(xv * yv) / np.sum(xv * xv)), float(np.var(xv))

    b2, vx2 = twoway(f, m, ci_, kidx, len(ALL), len(keys))
    tb = []
    rng6 = np.random.default_rng(6)
    for _ in range(300):
        parts, kk = [], []
        for j, s in enumerate(rng6.choice(SEEDS, len(SEEDS))):
            r_ = seed_rows[s]; parts.append(r_); kk.append(kidx[r_] + j * len(keys))   # 같은 시드가 두 번 뽑히면 다른 설정으로 본다
        idx = np.concatenate(parts); kb = np.concatenate(kk)
        _, kb = np.unique(kb, return_inverse=True)
        tb.append(twoway(f[idx], m[idx], ci_[idx], kb, len(ALL), kb.max() + 1, iters=60)[0])
    say(f"같은 경기 설정끼리의 비교 (선형확률 모형, 조건 고정효과 42개 + 경기 설정(대진·시나리오·시드) 고정효과 "
        f"{len(keys):,}개, 시드 군집 부트스트랩 300회): 기울기 {b2:.4f} {fmt_ci(tb)} /(°/s). "
        f"조건 고정효과만 둔 기울기 {lpm_within:.4f}와 비교한다. 이 기울기는 같은 대진·시나리오·시드의 경기가 "
        f"조건에 따라 평소보다 더 빗나갔을 때 뒤집힘이 얼마나 늘었는지를 잰다 (남은 mae 분산 {vx2:.3f}).\n")
    # 예측 변수와 결과를 서로 다른 경기에서: mae 는 시드 절반, D 는 나머지 절반
    splits = [sa for sa in itertools.combinations(SEEDS, len(SEEDS) // 2) if SEEDS[0] in sa]     # 35가지
    sr = {"r_all": [], "slope": [], "rms_e3": [], "r_mae": []}
    for sa in splits:
        sb_ = [s for s in SEEDS if s not in sa]
        va, vb = TAB.pick(list(sa)), TAB.pick(sb_)
        cross = {c: (va[c][0], vb[c][1]) for c in ALL}              # (A 의 mae, B 의 D)
        a_, b_ = line(*xy(cross, FIT))
        sr["r_all"].append(np.corrcoef([cross[c][0] for c in ALL], [cross[c][1] for c in ALL])[0, 1])
        sr["slope"].append(b_)
        sr["rms_e3"].append(np.sqrt(np.mean([(cross[c][1] - (a_ + b_ * cross[c][0])) ** 2 for c in TEST])))
        sr["r_mae"].append(np.corrcoef([va[c][0] for c in ALL], [vb[c][0] for c in ALL])[0, 1])
    rng_ = lambda k, d=3: f"{np.mean(sr[k]):.{d}f} (범위 {np.min(sr[k]):.{d}f}–{np.max(sr[k]):.{d}f})"
    say(f"예측 변수와 결과를 서로 다른 경기에서 잰 경우 (시드 8개를 4+4로 나누는 {len(splits)}가지 전부): "
        f"mae는 한쪽 절반의 경기에서, D는 겹치지 않는 다른 절반의 경기에서 잰다.\n")
    say("| 지표 | 35가지 분할의 평균 (범위) |")
    say("|---|---|")
    say(f"| 두 절반의 조건별 mae 상관 (mae가 조건의 성질인가) | {rng_('r_mae', 4)} |")
    say(f"| 42조건 corr(절반 A의 mae, 절반 B의 D) | {rng_('r_all')} |")
    say(f"| 적합 기울기 (E2, A의 mae → B의 D) | {rng_('slope', 4)} |")
    say(f"| E3 22조건 예측 RMS | {rng_('rms_e3')} |")
    say()
    RES["D5_split"] = {k: dict(mean=float(np.mean(v)), min=float(np.min(v)), max=float(np.max(v))) for k, v in sr.items()}
    RES["D5"] = dict(n_games=len(games), r_within=r_within, r_within_ci=ci(rb), r_between=r_between,
                     lpm_within=lpm_within, lpm_within_ci=ci(lb), quartile_flip=qrate, quartile_mae_dev=qmae,
                     logit_beta=beta, logit_beta_ci=ci(bb), lpm_twoway=b2, lpm_twoway_ci=ci(tb))


# ---------------------------------------------------------------- 그림
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"
C1, C2, C3, REF = "#2a78d6", "#eb6834", "#1baf7a", "#8d8c86"     # 팔레트 문서의 앞 3개 슬롯 + 기준 회색


def setup_mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 9,
                         "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.color": GRID, "grid.linewidth": 0.6, "savefig.dpi": 200, "figure.facecolor": SURF,
                         "axes.facecolor": SURF})
    return plt


def band(ax, xs, boot_lines, color):
    ys = np.array([a + b * xs for a, b in boot_lines])
    ax.fill_between(xs, np.percentile(ys, 2.5, 0), np.percentile(ys, 97.5, 0), color=color, alpha=0.15, lw=0)


def figures():
    plt = setup_mpl()
    e2_boot = [line(*xy(v, FIT)) for v in BOOT]
    ceil = RES["D4"]["main"]["ceiling"]

    # 그림 3: E2 곡선
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    xs = np.linspace(0, 11, 200)
    band(ax, xs, e2_boot, REF)
    ax.plot(xs, A0 + B0 * xs, color=INK2, lw=2, label=f"등록 직선 D = {A0:.3f} + {B0:.4f}·mae")
    for fc, col, mk in (("25", C1, "o"), ("12", C2, "s"), ("5", C3, "^")):
        cs = [c for c in FIT if c.startswith(f"F{fc}_")]
        ax.scatter([V[c][0] for c in cs], [V[c][1] for c in cs], s=34, color=col, marker=mk,
                   edgecolor=SURF, linewidth=1.2, zorder=3, label=f"필터 {fc} Hz × 비동기 지연")
    ax.axhline(ceil, color=INK2, lw=1, ls=(0, (4, 3)))
    ax.text(10.9, ceil + 0.012, f"무상관 상한 D = {ceil:.3f}", ha="right", va="bottom", color=INK2, fontsize=8)
    ax.set_xlabel("교전 중 피치 추종 오차 mae [°/s]"); ax.set_ylabel("결과 변화율 D")
    ax.set_xlim(0, 11); ax.set_ylim(0, 0.7)
    ax.legend(frameon=False, loc="upper left", fontsize=8)
    ax.set_title("그림 3. E2 적합: 추종 오차와 결과 변화율 (띠는 시드 부트스트랩 95 %)", fontsize=9, color=INK, loc="left")
    fig.tight_layout(); fig.savefig(os.path.join(OUTDIR, "fig3_e2_curve.png")); plt.close(fig)

    # 그림 4: E3 를 E2 위에 (원인별은 그림 D-1 에서)
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    xs = np.linspace(0, 4, 200)
    band(ax, xs, e2_boot, REF)
    ax.plot(xs, A0 + B0 * xs, color=INK2, lw=2, label="등록 직선 (E2)")
    ax.fill_between(xs, A0 + B0 * xs - DELTA, A0 + B0 * xs + DELTA, color=REF, alpha=0.08, lw=0, label=f"허용폭 ±δ_D = {DELTA:.3f}")
    fx = [c for c in FIT if V[c][0] <= 4]
    ax.scatter([V[c][0] for c in fx], [V[c][1] for c in fx], s=26, color=REF, edgecolor=SURF, linewidth=1, zorder=3,
               label="E2 적합 조건 (mae ≤ 4)")
    ax.scatter([V[c][0] for c in TEST], [V[c][1] for c in TEST], s=34, color=C1, edgecolor=SURF, linewidth=1.2, zorder=4,
               label="E3 검증 조건 22개")
    for c, dx, dy in (("R_kq_0.25", 0.08, 0.0), ("R_kappa_50", 0.08, 0.0), ("R_kappa_2", 0.07, -0.008)):
        ax.annotate(c, (V[c][0], V[c][1]), xytext=(V[c][0] + dx, V[c][1] + dy), fontsize=7.5, color=INK2, va="center")
    ax.axhline(ceil, color=INK2, lw=1, ls=(0, (4, 3)))
    ax.text(3.95, ceil + 0.012, f"무상관 상한 D = {ceil:.3f}", ha="right", va="bottom", color=INK2, fontsize=8)
    ax.set_xlabel("교전 중 피치 추종 오차 mae [°/s]"); ax.set_ylabel("결과 변화율 D")
    ax.set_xlim(0, 4); ax.set_ylim(0, 0.5)
    ax.legend(frameon=False, loc="lower right", fontsize=8)
    ax.set_title("그림 4. E3 검증 조건과 등록 직선 (mae 0–4 °/s, 진한 띠는 직선의 95 %)", fontsize=9, color=INK, loc="left")
    fig.tight_layout(); fig.savefig(os.path.join(OUTDIR, "fig4_e3_on_e2.png")); plt.close(fig)

    # 그림 D-1: 원인별 소형 다중 그림
    gs = [g for g in GROUPS if g != "필터·비동기"]
    fig, axes = plt.subplots(1, len(gs), figsize=(12.5, 3.3), sharey=True)
    for ax, g in zip(axes, gs):
        cs = GROUPS[g]
        x0, x1 = 0, max(4.0, max(V[c][0] for c in cs) + 0.2)
        xs = np.linspace(x0, x1, 100)
        band(ax, xs, e2_boot, REF)
        ax.plot(xs, A0 + B0 * xs, color=REF, lw=1.6, ls=(0, (4, 3)))
        fx = [c for c in FIT if V[c][0] <= x1]
        ax.scatter([V[c][0] for c in fx], [V[c][1] for c in fx], s=16, color=REF, edgecolor=SURF, linewidth=0.8, zorder=3)
        a, b = line(*xy(V, cs))
        lo, hi = min(V[c][0] for c in cs), max(V[c][0] for c in cs)
        xx = np.linspace(lo, hi, 50)
        ax.plot(xx, a + b * xx, color=C1, lw=2, zorder=4)
        ax.scatter([V[c][0] for c in cs], [V[c][1] for c in cs], s=34, color=C1, edgecolor=SURF, linewidth=1.2, zorder=5)
        s = RES["D1"]["groups"][g]
        ax.set_title(f"{CAUSE_KO[g]}: 기울기 {b:.3f}\n[{s['slope_ci'][0]:.3f}, {s['slope_ci'][1]:.3f}] (적합 {B0:.3f})",
                     fontsize=8.5, color=INK, loc="left")
        ax.set_xlim(x0, x1); ax.set_ylim(0, 0.5); ax.set_xlabel("mae [°/s]")
    axes[0].set_ylabel("결과 변화율 D")
    fig.suptitle("그림 D-1. 원인별 직선(파랑)과 등록 직선(회색 점선, 띠는 95 %). 회색 점은 같은 구간의 E2 적합 조건",
                 fontsize=9, color=INK, x=0.01, ha="left")
    fig.tight_layout(); fig.savefig(os.path.join(OUTDIR, "fig_d1_cause_slopes.png")); plt.close(fig)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    say("# 검토 의견 v1 재분석 (D-1~D-5)\n")
    say(f"원자료: `out/main`(E2·E3), `out/gen`(E4), `out/feas3`(SIG), `out/cal`(E1)의 games.csv. 경기를 새로 돌리지 않았다. "
        f"허용폭 δ_D = {DELTA:.3f}(`out/cal/tolerance.json`). 결과를 본 뒤 한 분석이며 등록된 판정을 바꾸지 않는다.\n")
    d1(); d2(); d3(); d4(); d5()
    figures()
    say("그림: `fig3_e2_curve.png`, `fig4_e3_on_e2.png`, `fig_d1_cause_slopes.png` (이 폴더)")
    with open(os.path.join(OUTDIR, "report_reanalysis_v2.md"), "w", encoding="utf-8") as fo:
        fo.write("\n".join(OUT) + "\n")
    with open(os.path.join(OUTDIR, "results.json"), "w", encoding="utf-8") as fo:
        json.dump(RES, fo, ensure_ascii=False, indent=1, default=float)
    print("보고서: out/reanalysis_v2/report_reanalysis_v2.md")


if __name__ == "__main__":
    main()
