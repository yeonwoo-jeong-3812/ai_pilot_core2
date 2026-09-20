"""이상 응답 대비 몫 분해 — 개정 A24-7 (추가 요청 2).

전체 추종 오차 중 **물리 한계 몫**(기체 최대 각가속도만으로도 생기는 오차)과 **제어기 몫**을 기동·조건별로 나눈다.

  이상 응답 = 기록된 ω_sp 를 |ω̇| ≤ (그 조건의 개루프 최대 각가속도) 로만 제한해 따라가는 응답 (A17 [3b] 와 같은 정의)
  물리 몫 = J_ideal / J_actual,  제어기 몫 = 1 − J_ideal / J_actual

사용: python research/l3_indi/ideal_share.py
출력: results/paper/ideal_share/<commit10>/runs.csv + research/l3_indi/reports/IDEALSHARE_<commit10>.md
"""
from __future__ import annotations

import contextlib
import csv
import io
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO, DT            # noqa: E402

OPENLOOP_CSV = os.path.join(REPO, "results", "paper", "cmdshape", "7760bbc8b9", "runs.csv")
MANS = ("M1_0.7", "M1_0.8", "M1_0.9", "M2a", "M2b", "M3_0.7", "M3_0.9")


def open_loop_limits() -> dict:
    """A17 실행에서 잰 조건별 개루프 최대 각가속도 [deg/s²]. 롤은 ± 중 작은 쪽."""
    out = {}
    for r in csv.DictReader(open(OPENLOOP_CSV, encoding="utf-8")):
        if r["exp"] != "openloop":
            continue
        k = (float(r["alt_ft"]), float(r["kcas"]))
        d = out.setdefault(k, {"p": [], "q": None})
        if r["kind"] == "ail":
            d["p"].append(float(r["pdot_max_dps2"]))
        else:
            d["q"] = float(r["qdot_max_dps2"])
    return {k: {"p": min(v["p"]), "q": v["q"]} for k, v in out.items()}


def job(j):
    from l3_indi.harness import build, run, Condition, Params
    from l3_indi.design import capability
    from l3_indi.evaluate import maneuver_by_name
    from l3_indi.cmdshape import ideal_follow
    from l3_indi import metrics as M
    cond = Condition(j["alt_ft"], j["kcas"])
    man = maneuver_by_name(j["man"], capability(cond))
    with contextlib.redirect_stdout(io.StringIO()):
        ts = run(build(cond, Params()), man)
    w = man.window()
    row = dict(j)
    for ax, lim in (("p", j["pdot_max"]), ("q", j["qdot_max"])):
        sp = np.rad2deg(ts[f"sp_{ax}"])
        row[f"J_{ax}"] = M.tracking_J(ts, ax, w)
        row[f"Jideal_{ax}"] = ideal_follow(ts["t"], sp, w, lim)
    return row


def main():
    from l3_indi.design import rq1_conditions
    from l3_indi.runner import run_experiment
    lim = open_loop_limits()
    jobs = []
    for cond in rq1_conditions(0):
        k = (cond.alt_ft, cond.kcas)
        for man in MANS:
            jobs.append({"alt_ft": cond.alt_ft, "kcas": cond.kcas, "man": man,
                         "pdot_max": lim[k]["p"], "qdot_max": lim[k]["q"]})
    out = run_experiment("ideal_share", jobs, job, os.path.join(REPO, "results", "paper"))
    rows = list(csv.DictReader(open(os.path.join(out, "runs.csv"), encoding="utf-8")))
    for r in rows:
        for c in r:
            if c != "man":
                r[c] = float(r[c])
    prim = lambda m: "q" if m.startswith("M1") else "p"
    L = [f"# 이상 응답 대비 몫 분해 — 실험 커밋 {os.path.basename(out)}\n",
         "- FLCS on, 기준 게인, RQ1 9조건. 이상 응답 = 같은 명령을 **기체 최대 각가속도만** 제한해 따라간 응답 (개정 A24-7).",
         "- 물리 몫 = J_ideal / J_actual (어떤 제어기도 피할 수 없는 부분), 제어기 몫 = 1 − 물리 몫.\n",
         "| 기동 | 주 축 | J 실제 (중앙, 범위) | J 이상 (중앙) | **물리 몫** | **제어기 몫** |",
         "|---|---|---|---|---|---|"]
    for man in MANS:
        R = [r for r in rows if r["man"] == man]
        ax = prim(man)
        ja = np.array([r[f"J_{ax}"] for r in R]); ji = np.array([r[f"Jideal_{ax}"] for r in R])
        share = ji / ja
        L.append(f"| {man} | {ax} | {np.median(ja):.3f} ({ja.min():.3f}~{ja.max():.3f}) | {np.median(ji):.3f} | "
                 f"**{100*np.median(share):.0f}%** | {100*(1-np.median(share)):.0f}% |")
    L.append("\n### 조건별 물리 몫 (%)\n")
    L.append("| 조건 | " + " | ".join(MANS) + " |")
    L.append("|---|" + "---|" * len(MANS))
    for a, c in sorted({(r["alt_ft"], r["kcas"]) for r in rows}):
        cells = []
        for man in MANS:
            r = next(x for x in rows if x["man"] == man and x["alt_ft"] == a and x["kcas"] == c)
            ax = prim(man)
            cells.append(f"{100*r[f'Jideal_{ax}']/r[f'J_{ax}']:.0f}")
        L.append(f"| {int(a/1000)}k/{int(c)} | " + " | ".join(cells) + " |")
    L.append("\n### 개루프 최대 각가속도 [deg/s²]\n")
    L.append("| 조건 | 롤 |ṗ|max | 피치 |q̇|max |")
    L.append("|---|---|---|")
    for (a, c), v in sorted(lim.items()):
        L.append(f"| {int(a/1000)}k/{int(c)} | {v['p']:.0f} | {v['q']:.0f} |")
    rep = os.path.join(HERE, "reports", f"IDEALSHARE_{os.path.basename(out)}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
