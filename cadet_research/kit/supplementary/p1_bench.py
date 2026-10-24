"""P1: 교전 없는 벤치 확장 (사전 등록 ../../PREREG_P1.md, 실행 전 고정).

  python p1_bench.py --check   # 재현 확인: 기존 out/margin/bench.json 의 E2 조건 값과 같은가, 두 번 돌려 같은가
  python p1_bench.py           # 벤치 실행 (약 5분) → p1_bench_runs.json, 그다음 분석 → p1_output.md, fig_p1.png
  python p1_bench.py --report  # 실행 없이 분석만

F-16 한 대를 교전 없이 날리며(교전과 같은 구성: 피치·롤 내장 FLCS 우회, 구동기 속도 제한·명령 클립 포함)
조건마다 피치 각속도 명령을 따라가게 한다. 엔진·키트 파일은 고치지 않고 run.apply_knobs 를 그대로 쓴다.
  이중펄스: 1–2 s +A, 2–3 s −A, 3–6 s 0. A = 5 °/s(작은 진폭), 15 °/s(큰 진폭)
  사인: A = 5 °/s, 0.5·1·2·4 Hz, 0.5 s부터 6 s까지, 2–6 s(정수 주기)에서 이득·위상
  비행점 3곳: 15,000 ft 350 kt, 15,000 ft 250 kt, 10,000 ft 450 kt (margin.py 와 같음)
주 벤치 지표 J̄ = 이중펄스 6회(비행점 3 × 진폭 2)의 정규화 RMS 오차 J 평균. 판정은 PREREG_P1.md.
"""
from __future__ import annotations

