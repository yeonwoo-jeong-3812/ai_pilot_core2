"""개정 A36 §5-2단계(a) — 자이로 잡음이 진동 판정기를 잘못 건드리는 범위.

1 단계에서 250 KCAS · M1_0.8 이 σ 0.1 · κ=1 에서 불안정으로 판정됐다(진동 플래그만 1).
그 조건 하나의 우연인지 저속 전반의 패턴인지 본다.

판정: σ 0 에서 안정인데 σ 0.1 에서 **진동 플래그만** 켜지는(봉투 초과 0, 이탈 0) 블록을 센다.
저속(≤ 300 KCAS) 비율이 고속(≥ 350 KCAS)보다 높으면 "저속 패턴", 아니면 "단일 조건의 우연".

사용: python research/l3_indi/osc_probe.py [--processes 8]
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi import rq2                                   # noqa: E402
from l3_indi.model_probe import job_fn                    # noqa: E402

KCAS = (200.0, 250.0, 300.0, 350.0, 400.0, 450.0)
MANS = ("M1_0.7", "M1_0.8", "M1_0.9", "M2a", "M3_0.7", "M3_0.9")
SIGMAS = (0.0, 0.1)
ALT = 14000.0


def build_jobs():
    return [{"cell": f"s{sig:g}", "model": "f16fix", "envelope": "manual",
             "fbw": 0, "alt_ft": ALT, "kcas": kcas, "man": man,
             "kp": 1.0, "kq": 1.0, "kr": 1.0, "filt": 25.0,
             "lam_p": 1.0, "lam_q": 1.0, "lam_r": 1.0,
             "sigma": sig, "seed": 20260930, "lam": 1.0}
            for sig in SIGMAS for kcas in KCAS for man in MANS]


def main(processes: int = 8) -> int:
    jobs = build_jobs()
    print(f"[osc] 운용점 {len(KCAS)} × 기동 {len(MANS)} × σ {len(SIGMAS)} = {len(jobs)} 런")
    with mp.get_context("spawn").Pool(min(processes, len(jobs))) as pool:
        rows = pool.map(job_fn, jobs, chunksize=2)
    idx = {(r["cell"], r["kcas"], r["man"]): r for r in rows}

    only_osc = lambda r: (r["oscillating"] >= 1 and r["g_exceeded"] < 1 and r["departure"] < 1)
    print()
    print("| KCAS | " + " | ".join(MANS) + " | 오판정 |")
    print("|---" * (len(MANS) + 2) + "|")
    flip = {}
    for kcas in KCAS:
        cells, n = [], 0
        for man in MANS:
            a, b = idx[("s0", kcas, man)], idx[("s0.1", kcas, man)]
            if rq2.unstable(a):
                cells.append("σ0도 불안정")
            elif only_osc(b):
                cells.append("**진동만**"); n += 1
            elif rq2.unstable(b):
                cells.append("봉투/이탈")
            else:
                cells.append("안정")
        flip[kcas] = n
        print(f"| {kcas:g} | " + " | ".join(cells) + f" | {n}/{len(MANS)} |")

    lo = [k for k in KCAS if k <= 300]
    hi = [k for k in KCAS if k >= 350]
    rlo = sum(flip[k] for k in lo) / (len(lo) * len(MANS))
    rhi = sum(flip[k] for k in hi) / (len(hi) * len(MANS))
    print()
    print(f"- 저속(≤ 300 KCAS) 오판정 비율 **{100*rlo:.1f}%** ({sum(flip[k] for k in lo)}/{len(lo)*len(MANS)})")
    print(f"- 고속(≥ 350 KCAS) 오판정 비율 **{100*rhi:.1f}%** ({sum(flip[k] for k in hi)}/{len(hi)*len(MANS)})")
    print(f"- 판정: **{'저속 패턴' if rlo > rhi else '저속 패턴 아님'}**")
    print()
    print("| KCAS | 기동 | σ0 J_q | σ0.1 J_q | σ0.1 진동주파수 [Hz] | 축 |")
    print("|---|---|---|---|---|---|")
    for kcas in KCAS:
        for man in MANS:
            b = idx[("s0.1", kcas, man)]
            if only_osc(b):
                a = idx[("s0", kcas, man)]
                print(f"| {kcas:g} | {man} | {a['J_q']:.4f} | {b['J_q']:.4f} | "
                      f"{b['osc_freq_hz']:.2f} | {b['osc_freq_axis']} |")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--processes", type=int, default=8)
    raise SystemExit(main(ap.parse_args().processes))
