"""개정 A36 §5 1단계 — 기체 모델·G 봉투·잡음 교체가 κ 경계를 옮기는지 본다.

κ = G_model / G_true (피치 행만). 논문 기호 κ, 코드 이름 lam_q (A36 §2).

판정 정의는 RQ2(개정 A19)의 것을 **그대로 import 한다**(`rq2.unstable`, `rq2.lam_s`,
`rq2.crossing`, `rq2.LOW/HIGH`). 정의가 달라서 경계가 움직이는 일을 없애기 위해서다.

셀 4개로 원인을 분리한다.
  cell1  f16    + platform + σ0     기준 (RQ2 재현 확인)
  cell2  f16fix + platform + σ0     기체 모델만
  cell3  f16fix + manual   + σ0     기체 모델 + G 봉투
  cell4  f16fix + manual   + σ0.1   A36 조건 전부

사용: python research/l3_indi/model_probe.py [--processes 8]
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi import rq2                                   # noqa: E402  (판정 정의 재사용)
from l3_indi.harness import REPO                          # noqa: E402

CELLS = (
    ("cell1_f16_platform_s0",     "f16",    "platform", 0.0),
    ("cell2_f16fix_platform_s0",  "f16fix", "platform", 0.0),
    ("cell3_f16fix_manual_s0",    "f16fix", "manual",   0.0),
    ("cell4_f16fix_manual_s01",   "f16fix", "manual",   0.1),
)
KAPPAS = (1.0,) + rq2.LOW + rq2.HIGH          # RQ2 와 같은 격자 (0.25~25, 10 점)
KCAS = (250.0, 350.0, 400.0)                  # RQ2 와 같은 14 kft 세 운용점
MANS = ("M1_0.8", "M1_0.9")                   # 피치 기동 (κ_f 는 M1·J_q 로 정의됨)
ALT = 14000.0
OUT = os.path.join(REPO, "results", "paper", "model_probe")


def build_jobs():
    out = []
    for cname, model, env, sigma in CELLS:
        for kcas in KCAS:
            for man in MANS:
                for k in KAPPAS:
                    out.append({"cell": cname, "model": model, "envelope": env,
                                "fbw": 0, "alt_ft": ALT, "kcas": kcas, "man": man,
                                "kp": 1.0, "kq": 1.0, "kr": 1.0, "filt": 25.0,
                                "lam_p": 1.0, "lam_q": k, "lam_r": 1.0,
                                "sigma": sigma, "seed": 20260930, "lam": k})
    return out


def job_fn(job):
    from l3_indi.evaluate import evaluate
    return evaluate(job)


def boundaries(rows):
    """셀별 κ_s(과소추정 쪽 안정 경계)와 κ_f(J_q 2 배)의 블록 중앙값."""
    out = {}
    for cname, _, _, _ in CELLS:
        R = [r for r in rows if r["cell"] == cname]
        ks, kf, base_bad, excl = [], [], 0, 0
        for kcas in KCAS:
            for man in MANS:
                series = {float(r["lam"]): r for r in R
                          if r["kcas"] == kcas and r["man"] == man}
                base = series.get(1.0)
                if base is None or rq2.unstable(base):
                    base_bad += 1
                    continue
                if rq2.excluded(base):
                    excl += 1
                    continue
                v, st, _ = rq2.lam_s(series, "low")
                if st == "ok":
                    ks.append(v)
                v2, st2, _ = rq2.crossing(series, "J_q", rq2.THR_F, True, "high")
                if st2 == "ok":
                    kf.append(v2)
        med = lambda a: float(np.median(a)) if a else float("nan")
        out[cname] = {"kappa_s": med(ks), "n_s": len(ks),
                      "kappa_f": med(kf), "n_f": len(kf),
                      "base_unstable": base_bad, "base_excluded": excl}
    return out


def main(processes: int = 8) -> int:
    jobs = build_jobs()
    print(f"[probe] 셀 {len(CELLS)} × κ {len(KAPPAS)} × 운용점 {len(KCAS)} × 기동 {len(MANS)} "
          f"= {len(jobs)} 런, 프로세스 {processes}")
    t0 = time.perf_counter()
    ctx = mp.get_context("spawn")
    with ctx.Pool(min(processes, len(jobs))) as pool:
        rows = pool.map(job_fn, jobs, chunksize=2)
    print(f"[probe] {time.perf_counter() - t0:.0f} s")

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "runs.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, default=float)

    b = boundaries(rows)
    # RQ2 원 격자 값 (docs/RQ2_SUMMARY.md D2·D6) 과 A36 §5 의 ±50 % 판정
    REF_S, REF_F = 0.418, 8.35
    print()
    print("| 셀 | 기체 | 봉투 | σ | κ_s (블록) | 원본비 | κ_f (블록) | 원본비 | ±50% 안 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for cname, model, env, sigma in CELLS:
        r = b[cname]
        rs = r["kappa_s"] / REF_S if np.isfinite(r["kappa_s"]) else float("nan")
        rf = r["kappa_f"] / REF_F if np.isfinite(r["kappa_f"]) else float("nan")
        ok = (np.isfinite(rs) and 0.5 <= rs <= 1.5) and (np.isfinite(rf) and 0.5 <= rf <= 1.5)
        print(f"| {cname} | {model} | {env} | {sigma:g} | "
              f"{r['kappa_s']:.3f} ({r['n_s']}) | {rs:.2f}× | "
              f"{r['kappa_f']:.2f} ({r['n_f']}) | {rf:.2f}× | {'예' if ok else '**아니오**'} |")
    print()
    print(f"- 기준: RQ2 원 격자 κ_s = {REF_S}, κ_f = {REF_F} (docs/RQ2_SUMMARY.md D2·D6, FLCS on).")
    print("- 괄호는 판정된 블록 수(운용점 3 × 기동 2 = 최대 6).")
    print("- 판정 정의는 rq2.unstable / rq2.lam_s / rq2.crossing 을 그대로 썼다(개정 A19).")
    for cname, *_ in CELLS:
        r = b[cname]
        if r["base_unstable"] or r["base_excluded"]:
            print(f"- {cname}: κ=1 이 불안정한 블록 {r['base_unstable']}, 제외된 블록 {r['base_excluded']}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--processes", type=int, default=8)
    raise SystemExit(main(ap.parse_args().processes))
