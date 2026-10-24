"""P4: 새 시드(rep-0–7) 독립 재현 (사전 등록 ../../PREREG_P4.md, 실행 전 고정).

  python p4_replicate.py           # 16,128경기 (약 8.5시간) → ../out/rep/games.csv, 그다음 분석 → p4_output.md
  python p4_replicate.py --report  # 경기 없이 분석만
  python p4_replicate.py --smoke   # 점검: 확증 시드가 아닌 p4smoke-0 에서 6경기 (결과 파일에 쓰지 않음)

1단계 (계획분, 10,752경기): 대칭 {BASE, F12_D6, F5_D6, 동기 24, κ 100, κ 400} × 168경기 × 시드 8
                          + 한 기체만 열화 {GunTracker, Extender} × {SHAM, F25_D2, F25_D4, F25_D6} × 42경기 × 시드 8
2단계 (오차 유형 확인, 5,376경기): 대칭 {κ 50, F25_D0.5, F5_D2, σ 6} × 168경기 × 시드 8
끊기면 다시 치면 이어서 돈다. 1단계를 먼저 끝낸 뒤 2단계를 돈다. 엔진·키트 파일은 고치지 않는다.
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
from experiments import AGENTS_MAIN, EXPERIMENTS, LEAGUE  # noqa: E402

SALT, N_SEEDS = "rep", 8
SYM1 = ["BASE", "F12_D6", "F5_D6", "R_delay_sync_24", "R_kappa_100", "R_kappa_400"]
TARGETS = ["GunTracker", "Extender"]
ASYM = ["SHAM", "F25_D2", "F25_D4", "F25_D6"]
SYM2 = ["R_kappa_50", "F25_D0.5", "F5_D2", "R_sigma_dps_6"]
SLUG = ["R_kappa_50", "R_kappa_100"]                 # 둔한 지연형 (P3 기준, 본실험 mae 1.0–2.0)
OSC = ["F25_D0.5", "F5_D2", "R_sigma_dps_6"]         # 진동형 (같은 기준)
OUTDIR = os.path.join(KIT, "out", "rep")
OUT = os.environ.get("P4_GAMES", os.path.join(OUTDIR, "games.csv"))   # 환경 변수는 분석 점검용
REPORT = os.environ.get("P4_REPORT", os.path.join(HERE, "p4_output.md"))
LOG = os.path.join(HERE, "p4.log")
KEY = ("cond", "target", "blue", "red", "scenario", "salt")
N_BOOT = 2000


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


def jobs(salt=SALT, n=N_SEEDS):
    sym1 = run.build_jobs(dict(agents=AGENTS_MAIN, scenarios=LEAGUE, salt=salt, conds=SYM1), n)
    asym = [j for j in run.build_jobs(dict(agents=AGENTS_MAIN, scenarios=LEAGUE, salt=salt, conds=ASYM, target="each"), n)
            if j["target"] in TARGETS]
    sym2 = run.build_jobs(dict(agents=AGENTS_MAIN, scenarios=LEAGUE, salt=salt, conds=SYM2), n)
    return sym1 + asym, sym2


def smoke():
    p1, p2 = jobs("p4smoke", 1)
    pick = lambda js, c, t="": next(j for j in js if j["cond"] == c and j["target"] == t and j["scenario"] == "neutral")
    js = [pick(p1, "BASE"), pick(p1, "R_kappa_400"), pick(p1, "F25_D6", "GunTracker"), pick(p1, "SHAM", "Extender"),
          pick(p2, "R_kappa_50"), pick(p2, "R_sigma_dps_6")]
    with mp.Pool(6) as pool:
        rs = pool.map(run.play, js)
    for r in rs:
        print(r["cond"], r["target"] or "-", r["blue"], r["red"], r["winner"], r["condition"], r["blue_mae_q_dps"], r["red_mae_q_dps"])
    p1, p2 = jobs()
    log(f"점검(p4smoke-0, 6경기) 통과. 본 실행 1단계 {len(p1)}판, 2단계 {len(p2)}판")


def run_phase(js, name):
    rows = read(OUT)
    keep = [r for r in rows if r["condition"] != "wall_clock"]
    if len(keep) != len(rows):
        log(f"wall_clock {len(rows) - len(keep)}판을 지우고 다시 돈다")
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=run.FIELDS); w.writeheader(); w.writerows(keep)
    done = {tuple(r[k] for k in KEY) for r in keep}
    todo = [j for j in js if tuple(j[k] for k in KEY) not in done]
    log(f"{name}: 전체 {len(js)}판, 기록됨 {len(js) - len(todo)}, 남음 {len(todo)}")
    if not todo:
        return
    new = not os.path.isfile(OUT)
    t0 = time.time()
    with mp.Pool(14) as pool, open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=run.FIELDS)
        if new:
            w.writeheader()
        for i, row in enumerate(pool.imap_unordered(run.play, todo, chunksize=1), 1):
            w.writerow(row); f.flush()
            if i % 200 == 0 or i == len(todo):
                el = time.time() - t0
                log(f"  {name} {i}/{len(todo)}  {el:.0f}s 경과, 남은 예상 {el / i * (len(todo) - i):.0f}s")
    if any(r["condition"] == "wall_clock" for r in read(OUT)):
        run_phase(js, name)


def run_all():
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    os.makedirs(OUTDIR, exist_ok=True)
    p1, p2 = jobs()
    run_phase(p1, "1단계")
    log("1단계 완료")
    run_phase(p2, "2단계")
    log("2단계 완료")


# ---------------------------------------------------------------- 분석
def report():
    import predict as P
    from analyze import points
    P.SHAPE = "linear"
    tol = {"D": json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))["D"],
           "M": json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))["M"]}
    dpts_delta = json.load(open(os.path.join(KIT, "out", "cal", "delta.json"), encoding="utf-8"))
    dpts_delta = float(dpts_delta.get("delta", dpts_delta.get("delta_pts", 11.10))) if isinstance(dpts_delta, dict) else 11.10
    AG = list(EXPERIMENTS["E2"]["agents"])
    fitc = [c for c in EXPERIMENTS["E2"]["conds"] if c != "BASE"]
    rows = read(OUT)
    p1, p2 = jobs()
    have = {tuple(r[k] for k in KEY) for r in rows if r["condition"] != "wall_clock"}
    n1 = sum(tuple(j[k] for k in KEY) in have for j in p1)
    n2 = sum(tuple(j[k] for k in KEY) in have for j in p2)
    L = ["# P4: 새 시드 독립 재현 (사전 등록 `PREREG_P4.md`)\n",
         f"경기 {len(rows):,} (1단계 {n1:,}/{len(p1):,}, 2단계 {n2:,}/{len(p2):,}), `wall_clock` {sum(r['condition'] == 'wall_clock' for r in rows)}. "
         f"시드 rep-0–7. 곡선은 본실험 E2(main 시드)의 등록 곡선이고, 부트스트랩은 main 시드와 rep 시드를 따로 재표본한다.\n"]
    res = {}
    BYM = collections.defaultdict(list)
    for d in ("main", "e3x"):
        for r in read(os.path.join(KIT, "out", d, "games.csv")):
            if r["target"] == "":
                BYM[(r["cond"], r["salt"])].append(r)
    BYR = collections.defaultdict(list)
    for r in rows:
        if r["target"] == "":
            BYR[(r["cond"], r["salt"])].append(r)
    sm = P.seeds_of(BYM, "main", fitc)
    sr = sorted({s for (c, s) in BYR}, key=lambda x: int(x.rsplit("-", 1)[1]))
    rng = np.random.default_rng(0)
    BM = [list(rng.choice(sm, len(sm))) for _ in range(N_BOOT)]
    BR = [list(rng.choice(sr, len(sr))) for _ in range(N_BOOT)]
    ci = lambda a, lv=95.0: tuple(float(x) for x in np.percentile(a, [(100 - lv) / 2, 100 - (100 - lv) / 2]))
    tm = P.Table(BYM, fitc, "BASE", sm, AG)
    line = lambda v: tuple(np.polyfit([v[c][0] for c in fitc], [v[c][1] for c in fitc], 1)[::-1])
    curves = [line(tm.pick(b)) for b in BM]
    a0, b0 = line(tm.pick(sm))

    # ---- T-A: E3X 실패의 재현 (등록 판정 규칙)
    ta = ["R_delay_sync_24", "R_kappa_100", "R_kappa_400"]
    if all((c, s) in BYR for c in ta + ["BASE"] for s in sr):
        P.OUT.clear()
        P.validate(BYM, fitc, BYR, ta, "BASE", sm, sr, AG, tol, "T-A. E2 곡선(main)으로 rep 시드의 동기 24·κ 100·κ 400 예측")
        L.extend(P.OUT); P.OUT.clear()
        tr = P.Table(BYR, ta, "BASE", sr, AG)
        vr = tr.pick(sr)
        L.append("| 묶음 | 원래 (E3X, main) | rep 평균 오차 [95 % CI] | rep 판정 | 재현 |")
        L.append("|---|---|---|---|---|")
        orig = {"delay_sync": "−0.343 예측 실패", "kappa": "+0.114 예측 실패(퍼센타일)"}
        res["TA"] = {}
        for g, cs in (("delay_sync", ["R_delay_sync_24"]), ("kappa", ["R_kappa_100", "R_kappa_400"])):
            arr = []
            for (a, b), bb in zip(curves, BR):
                v = tr.pick(bb)
                arr.append(np.mean([v[c][1] - (a + b * v[c][0]) for c in cs]))
            m = float(np.mean([vr[c][1] - (a0 + b0 * vr[c][0]) for c in cs]))
            lo, hi = ci(arr)
            j = P.judge(lo, hi, tol["D"])
            rep = "재현" if j == "예측 실패" else "재현 안 됨"
            res["TA"][g] = dict(mean=m, ci=(lo, hi), judge=j, replicated=rep)
            L.append(f"| {g} | {orig[g]} | {m:+.3f} [{lo:+.3f}, {hi:+.3f}] | {j} | **{rep}** |")
        L.append("")
    # ---- T-C: 동기 24 대 F5_D6 (같은 mae)
    tc = ["F5_D6", "R_delay_sync_24"]
    if all((c, s) in BYR for c in tc + ["BASE"] for s in sr):
        t2 = P.Table(BYR, tc, "BASE", sr, AG)
        v = t2.pick(sr)
        d0 = v["F5_D6"][1] - v["R_delay_sync_24"][1]
        arr = [(lambda x: x["F5_D6"][1] - x["R_delay_sync_24"][1])(t2.pick(bb)) for bb in BR]
        lo, hi = ci(arr)
        j = "재현" if lo > tol["D"] else ("재현 안 됨" if hi < tol["D"] else "판정 불가")
        L.append("## T-C. 같은 mae에서 동기 지연 24틱은 F5_D6보다 결과를 덜 바꾼다\n")
        L.append(f"rep: F5_D6 mae {v['F5_D6'][0]:.2f}, D {v['F5_D6'][1]:.3f} / 동기 24 mae {v['R_delay_sync_24'][0]:.2f}, D {v['R_delay_sync_24'][1]:.3f}. "
                 f"차이 {d0:+.3f} [{lo:+.3f}, {hi:+.3f}] (원래 main: 0.629 − 0.347 = +0.282) → **{j}** (CI 전체가 +δ_D {tol['D']:.3f} 위면 재현)\n")
        res["TC"] = dict(diff=d0, ci=(lo, hi), verdict=j)
    # ---- T-B: ASYM U자 대비
    BASEK = {(r["blue"], r["red"], r["scenario"], r["salt"]): r for r in rows if r["cond"] == "BASE" and r["target"] == ""}
    kb = lambda r: (r["blue"], r["red"], r["scenario"], r["salt"])
    lv = 100 * (1 - 0.05 / 3)
    L.append(f"## T-B. 한 기체만 열화한 U자 (시드 부트스트랩 {lv:.2f} % CI, δ_점수 {dpts_delta:.2f})\n")
    L.append("| 대상 | Δ점수 SHAM | 2틱 | 4틱 | 6틱 | **반등 6틱 − 2틱 [CI]** | 반등 > 0 시드 | 원래 (main) | 재현 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    res["TB"] = {}
    orig_u = {"GunTracker": "+46.5 [+35.6, +59.6]", "Extender": "+36.1 [+30.4, +42.5]"}
    for t in TARGETS:
        cell = {}
        okk = True
        for c in ASYM:
            for s in sr:
                gs = [r for r in rows if r["cond"] == c and r["target"] == t and r["salt"] == s]
                if not gs or any(kb(g) not in BASEK for g in gs):
                    okk = False
                    continue
                cell[(c, s)] = points(gs, AG)[0][t] - points([BASEK[kb(g)] for g in gs], AG)[0][t]
        if not okk:
            L.append(f"| {t} | 자료 부족 | | | | | | | |")
            continue
        mean = {c: float(np.mean([cell[(c, s)] for s in sr])) for c in ASYM}
        con = {s: cell[("F25_D6", s)] - cell[("F25_D2", s)] for s in sr}
        arr = [np.mean([con[s] for s in bb]) for bb in BR]
        lo, hi = ci(arr, lv)
        m = float(np.mean(list(con.values())))
        j = "재현" if lo > dpts_delta else ("재현 안 됨" if hi < dpts_delta else "판정 불가")
        sham = [np.mean([cell[("SHAM", s)] for s in bb]) for bb in BR]
        slo, shi = ci(sham, lv)
        res["TB"][t] = dict(contrast=m, ci=(lo, hi), verdict=j, means=mean, sham_ci=(slo, shi))
        L.append(f"| {t} | {mean['SHAM']:+.1f} [{slo:+.1f}, {shi:+.1f}] | {mean['F25_D2']:+.1f} | {mean['F25_D4']:+.1f} | {mean['F25_D6']:+.1f} | "
                 f"**{m:+.1f} [{lo:+.1f}, {hi:+.1f}]** | {sum(v > 0 for v in con.values())}/{len(sr)} | {orig_u[t]} | **{j}** |")
    L.append("")
    # ---- T-D: 둔한 지연형 대 진동형
    td = SLUG + OSC
    if all((c, s) in BYR for c in td + ["BASE"] for s in sr):
        t4 = P.Table(BYR, td, "BASE", sr, AG)
        v = t4.pick(sr)
        rs = lambda vv, a, b, cs: float(np.mean([vv[c][1] - (a + b * vv[c][0]) for c in cs]))
        d0 = rs(v, a0, b0, SLUG) - rs(v, a0, b0, OSC)
        arr = []
        for (a, b), bb in zip(curves, BR):
            vv = t4.pick(bb)
            arr.append(rs(vv, a, b, SLUG) - rs(vv, a, b, OSC))
        lo, hi = ci(arr)
        j = "확인" if lo > 0 else ("반대" if hi < 0 else "판정 불가")
        L.append("## T-D. 같은 오차 크기에서 둔한 지연형이 진동형보다 결과를 더 바꾼다 (새 가설, P3에서 나옴)\n")
        L.append("| 조건 | 유형 | rep mae | rep D | 등록 직선 잔차 |")
        L.append("|---|---|---|---|---|")
        for c in td:
            L.append(f"| {c} | {'둔한 지연형' if c in SLUG else '진동형'} | {v[c][0]:.2f} | {v[c][1]:.3f} | {v[c][1] - (a0 + b0 * v[c][0]):+.3f} |")
        L.append(f"\n잔차 평균 차이(둔한 − 진동) = **{d0:+.3f} [{lo:+.3f}, {hi:+.3f}]** (95 %; main 시드 사후 값 +0.069) → **{j}**\n")
        res["TD"] = dict(diff=d0, ci=(lo, hi), verdict=j)
    # ---- 기술: 조건별 main 대 rep
    conds = [c for c in SYM1 + SYM2 if c != "BASE" and all((c, s) in BYR for s in sr)]
    if conds:
        BYM2 = collections.defaultdict(list)
        for d in ("main", "e3x"):
            for r in read(os.path.join(KIT, "out", d, "games.csv")):
                if r["target"] == "":
                    BYM2[(r["cond"], r["salt"])].append(r)
        vm = P.Table(BYM2, conds, "BASE", sm, AG).pick(sm)
        vr = P.Table(BYR, conds, "BASE", sr, AG).pick(sr)
        L.append("## 기술: 조건별 main 대 rep\n")
        L.append("| 조건 | mae main / rep | D main / rep | 등록 직선 예측 (rep mae) | rep 오차 |")
        L.append("|---|---|---|---|---|")
        for c in conds:
            pr = a0 + b0 * vr[c][0]
            L.append(f"| {c} | {vm[c][0]:.2f} / {vr[c][0]:.2f} | {vm[c][1]:.3f} / {vr[c][1]:.3f} | {pr:.3f} | {vr[c][1] - pr:+.3f} |")
        L.append("")
    txt = "\n".join(L) + "\n"
    open(REPORT, "w", encoding="utf-8").write(txt)
    json.dump(res, open(os.environ.get("P4_RESULTS", os.path.join(HERE, "p4_results.json")), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(txt)


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        smoke()
    elif "--report" in sys.argv:
        report()
    else:
        run_all()
        report()
        log("P4 완료")
