"""λ 격자 보충 — 개정 A21 (RQ2 결과를 본 뒤의 해상도 보완).

추가 λ {0.40, 0.45, 0.55, 0.60, 0.65} 와 {6, 8, 15, 20}, FLCS on, 주입 축 {p, q, all}, 설정 13, 조건 3, 기동 6 = 6,318 런.
분석은 RQ2(A19) 규칙을 **합친 격자**에 그대로 적용한다 (λ = 1 런은 RQ2 실행에서 가져옴).

사용: python research/l3_indi/refine.py            실행 + 합친 격자 분석
      python research/l3_indi/refine.py --analyze <results/paper/refine/<commit10>>
"""
from __future__ import annotations

import csv
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO            # noqa: E402
from l3_indi import rq2                      # noqa: E402

NEW_LOW = (0.40, 0.45, 0.55, 0.60, 0.65)
NEW_HIGH = (6.0, 8.0, 15.0, 20.0)
AXES = ("p", "q", "all")
RQ2_DIR = os.path.join(REPO, "results", "paper", "rq2", "37bfd99735")


def jobs():
    from l3_indi.design import rq2_conditions
    out = []
    for cond in rq2_conditions(0):
        for man in rq2.MANS:
            for sname, (kp, kq, kr, f) in rq2.settings().items():
                for ax in AXES:
                    for lam in NEW_LOW + NEW_HIGH:
                        lp = lam if ax in ("p", "all") else 1.0
                        lq = lam if ax in ("q", "all") else 1.0
                        lr = lam if ax == "all" else 1.0
                        out.append({"fbw": 0, "alt_ft": cond.alt_ft, "kcas": cond.kcas, "man": man,
                                    "setting": sname, "kp": kp, "kq": kq, "kr": kr, "filt": f,
                                    "lam_axis": ax, "lam": lam, "lam_p": lp, "lam_q": lq, "lam_r": lr})
    return out


def job_fn(job):
    from l3_indi.evaluate import evaluate
    return evaluate(job)


def merged_dir(run_dir: str) -> str:
    """RQ2(FLCS on) + 보충 런을 한 폴더로 합쳐 A19 분석을 그대로 돌린다."""
    out = os.path.join(run_dir, "merged")
    os.makedirs(out, exist_ok=True)
    new = list(csv.DictReader(open(os.path.join(run_dir, "runs.csv"), encoding="utf-8")))
    old = [r for r in csv.DictReader(open(os.path.join(RQ2_DIR, "runs.csv"), encoding="utf-8"))
           if r["fbw"] == "0" and (r["lam_axis"] in AXES or r["lam_axis"] == "none")]
    keys = sorted({k for r in new + old for k in r})
    with open(os.path.join(out, "runs.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, restval="")
        w.writeheader()
        w.writerows(old + new)
    return out


def analyze(run_dir: str):
    rq2.LOW = tuple(sorted((0.7, 0.65, 0.6, 0.55, 0.5, 0.45, 0.4, 0.35, 0.25), reverse=True))
    rq2.HIGH = (1.4, 2.0, 4.0, 6.0, 8.0, 10.0, 15.0, 20.0, 25.0)
    rq2.LAMBDAS = tuple(sorted(set(rq2.LOW) | set(rq2.HIGH) | {1.0}))
    out = merged_dir(run_dir)
    rq2.analyze(out)
    src = os.path.join(HERE, "reports", f"RQ2_{os.path.basename(out)}.md")
    dst = os.path.join(HERE, "reports", f"REFINE_{os.path.basename(os.path.normpath(run_dir))}.md")
    if os.path.exists(src):
        shutil.move(src, dst)
        print("->", dst)


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--analyze":
        analyze(sys.argv[2])
        return 0
    from l3_indi.runner import run_experiment
    out = run_experiment("refine", jobs(), job_fn, os.path.join(REPO, "results", "paper"))
    print("->", out)
    analyze(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
