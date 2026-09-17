"""측정 지연 실험 — 개정 A10-4 설계, A20 분석 정의.

  파라미터 {기준 (1,1,1)/filt 25, 튜닝 (1,1.5,0.5)/filt 15} × RQ1 9조건 × {M1×3, M2a, M3×2} × FLCS on
  × (N = 0 공통 + N ∈ {1,2,4,8} 틱 × {비동기, 동기}) = 972 런. 1틱 = 8.33 ms.

사용: python research/l3_indi/delay.py            실행 + 분석
      python research/l3_indi/delay.py --analyze <results/paper/delay/<commit10>>
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO, DT            # noqa: E402

NS = (1, 2, 4, 8)
GAINS = {"base": (1.0, 1.0, 1.0, 25.0), "tuned": (1.0, 1.5, 0.5, 15.0)}
MANS = ("M1_0.7", "M1_0.8", "M1_0.9", "M2a", "M3_0.7", "M3_0.9")


def jobs():
    from l3_indi.design import rq1_conditions
    out = []
    for cond in rq1_conditions(0):
        for man in MANS:
            for g, (kp, kq, kr, f) in GAINS.items():
                common = {"fbw": 0, "alt_ft": cond.alt_ft, "kcas": cond.kcas, "man": man,
                          "gain": g, "kp": kp, "kq": kq, "kr": kr, "filt": f}
                out.append(dict(common, delay_n=0, sync=False, variant="none"))
                for n in NS:
                    out.append(dict(common, delay_n=n, sync=False, variant="async"))
                    out.append(dict(common, delay_n=n, sync=True, variant="sync"))
    return out


def job_fn(job):
    from l3_indi.evaluate import evaluate
    return evaluate(job)


STR_COLS = {"man", "gain", "variant", "osc_freq_axis"}


def analyze(run_dir: str):
    from l3_indi import metrics as M
    from l3_indi.rq1_analysis import band_keys, exclusion, primary_metrics, fnum
    commit = os.path.basename(os.path.normpath(run_dir))
    rows = list(csv.DictReader(open(os.path.join(run_dir, "runs.csv"), encoding="utf-8")))
    for r in rows:
        for k, v in list(r.items()):
            if k not in STR_COLS:
                r[k] = fnum(v)

    base = {(r["alt_ft"], r["kcas"], r["man"], r["gain"]): r for r in rows if r["delay_n"] == 0}
    for r in rows:
        r["excluded"] = exclusion(r)
        b = base.get((r["alt_ft"], r["kcas"], r["man"], r["gain"]))
        if b is None or b["departure"] >= 1:
            r["band"] = "기준 없음"
            continue
        rho = []
        for k in band_keys(r["man"]):
            if k.startswith("J_"):
                rho.append(r[k] / b[k] if b[k] > 0 and np.isfinite(r[k]) else float("inf"))
            else:
                rho.append(M.floored_ratio(k, r[k], b[k]))
        if r["oscillating"] >= 1 or r["g_exceeded"] >= 1 or r["departure"] >= 1:
            r["band"] = "unstable"
        elif any(v != v for v in rho):                      # NaN = 기준값 없음
            r["band"] = "기준 없음"
        elif max(rho) > 1.5:
            r["band"] = "degraded"
        else:
            r["band"] = "stable"

    L = [f"# 측정 지연 실험 — 실험 커밋 {commit}\n",
         f"- 런 {len(rows)}, FLCS on, 무잡음. 규칙: 개정 A10-4(설계)·A20(분석). 1틱 = {1000*DT:.2f} ms.",
         "- 비동기 = 자이로·각가속도 읽기만 지연, 동기 = INDI 액추에이터 되먹임도 같은 크기로 지연.\n"]

    L.append("## 1. 지연 N 에 따른 주 지표 J 중앙값과 3구간 분포\n")
    L.append("| 게인 | 변형 | N (ms) | J 중앙값 | N=0 대비 배율 | 안정 | 열화 | 불안정 |")
    L.append("|---|---|---|---|---|---|---|---|")
    jmed = {}
    for g in GAINS:
        for variant in ("async", "sync"):
            for n in (0,) + NS:
                v = "none" if n == 0 else variant
                R = [r for r in rows if r["gain"] == g and r["delay_n"] == n and r["variant"] == v and not r["excluded"]]
                if not R:
                    continue
                js = []
                for r in R:
                    js += [r[m] for m in primary_metrics(r["man"]) if np.isfinite(r[m])]
                med = float(np.median(js))
                jmed[(g, variant, n)] = med
                ratio = med / jmed[(g, variant, 0)] if (g, variant, 0) in jmed else 1.0
                c = lambda b: sum(1 for r in R if r["band"] == b)
                L.append(f"| {g} | {'—' if n == 0 else variant} | {n} ({n*1000*DT:.0f}) | {med:.3f} | {ratio:.2f} | "
                         f"{c('stable')} | {c('degraded')} | {c('unstable')} |")

    L.append("\n## 2. 블록별 처음 열화·불안정해지는 N (블록 = 조건 × 기동, 54개)\n")
    L.append("| 게인 | 변형 | 처음 열화 N 중앙값 | 분포 (1/2/4/8/>8틱) | 처음 불안정 N 중앙값 | 분포 (1/2/4/8/>8틱) |")
    L.append("|---|---|---|---|---|---|")
    first = {}
    for g in GAINS:
        for variant in ("async", "sync"):
            fd, fu = [], []
            for (alt, kc, man) in sorted({(r["alt_ft"], r["kcas"], r["man"]) for r in rows}):
                seq = {n: next((r for r in rows if r["gain"] == g and r["delay_n"] == n and r["alt_ft"] == alt
                                and r["kcas"] == kc and r["man"] == man
                                and (r["variant"] == ("none" if n == 0 else variant))), None) for n in (0,) + NS}
                if seq[0] is None or seq[0]["band"] != "stable":
                    continue
                d = next((n for n in NS if seq[n] is not None and seq[n]["band"] in ("degraded", "unstable")), None)
                u = next((n for n in NS if seq[n] is not None and seq[n]["band"] == "unstable"), None)
                fd.append(d); fu.append(u)
            first[(g, variant)] = (fd, fu)
            dist = lambda a: "/".join(str(sum(1 for x in a if x == n)) for n in NS) + f"/{sum(1 for x in a if x is None)}"
            m = lambda a: float(np.median([x for x in a if x is not None])) if any(x is not None for x in a) else float("nan")
            L.append(f"| {g} | {variant} | {m(fd):.1f} | {dist(fd)} | {m(fu):.1f} | {dist(fu)} |")

    L.append("\n## 3. 동기화 효과 (같은 N 에서 동기 / 비동기)\n")
    L.append("| 게인 | N (ms) | J 비 (동기/비동기) 중앙값 | 3구간이 좋아진 블록 | 같음 | 나빠진 블록 |")
    L.append("|---|---|---|---|---|---|")
    order = {"stable": 0, "degraded": 1, "unstable": 2, "기준 없음": 3}
    for g in GAINS:
        for n in NS:
            pairs = []
            for (alt, kc, man) in sorted({(r["alt_ft"], r["kcas"], r["man"]) for r in rows}):
                a = next((r for r in rows if r["gain"] == g and r["delay_n"] == n and r["variant"] == "async"
                          and r["alt_ft"] == alt and r["kcas"] == kc and r["man"] == man), None)
                s = next((r for r in rows if r["gain"] == g and r["delay_n"] == n and r["variant"] == "sync"
                          and r["alt_ft"] == alt and r["kcas"] == kc and r["man"] == man), None)
                if a and s and not a["excluded"] and not s["excluded"]:
                    pairs.append((a, s))
            rat = []
            for a, s in pairs:
                for m in primary_metrics(a["man"]):
                    if np.isfinite(a[m]) and a[m] > 0 and np.isfinite(s[m]):
                        rat.append(s[m] / a[m])
            better = sum(1 for a, s in pairs if order[s["band"]] < order[a["band"]])
            same = sum(1 for a, s in pairs if order[s["band"]] == order[a["band"]])
            worse = sum(1 for a, s in pairs if order[s["band"]] > order[a["band"]])
            L.append(f"| {g} | {n} ({n*1000*DT:.0f}) | {np.median(rat) if rat else float('nan'):.3f} | {better} | {same} | {worse} |")

    L.append("\n## 4. 기동별 민감도 (기준 게인, 비동기, N = 4틱 33 ms)\n")
    L.append("| 기동 | J 중앙값 N=0 → N=4 | 배율 | 불안정 블록 |")
    L.append("|---|---|---|---|")
    for man in MANS:
        j0, j4, uns = [], [], 0
        for r in rows:
            if r["gain"] != "base" or r["man"] != man or r["excluded"]:
                continue
            ms = [r[m] for m in primary_metrics(man) if np.isfinite(r[m])]
            if r["delay_n"] == 0:
                j0 += ms
            elif r["delay_n"] == 4 and r["variant"] == "async":
                j4 += ms
                uns += int(r["band"] == "unstable")
        if j0 and j4:
            L.append(f"| {man} | {np.median(j0):.3f} → {np.median(j4):.3f} | {np.median(j4)/np.median(j0):.2f} | {uns}/9 |")

    with open(os.path.join(run_dir, "runs_classified.csv"), "w", newline="", encoding="utf-8") as fh:
        keys = sorted({k for r in rows for k in r})
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    rep = os.path.join(HERE, "reports", f"DELAY_{commit}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", rep)


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--analyze":
        analyze(sys.argv[2])
        return 0
    from l3_indi.runner import run_experiment
    out = run_experiment("delay", jobs(), job_fn, os.path.join(REPO, "results", "paper"))
    print("->", out)
    analyze(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
