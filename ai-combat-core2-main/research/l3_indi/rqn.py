"""실험 2 — RQ1-N 센서 잡음 × 필터 (사전등록 §9 RQ1-N, 개정 A11-4·A14).

사용: python research/l3_indi/rqn.py <RQ1 분석 폴더 (tuned.json 이 있는 곳)>
      python research/l3_indi/rqn.py --analyze <results/paper/rqn/<commit10>>
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO            # noqa: E402

FILT = (3.0, 5.0, 10.0, 15.0, 25.0, 50.0)
SIGMA = (0.0, 0.01, 0.03, 0.1, 0.3, 1.0)
SEEDS = (1, 2, 3, 4, 5)
MANS = ("M1_0.7", "M1_0.8", "M1_0.9", "M2a", "M3_0.7", "M3_0.9")


def jobs(tuned_k: tuple) -> list[dict]:
    from l3_indi.design import rq1_conditions
    out = []
    gains = {"base": (1.0, 1.0, 1.0), "tuned": tuple(tuned_k)}
    for cond in rq1_conditions(0):
        for man in MANS:
            for sigma in SIGMA:
                for seed in ((0,) if sigma == 0 else SEEDS):
                    for f in FILT:
                        seen = set()
                        for gname, k in gains.items():
                            if k in seen:          # 튜닝 = 기준이면 한 번만
                                continue
                            seen.add(k)
                            out.append({"fbw": 0, "alt_ft": cond.alt_ft, "kcas": cond.kcas, "man": man,
                                        "kp": k[0], "kq": k[1], "kr": k[2], "filt": f, "sigma": sigma,
                                        "seed": seed, "gain": gname})
    return out


def job_fn(job):
    from l3_indi.evaluate import evaluate
    return evaluate(job)


def load(run_dir: str) -> list[dict]:
    from l3_indi.rq1_analysis import fnum
    rows = list(csv.DictReader(open(os.path.join(run_dir, "runs.csv"), encoding="utf-8")))
    for r in rows:
        for k, v in list(r.items()):
            if k not in ("man", "gain"):
                r[k] = fnum(v)
        r["fbw"] = int(r["fbw"])
    return rows


def analyze(run_dir: str):
    from l3_indi import metrics as M
    from l3_indi.rq1_analysis import band_keys, exclusion, primary_metrics
    rows = load(run_dir)
    commit = os.path.basename(os.path.normpath(run_dir))
    ref = {}
    for r in rows:
        if (r["kp"], r["kq"], r["kr"]) == (1.0, 1.0, 1.0):
            ref[(r["alt_ft"], r["kcas"], r["man"], r["filt"], r["sigma"], r["seed"])] = r
    gains = sorted({r["gain"] for r in rows})
    # 튜닝 = 기준이면 기준 런이 두 게인을 대표
    for r in rows:
        r["excluded"] = exclusion(r)
        base = ref.get((r["alt_ft"], r["kcas"], r["man"], r["filt"], r["sigma"], r["seed"]))
        rho = []
        for k in band_keys(r["man"]):
            if base is None:
                rho.append(float("nan"))
            elif k.startswith("J_"):
                rho.append(r[k] / base[k] if base[k] > 0 and np.isfinite(r[k]) else float("inf"))
            else:
                rho.append(M.floored_ratio(k, r[k], base[k]))
        if r["oscillating"] >= 1 or r["g_exceeded"] >= 1:
            r["band"] = "unstable"
        elif any(isinstance(v, float) and math.isnan(v) for v in rho):
            r["band"] = "no_ref"
        elif max(rho) > 1.5:
            r["band"] = "degraded"
        else:
            r["band"] = "stable"
    L = [f"# RQ1-N 결과 — 실험 커밋 {commit}\n",
         f"- 런 {len(rows)}개. 규칙: 사전등록 §9 RQ1-N, 개정 A13·A14. 게인 설정 {gains}.\n"]
    cells = defaultdict(list)
    for r in rows:
        for m in primary_metrics(r["man"]):
            cells[(r["gain"], r["alt_ft"], r["kcas"], r["man"], m, r["sigma"], r["filt"])].append(r)
    table = []
    for key, R in cells.items():
        gain, alt, kcas, man, m, sigma, f = key
        elig = all(rr["band"] != "unstable" and not rr["excluded"] for rr in R)
        vals = [rr[m] for rr in R]
        table.append({"gain": gain, "alt_kft": int(alt / 1000), "kcas": int(kcas), "man": man, "metric": m,
                      "sigma": sigma, "filt": f, "n_seeds": len(R), "eligible": int(elig),
                      "J_mean": float(np.mean(vals)), "J_min": float(np.min(vals)), "J_max": float(np.max(vals)),
                      "n_unstable": sum(rr["band"] == "unstable" for rr in R),
                      "n_excluded": sum(bool(rr["excluded"]) for rr in R)})
    with open(os.path.join(run_dir, "cells.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
        w.writeheader()
        w.writerows(table)
    blocks = defaultdict(dict)
    for c in table:
        blocks[(c["gain"], c["alt_kft"], c["kcas"], c["man"], c["metric"])].setdefault(c["sigma"], []).append(c)
    fstar, xint = [], []
    for bk, bys in sorted(blocks.items()):
        fs = {}
        for s in SIGMA:
            el = [c for c in bys.get(s, []) if c["eligible"]]
            fs[s] = min(el, key=lambda c: (c["J_mean"], c["filt"]))["filt"] if el else None
        x = next((s for s in SIGMA[1:] if fs[s] != fs[0.0]), None)
        prev = None if x is None else SIGMA[SIGMA.index(x) - 1]
        fstar.append((bk, fs))
        xint.append((bk, prev, x))
    L.append("## 1. 부적격 칸 (시드 중 불안정·제외 포함)\n")
    L.append("| 게인 | σ | 칸 | 부적격 |")
    L.append("|---|---|---|---|")
    for g in gains:
        for s in SIGMA:
            C = [c for c in table if c["gain"] == g and c["sigma"] == s]
            L.append(f"| {g} | {s:g} | {len(C)} | {sum(1 - c['eligible'] for c in C)} |")
    L.append("\n## 2. 최적 필터 f*(σ) 분포 — 블록 수 (블록 = 게인 × 조건 × 기동 × 지표)\n")
    for g in gains:
        for mt in ("M1", "M2a", "M3"):
            sel = [(bk, fs) for bk, fs in fstar if bk[0] == g and bk[3].startswith(mt)]
            if not sel:
                continue
            L.append(f"**게인 {g} · {mt}** (블록 {len(sel)})\n")
            L.append("| σ | " + " | ".join(f"{f:g} Hz" for f in FILT) + " | 적격 없음 | 내부 최소 비율 |")
            L.append("|---|" + "---|" * (len(FILT) + 2))
            for s in SIGMA:
                cnt = [sum(1 for _, fs in sel if fs[s] == f) for f in FILT]
                none = sum(1 for _, fs in sel if fs[s] is None)
                inner = [fs[s] not in (FILT[0], FILT[-1]) for _, fs in sel if fs[s] is not None]
                L.append(f"| {s:g} | " + " | ".join(str(c) for c in cnt) + f" | {none} | "
                         f"{100*np.mean(inner):.0f}% |" if inner else f"| {s:g} | " + " | ".join(str(c) for c in cnt) + f" | {none} | — |")
            L.append("")
    L.append("## 3. 전환 수준 X — f*(σ) ≠ f*(0) 이 처음 되는 σ 구간 (블록 수)\n")
    L.append("| 게인 | 기동 | " + " | ".join(f"({SIGMA[i-1]:g}, {SIGMA[i]:g}]" for i in range(1, len(SIGMA))) + " | 전환 없음 |")
    L.append("|---|---|" + "---|" * len(SIGMA))
    for g in gains:
        for mt in ("M1", "M2a", "M3"):
            sel = [(bk, p, x) for bk, p, x in xint if bk[0] == g and bk[3].startswith(mt)]
            if not sel:
                continue
            cnt = [sum(1 for _, p, x in sel if x == SIGMA[i]) for i in range(1, len(SIGMA))]
            L.append(f"| {g} | {mt} | " + " | ".join(str(c) for c in cnt) + f" | {sum(1 for _, p, x in sel if x is None)} |")
    L.append("\n## 4. 필터별 평균 J (적격 칸 블록 중앙값) — 게인 기준, 대표 조건 14 kft / 350 KCAS\n")
    for man, m in (("M1_0.8", "J_q"), ("M2a", "J_p"), ("M3_0.9", "J_q"), ("M3_0.9", "J_p")):
        L.append(f"**{man} · {m}**\n")
        L.append("| σ \\ filt | " + " | ".join(f"{f:g}" for f in FILT) + " |")
        L.append("|---|" + "---|" * len(FILT))
        for s in SIGMA:
            vals = []
            for f in FILT:
                C = [c for c in table if c["gain"] == "base" and c["alt_kft"] == 14 and c["kcas"] == 350
                     and c["man"] == man and c["metric"] == m and c["sigma"] == s and c["filt"] == f]
                vals.append("—" if not C else (f"{C[0]['J_mean']:.3f}" + ("" if C[0]["eligible"] else "✗")))
            L.append(f"| {s:g} | " + " | ".join(vals) + " |")
        L.append("")
    rep = os.path.join(HERE, "reports", f"RQ1N_{commit}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", rep)


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--analyze":
        analyze(sys.argv[2])
        return 0
    tuned = json.load(open(os.path.join(sys.argv[1], "tuned.json"), encoding="utf-8"))["tuned"]
    from l3_indi.runner import run_experiment
    js = jobs(tuple(tuned[:3]))
    out = run_experiment("rqn", js, job_fn, os.path.join(REPO, "results", "paper"))
    with open(os.path.join(out, "tuned_source.json"), "w", encoding="utf-8") as fh:
        json.dump({"rq1_analysis_dir": sys.argv[1], "tuned": tuned}, fh)
    print("->", out)
    analyze(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
