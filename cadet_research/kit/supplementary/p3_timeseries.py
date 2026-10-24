"""P3: 시계열 기록 재생 (사전 등록 ../../PREREG_P3.md, 실행 전 고정).

  python p3_timeseries.py           # 2,744경기 (약 2시간) → p3_games.csv, 그다음 분석 → p3_output.md, fig_p3.png
  python p3_timeseries.py --report  # 경기 없이 분석만
  python p3_timeseries.py --smoke   # 점검: 확증 시드가 아닌 p3smoke-0 에서 3경기, 같은 경기 두 번 (결과 파일에 쓰지 않음)

BASE + E2 20 + E3 22 + E3X 6 = 49조건 × 시드 main-0 × 시나리오 neutral × 56대진. 엔진·키트 파일은 고치지 않는다.
run.play 를 그대로 쓰고 INDI 호출 바깥에서 제어 틱(120 Hz)마다 피치 명령·응답, 승강타 위치, n_z, 받음각을 기록한 뒤
경기가 끝나면 작업 프로세스 안에서 요약 지표만 계산해 돌려준다(시계열 자체는 저장하지 않는다).
먼저 다시 돈 경기가 기록(out/main, out/e3x)과 같은지 확인한다(승자·종료 사유·HP·mae).
"""
from __future__ import annotations

import collections
import csv
import ctypes
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
import run  # noqa: E402
from experiments import AGENTS_MAIN, E3X_CONDS, EXPERIMENTS  # noqa: E402

FS = 120.0
BANDS = (0.0, 0.5, 1.0, 2.0, 4.0, 60.01)          # 오차·명령 대역 경계 [Hz]
SPLIT = 1.0                                       # 주 분석의 느린/빠른 경계 [Hz] (사전 등록)
MAX_LAG = 120                                     # 시간 이동 탐색 0–1 s [틱]
ELEV_RATE = 2.0 / 0.3 / FS                        # 승강타 정규 위치의 틱당 최대 변화 (f16.xml kinematic 0.3 s)
OUT = os.path.join(HERE, "p3_games.csv")
REPORT = os.path.join(HERE, "p3_output.md")
FIG = os.path.join(HERE, "fig_p3.png")
LOG = os.path.join(HERE, "p3.log")
KEY = ("cond", "target", "blue", "red", "scenario", "salt")
SIDE_FIELDS = ["n", "mae", "e_rms", "e_b0", "e_b1", "e_b2", "e_b3", "e_b4", "e_lo", "e_hi",
               "c_rms", "c_sh05", "c_sh1", "c_sh2", "c_fmed", "e_fmed", "lag_s", "res_mae",
               "elev_sat", "nz_max", "nz_over9", "alpha_over25"]
FIELDS = run.FIELDS + [f"{s}_{k}" for s in ("blue", "red") for k in SIDE_FIELDS]

REC: dict = collections.defaultdict(list)
_orig_apply = run.apply_knobs


def apply_logged(pilot, knobs, seed):
    """run.apply_knobs(열화 주입·피치 기록)를 그대로 건 뒤, 그 바깥에서 틱마다 기록한다."""
    _orig_apply(pilot, knobs, seed)
    inner = pilot.indi.update
    rec = REC[pilot.color]
    plant = pilot.plant

    def update(omega, omega_sp, qbar, ang_accel=None, **kw):
        rec.append((float(np.degrees(omega_sp[1])), float(np.degrees(np.asarray(omega, float)[1])),
                    float(plant["fcs/elevator-pos-norm"]), float(plant["accelerations/Nz"]),
                    float(np.degrees(plant["aero/alpha-rad"]))))
        return inner(omega, omega_sp, qbar, ang_accel=ang_accel, **kw)
    pilot.indi.update = update


run.apply_knobs = apply_logged        # run._patched_setup 이 호출 시점에 이 이름을 찾는다


