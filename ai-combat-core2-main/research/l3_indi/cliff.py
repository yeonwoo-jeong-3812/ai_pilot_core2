"""25 Hz 절벽 정밀화 — 개정 A11-6.

  k_p = k_q 배율 1.40~1.80 (0.05) × filt 20~35 Hz (1 Hz), k_r 1.0, 14 kft / 350 KCAS, M1_0.8·M3_0.9, FLCS on, 무잡음 = 288 런
  + 3구간 기준 런 (k 배율 1, 같은 filt) 32 런

보고: filt 마다 마지막 안정 k, 첫 열화 k, 첫 불안정 k, 열화 구간 폭(열화 판정 수준 수).

사용: python research/l3_indi/cliff.py            실행
      python research/l3_indi/cliff.py --analyze <results/paper/cliff/<commit10>>
"""
from __future__ import annotations

import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO            # noqa: E402

K = tuple(round(1.40 + 0.05 * i, 2) for i in range(9))
FILT = tuple(float(f) for f in range(20, 36))
MANS = ("M1_0.8", "M3_0.9")


def jobs():
    out = []
    for man in MANS:
        for f in FILT:
            for k in (1.0,) + K:
                out.append({"fbw": 0, "alt_ft": 14000.0, "kcas": 350.0, "man": man,
                            "kp": k, "kq": k, "kr": 1.0, "filt": f})
    return out


def job_fn(job):
    from l3_indi.evaluate import evaluate
    return evaluate(job)


def analyze(run_dir: str):
    from l3_indi.rq1_analysis import load, classify_all
    rows = load(run_dir)
    classify_all(rows)
    commit = os.path.basename(os.path.normpath(run_dir))
    L = [f"# 25 Hz 절벽 정밀화 — 실험 커밋 {commit}\n",
         "- 14 kft / 350 KCAS, FLCS on, k_p = k_q 배율 (k_r 1), 판정 = RQ1 과 같은 규칙(임계 1.5, 개정 A13).\n"]
    mark = {"stable": "S", "degraded": "D", "unstable": "X", "no_ref": "?"}
    for man in MANS:
        L.append(f"## {man}\n")
        L.append("```")
        L.append("filt\\k " + " ".join(f"{k:>5.2f}" for k in K))
        summary = []
        for f in FILT:
            R = {r["kp"]: r for r in rows if r["man"] == man and r["filt"] == f}
            cells = []
            for k in K:
                r = R.get(k)
                cells.append(f"{('-' if r['excluded'] else mark[r['band']]) if r else ' ':>5}")
            L.append(f"{f:>6g} " + " ".join(cells))
            bands = [(k, R[k]["band"]) for k in K if k in R and not R[k]["excluded"]]
            last_s = max([k for k, b in bands if b == "stable"], default=None)
            first_d = min([k for k, b in bands if b == "degraded"], default=None)
            first_x = min([k for k, b in bands if b == "unstable"], default=None)
            width = sum(1 for k, b in bands if b == "degraded" and (first_x is None or k < first_x))
            summary.append((f, last_s, first_d, first_x, width))
        L.append("```\n")
        L.append("| filt | 마지막 안정 k | 첫 열화 k | 첫 불안정 k | 불안정 전 열화 수준 수 (0.05 간격) |")
        L.append("|---|---|---|---|---|")
        for f, s, d, x, w in summary:
            fmt = lambda v: "—" if v is None else f"{v:.2f}"
            L.append(f"| {f:g} | {fmt(s)} | {fmt(d)} | {fmt(x)} | {w} |")
        L.append("")
    rep = os.path.join(HERE, "reports", f"CLIFF_{commit}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    with open(os.path.join(run_dir, "runs_classified.csv"), "w", newline="", encoding="utf-8") as fh:
        keys = sorted({k for r in rows for k in r})
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print("->", rep)


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--analyze":
        analyze(sys.argv[2])
        return 0
    from l3_indi.runner import run_experiment
    out = run_experiment("cliff", jobs(), job_fn, os.path.join(REPO, "results", "paper"))
    print("->", out)
    analyze(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
