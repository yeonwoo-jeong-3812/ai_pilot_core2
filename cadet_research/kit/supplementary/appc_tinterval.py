"""부록 C용 시드 단위 t 구간 — 퍼센타일 부트스트랩만 있던 검정들 (사후 민감도, 2026-10-24). 등록 판정을 바꾸지 않는다.

  python supplementary/appc_tinterval.py   # → appc_tinterval_output.md, appc_tinterval.json (경기 0판)

P5 이후의 사전 등록은 "퍼센타일 부트스트랩과 시드 단위 t 구간이 같은 판정일 때만 결론"을 규칙으로 썼다.
그 이전 검정 중 t 구간이 없던 것을 같은 방식으로 다시 계산한다(E3는 D-9에 이미 있다).
  가. ASYM A1 (조건 × 대상 Δ점수, 98.33 %), A2 (기울기 b, 95 %), 원래 시드 반등 — 원자료 out/asym, 짝 out/main BASE
  나. E3X 원인 묶음 판정 (95 %, 등록 곡선)                              — out/e3x, 짝 out/main BASE
  다. P2-b 정밀 조준 기총의 반등 (98.33 %)                              — p2b_games.csv (안의 BASE)
  라. P4 T-B 새 시드의 반등 (98.33 %)                                   — out/rep
  마. P4 T-C F5_D6 − 동기 24의 D 차이 (95 %)                            — out/rep
  바. P4 T-A·T-D (95 %, 곡선은 main, 자료는 rep)                         — out/rep
퍼센타일 구간은 원래 스크립트와 같은 난수(np.random.default_rng(0), 2,000회)로 다시 계산해 등록 보고서 값과 같은지 확인한다(E3X만 등록 값을 옮겨 적음).
t 구간은 시드별 값의 평균 ± t(자유도 = 시드 수 − 1) × 표준오차. 곡선을 쓰는 E3X는 잭나이프 t(D-9 방식, 주)와
(1) 곡선 고정 (2) 곡선 불확실성(main 시드 부트스트랩 표준편차) 포함을 함께 낸다.
"""
from __future__ import annotations

import collections
import csv
import json
import os
import sys

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, KIT)
sys.stdout.reconfigure(encoding="utf-8")
import predict as P  # noqa: E402
from analyze import points  # noqa: E402
from experiments import ASYM_CONDS, ASYM_TARGETS, E3X_CONDS, EXPERIMENTS  # noqa: E402

P.SHAPE = "linear"
N_BOOT = 2000
AG = list(EXPERIMENTS["E2"]["agents"])
FIT = [c for c in EXPERIMENTS["E2"]["conds"] if c != "BASE"]
DD = json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))["D"]
DP = json.load(open(os.path.join(KIT, "out", "cal", "delta.json"), encoding="utf-8"))["delta_pts"]
LV3 = 100 * (1 - 0.05 / 3)
OUT, RES = [], {}
KB = lambda r: (r["blue"], r["red"], r["scenario"], r["salt"])


def say(s=""):
    print(s)
    OUT.append(s)


def read(path):
    return list(csv.DictReader(open(path, encoding="utf-8")))


def pct(a, lv):
    lo, hi = np.percentile(np.asarray(a, float), [(100 - lv) / 2, 100 - (100 - lv) / 2])
    return float(lo), float(hi)


def tint(per_seed, lv, extra_sd=0.0):
    x = np.asarray(per_seed, float)
    m, se = float(x.mean()), float(x.std(ddof=1) / np.sqrt(len(x)))
    se = float(np.sqrt(se ** 2 + extra_sd ** 2))
    q = stats.t.ppf(1 - (1 - lv / 100) / 2, len(x) - 1)
    return m - q * se, m + q * se


def judge_pts(lo, hi):
    return "차이 없음" if -DP <= lo and hi <= DP else ("차이 있음" if lo > DP or hi < -DP else "판정 불가")


def judge_above(lo, hi, thr, yes, no):
    return yes if lo > thr else (no if hi < thr else "판정 불가")