def spectrum(x):
    """한쪽 파워 스펙트럼 (Σ = mean(x²)). 반환 (주파수, 파워)."""
    n = len(x)
    X = np.fft.rfft(x)
    p = np.abs(X) ** 2 / n ** 2
    p[1:] *= 2
    if n % 2 == 0:
        p[-1] /= 2
    return np.fft.rfftfreq(n, 1.0 / FS), p


def band_rms(f, p):
    return [float(np.sqrt(p[(f >= a) & (f < b)].sum())) for a, b in zip(BANDS, BANDS[1:])]


def fmed(f, p):
    c = np.cumsum(p)
    return float(f[np.searchsorted(c, c[-1] / 2)]) if c[-1] > 0 else float("nan")


def side_stats(rows):
    a = np.asarray(rows, float)
    qc, q, el, nz, al = a.T
    e = qc - q
    out = {"n": len(e), "mae": float(np.mean(np.abs(e))), "e_rms": float(np.sqrt(np.mean(e ** 2)))}
    f, pe = spectrum(e)
    b = band_rms(f, pe)
    out.update({f"e_b{i}": v for i, v in enumerate(b)})
    out["e_lo"] = float(np.sqrt(pe[f < SPLIT].sum()))
    out["e_hi"] = float(np.sqrt(pe[f >= SPLIT].sum()))
    _, pc = spectrum(qc)
    _, pc0 = spectrum(qc - qc.mean())
    _, pe0 = spectrum(e - e.mean())
    tot = pc0.sum()
    out["c_rms"] = float(np.sqrt(pc.sum()))
    for k, lim in (("c_sh05", 0.5), ("c_sh1", 1.0), ("c_sh2", 2.0)):
        out[k] = float(pc0[f >= lim].sum() / tot) if tot > 0 else float("nan")
    out["c_fmed"], out["e_fmed"] = fmed(f, pc0), fmed(f, pe0)
    best, lag = np.inf, 0
    for k in range(0, min(MAX_LAG, len(e) - 1) + 1):
        m = float(np.mean(np.abs(qc[: len(qc) - k] - q[k:])))
        if m < best:
            best, lag = m, k
    out["lag_s"], out["res_mae"] = lag / FS, best
    out["elev_sat"] = float(np.mean(np.abs(np.diff(el)) >= 0.95 * ELEV_RATE)) if len(el) > 1 else 0.0
    out["nz_max"] = float(nz.max())
    out["nz_over9"] = float(np.mean(nz > 9.0))
    out["alpha_over25"] = float(np.mean(al > 25.0))
    return out


def play(job):
    REC.clear()
    r = run.play(job)
    for color, s in (("Blue", "blue"), ("Red", "red")):
        st = side_stats(REC[color])
        for k in SIDE_FIELDS:
            v = st[k]
            r[f"{s}_{k}"] = v if isinstance(v, int) else round(v, 6)
    return r


def jobs():
    conds = ["BASE"] + [c for c in EXPERIMENTS["E2"]["conds"] if c != "BASE"] + \
            [c for c in EXPERIMENTS["E3"]["conds"] if c != "BASE"] + list(E3X_CONDS)
    exp = dict(agents=AGENTS_MAIN, scenarios=("neutral",), salt="main", conds=conds)
    return run.build_jobs(exp, 1)


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def smoke():
    js = [dict(j, salt="p3smoke-0") for j in jobs() if j["cond"] in ("BASE", "F25_D6", "R_kappa_50")
          and j["blue"] == "GunTracker" and j["red"] == "Extender"]
    with mp.Pool(4) as pool:
        r1 = pool.map(play, js + js[:1])
    for r in r1[:3]:
        print(r["cond"], r["winner"], r["condition"], "mae", r["blue_mae_q_dps"], "=", round(r["blue_mae"], 4),
              "e_lo/e_hi", round(r["blue_e_lo"], 3), round(r["blue_e_hi"], 3), "lag", r["blue_lag_s"],
              "c_sh1", round(r["blue_c_sh1"], 3), "elev_sat", round(r["blue_elev_sat"], 4))
    same = all(r1[0][k] == r1[3][k] for k in FIELDS if k != "wall_s")
    log(f"점검(p3smoke-0, 3경기): mae 일치 {all(abs(r['blue_mae'] - r['blue_mae_q_dps']) < 1e-4 for r in r1)}, 반복 동일 {same}")


