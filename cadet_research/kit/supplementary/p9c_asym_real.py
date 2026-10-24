"""P9-c: 실제형 센서·구동기에서도 한 기체 열화의 U자가 나오는가 (사전 등록 ../../PREREG_P9.md §P9-c).

  python p9c_asym_real.py --smoke   # 점검: p9smoke-0 2경기
  python p9c_asym_real.py           # 2,688경기 → ../out/p9c/games.csv, 분석 → p9c_output.md
  python p9c_asym_real.py --report  # 분석만

실제형 구성(p7_realistic)은 두 기체 모두에 걸리고, 비동기 지연은 대상 한 기체에만 건다(원래 ASYM과 같은 방식).
짝이 되는 BASE 는 P7 의 실제형 BASE(../out/p7/games.csv, 같은 main 시드·대진·시나리오)다.
"""
from __future__ import annotations

import collections
import ctypes
import json
import multiprocessing as mp
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p7_run  # noqa: E402  (실제형 구성 enable)
import run  # noqa: E402
from experiments import AGENTS_MAIN, EXPERIMENTS, LEAGUE  # noqa: E402
from p8_run import KEY, log as _log, run_jobs as _run_jobs  # noqa: E402

KIT = p7_run.KIT
TARGETS = ["GunTracker", "Extender"]
CONDS = ["F25_D6", "F25_D8", "F25_D10", "F25_D12"]
MODERATE, SEVERE = "F25_D8", "F25_D10"   # 원래 ASYM 2틱·6틱의 대상 mae(5.16·7.79)에 가장 가까운 실제형 조건 (P7 mae 4.62·9.22)
OUTDIR = os.path.join(KIT, "out", "p9c")
OUT = os.path.join(OUTDIR, "games.csv")
REPORT = os.path.join(HERE, "p9c_output.md")
DELTA_PTS = 11.10


def jobs(salt="main", n=8):
    return [j for j in run.build_jobs(dict(agents=AGENTS_MAIN, scenarios=LEAGUE, salt=salt, conds=CONDS, target="each"), n)
            if j["target"] in TARGETS]


def report():
    from analyze import points
    from scipy import stats
    AG = list(EXPERIMENTS["E2"]["agents"])
    rows = p7_run.read(OUT)
    base = {(r["blue"], r["red"], r["scenario"], r["salt"]): r for r in p7_run.read(os.path.join(KIT, "out", "p7", "games.csv"))
            if r["cond"] == "BASE" and r["target"] == ""}
    seeds = sorted({r["salt"] for r in rows}, key=lambda x: int(x.rsplit("-", 1)[1]))
    kb = lambda r: (r["blue"], r["red"], r["scenario"], r["salt"])
    lv = 100 * (1 - 0.05 / 3)
    rng = np.random.default_rng(0)
    BS = [list(rng.choice(seeds, len(seeds))) for _ in range(2000)]
    tq = stats.t.ppf(1 - (1 - lv / 100) / 2, len(seeds) - 1)
    L = ["# P9-c: 실제형 구성의 한 기체 열화 (사전 등록 `PREREG_P9.md` §P9-c)\n",
         f"경기 {len(rows):,} (사전 등록 2,688), `wall_clock` {sum(r['condition'] == 'wall_clock' for r in rows)}. 짝: P7 실제형 BASE. δ_점수 {DELTA_PTS}, {lv:.2f} % 구간.\n",
         "| 대상 | 조건 | 대상 mae | Δ점수 [퍼센타일] |", "|---|---|---|---|"]
    res = {}
    for t in TARGETS:
        cell, mae = {}, {}
        for c in CONDS:
            for s in seeds:
                gs = [r for r in rows if r["cond"] == c and r["target"] == t and r["salt"] == s]
                cell[(c, s)] = points(gs, AG)[0][t] - points([base[kb(g)] for g in gs], AG)[0][t]
            own = [float(g["blue_mae_q_dps"] if g["blue"] == t else g["red_mae_q_dps"]) for g in rows if g["cond"] == c and g["target"] == t]
            mae[c] = float(np.mean(own))
            m = float(np.mean([cell[(c, s)] for s in seeds]))
            b = [np.mean([cell[(c, s)] for s in bb]) for bb in BS]
            lo, hi = np.percentile(b, [(100 - lv) / 2, 100 - (100 - lv) / 2])
            L.append(f"| {t} | {c} | {mae[c]:.2f} | {m:+.1f} [{lo:+.1f}, {hi:+.1f}] |")
        con = {s: cell[(SEVERE, s)] - cell[(MODERATE, s)] for s in seeds}
        m = float(np.mean(list(con.values())))
        b = [np.mean([con[s] for s in bb]) for bb in BS]
        cb = tuple(float(x) for x in np.percentile(b, [(100 - lv) / 2, 100 - (100 - lv) / 2]))
        sd = np.std(list(con.values()), ddof=1) / np.sqrt(len(seeds))
        ct = (m - tq * sd, m + tq * sd)
        j = lambda lo, hi: "반등 있음 (U자 재현)" if lo > DELTA_PTS else ("반등 없음" if hi < DELTA_PTS else "판정 불가")
        v = j(*cb) if j(*cb) == j(*ct) else "판정 불가 (구간 방식에 따라 다름)"
        res[t] = dict(contrast=m, ci_boot=cb, ci_t=ct, verdict=v, mae=mae,
                      dpts={c: float(np.mean([cell[(c, s)] for s in seeds])) for c in CONDS})
    L.append("")
    for t in TARGETS:
        r = res[t]
        L.append(f"**{t}: 반등 {SEVERE} − {MODERATE} = {r['contrast']:+.1f}**, 퍼센타일 [{r['ci_boot'][0]:+.1f}, {r['ci_boot'][1]:+.1f}], "
                 f"시드 t [{r['ci_t'][0]:+.1f}, {r['ci_t'][1]:+.1f}] → **{r['verdict']}**\n")
    txt = "\n".join(L) + "\n"
    open(REPORT, "w", encoding="utf-8").write(txt)
    json.dump(res, open(os.path.join(HERE, "p9c_results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(txt)


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        js = [j for j in jobs("p9smoke", 1) if j["scenario"] == "neutral" and j["cond"] in ("F25_D8", "F25_D12")
              and j["target"] == "GunTracker" and "RedPrime" in (j["blue"], j["red"])][:2]
        with mp.Pool(2) as pool:
            rs = pool.map(p7_run.play, js)
        for r in rs:
            print(r["cond"], r["target"], r["blue"], r["red"], r["winner"], r["condition"], r["blue_mae_q_dps"], r["red_mae_q_dps"])
    elif "--report" in sys.argv:
        report()
    else:
        if os.name == "nt":
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        os.makedirs(OUTDIR, exist_ok=True)
        _run_jobs(jobs(), OUT, "P9-c")
        _log("P9-c 경기 완료")
        report()
        _log("P9-c 완료")