def both(j1, j2):
    return j1 if j1 == j2 else "판정 불가(구간 방식에 따라 다름)"


MAIN = [r for r in read(os.path.join(KIT, "out", "main", "games.csv")) if r["target"] == ""]
MAIN_BASE = {KB(r): r for r in MAIN if r["cond"] == "BASE"}
SEEDS = [f"main-{i}" for i in range(8)]


# ---------------------------------------------------------------- 가. ASYM A1·A2
def asym():
    rows = read(os.path.join(KIT, "out", "asym", "games.csv"))
    cell = {}
    for c in ASYM_CONDS:
        for t in ASYM_TARGETS:
            for s in SEEDS:
                gs = [r for r in rows if r["cond"] == c and r["target"] == t and r["salt"] == s]
                bs = [MAIN_BASE[KB(g)] for g in gs]
                own = lambda g: float(g["blue_mae_q_dps"] if g["blue"] == t else g["red_mae_q_dps"])
                cell[(c, t, s)] = (points(gs, AG)[0][t] - points(bs, AG)[0][t], float(np.mean([own(g) for g in gs])))
    rng = np.random.default_rng(0)
    boots = [list(rng.choice(SEEDS, len(SEEDS))) for _ in range(N_BOOT)]
    say(f"## 가. ASYM A1 — 조건 × 대상 Δ점수 ({LV3:.2f} %, δ_점수 {DP:.2f}점, 시드 8)\n")
    say("| 조건 | 대상 | Δ점수 | 퍼센타일 (재계산) | 판정 | 시드 t | 판정 | 두 방식 |")
    say("|---|---|---|---|---|---|---|---|")
    a1, n_dis = {}, 0
    for c in ASYM_CONDS:
        for t in ASYM_TARGETS:
            ps = [cell[(c, t, s)][0] for s in SEEDS]
            m = float(np.mean(ps))
            p_lo, p_hi = pct([np.mean([cell[(c, t, s)][0] for s in b]) for b in boots], LV3)
            t_lo, t_hi = tint(ps, LV3)
            jp, jt = judge_pts(p_lo, p_hi), judge_pts(t_lo, t_hi)
            n_dis += jp != jt
            a1[f"{c}|{t}"] = dict(mean=m, pct=(p_lo, p_hi), t=(t_lo, t_hi), judge_pct=jp, judge_t=jt)
            say(f"| {c} | {t} | {m:+.1f} | [{p_lo:+.1f}, {p_hi:+.1f}] | {jp} | [{t_lo:+.1f}, {t_hi:+.1f}] | {jt} | "
                f"{'같음' if jp == jt else '**다름**'} |")
    say(f"\n30칸 중 두 방식의 판정이 다른 칸: {n_dis}.\n")
    deg = [c for c in ASYM_CONDS if c != "SHAM"]

    def fit_b(seeds):
        X, y = [], []
        for c in deg:
            for i, t in enumerate(ASYM_TARGETS):
                row = [0.0] * len(ASYM_TARGETS); row[i] = 1.0
                X.append(row + [np.mean([cell[(c, t, s)][1] for s in seeds])])
                y.append(np.mean([cell[(c, t, s)][0] for s in seeds]))
        return float(np.linalg.lstsq(np.array(X), np.array(y), rcond=None)[0][-1])
    b0 = fit_b(SEEDS)
    p_lo, p_hi = pct([fit_b(b) for b in boots], 95.0)
    per = [fit_b([s]) for s in SEEDS]
    t_lo, t_hi = tint(per, 95.0)
    v = lambda lo, hi: "반대 방향" if lo > 0 else ("성립" if hi < 0 else "성립하지 않음")
    say(f"**A2 (주) 기울기 b**: {b0:+.2f}점/(°/s). 퍼센타일 95 % [{p_lo:+.2f}, {p_hi:+.2f}] → {v(p_lo, p_hi)}. "
        f"시드별 기울기 {', '.join(f'{x:+.2f}' for x in per)} → 시드 t 95 % [{t_lo:+.2f}, {t_hi:+.2f}] → {v(t_lo, t_hi)}. "
        f"두 방식: **{both(v(p_lo, p_hi), v(t_lo, t_hi))}**. "
        "(시드 t는 시드마다 따로 맞춘 기울기의 평균이라 전체 자료로 맞춘 b와 조금 다를 수 있다.)\n")
    RES["ASYM"] = dict(a1=a1, disagree=n_dis, a2=dict(b=b0, pct=(p_lo, p_hi), per_seed=per, t=(t_lo, t_hi)))


