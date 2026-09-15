"""실험 1 — RQ1 무잡음 게인 × 필터 완전요인 (사전등록 §9, 개정 A9·A11·A13).

  k_p, k_q 배율 {0.5, 0.75, 1.0, 1.5, 2.0} × k_r 배율 {0.5, 1.0, 2.0} × filt {10, 15, 20, 25, 35, 50} Hz = 450
  × RQ1 9조건 × 기동 변형 7종(M1×3, M2a, M2b, M3×2) × FLCS on/off = 56,700 런

기준 파라미터 (1, 1, 1, 25 Hz) 런은 시계열을 저장한다 (A10-1 히트맵용).

사용: python research/l3_indi/rq1.py [--limit N]     (--limit 은 시간 측정용, 결과 분석에 쓰지 않음)
출력: results/paper/rq1/<commit10>/{runs.csv, manifest.json, jobs.json, ts/}
"""
from __future__ import annotations

import argparse
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO                        # noqa: E402

KP = KQ = (0.5, 0.75, 1.0, 1.5, 2.0)
KR = (0.5, 1.0, 2.0)
FILT = (10.0, 15.0, 20.0, 25.0, 35.0, 50.0)
MANEUVERS = ("M1_0.7", "M1_0.8", "M1_0.9", "M2a", "M2b", "M3_0.7", "M3_0.9")


def jobs(out_dir: str) -> list[dict]:
    from l3_indi.design import rq1_conditions
    out = []
    for fbw in (0, 1):
        for cond in rq1_conditions(fbw):
            for man in MANEUVERS:
                for kp, kq, kr, f in itertools.product(KP, KQ, KR, FILT):
                    j = {"fbw": fbw, "alt_ft": cond.alt_ft, "kcas": cond.kcas, "man": man,
                         "kp": kp, "kq": kq, "kr": kr, "filt": f}
                    if (kp, kq, kr, f) == (1.0, 1.0, 1.0, 25.0):
                        j["_ts_dir"] = os.path.join(out_dir, "ts")
                    out.append(j)
    return out


def job_fn(job):
    from l3_indi.evaluate import evaluate
    return evaluate(job, job.get("_ts_dir"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    from l3_indi.runner import run_experiment, git_state
    name = "rq1_timing" if args.limit else "rq1"
    out_dir = os.path.join(REPO, "results", "paper", name, git_state()["commit"][:10])
    js = jobs(out_dir)
    if args.limit:
        js = js[:: max(1, len(js) // args.limit)][: args.limit]
    out = run_experiment(name, js, job_fn, os.path.join(REPO, "results", "paper"))
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
