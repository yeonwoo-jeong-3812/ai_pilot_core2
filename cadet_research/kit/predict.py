"""예측 분석기 — 추종 오차로 교전 결과 변화를 예측할 수 있는가.

  python predict.py E1                  # 잡음 바닥과 허용폭 δ 등록 → out/cal/tolerance.json
  python predict.py E2                  # 적합: 결과 변화 = a + b·추종 오차 → out/main/curve.json
  python predict.py E3                  # 검증: E2 곡선의 예측과 실제 비교 (E2 다음에만)
  python predict.py E4                  # 일반화: 다른 참가자 12종에서 E2 곡선의 예측 비교
  python predict.py E2 --prefix smoke   # 실행 점검 결과 분석
  python predict.py FEAS2               # 탐색 기록 재현: DOSE 로 적합, ROUTE 로 검증 (시드 2개, 판정 없음)

조건 하나의 측정값 (기준 조건 ref 와 같은 시드·대진·시나리오의 짝 비교):
  mae  교전 중 피치 추종 오차 [°/s] (양 기체 평균)            — 예측 변수
  D    결과 변화율 = 승자 또는 종료 사유가 기준과 다른 경기의 비율   — 주 결과 변수
  M    참가자별 |Δ점수| 평균 [점/리그 한 바퀴]                  — 보조 결과 변수
독립 단위는 시드다. 신뢰구간은 시드 부트스트랩(2,000회)이며, 적합과 예측을 표본마다 다시 한다.
판정: 원인별 평균 예측 오차의 95 % CI 가 [−δ, +δ] 안이면 "예측 성공", δ 를 완전히 벗어나면 "예측 실패", 그 밖은 "판정 불가".
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
from analyze import points  # noqa: E402
from experiments import EXPERIMENTS  # noqa: E402

FLOOR = {"D": 0.05, "M": 3.0}      # 실용 바닥: 경기 20판 중 1판, 리그 한 바퀴 1승
N_BOOT = 2000
OUT = []
PREFIX = None      # --prefix smoke: 모든 실험을 out/smoke 에서 읽고 쓴다


def say(s=""):
    print(s)
    OUT.append(s)


def load(salt):
    salt = PREFIX or salt
    with open(os.path.join(KIT, "out", salt, "games.csv"), encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["target"] == ""]
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["cond"], r["salt"])].append(r)
    return by


def per_seed(by, cond, ref, seed, agents):
    """한 시드에서 조건 하나: (mae, 다른 경기 수, 경기 수, 참가자별 Δ점수)."""
    gs, rs = by[(cond, seed)], {(g["blue"], g["red"], g["scenario"]): g for g in by[(ref, seed)]}
    gs = [g for g in gs if g["blue"] in agents]
    diff = sum((g["winner"], g["condition"]) != (rs[(g["blue"], g["red"], g["scenario"])]["winner"],
                                                 rs[(g["blue"], g["red"], g["scenario"])]["condition"]) for g in gs)
    mae = np.mean([float(g[k]) for g in gs for k in ("blue_mae_q_dps", "red_mae_q_dps")])
    pc, pr = points(gs, agents)[0], points([r for r in by[(ref, seed)] if r["blue"] in agents], agents)[0]
    return mae, diff, len(gs), np.array([pc[a] - pr[a] for a in agents], float)


class Table:
    """조건 × 시드 측정값. pick(시드 목록) 으로 조건별 (mae, D, M) 을 계산한다."""

    def __init__(self, by, conds, ref, seeds, agents):
        self.conds, self.seeds = list(conds), list(seeds)
        self.v = {(c, s): per_seed(by, c, ref, s, agents) for c in self.conds for s in self.seeds}

    def pick(self, seeds):
        out = {}
        for c in self.conds:
            vs = [self.v[(c, s)] for s in seeds]
            mae = float(np.mean([v[0] for v in vs]))
            D = sum(v[1] for v in vs) / sum(v[2] for v in vs)
            M = float(np.abs(np.mean([v[3] for v in vs], axis=0)).mean())
            out[c] = (mae, D, M)
        return out


# 곡선 모양 후보. E2 에서 한 조건씩 빼고 맞춘 오차(LOO)가 가장 작은 모양을 고르고 curve.json 에 등록한다.
SHAPES = {"linear": lambda m: np.asarray(m, float), "sqrt": lambda m: np.sqrt(m), "log": lambda m: np.log(m)}
SHAPE = "linear"


def T(m):
    return SHAPES[SHAPE](m)


def pred(curve, y, mae):
    a, b = curve[y]
    return a + b * T(mae)


def choose_shape(vals, conds):
    """D 의 LOO 예측 오차 RMS 로 모양을 고른다. 반환 (고른 모양, {모양: RMS})."""
    global SHAPE
    scores = {}
    for name in SHAPES:
        SHAPE = name
        err = []
        for c in conds:
            rest = [k for k in conds if k != c]
            err.append(vals[c][1] - pred(fit(vals, rest), "D", vals[c][0]))
        scores[name] = float(np.sqrt(np.mean(np.square(err))))
    SHAPE = min(scores, key=scores.get)
    return SHAPE, scores


def fit(vals, conds):
    x = T([vals[c][0] for c in conds])
    res = {}
    for i, y in ((1, "D"), (2, "M")):
        b, a = np.polyfit(x, [vals[c][i] for c in conds], 1)
        res[y] = (float(a), float(b))
    return res


def judge(lo, hi, d):
    if -d <= lo and hi <= d:
        return "예측 성공"
    if lo > d or hi < -d:
        return "예측 실패"
    return "판정 불가"


def cause(c):
    if c.startswith("R_"):
        return c[2:].rsplit("_", 1)[0]
    if c.startswith("C_"):
        return "조합"
    return "필터·비동기 지연"


def validate(by_fit, fit_conds, by_test, test_conds, ref, seeds_fit, seeds_test, agents, tol, title):
    """적합 집합으로 곡선을 맞추고 검증 집합을 예측한다. 같은 시드 묶음이면 짝지어 재표본한다."""
    tf = Table(by_fit, fit_conds, ref, seeds_fit, agents)
    tt = Table(by_test, test_conds, ref, seeds_test, agents)
    same = seeds_fit == seeds_test
    vf, vt = tf.pick(seeds_fit), tt.pick(seeds_test)
    curve = fit(vf, fit_conds)
    rng = np.random.default_rng(0)
    boots = collections.defaultdict(list)
    for _ in range(N_BOOT):
        sf = list(rng.choice(seeds_fit, len(seeds_fit)))
        st = sf if same else list(rng.choice(seeds_test, len(seeds_test)))
        cb, vb = fit(tf.pick(sf), fit_conds), tt.pick(st)
        for y, i in (("D", 1), ("M", 2)):
            r = {c: vb[c][i] - pred(cb, y, vb[c][0]) for c in test_conds}
            for c in test_conds:
                boots[(y, c)].append(r[c])
            for g in {cause(c) for c in test_conds}:
                boots[(y, "원인:" + g)].append(np.mean([r[c] for c in test_conds if cause(c) == g]))
            boots[(y, "전체")].append(np.mean(list(r.values())))
    say(f"## {title}\n")
    say(f"곡선 (모양 {SHAPE}, 적합 조건 {len(fit_conds)}개, 시드 {len(seeds_fit)}개): "
        f"D = {curve['D'][0]:.3f} + {curve['D'][1]:.4f}·{SHAPE}(mae), "
        f"M = {curve['M'][0]:.2f} + {curve['M'][1]:.3f}·{SHAPE}(mae)\n")
    say(f"허용폭 δ: D {tol['D']:.3f}, M {tol['M']:.2f}점\n")
    say("| 조건 | 원인 | 추종 오차 [°/s] | D 실제 | D 예측 | D 오차 [95 % CI] | M 실제 | M 예측 | M 오차 [95 % CI] |")
    say("|---|---|---|---|---|---|---|---|---|")
    for c in test_conds:
        mae, D, M = vt[c]
        pd, pm = pred(curve, "D", mae), pred(curve, "M", mae)
        ld, hd = np.percentile(boots[("D", c)], [2.5, 97.5])
        lm, hm = np.percentile(boots[("M", c)], [2.5, 97.5])
        say(f"| {c} | {cause(c)} | {mae:.2f} | {D:.3f} | {pd:.3f} | {D - pd:+.3f} [{ld:+.3f}, {hd:+.3f}] | "
            f"{M:.2f} | {pm:.2f} | {M - pm:+.2f} [{lm:+.2f}, {hm:+.2f}] |")
    say()
    say("원인별 평균 예측 오차와 판정 (주 판정은 D)\n")
    say("| 묶음 | D 평균 오차 [95 % CI] | D 판정 | M 평균 오차 [95 % CI] | M 판정 |")
    say("|---|---|---|---|---|")
    groups = sorted({cause(c) for c in test_conds})
    for g in ["원인:" + x for x in groups] + ["전체"]:
        row = []
        for y in ("D", "M"):
            arr = np.array(boots[(y, g)])
            lo, hi = np.percentile(arr, [2.5, 97.5])
            row.append(f"{arr.mean():+.3f} [{lo:+.3f}, {hi:+.3f}] | {judge(lo, hi, tol[y])}")
        say(f"| {g} | " + " | ".join(row) + " |")
    say()
    return curve, vt


def seeds_of(by, prefix, conds):
    s = {seed for (c, seed) in by if c in conds}
    return sorted(s, key=lambda x: int(x.rsplit("-", 1)[1]))


def tolerance_path():
    return os.path.join(KIT, "out", PREFIX or "cal", "tolerance.json")


def read_tol():
    if not os.path.isfile(tolerance_path()):
        sys.exit("허용폭이 없다. E1 을 실행하고 `python predict.py E1` 을 먼저 돌린다.")
    return json.load(open(tolerance_path(), encoding="utf-8"))


def write(salt, name):
    path = os.path.join(KIT, "out", PREFIX or salt, f"report_predict_{name}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")
    print("보고서:", path)


def sig_mode():
    """유의성 확인 (feas3). 기준은 실행 전에 고정했다:
    1 곡선 기울기의 95 % CI 가 0 을 포함하지 않는다
    2 원인별·고오차 묶음의 평균 예측 오차 95 % CI 가 [−δ, +δ] 안이다
    3 열화 조건의 D 가 SHAM 의 D 보다 크다 (차이의 95 % CI 하한 > 0)
    δ 는 같은 시드의 SHAM 으로 정한다 (탐색 단계라 별도 보정 시드 없이)."""
    global SHAPE
    exp = EXPERIMENTS["SIG"]
    agents, ref = list(exp["agents"]), exp["ref"]
    by = load(exp["salt"])
    fitc = [c for c in exp["conds"] if c.startswith("F")]
    testc = [c for c in exp["conds"] if c.startswith(("R_", "C_"))]
    allc = ["SHAM"] + fitc + testc
    seeds = seeds_of(by, exp["salt"], allc)
    t = Table(by, allc, ref, seeds, agents)
    Ds = [t.v[("SHAM", s)][1] / t.v[("SHAM", s)][2] for s in seeds]
    tol = {"D": max(2 * float(np.percentile(Ds, 95)), FLOOR["D"]), "M": FLOOR["M"]}
    v = t.pick(seeds)
    shape, scores = choose_shape(v, fitc)
    curve = fit(v, fitc)
    say(f"# 유의성 확인 (시드 {len(seeds)}개, 참가자 {len(agents)}명, 판정 기준은 실행 전에 고정)\n")
    say(f"SHAM 시드별 D: {', '.join(f'{x:.3f}' for x in Ds)} → δ_D = {tol['D']:.3f}")
    say("곡선 모양 LOO 오차 RMS: " + ", ".join(f"{k} {x:.4f}" for k, x in scores.items()) + f" → {shape}\n")
    rng = np.random.default_rng(1)
    slope, gap, res = [], collections.defaultdict(list), collections.defaultdict(list)
    hi = [c for c in testc if v[c][0] >= 2.0]
    groups = {("원인:" + g): [c for c in testc if cause(c) == g] for g in sorted({cause(c) for c in testc})}
    groups["추종 오차 ≥ 2 °/s"] = hi
    groups["전체"] = testc
    for _ in range(N_BOOT):
        sb = list(rng.choice(seeds, len(seeds)))
        vb = t.pick(sb)
        cb = fit(vb, fitc)
        slope.append(cb["D"][1])
        for c in fitc + testc:
            gap[c].append(vb[c][1] - vb["SHAM"][1])
        r = {c: vb[c][1] - pred(cb, "D", vb[c][0]) for c in testc}
        for g, cs in groups.items():
            if cs:
                res[g].append(np.mean([r[c] for c in cs]))
    lo, hi_ = np.percentile(slope, [2.5, 97.5])
    ok1 = lo > 0 or hi_ < 0
    say("## 기준 1. 관계의 유의성\n")
    say(f"D = {curve['D'][0]:.3f} + {curve['D'][1]:.4f}·{shape}(mae). 기울기 95 % CI [{lo:.4f}, {hi_:.4f}] → "
        f"{'0 을 포함하지 않음 (충족)' if ok1 else '0 을 포함 (미충족)'}\n")
    say("## 기준 2. 처음 보는 원인의 예측\n")
    say("| 조건 | 원인 | 추종 오차 [°/s] | D 실제 | D 예측 | 오차 |")
    say("|---|---|---|---|---|---|")
    for c in testc:
        p = pred(curve, "D", v[c][0])
        say(f"| {c} | {cause(c)} | {v[c][0]:.2f} | {v[c][1]:.3f} | {p:.3f} | {v[c][1] - p:+.3f} |")
    say()
    say(f"| 묶음 | 조건 수 | 평균 예측 오차 [95 % CI] | 판정 (δ_D = {tol['D']:.3f}) |")
    say("|---|---|---|---|")
    ok2 = True
    for g, cs in groups.items():
        if not cs:
            continue
        a = np.array(res[g])
        l, h = np.percentile(a, [2.5, 97.5])
        j = judge(l, h, tol["D"])
        ok2 &= j == "예측 성공"
        say(f"| {g} | {len(cs)} | {a.mean():+.3f} [{l:+.3f}, {h:+.3f}] | {j} |")
    say()
    say("## 기준 3. 잡음 바닥과의 구분 (D − D_SHAM)\n")
    say("| 조건 | 추종 오차 [°/s] | D − D_SHAM [95 % CI] | 0 보다 큰가 |")
    say("|---|---|---|---|")
    n_ok = 0
    for c in sorted(fitc + testc, key=lambda c: v[c][0]):
        l, h = np.percentile(gap[c], [2.5, 97.5])
        n_ok += l > 0
        say(f"| {c} | {v[c][0]:.2f} | {np.mean(gap[c]):+.3f} [{l:+.3f}, {h:+.3f}] | {'예' if l > 0 else '아니오'} |")
    say(f"\n{len(fitc + testc)}개 조건 중 {n_ok}개가 SHAM보다 크다.\n")
    say("## 종합\n")
    say(f"기준 1 {'충족' if ok1 else '미충족'}, 기준 2 {'전 묶음 예측 성공' if ok2 else '일부 묶음 성공 아님'}, "
        f"기준 3 {n_ok}/{len(fitc + testc)}")
    write(exp["salt"], "SIG")


def main():
    global PREFIX
    if len(sys.argv) > 1 and sys.argv[1] == "SIG":
        return sig_mode()
    name = sys.argv[1] if len(sys.argv) > 1 else "FEAS2"
    PREFIX = sys.argv[sys.argv.index("--prefix") + 1] if "--prefix" in sys.argv else None
    if name == "FEAS2":
        by = load("feas2")
        agents = list(EXPERIMENTS["DOSE"]["agents"])
        fitc = [c for c in EXPERIMENTS["DOSE"]["conds"] if c.startswith("F") and c != "F25_D0"]
        testc = [c for c in EXPERIMENTS["ROUTE"]["conds"] if c != "F25_D0"]
        seeds = seeds_of(by, "feas2", fitc)
        say("# 탐색 기록 재현 (판정 없음. 시드 2개라 CI 는 참고만)\n")
        shape, scores = choose_shape(Table(by, fitc, "F25_D0", seeds, agents).pick(seeds), fitc)
        say("곡선 모양 LOO 오차 RMS (D): " + ", ".join(f"{k} {v:.4f}" for k, v in scores.items()) + f" → {shape}\n")
        validate(by, fitc, by, testc, "F25_D0", seeds, seeds, agents, FLOOR, "DOSE 로 적합, ROUTE 로 검증")
        return write("feas2", name)
    exp = EXPERIMENTS[name]
    agents, ref = list(exp["agents"]), exp["ref"]
    by = load(exp["salt"])
    if name == "E1":
        t = Table(by, ["SHAM"], ref, seeds_of(by, "cal", ["SHAM"]), agents)
        Ds = [t.v[("SHAM", s)][1] / t.v[("SHAM", s)][2] for s in t.seeds]
        Ms = [float(np.abs(t.v[("SHAM", s)][3]).mean()) for s in t.seeds]
        tol = {"D": max(2 * float(np.percentile(Ds, 95)), FLOOR["D"]),
               "M": max(2 * float(np.percentile(Ms, 95)), FLOOR["M"]),
               "sham_D_p95": float(np.percentile(Ds, 95)), "sham_M_p95": float(np.percentile(Ms, 95)),
               "seeds": t.seeds}
        say("# E1 잡음 바닥과 허용폭\n")
        say(f"SHAM 시드별 D: {', '.join(f'{x:.3f}' for x in Ds)}")
        say(f"SHAM 시드별 M: {', '.join(f'{x:.2f}' for x in Ms)}\n")
        say(f"δ_D = max(2 × {tol['sham_D_p95']:.3f}, {FLOOR['D']}) = {tol['D']:.3f}")
        say(f"δ_M = max(2 × {tol['sham_M_p95']:.2f}, {FLOOR['M']}) = {tol['M']:.2f}점\n")
        with open(tolerance_path(), "w", encoding="utf-8") as f:
            json.dump(tol, f, ensure_ascii=False, indent=1)
        say(f"등록: {tolerance_path()}")
        return write("cal", name)
    tol = read_tol()
    e2 = EXPERIMENTS["E2"]
    fitc = [c for c in e2["conds"] if c != e2["ref"]]
    by2 = load(e2["salt"])
    seeds2 = seeds_of(by2, e2["salt"], fitc)
    if name == "E2":
        say("# E2 적합\n")
        t = Table(by2, fitc, e2["ref"], seeds2, agents)
        v = t.pick(seeds2)
        shape, scores = choose_shape(v, fitc)
        say("곡선 모양 LOO 오차 RMS (D): " + ", ".join(f"{k} {x:.4f}" for k, x in scores.items()) + f" → {shape}\n")
        curve = fit(v, fitc)
        resid = {y: [v[c][i] - pred(curve, y, v[c][0]) for c in fitc] for y, i in (("D", 1), ("M", 2))}
        say(f"D = {curve['D'][0]:.3f} + {curve['D'][1]:.4f}·{shape}(mae) (잔차 RMS {np.sqrt(np.mean(np.square(resid['D']))):.3f})")
        say(f"M = {curve['M'][0]:.2f} + {curve['M'][1]:.3f}·{shape}(mae) (잔차 RMS {np.sqrt(np.mean(np.square(resid['M']))):.2f})\n")
        say("| 조건 | 추종 오차 [°/s] | D | M |")
        say("|---|---|---|---|")
        for c in fitc:
            say(f"| {c} | {v[c][0]:.2f} | {v[c][1]:.3f} | {v[c][2]:.2f} |")
        with open(os.path.join(KIT, "out", PREFIX or e2["salt"], "curve.json"), "w", encoding="utf-8") as f:
            json.dump({"curve": curve, "shape": shape, "loo_rms": scores, "conds": fitc, "seeds": seeds2},
                      f, ensure_ascii=False, indent=1)
        return write(e2["salt"], name)
    if not os.path.isfile(os.path.join(KIT, "out", PREFIX or e2["salt"], "curve.json")):
        sys.exit("E2 곡선이 없다. `python predict.py E2` 를 먼저 돌린다.")
    global SHAPE
    with open(os.path.join(KIT, "out", PREFIX or e2["salt"], "curve.json"), encoding="utf-8") as f:
        SHAPE = json.load(f)["shape"]          # E2 에서 등록한 모양만 쓴다
    testc = [c for c in exp["conds"] if c != ref]
    seeds_t = seeds_of(by, exp["salt"], testc)
    say(f"# {name} 검증\n")
    if name == "E4":
        agents_t = agents
        say("참가자가 다르므로 E2 곡선(E2 참가자)으로 E4 참가자의 결과 변화를 예측한다.\n")
        # 곡선은 E2 참가자·시드로, 측정은 E4 참가자·시드로
        tf = Table(by2, fitc, e2["ref"], seeds2, list(e2["agents"]))
        curve = fit(tf.pick(seeds2), fitc)
        tt = Table(by, testc, ref, seeds_t, agents_t)
        vt = tt.pick(seeds_t)
        say("| 조건 | 추종 오차 | D 실제 | D 예측 | 오차 |")
        say("|---|---|---|---|---|")
        for c in testc:
            pd = pred(curve, "D", vt[c][0])
            say(f"| {c} | {vt[c][0]:.2f} | {vt[c][1]:.3f} | {pd:.3f} | {vt[c][1] - pd:+.3f} |")
        return write(exp["salt"], name)
    validate(by2, fitc, by, testc, ref, seeds2, seeds_t, agents, tol, "E2 로 적합, E3 로 검증")
    write(exp["salt"], name)


if __name__ == "__main__":
    main()