# ---------------------------------------------------------------- 나. E3X
def e3x():
    by = collections.defaultdict(list)
    for r in MAIN + read(os.path.join(KIT, "out", "e3x", "games.csv")):
        by[(r["cond"], r["salt"])].append(r)
    tf = P.Table(by, FIT, "BASE", SEEDS, AG)
    tt = P.Table(by, E3X_CONDS, "BASE", SEEDS, AG)
    line = lambda v: tuple(np.polyfit([v[c][0] for c in FIT], [v[c][1] for c in FIT], 1)[::-1])
    a0, b0 = line(tf.pick(SEEDS))
    rng = np.random.default_rng(0)
    curves = [line(tf.pick(list(rng.choice(SEEDS, len(SEEDS))))) for _ in range(N_BOOT)]
    v_all = tt.pick(SEEDS)
    per = {s: tt.pick([s]) for s in SEEDS}
    reg = {"delay_sync": (-0.370, -0.312), "kappa": (0.086, 0.146), "kq": (-0.059, -0.003), "sigma_dps": (0.016, 0.056)}
    # 잭나이프 t (D-9와 같은 방식): 시드 하나를 빼고 곡선 적합과 검증을 같은 7개 시드로 다시 한다
    jk_fit = {x: line(tf.pick([s for s in SEEDS if s != x])) for x in SEEDS}
    jk_val = {x: tt.pick([s for s in SEEDS if s != x]) for x in SEEDS}
    tq = stats.t.ppf(0.975, len(SEEDS) - 1)
    say(f"## 나. E3X 원인 묶음 (95 %, 등록 곡선 D = {a0:.3f} + {b0:.4f}·mae, δ_D {DD:.3f}, 시드 8)\n")
    say("E3X는 곡선을 맞춘 시드와 검증 시드가 같다(main 8). 그래서 t 구간을 세 가지로 냈다. "
        "**잭나이프 t가 E3의 D-9(`FEEDBACK_FOR_CADET_v3.md` §4)와 같은 방식이고, 곡선과 검증의 상관을 반영하므로 주 비교로 쓴다.** "
        "곡선 고정은 곡선 불확실성을 빼고, \"곡선 불확실성 포함\"은 그것을 독립이라고 보고 더한 값이다.\n")
    say("| 묶음 | 평균 오차 | 퍼센타일 (등록 보고서 인용) | 잭나이프 t (D-9 방식) | t: 곡선 고정 | t: 곡선 불확실성 포함 | 판정: 퍼센타일 / 잭나이프 / 고정 / 포함 | 두 방식 (퍼센타일 대 잭나이프 t) |")
    say("|---|---|---|---|---|---|---|---|")
    out = {}
    for g, (rlo, rhi) in reg.items():
        cs = [c for c in E3X_CONDS if P.cause(c) == g]
        f = lambda v, a, b: float(np.mean([v[c][1] - (a + b * v[c][0]) for c in cs]))
        m = f(v_all, a0, b0)
        ps = [f(per[s], a0, b0) for s in SEEDS]
        sdc = float(np.std([f(v_all, a, b) for a, b in curves]))
        t1, t2 = tint(ps, 95.0), tint(ps, 95.0, sdc)
        jk = np.array([f(jk_val[x], *jk_fit[x]) for x in SEEDS])
        se = float(np.sqrt((len(SEEDS) - 1) / len(SEEDS) * np.sum((jk - jk.mean()) ** 2)))
        tj = (m - tq * se, m + tq * se)
        jp, jj, j1, j2 = P.judge(rlo, rhi, DD), P.judge(*tj, DD), P.judge(*t1, DD), P.judge(*t2, DD)
        out[g] = dict(conds=cs, mean=m, per_seed=ps, pct=(rlo, rhi), jack_t=tj, t_fixed=t1, t_curve=t2,
                      judges=dict(pct=jp, jack=jj, fixed=j1, curve=j2))
        say(f"| {g} ({', '.join(cs)}) | {m:+.3f} | [{rlo:+.3f}, {rhi:+.3f}] | [{tj[0]:+.3f}, {tj[1]:+.3f}] | "
            f"[{t1[0]:+.3f}, {t1[1]:+.3f}] | [{t2[0]:+.3f}, {t2[1]:+.3f}] | {jp} / {jj} / {j1} / {j2} | **{both(jp, jj)}** |")
    say("\n퍼센타일 구간은 다시 계산하지 않고 `out/extra_report/report_extra.md` X1의 등록 값(곡선과 검증 자료를 함께 재표본)을 옮겨 적었다. "
        f"평균 오차의 점추정은 두 조건 오차의 단순 평균이고, 등록 보고서의 +0.114는 부트스트랩 평균이다(`predict.py`).\n")
    RES["E3X"] = out