def run_games():
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    js = jobs()
    rows = read(OUT)
    keep = [r for r in rows if r["condition"] != "wall_clock"]
    if len(keep) != len(rows):
        log(f"wall_clock {len(rows) - len(keep)}판을 지우고 다시 돈다")
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(keep)
    done = {tuple(r[k] for k in KEY) for r in keep}
    todo = [j for j in js if tuple(j[k] for k in KEY) not in done]
    log(f"전체 {len(js)}판, 기록됨 {len(js) - len(todo)}, 남음 {len(todo)}")
    if not todo:
        return
    new = not os.path.isfile(OUT)
    t0 = time.time()
    with mp.Pool(14) as pool, open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for i, row in enumerate(pool.imap_unordered(play, todo, chunksize=1), 1):
            w.writerow(row); f.flush()
            if i % 100 == 0 or i == len(todo):
                el = time.time() - t0
                log(f"  {i}/{len(todo)}  {el:.0f}s 경과, 남은 예상 {el / i * (len(todo) - i):.0f}s")
    if any(r["condition"] == "wall_clock" for r in read(OUT)):
        return run_games()


# ---------------------------------------------------------------- 분석
def report():
    import predict as P
    rows = read(OUT)
    fit = [c for c in EXPERIMENTS["E2"]["conds"] if c != "BASE"]
    test = [c for c in EXPERIMENTS["E3"]["conds"] if c != "BASE"]
    e3x = list(E3X_CONDS)
    allc = fit + test + e3x
    rec = {}
    for d in ("main", "e3x"):
        for r in read(os.path.join(KIT, "out", d, "games.csv")):
            if r["target"] == "":
                rec[tuple(r[k] for k in KEY)] = r
    ok = 0
    bad = []
    for r in rows:
        g = rec[tuple(r[k] for k in KEY)]
        same = (g["winner"], g["condition"]) == (r["winner"], r["condition"]) and \
            all(abs(float(g[k]) - float(r[k])) < 1e-4 for k in ("hp_blue", "hp_red", "blue_mae_q_dps", "red_mae_q_dps"))
        ok += same
        if not same:
            bad.append(tuple(r[k] for k in KEY))
    L = ["# P3: 시계열 기록 재생 (사전 등록 `PREREG_P3.md`)\n",
         f"경기 {len(rows)} (사전 등록 2,744), `wall_clock` {sum(r['condition'] == 'wall_clock' for r in rows)}. "
         f"**재생 일치 {ok}/{len(rows)}** (승자·종료 사유·HP·mae).\n"]
    if bad:
        L.append(f"불일치 {len(bad)}경기: 사전 등록에 따라 원인을 찾기 전에는 아래 분석을 쓰지 않는다. 예: {bad[:5]}\n")
    by = collections.defaultdict(list)
    for r in rows:
        by[r["cond"]].append(r)

    def cm(c, k):
        return float(np.nanmean([float(r[f"{s}_{k}"]) for r in by[c] for s in ("blue", "red")]))
    X = {c: {k: cm(c, k) for k in SIDE_FIELDS if k != "n"} for c in ["BASE"] + allc}
    for c in X:
        X[c]["hi_share"] = float(np.mean([float(r[f"{s}_e_hi"]) ** 2 / max(float(r[f"{s}_e_rms"]) ** 2, 1e-12)
                                          for r in by[c] for s in ("blue", "red")]))
        X[c]["res_ratio"] = X[c]["res_mae"] / max(X[c]["mae"], 1e-9)
    BY = collections.defaultdict(list)
    for d in ("main", "e3x"):
        for r in read(os.path.join(KIT, "out", d, "games.csv")):
            if r["target"] == "":
                BY[(r["cond"], r["salt"])].append(r)
    seeds = P.seeds_of(BY, "main", fit)
    V = P.Table(BY, allc, "BASE", seeds, list(EXPERIMENTS["E2"]["agents"])).pick(seeds)

    def fitpred(cols, cs_fit, cs_test):
        A = np.column_stack([np.ones(len(cs_fit))] + [[X[c][k] for c in cs_fit] for k in cols])
        coef, *_ = np.linalg.lstsq(A, [V[c][1] for c in cs_fit], rcond=None)
        B = np.column_stack([np.ones(len(cs_test))] + [[X[c][k] for c in cs_test] for k in cols])
        return coef, B @ coef

    def loo(cols):
        e = []
        for c in fit:
            rest = [k for k in fit if k != c]
            _, p = fitpred(cols, rest, [c])
            e.append(V[c][1] - p[0])
        return float(np.sqrt(np.mean(np.square(e))))
    models = {"P_sub": ["mae"], "B": ["e_lo", "e_hi"], "R_sub": ["e_rms"]}
    names = {"P_sub": "P_sub  mae (재생에서 잰 값)", "B": "**B  느린(< 1 Hz) + 빠른(≥ 1 Hz) 오차**", "R_sub": "R_sub  전체 오차 RMS"}
    L.append("## 1. 주 분석: 대역으로 나눈 오차가 예측을 낫게 하는가 (E2 적합, E3 예측)\n")
    L.append("D는 본실험 원자료(시드 8 × 시나리오 3, E3X 포함)에서, 예측 변수는 재생(main-0, neutral 56대진 × 2기체)에서 온다. "
             "판단 기준은 롤 탐색과 같다: B의 E3 RMS가 P_sub보다 20 % 이상 줄면 \"의미 있게 나아짐\", 5 % 미만이면 \"나아지지 않음\", 그 사이 \"약간\".\n")
    L.append("| 모형 | 계수 | E2 LOO RMS | E3 RMS | E3X RMS | κ | k_q | σ | 동기 | 조합 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    res = {}
    for m, cols in models.items():
        coef, pT = fitpred(cols, fit, test)
        _, pX = fitpred(cols, fit, e3x)
        eT = np.array([V[c][1] for c in test]) - pT
        eX = np.array([V[c][1] for c in e3x]) - pX
        grp = {g: float(np.mean([eT[i] for i, c in enumerate(test) if P.cause(c) == g]))
               for g in ("kappa", "kq", "sigma_dps", "delay_sync", "조합")}
        res[m] = dict(coef=[float(x) for x in coef], loo=loo(cols), e3=float(np.sqrt(np.mean(eT ** 2))),
                      e3x=float(np.sqrt(np.mean(eX ** 2))), grp=grp)
        L.append(f"| {names[m]} | {', '.join(f'{x:+.4f}' for x in coef)} | {res[m]['loo']:.3f} | {res[m]['e3']:.3f} | "
                 f"{res[m]['e3x']:.3f} | " + " | ".join(f"{grp[g]:+.3f}" for g in grp) + " |")
    red = 1 - res["B"]["e3"] / res["P_sub"]["e3"]
    verdict = "의미 있게 나아짐" if red >= 0.20 else ("나아지지 않음" if red < 0.05 else "약간")
    chg = f"{red * 100:.1f} % 감소" if red >= 0 else f"{-red * 100:.1f} % 증가(나빠짐)"
    L.append(f"\n**사전 등록 판단: B는 P_sub 대비 E3 RMS {chg} → {verdict}** "
             f"(참고: 등록 직선은 본실험 전체 mae로 E3 RMS 0.041. R_sub 대비 B {100 * (1 - res['B']['e3'] / res['R_sub']['e3']):+.1f} %)\n")
    res["verdict"], res["reduction"] = verdict, red
    rho_lh = float(np.corrcoef([X[c]["e_lo"] for c in fit], [X[c]["e_hi"] for c in fit])[0, 1])
    L.append(f"E2 안에서 느린 오차와 빠른 오차의 상관: {rho_lh:.3f} (1에 가까우면 두 몫을 나눌 수 없다)\n")
    # S1 명령 스펙트럼
    t = np.arange(int(6 * FS)) / FS
    dbl = np.where((t >= 1) & (t < 2), 5.0, np.where((t >= 2) & (t < 3), -5.0, 0.0))
    fd, pd = spectrum(dbl - dbl.mean())
    sh_dbl = {lim: float(pd[fd >= lim].sum() / pd.sum()) for lim in (0.5, 1.0, 2.0)}
    b = X["BASE"]
    ratio = b["c_sh1"] / sh_dbl[1.0]
    s1 = "지지" if ratio < 0.5 else ("기각" if ratio >= 1.0 else "부분 지지")
    L.append("## 2. 교전 명령은 시험 입력보다 느린가 (P1 해석의 확인)\n")
    L.append("| 명령 | 0.5 Hz 이상 몫 | 1 Hz 이상 몫 | 2 Hz 이상 몫 | 중앙 주파수 [Hz] | RMS [°/s] |")
    L.append("|---|---|---|---|---|---|")
    L.append(f"| 교전 BASE (양 기체, 112 기록) | {b['c_sh05']:.3f} | {b['c_sh1']:.3f} | {b['c_sh2']:.3f} | {b['c_fmed']:.2f} | {b['c_rms']:.1f} |")
    L.append(f"| 벤치 작은 이중펄스 (P1) | {sh_dbl[0.5]:.3f} | {sh_dbl[1.0]:.3f} | {sh_dbl[2.0]:.3f} | {fmed(fd, pd):.2f} | – |")
    L.append(f"\n**사전 등록 판단: 교전 명령의 1 Hz 이상 몫이 이중펄스의 {ratio:.2f}배 → {s1}** "
             "(0.5배 미만 \"지지\", 1배 이상 \"기각\", 그 사이 \"부분 지지\")\n")
    res["S1"] = dict(base=b["c_sh1"], doublet=sh_dbl[1.0], ratio=ratio, verdict=s1)
    # 조건표
    L.append("## 3. 조건별 시계열 지표 (기술)\n")
    L.append("| 조건 | 집합 | mae | 느린 / 빠른 오차 RMS | 빠른 몫 | 오차 중앙 주파수 [Hz] | 시간 이동 [s] | 이동 후 잔차 / mae | 명령 1 Hz 이상 몫 | 승강타 속도 포화 | n_z > 9 | D |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for setname, cs in (("기준", ["BASE"]), ("E2", fit), ("E3", test), ("E3X", e3x)):
        for c in cs:
            x = X[c]
            d = f"{V[c][1]:.3f}" if c in V else "–"
            L.append(f"| {c} | {setname} | {x['mae']:.2f} | {x['e_lo']:.2f} / {x['e_hi']:.2f} | {x['hi_share']:.2f} | {x['e_fmed']:.2f} | "
                     f"{x['lag_s']:.3f} | {x['res_ratio']:.2f} | {x['c_sh1']:.3f} | {x['elev_sat']:.4f} | {x['nz_over9']:.4f} | {d} |")
    # S3 잔차와 빠른 몫
    a, bb = np.polyfit([V[c][0] for c in fit], [V[c][1] for c in fit], 1)
    resid = {c: V[c][1] - (bb + a * V[c][0]) for c in allc}
    rho = float(np.corrcoef([resid[c] for c in allc], [X[c]["hi_share"] for c in allc])[0, 1])
    rho_lag = float(np.corrcoef([resid[c] for c in allc], [X[c]["lag_s"] for c in allc])[0, 1])
    L.append(f"\n**같은 mae, 다른 D**: 등록 직선(본실험 전체)의 잔차와 빠른 오차 몫의 상관 {rho:+.2f}, 시간 이동과의 상관 {rho_lag:+.2f} (48조건, 기술)\n")
    res["S3"] = dict(rho_hi=rho, rho_lag=rho_lag)
    # 탐색
    L.append("## 4. 탐색 (사후 표시, 판정 없음)\n")
    L.append("| 모형 | E2 LOO | E3 RMS | E3X RMS |")
    L.append("|---|---|---|---|")
    for c in X:
        x = X[c]
        x["lo05"] = x["e_b0"]
        x["hi05"] = float(np.sqrt(x["e_b1"] ** 2 + x["e_b2"] ** 2 + x["e_b3"] ** 2 + x["e_b4"] ** 2))
        x["lo2"] = float(np.sqrt(x["e_b0"] ** 2 + x["e_b1"] ** 2 + x["e_b2"] ** 2))
        x["hi2"] = float(np.sqrt(x["e_b3"] ** 2 + x["e_b4"] ** 2))
    for nm, cols in (("경계 0.5 Hz", ["lo05", "hi05"]), ("경계 2 Hz", ["lo2", "hi2"]), ("mae + 시간 이동", ["mae", "lag_s"]),
                     ("이동 후 잔차 + 시간 이동", ["res_mae", "lag_s"]), ("mae + 승강타 포화", ["mae", "elev_sat"])):
        _, pT = fitpred(cols, fit, test)
        _, pX = fitpred(cols, fit, e3x)
        L.append(f"| {nm} | {loo(cols):.3f} | {np.sqrt(np.mean((np.array([V[c][1] for c in test]) - pT) ** 2)):.3f} | "
                 f"{np.sqrt(np.mean((np.array([V[c][1] for c in e3x]) - pX) ** 2)):.3f} |")
    txt = "\n".join(L) + "\n"
    open(REPORT, "w", encoding="utf-8").write(txt)
    json.dump({"metrics": X, "result": res, "replay_ok": ok, "n": len(rows)},
              open(os.path.join(HERE, "p3_results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(txt)
    figure(X, V, fit, test, e3x, resid)


def figure(X, V, fit, test, e3x, resid):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.4))
    for cs, nm, mk, col in ((fit, "E2 (적합)", "o", "#2a6fdb"), (test, "E3 (검증)", "s", "#e07b00"), (e3x, "E3X (보조)", "^", "#7a7a7a")):
        ax[0].scatter([X[c]["e_lo"] for c in cs], [X[c]["e_hi"] for c in cs], marker=mk, s=36, c=col, label=nm,
                      edgecolors="white", linewidths=1.2, zorder=3)
        ax[1].scatter([X[c]["hi_share"] for c in cs], [resid[c] for c in cs], marker=mk, s=36, c=col, label=nm,
                      edgecolors="white", linewidths=1.2, zorder=3)
    ax[0].set_xlabel("느린 오차 RMS (< 1 Hz) [°/s]"); ax[0].set_ylabel("빠른 오차 RMS (≥ 1 Hz) [°/s]")
    ax[0].set_title("교전 중 피치 오차의 대역 구성")
    ax[1].axhline(0, color="#999999", lw=1)
    ax[1].set_xlabel("빠른 오차의 몫 (≥ 1 Hz 파워 / 전체)"); ax[1].set_ylabel("등록 직선의 잔차 (D 실제 − 예측)")
    ax[1].set_title("같은 mae, 다른 D")
    for a in ax:
        a.grid(alpha=0.25); a.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(FIG, dpi=150)


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        smoke()
    elif "--report" in sys.argv:
        report()
    else:
        run_games()
        log("경기 완료")
        report()
        log("P3 완료")