import collections
import csv
import json
import multiprocessing as mp
import os
import sys
import time

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # kit/supplementary → kit
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
os.chdir(KIT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DT = 1.0 / 120.0
T_END = 6.0
FLIGHT_POINTS = [(15000.0, 350.0), (15000.0, 250.0), (10000.0, 450.0)]
AMPS = (5.0, 15.0)                 # 이중펄스 진폭 [°/s]
FREQS = (0.5, 1.0, 2.0, 4.0)       # 사인 주파수 [Hz]
SINE_AMP = 5.0
DIVERGE_DPS = 60.0                 # margin.py 와 같은 발산 기준
J_CAP = 10.0                       # 발산한 실행의 J (사전 등록)
LC_RMS, LC_RATIO = 0.5, 0.7        # 한계 순환: 5–6 s 잔류 RMS > 0.5 °/s 이고 RMS(5–6)/RMS(4–5) > 0.7
MARGIN = 0.02                      # T2 대등 여유 [D]
RUNS = os.path.join(HERE, "p1_bench_runs.json")
REPORT = os.path.join(HERE, "p1_output.md")
FIG = os.path.join(HERE, "fig_p1.png")
LOG = os.path.join(HERE, "p1.log")


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def conds_all():
    from experiments import E3X_CONDS, EXPERIMENTS
    fit = [c for c in EXPERIMENTS["E2"]["conds"] if c != "BASE"]
    test = [c for c in EXPERIMENTS["E3"]["conds"] if c != "BASE"]
    gen = [c for c in EXPERIMENTS["E4"]["conds"] if c not in ("BASE",)]
    extra = [c for c in ["BASE", "F25_D0"] + gen if c not in fit + test]
    return fit, test, list(E3X_CONDS), gen, extra


def command(kind, p, t):
    if kind == "doublet":
        return p if 1.0 <= t < 2.0 else (-p if 2.0 <= t < 3.0 else 0.0)
    return SINE_AMP * np.sin(2 * np.pi * p * (t - 0.5)) if t >= 0.5 else 0.0


def run_one(job):
    """job = (knobs 이름표, knobs, alt, kcas, kind, p, seed). 반환: 시계열 요약."""
    label, knobs, alt, kcas, kind, p, seed = job
    import run
    from aircombat.engine.pilot import Pilot
    from aircombat.fdm.plant import F16Plant
    plant = F16Plant(dt=DT)
    plant.set_ic(alt_ft=alt, vc_kts=kcas, psi_deg=0.0)
    plant["fcs/throttle-cmd-norm"] = 0.85
    plant.trim()
    pilot = Pilot(plant, color="Bench")
    run._orig_setup(pilot)
    run.TRACE.clear()
    run.apply_knobs(pilot, dict(knobs), seed)
    indi = pilot.indi
    n = int(round(T_END / DT))
    cmd, q = np.zeros(n), np.full(n, np.nan)
    diverged = False
    for k in range(n):
        t = k * DT
        c = np.radians(command(kind, p, t))
        pqr = np.array([plant["velocities/p-rad_sec"], plant["velocities/q-rad_sec"], plant["velocities/r-rad_sec"]])
        u = indi.update(pqr, np.array([0.0, c, 0.0]), plant["aero/qbar-psf"], ang_accel=[
            plant["accelerations/pdot-rad_sec2"], plant["accelerations/qdot-rad_sec2"],
            plant["accelerations/rdot-rad_sec2"]])
        plant.set_input([0.85, u[1], u[0], 0.0])
        plant.step(1)
        qq = plant["velocities/q-rad_sec"]
        cmd[k], q[k] = c, qq
        if not np.isfinite(qq) or abs(qq) > np.radians(DIVERGE_DPS):
            diverged = True
            break
    out = {"label": label, "alt": alt, "kcas": kcas, "kind": kind, "p": p, "diverged": diverged}
    t = np.arange(n) * DT
    if kind == "doublet":
        if diverged:
            out.update(J=J_CAP, mae_dps=None, res45=None, res56=None)
        else:
            e = cmd - q
            out["J"] = float(np.sqrt(np.sum(e ** 2) / np.sum(cmd ** 2)))
            out["mae_dps"] = float(np.degrees(np.mean(np.abs(e))))
            out["res45"] = float(np.degrees(np.sqrt(np.mean(q[(t >= 4) & (t < 5)] ** 2))))
            out["res56"] = float(np.degrees(np.sqrt(np.mean(q[(t >= 5) & (t < 6)] ** 2))))
    else:
        if diverged:
            out.update(gain=None, phase_deg=None)
        else:
            w = (t >= 2.0) & (t < 6.0)
            ph = np.exp(-1j * 2 * np.pi * p * t[w])
            H = np.sum(q[w] * ph) / np.sum(cmd[w] * ph)
            out["gain"], out["phase_deg"] = float(abs(H)), float(np.degrees(np.angle(H)))
    return out


def jobs_for(conds):
    from experiments import CONDITIONS
    js = []
    for c in conds:
        kn = CONDITIONS[c]
        for alt, kcas in FLIGHT_POINTS:
            for a in AMPS:
                js.append((c, kn, alt, kcas, "doublet", a, ("p1bench", c, alt, kcas, "doublet", a)))
            for f in FREQS:
                js.append((c, kn, alt, kcas, "sine", f, ("p1bench", c, alt, kcas, "sine", f)))
            if "sigma_dps" in kn:      # 분류용: 잡음을 뺀 같은 조건 (작은 이중펄스)
                kn0 = {k: v for k, v in kn.items() if k != "sigma_dps"}
                js.append((c + "|잡음없음", kn0, alt, kcas, "doublet", AMPS[0], ("p1bench", c, alt, kcas, "nonoise")))
    return js


def check():
    """기존 margin 벤치 재현 (작은 이중펄스, E2 조건만)과 결정론."""
    from experiments import CONDITIONS
    old = json.load(open(os.path.join(KIT, "out", "margin", "bench.json"), encoding="utf-8"))
    oldm = {(r["fc"], r["alt"], r["kcas"], r["delay"]): r["J"] for r in old}
    fit = conds_all()[0] + ["F25_D0"]
    js = []
    for c in fit:
        kn = CONDITIONS[c]
        for alt, kcas in FLIGHT_POINTS:
            js.append((c, kn, alt, kcas, "doublet", AMPS[0], ("p1bench", c, alt, kcas, "doublet", AMPS[0])))
    with mp.Pool(14) as pool:
        r1 = pool.map(run_one, js, chunksize=2)
        r2 = pool.map(run_one, js[:6], chunksize=1)
    worst = 0.0
    for r in r1:
        kn = CONDITIONS[r["label"]]
        key = (float(kn["filt_hz"]), r["alt"], r["kcas"], float(kn.get("delay_async", 0)))
        worst = max(worst, abs(r["J"] - oldm[key]))
    same = all(a["J"] == b["J"] for a, b in zip(r1[:6], r2))
    log(f"재현 확인: E2 {len(fit)}조건 × 비행점 3, 기존 bench.json 과의 최대 차이 {worst:.2e}, 두 번 실행 동일 {same}")
    return worst, same


def run_bench():
    fit, test, e3x, gen, extra = conds_all()
    conds = extra + fit + test + e3x
    js = jobs_for(conds)
    log(f"벤치 시작: 조건 {len(conds)}개, 실행 {len(js)}회")
    t0 = time.time()
    with mp.Pool(14) as pool:
        res = pool.map(run_one, js, chunksize=4)
    json.dump(res, open(RUNS, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    log(f"벤치 완료: {len(res)}회, {time.time() - t0:.0f}s")


# ---------------------------------------------------------------- 분석
def metrics():
    res = json.load(open(RUNS, encoding="utf-8"))
    by = collections.defaultdict(list)
    for r in res:
        by[r["label"]].append(r)
    M = {}
    for lab, rs in by.items():
        if lab.endswith("|잡음없음"):
            continue
        d = [r for r in rs if r["kind"] == "doublet"]
        small = [r for r in d if r["p"] == AMPS[0]]
        large = [r for r in d if r["p"] == AMPS[1]]
        sine = {f: [r for r in rs if r["kind"] == "sine" and r["p"] == f] for f in FREQS}
        cls_runs = by.get(lab + "|잡음없음", small)
        div = any(r["diverged"] for r in rs)
        lc = sum((not r["diverged"]) and r["res56"] > LC_RMS and r["res56"] / max(r["res45"], 1e-9) > LC_RATIO
                 for r in cls_runs)
        cls = "발산" if any(r["diverged"] for r in cls_runs) else ("한계 순환" if lc >= 2 else "안정")
        gn = {f: [r["gain"] for r in sine[f] if r["gain"] is not None] for f in FREQS}
        ph = collections.defaultdict(list)      # 비행점마다 위상을 주파수 순으로 펼친다(unwrap): 180°를 넘는 지연을 감지 않는다
        for alt, kcas in FLIGHT_POINTS:
            seq = [next(r["phase_deg"] for r in sine[f] if (r["alt"], r["kcas"]) == (alt, kcas)) for f in FREQS]
            if any(x is None for x in seq):
                continue
            for f, x in zip(FREQS, np.degrees(np.unwrap(np.radians(seq)))):
                ph[f].append(x)
        lag = {f: -float(np.mean(ph[f])) if len(ph[f]) == 3 else None for f in FREQS}
        f45 = None
        fs = [f for f in FREQS if lag[f] is not None]
        for a, b in zip(fs, fs[1:]):
            if lag[a] < 45 <= lag[b]:
                f45 = float(np.exp(np.log(a) + (45 - lag[a]) / (lag[b] - lag[a]) * (np.log(b) - np.log(a))))
                break
        if f45 is None and fs and lag[fs[0]] >= 45:
            f45 = f"< {fs[0]}"
        if f45 is None and fs and lag[fs[-1]] < 45:
            f45 = f"> {fs[-1]}"
        M[lab] = dict(J=float(np.mean([r["J"] for r in d])), J_small=float(np.mean([r["J"] for r in small])),
                      J_large=float(np.mean([r["J"] for r in large])),
                      mae_large=float(np.mean([r["mae_dps"] for r in large])) if not any(r["diverged"] for r in large) else None,
                      res56=float(np.mean([r["res56"] for r in cls_runs])) if not any(r["diverged"] for r in cls_runs) else None,
                      lag1=lag[1.0], lag2=lag[2.0], gain2=float(np.mean(gn[2.0])) if len(gn[2.0]) == 3 else None,
                      f45=f45, cls=cls, diverged=div)
    return M


def report():
    import predict as P
    from experiments import AGENTS_E4, EXPERIMENTS
    M = metrics()
    fit, test, e3x, gen, extra = conds_all()
    rd = lambda d: list(csv.DictReader(open(os.path.join(KIT, "out", d, "games.csv"), encoding="utf-8")))
    AG = list(EXPERIMENTS["E2"]["agents"])
    delta = json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))["D"]
    BY = collections.defaultdict(list)
    for r in [r for r in rd("main") if r["target"] == ""] + rd("e3x"):
        BY[(r["cond"], r["salt"])].append(r)
    seeds = P.seeds_of(BY, "main", fit)
    tab = P.Table(BY, fit + test + e3x, "BASE", seeds, AG)
    V = tab.pick(seeds)
    rng = np.random.default_rng(0)
    BS = [list(rng.choice(seeds, len(seeds))) for _ in range(2000)]
    BV = [tab.pick(b) for b in BS]
    shapes = {"linear": lambda x: np.asarray(x, float), "sqrt": np.sqrt, "log": np.log}

    def line(xs, ys):
        b, a = np.polyfit(xs, ys, 1)
        return float(a), float(b)

    def loo(xf, tr):
        e = []
        for c in fit:
            rest = [k for k in fit if k != c]
            a, b = line([tr(xf[k]) for k in rest], [V[k][1] for k in rest])
            e.append(V[c][1] - (a + b * tr(xf[c])))
        return float(np.sqrt(np.mean(np.square(e))))
    J = {c: M[c]["J"] for c in M}
    sc = {nm: loo(J, tr) for nm, tr in shapes.items()}
    shape = min(sc, key=sc.get)
    tr = shapes[shape]

    def preds(vals):
        """세 예측기: 교전 mae 직선, 벤치 J̄ 직선, 상수(교전 직선 절편)."""
        ac, bc = line([vals[c][0] for c in fit], [vals[c][1] for c in fit])
        ab, bb = line([tr(J[c]) for c in fit], [vals[c][1] for c in fit])
        return {"combat": lambda c: ac + bc * vals[c][0], "bench": lambda c: ab + bb * tr(J[c]),
                "const": lambda c: ac}, (ac, bc, ab, bb)

    def rms(f, vals, cs):
        return float(np.sqrt(np.mean([(vals[c][1] - f(c)) ** 2 for c in cs])))
    p0, coef = preds(V)
    boot = [preds(vb)[0] for vb in BV]
    L = ["# P1: 교전 없는 벤치 확장 (사전 등록 `PREREG_P1.md`)\n",
         f"벤치 실행 {len(json.load(open(RUNS, encoding='utf-8')))}회, 조건 {len(M)}개. 교전 자료: E2·E3 `out/main`, E3X `out/e3x`, 시드 {len(seeds)}개, "
         f"부트스트랩 2,000회(시드 재표본, 표본마다 두 직선을 다시 맞춤, 벤치 값은 고정).\n",
         f"## 1. 벤치 곡선 (E2 20조건으로 적합)\n",
         f"모양 선택(LOO RMS): " + ", ".join(f"{k} {v:.4f}" for k, v in sc.items()) + f" → **{shape}**\n",
         f"- 교전 직선: D = {coef[0]:.3f} + {coef[1]:.4f}·mae",
         f"- 벤치 직선: D = {coef[2]:.3f} + {coef[3]:.4f}·{shape}(J̄)\n"]
    res = {"shape": shape, "loo": sc, "coef": coef}

    def block(cs, title):
        r = {k: rms(p0[k], V, cs) for k in p0}
        rb = {k: np.array([rms(b[k], vb, cs) for b, vb in zip(boot, BV)]) for k in p0}
        S = 1 - rb["bench"] / rb["const"]
        Sc = 1 - rb["combat"] / rb["const"]
        dR = rb["bench"] - rb["combat"]
        ci = lambda a: tuple(float(x) for x in np.percentile(a, [2.5, 97.5]))
        L.append(f"### {title}\n")
        L.append("| 예측기 | RMS [95 % CI] |")
        L.append("|---|---|")
        for k, nm in (("combat", "교전 추종 오차 mae (등록 직선)"), ("bench", f"**벤치 J̄** ({shape})"), ("const", "상수 (교전 직선 절편)")):
            lo, hi = ci(rb[k])
            L.append(f"| {nm} | {r[k]:.3f} [{lo:.3f}, {hi:.3f}] |")
        s0 = 1 - r["bench"] / r["const"]
        sc0 = 1 - r["combat"] / r["const"]
        L.append(f"\n- 벤치 기술 점수 S = 1 − RMS(벤치)/RMS(상수) = **{s0:+.2f}** [{ci(S)[0]:+.2f}, {ci(S)[1]:+.2f}] "
                 f"(교전 mae는 {sc0:+.2f} [{ci(Sc)[0]:+.2f}, {ci(Sc)[1]:+.2f}])")
        L.append(f"- ΔRMS = RMS(벤치) − RMS(교전) = **{r['bench'] - r['combat']:+.3f}** [{ci(dR)[0]:+.3f}, {ci(dR)[1]:+.3f}]\n")
        return dict(rms=r, S=(s0, ci(S)), Sc=(sc0, ci(Sc)), dR=(r["bench"] - r["combat"], ci(dR)))
    L.append("## 2. 검증\n")
    e3r = block(test, "E3 22조건 (사전 등록 판정)")
    lo, hi = e3r["S"][1]
    t1 = "상수보다 낫다" if lo > 0 else ("상수보다 못하다" if hi < 0 else "판정 불가")
    lo2, hi2 = e3r["dR"][1]
    t2 = ("교전 지표보다 낫다" if hi2 < 0 else "교전 지표와 대등") if hi2 <= MARGIN else \
        ("교전 지표보다 못하다" if lo2 > MARGIN else "판정 불가")
    overall = "교전 없이 예측 가능" if t1 == "상수보다 낫다" and t2 in ("교전 지표와 대등", "교전 지표보다 낫다") \
        else "교전 없이 예측 불충분"
    L.append(f"**사전 등록 판정** — T1: **{t1}**, T2 (여유 {MARGIN}): **{t2}** → **{overall}**\n")
    res.update(E3=e3r, T1=t1, T2=t2, overall=overall)
    # 원인 묶음 (등록 규칙 ±δ_D)
    groups = collections.defaultdict(list)
    for c in test + e3x:
        groups[P.cause(c)].append(c)
    L.append(f"원인 묶음 판정 (등록 규칙: 평균 오차의 95 % CI를 ±δ_D {delta:.3f}과 비교, 벤치 직선)\n")
    L.append("| 묶음 | 조건 | 벤치 평균 오차 [95 % CI] | 판정 | 교전 mae 평균 오차 | 판정 |")
    L.append("|---|---|---|---|---|---|")
    for g in sorted(groups):
        for setname, cs0 in (("E3", test), ("E3X", e3x)):
            cs = [c for c in groups[g] if c in cs0]
            if not cs:
                continue
            row = [g, f"{setname} {len(cs)}"]
            for k in ("bench", "combat"):
                m = float(np.mean([V[c][1] - p0[k](c) for c in cs]))
                arr = [np.mean([vb[c][1] - b[k](c) for c in cs]) for b, vb in zip(boot, BV)]
                l_, h_ = np.percentile(arr, [2.5, 97.5])
                row += [f"{m:+.3f} [{l_:+.3f}, {h_:+.3f}]", P.judge(l_, h_, delta)]
            L.append("| " + " | ".join(row) + " |")
    L.append("")
    res["E3X"] = block(e3x, "E3X 6조건 (보조, 사후 추가 조건)")
    # E4 보조
    rows4 = rd("gen")
    BY4 = collections.defaultdict(list)
    for r in rows4:
        if r["target"] == "":
            BY4[(r["cond"], r["salt"])].append(r)
    g4 = [c for c in gen if c != "SHAM"]
    s4 = sorted({s for (c, s) in BY4}, key=lambda x: int(x.rsplit("-", 1)[1]))
    t4 = P.Table(BY4, g4 + ["SHAM"], "BASE", s4, list(AGENTS_E4))
    v4 = t4.pick(s4)
    ac, bc, ab, bb = coef
    e4c = [v4[c][1] - (ac + bc * v4[c][0]) for c in g4]
    e4b = [v4[c][1] - (ab + bb * tr(J[c])) for c in g4]
    L.append("### E4 열화 5조건 (보조, 다른 참가자 12종, gen 시드 4개)\n")
    L.append(f"평균 오차: 교전 mae {np.mean(e4c):+.3f}, 벤치 J̄ {np.mean(e4b):+.3f}. "
             f"RMS: 교전 {np.sqrt(np.mean(np.square(e4c))):.3f}, 벤치 {np.sqrt(np.mean(np.square(e4b))):.3f}. "
             f"SHAM: 실제 D {v4['SHAM'][1]:.3f}, 벤치 예측 {ab + bb * tr(J['SHAM']):.3f}\n")
    res["E4"] = dict(mean_combat=float(np.mean(e4c)), mean_bench=float(np.mean(e4b)))
    # 조건표
    L.append("## 3. 조건별 벤치 특성 (기술, 판정 없음)\n")
    L.append(f"분류: 잡음을 뺀 작은 이중펄스 3회 중 2회 이상에서 5–6 s 잔류 RMS > {LC_RMS} °/s 이고 RMS(5–6)/RMS(4–5) > {LC_RATIO}이면 "
             "\"한계 순환\", 한 번이라도 |q| > 60 °/s면 \"발산\". 위상 지연은 비행점마다 0.5 Hz부터 주파수 순으로 펼쳐(unwrap) 평균했다. "
             "한계 순환 조건의 사인 응답에는 자체 진동이 섞여 위상·이득이 흔들린다.\n")
    L.append("| 조건 | 집합 | 분류 | J̄ | J 작은/큰 | 잔류 RMS [°/s] | 위상 지연 1 Hz / 2 Hz [°] | 이득 2 Hz | f₄₅ [Hz] | 교전 mae | D 실제 | D 벤치 예측 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    fmt = lambda x, d=2: "–" if x is None else (x if isinstance(x, str) else f"{x:.{d}f}")
    for setname, cs in (("기준", [c for c in extra if c in M and c not in gen]), ("E2", fit), ("E3", test), ("E3X", e3x)):
        for c in cs:
            m = M[c]
            dd = V.get(c)
            L.append(f"| {c} | {setname} | {m['cls']} | {m['J']:.2f} | {m['J_small']:.2f} / {m['J_large']:.2f} | {fmt(m['res56'])} | "
                     f"{fmt(m['lag1'], 0)} / {fmt(m['lag2'], 0)} | {fmt(m['gain2'])} | {fmt(m['f45'])} | "
                     f"{fmt(dd[0] if dd else None)} | {fmt(dd[1] if dd else None, 3)} | {fmt(p0['bench'](c) if dd else None, 3)} |")
    cnt = collections.Counter((s, M[c]["cls"]) for s, cs in (("E2", fit), ("E3", test), ("E3X", e3x)) for c in cs)
    L.append("\n분류 집계: " + "; ".join(f"{s} {k} {v}" for (s, k), v in sorted(cnt.items())) + "\n")
    allc = fit + test + e3x
    rho = float(np.corrcoef([np.log(J[c]) for c in allc], [np.log(V[c][0]) for c in allc])[0, 1])
    L.append(f"벤치 J̄와 교전 mae의 상관 (48조건, 둘 다 로그): {rho:.2f}\n")
    # 탐색 (판정 없음)
    L.append("## 4. 탐색: 다른 벤치 지표 (사후 표시, 판정 없음)\n")
    L.append("| 지표 | 모양 (LOO) | E3 RMS | E3X RMS |")
    L.append("|---|---|---|---|")
    for key, nm in (("J_small", "J 작은 진폭만"), ("J_large", "J 큰 진폭만"), ("mae_large", "큰 이중펄스 mae [°/s]"),
                    ("lag1", "위상 지연 1 Hz"), ("lag2", "위상 지연 2 Hz"), ("res56", "잔류 RMS")):
        xs = {c: M[c][key] for c in allc}
        if any(x is None or not np.isfinite(x) for x in xs.values()):
            L.append(f"| {nm} | 발산 조건이 있어 계산하지 않음 | – | – |")
            continue
        ok = {nm2: f for nm2, f in shapes.items() if all(xs[c] > 0 for c in allc) or nm2 == "linear"}
        s2 = {nm2: loo(xs, f) for nm2, f in ok.items()}
        best = min(s2, key=s2.get)
        a, b = line([ok[best](xs[c]) for c in fit], [V[c][1] for c in fit])
        rr = lambda cs: float(np.sqrt(np.mean([(V[c][1] - (a + b * ok[best](xs[c]))) ** 2 for c in cs])))
        L.append(f"| {nm} | {best} | {rr(test):.3f} | {rr(e3x):.3f} |")
    L.append("")
    txt = "\n".join(L) + "\n"
    open(REPORT, "w", encoding="utf-8").write(txt)
    json.dump({"metrics": M, "result": res}, open(os.path.join(HERE, "p1_results.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    print(txt)
    figure(M, V, fit, test, e3x, coef, tr, shape)


def figure(M, V, fit, test, e3x, coef, tr, shape):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.4))
    for cs, nm, mk, col in ((fit, "E2 (적합)", "o", "#2a6fdb"), (test, "E3 (검증)", "s", "#e07b00"), (e3x, "E3X (보조)", "^", "#7a7a7a")):
        ax[0].scatter([M[c]["J"] for c in cs], [V[c][1] for c in cs], marker=mk, s=36, c=col, label=nm,
                      edgecolors="white", linewidths=1.2, zorder=3)
        ax[1].scatter([V[c][0] for c in cs], [M[c]["J"] for c in cs], marker=mk, s=36, c=col, label=nm,
                      edgecolors="white", linewidths=1.2, zorder=3)
    xs = np.linspace(min(M[c]["J"] for c in fit + test + e3x), max(M[c]["J"] for c in fit + test + e3x), 200)
    ax[0].plot(xs, coef[2] + coef[3] * tr(xs), color="#2a6fdb", lw=2, label=f"벤치 직선 ({shape})")
    ax[0].set_xscale("log"); ax[0].set_xlabel("벤치 추종 오차 J̄ (교전 없음)"); ax[0].set_ylabel("결과 변화율 D (교전)")
    ax[0].set_title("벤치 지표로 본 결과 변화")
    ax[1].set_xscale("log"); ax[1].set_yscale("log")
    ax[1].set_xlabel("교전 중 피치 추종 오차 mae [°/s]"); ax[1].set_ylabel("벤치 추종 오차 J̄")
    ax[1].set_title("교전 지표와 벤치 지표")
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter
    ticks = [0.5, 0.7, 1, 1.5, 2, 3]
    for axis, tk in ((ax[0].xaxis, ticks), (ax[1].yaxis, ticks), (ax[1].xaxis, [0.2, 0.5, 1, 2, 5, 10])):
        axis.set_major_locator(FixedLocator(tk))
        axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        axis.set_minor_formatter(NullFormatter())
    for a in ax:
        a.grid(alpha=0.25); a.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(FIG, dpi=150)


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    elif "--report" in sys.argv:
        report()
    else:
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        run_bench()
        report()
        log("P1 완료")