# ---------------------------------------------------------------- 다·라. 반등 (P2-b, P4 T-B)
def rebound(rows, base_rows, target, seeds, boots, label, rule):
    base = {KB(r): r for r in base_rows}
    d = {}
    for c in ("F25_D2", "F25_D6"):
        for s in seeds:
            gs = [r for r in rows if r["cond"] == c and r["target"] == target and r["salt"] == s]
            d[(c, s)] = points(gs, AG)[0][target] - points([base[KB(g)] for g in gs], AG)[0][target]
    con = [d[("F25_D6", s)] - d[("F25_D2", s)] for s in seeds]
    m = float(np.mean(con))
    idx = {s: i for i, s in enumerate(seeds)}
    p = pct([np.mean([con[idx[s]] for s in b]) for b in boots], LV3)
    t = tint(con, LV3)
    jp, jt = rule(*p), rule(*t)
    say(f"| {label} | {m:+.1f} | {', '.join(f'{x:+.0f}' for x in con)} | [{p[0]:+.1f}, {p[1]:+.1f}] | {jp} | "
        f"[{t[0]:+.1f}, {t[1]:+.1f}] | {jt} | **{both(jp, jt)}** |")
    return dict(mean=m, per_seed=con, pct=p, t=t, judges=(jp, jt))


def rebounds():
    say(f"## 다·라. 한 기체 열화의 반등 C = Δ점수(6틱) − Δ점수(2틱) ({LV3:.2f} %, 문턱 +{DP:.2f}점, 시드 8)\n")
    say("| 검정 | C | 시드별 | 퍼센타일 (재계산) | 판정 | 시드 t | 판정 | 두 방식 |")
    say("|---|---|---|---|---|---|---|---|")
    rng = np.random.default_rng(0)
    boots = [list(rng.choice(SEEDS, len(SEEDS))) for _ in range(N_BOOT)]
    asym_rows = read(os.path.join(KIT, "out", "asym", "games.csv"))
    RES["ASYM_rebound"] = {t: rebound(asym_rows, list(MAIN_BASE.values()), t, SEEDS, boots, f"ASYM 원래 시드, {t}",
                                      lambda lo, hi: judge_above(lo, hi, DP, "반등 있음", "반등 없음"))
                           for t in ("GunTracker", "Extender")}
    p2 = read(os.path.join(HERE, "p2b_games.csv"))
    RES["P2b"] = rebound(p2, [r for r in p2 if r["cond"] == "BASE"], "GunTracker", SEEDS, boots,
                         "P2-b 정밀 조준 기총, GunTracker",
                         lambda lo, hi: judge_above(lo, hi, DP, "반등 유지", "반등 소멸"))
    rep = read(os.path.join(KIT, "out", "rep", "games.csv"))
    sr = [f"rep-{i}" for i in range(8)]
    rng = np.random.default_rng(0)
    _bm = [list(rng.choice(SEEDS, len(SEEDS))) for _ in range(N_BOOT)]      # p4_replicate.py 와 같은 난수 순서
    br = [list(rng.choice(sr, len(sr))) for _ in range(N_BOOT)]
    base_rep = [r for r in rep if r["cond"] == "BASE" and r["target"] == ""]
    RES["TB"] = {t: rebound(rep, base_rep, t, sr, br, f"P4 T-B 새 시드, {t}",
                            lambda lo, hi: judge_above(lo, hi, DP, "재현", "재현 안 됨")) for t in ("GunTracker", "Extender")}
    say("\nASYM 원래 시드의 반등은 판정 규칙이 따로 없던 서술 값이다(`p4_output.md`의 \"원래 (main)\" 열: GunTracker +46.5 [+35.6, +59.6], "
        "Extender +36.1 [+30.4, +42.5]). 여기서는 같은 문턱(+11.10)으로 비교만 한다.")
    say("등록 보고서 값: P2-b +29.6 [+20.2, +38.6] \"반등 유지\"(`p2b_output.md`), "
        "T-B GunTracker +50.9 [+42.5, +58.6], Extender +35.2 [+25.1, +45.0] \"재현\"(`p4_output.md`).\n")
    return br


# ---------------------------------------------------------------- 마. P4 T-C
def tc(br):
    by = collections.defaultdict(list)
    for r in read(os.path.join(KIT, "out", "rep", "games.csv")):
        if r["target"] == "":
            by[(r["cond"], r["salt"])].append(r)
    sr = [f"rep-{i}" for i in range(8)]
    t2 = P.Table(by, ["F5_D6", "R_delay_sync_24"], "BASE", sr, AG)
    f = lambda v: v["F5_D6"][1] - v["R_delay_sync_24"][1]
    m = f(t2.pick(sr))
    per = [f(t2.pick([s])) for s in sr]
    p = pct([f(t2.pick(b)) for b in br], 95.0)
    t = tint(per, 95.0)
    rule = lambda lo, hi: judge_above(lo, hi, DD, "재현", "재현 안 됨")
    jp, jt = rule(*p), rule(*t)
    say(f"## 마. P4 T-C — D(F5_D6) − D(동기 24) (95 %, 문턱 +δ_D {DD:.3f}, 시드 rep 8)\n")
    say(f"차이 {m:+.3f}. 시드별 {', '.join(f'{x:+.3f}' for x in per)}. 퍼센타일 (재계산) [{p[0]:+.3f}, {p[1]:+.3f}] → {jp}. "
        f"시드 t [{t[0]:+.3f}, {t[1]:+.3f}] → {jt}. 두 방식: **{both(jp, jt)}**. "
        "(등록 보고서: +0.236 [+0.219, +0.253] \"재현\", `p4_output.md`)\n")
    RES["TC"] = dict(mean=m, per_seed=per, pct=p, t=t, judges=(jp, jt))


# ---------------------------------------------------------------- 바. P4 T-A·T-D (곡선을 쓰는 새 시드 검정)
def ta_td():
    bym, byr = collections.defaultdict(list), collections.defaultdict(list)
    for d in ("main", "e3x"):
        for r in read(os.path.join(KIT, "out", d, "games.csv")):
            if r["target"] == "":
                bym[(r["cond"], r["salt"])].append(r)
    for r in read(os.path.join(KIT, "out", "rep", "games.csv")):
        if r["target"] == "":
            byr[(r["cond"], r["salt"])].append(r)
    sr = [f"rep-{i}" for i in range(8)]
    rng = np.random.default_rng(0)                                   # p4_replicate.py 와 같은 난수 순서
    bm = [list(rng.choice(SEEDS, len(SEEDS))) for _ in range(N_BOOT)]
    br = [list(rng.choice(sr, len(sr))) for _ in range(N_BOOT)]
    tm = P.Table(bym, FIT, "BASE", SEEDS, AG)
    line = lambda v: tuple(np.polyfit([v[c][0] for c in FIT], [v[c][1] for c in FIT], 1)[::-1])
    a0, b0 = line(tm.pick(SEEDS))
    curves = [line(tm.pick(b)) for b in bm]
    slug, osc = ["R_kappa_50", "R_kappa_100"], ["F25_D0.5", "F5_D2", "R_sigma_dps_6"]
    tests = {"T-A 동기 24 (재현 = 예측 실패)": (["R_delay_sync_24"], None),
             "T-A κ 100·400 (재현 = 예측 실패)": (["R_kappa_100", "R_kappa_400"], None),
             "T-D 둔한 − 진동형 잔차 (확인 = 하한 > 0)": (slug, osc)}
    conds = sorted({c for a, b in tests.values() for c in a + (b or [])})
    tr = P.Table(byr, conds, "BASE", sr, AG)
    v_all = tr.pick(sr)
    per = {s: tr.pick([s]) for s in sr}
    say("## 바. P4 T-A·T-D (95 %, 등록 곡선은 main 시드, 자료는 rep 시드 8)\n")
    say("| 검정 | 값 | 시드별 | 퍼센타일 (재계산) | t: 곡선 고정 | t: 곡선 불확실성 포함 | 판정: 퍼센타일 / t 포함 | 두 방식 |")
    say("|---|---|---|---|---|---|---|---|")
    out = {}
    for name, (a_cs, b_cs) in tests.items():
        res = lambda v, a, b, cs: float(np.mean([v[c][1] - (a + b * v[c][0]) for c in cs]))
        f = (lambda v, a, b: res(v, a, b, a_cs)) if b_cs is None else (lambda v, a, b: res(v, a, b, a_cs) - res(v, a, b, b_cs))
        m = f(v_all, a0, b0)
        p = pct([f(tr.pick(rb), a, b) for (a, b), rb in zip(curves, br)], 95.0)
        ps = [f(per[s], a0, b0) for s in sr]
        sdc = float(np.std([f(v_all, a, b) for a, b in curves]))
        t1, t2 = tint(ps, 95.0), tint(ps, 95.0, sdc)
        if b_cs is None:
            rule = lambda lo, hi: "재현" if P.judge(lo, hi, DD) == "예측 실패" else "재현 안 됨"
        else:
            rule = lambda lo, hi: "확인" if lo > 0 else ("반대" if hi < 0 else "판정 불가")
        jp, j2 = rule(*p), rule(*t2)
        out[name] = dict(mean=m, per_seed=ps, pct=p, t_fixed=t1, t_curve=t2, judges=(jp, j2))
        say(f"| {name} | {m:+.3f} | {', '.join(f'{x:+.3f}' for x in ps)} | [{p[0]:+.3f}, {p[1]:+.3f}] | "
            f"[{t1[0]:+.3f}, {t1[1]:+.3f}] | [{t2[0]:+.3f}, {t2[1]:+.3f}] | {jp} / {j2} | **{both(jp, j2)}** |")
    say("\n등록 보고서 값(`p4_output.md`): 동기 24 −0.320 [−0.350, −0.292], κ +0.121 [+0.092, +0.149], T-D +0.060 [+0.048, +0.074].\n")
    RES["TA_TD"] = out


def main():
    say("# 부록 C용 시드 단위 t 구간 (사후 민감도, 경기 0판, 등록 판정을 바꾸지 않음)\n")
    say("퍼센타일 구간은 원래 스크립트와 같은 난수로 다시 계산했다(E3X만 등록 보고서 값을 옮겨 적음). \"두 방식\"은 P5 이후의 규칙(두 구간의 판정이 같을 때만 결론)을 "
        "이 검정들에 **사후로** 적용한 결과다.\n")
    asym()
    e3x()
    br = rebounds()
    tc(br)
    ta_td()
    open(os.path.join(HERE, "appc_tinterval_output.md"), "w", encoding="utf-8").write("\n".join(OUT) + "\n")
    json.dump(RES, open(os.path.join(HERE, "appc_tinterval.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1,
              default=float)


if __name__ == "__main__":
    main()
