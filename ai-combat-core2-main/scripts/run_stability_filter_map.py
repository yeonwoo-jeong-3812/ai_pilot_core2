"""[3][4] 안정 경계의 filt_hz 의존성 정밀화 — k_scale x filt_hz 세밀 지도.

배경
----
results/stability_boundary_summary.csv(6x5=30조합)에서 안정 경계가 k_scale
1.6~1.8 사이에 있고 filt_hz 가 높을수록 왼쪽(낮은 이득)으로 밀린다는 게 확인됐다.
여기서는 격자를 촘촘히 해 경계선을 해상하고, 동시에 **안정성과 속응성의 맞교환**을
정량화한다.

격자
----
filt_hz : 10 / 12 / 15 / 20 / 25 / 30 / 40 / 50        (8수준)
k_scale : 1.0 / 1.4 / 1.5 / 1.6 / 1.7 / 1.8 / 1.9 / 2.0 / 2.2 / 2.5   (10수준)
          -> 요청 격자는 1.4 부터지만 **k_scale=1.0 을 기준선으로 함께 돌린다**.
             3구간 분류가 "같은 filt_hz 의 최저 이득 대비 배수" 로 정의돼 있어
             기준 행이 격자 안에 있어야 stability_boundary 와 같은 척도가 된다.
g_target: 5.0 고정
나머지(고도 15000ft / 400KCAS / 80도 뱅크 지속선회 / 12초)는
run_corner_pull_sweep.py 와 100% 동일 — 같은 run_one 을 그대로 import 해서 쓴다.

기록
----
· oscillating 플래그 및 리밋사이클 지표 (sweep_diagnostics.oscillation_metrics)
· 3구간 분류 band (sweep_diagnostics.classify_band)
· **지연시간** lag_q_s — 피치레이트 명령(omega_sp_q)과 실제(omega_q)의 상호상관
  최대점. 안정/열화 케이스에서만 의미가 있다(불안정 케이스는 명령-응답 관계가
  깨져 있어 lag_valid 로 구분해 기록만 한다).

사용
----
  python scripts/run_stability_filter_map.py
  python scripts/run_stability_filter_map.py --quick
출력: results/stability_filter_map.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_corner_pull_sweep import run_one, DT, SUMMARY_HEADER   # 물리 루프 100% 재사용
from sweep_diagnostics import xcorr_lag_s, classify_band, BAND_KO, BAND_ORDER

# Windows 콘솔(cp949)에서 한글/em-dash 출력이 죽지 않게 — 파일 출력은 항상 UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

G_TARGET = 5.0
FILT_HZ_GRID = (10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0)
K_SCALE_GRID = (1.0, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.2, 2.5)
K_REF = 1.0                      # 3구간 분류의 기준 이득

# run_corner_pull_sweep.TS_HEADER 상의 열 위치
COL_T, COL_SP_Q, COL_Q = 4, 6, 9

OUT_HEADER = SUMMARY_HEADER + [
    "lag_q_s", "xcorr_peak_q", "lag_valid",
    "rho_overshoot", "rho_settle", "rho_rms_track", "ref_k_scale", "band", "band_ko",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true",
                     help="filt_hz 2수준 x k_scale 3수준 동작확인")
    ap.add_argument("--out", default=os.path.join(REPO_ROOT, "results",
                                                   "stability_filter_map.csv"))
    args = ap.parse_args()

    filt_grid = FILT_HZ_GRID[:2] if args.quick else FILT_HZ_GRID
    k_grid = (K_REF, 1.6, 2.0) if args.quick else K_SCALE_GRID

    combos = [(f, k) for f in filt_grid for k in k_grid]
    print(f"[stability_filter_map] {len(combos)} combos "
          f"(filt_hz {len(filt_grid)} x k_scale {len(k_grid)}), g_target={G_TARGET:g}")

    t_start = time.perf_counter()
    rows = []
    for i, (filt_hz, k_scale) in enumerate(combos, 1):
        ts, summary = run_one(G_TARGET, k_scale, filt_hz)
        arr = np.asarray([[r[COL_T], r[COL_SP_Q], r[COL_Q]] for r in ts], float)
        lag = xcorr_lag_s(arr[:, 1], arr[:, 2], DT, max_lag_s=1.0)
        summary["lag_q_s"] = lag["lag_s"]
        summary["xcorr_peak_q"] = lag["xcorr_peak"]
        summary["lag_valid"] = lag["lag_valid"]
        rows.append(summary)
        print(f"  [{i}/{len(combos)}] f={filt_hz:<5g} k={k_scale:<5g} "
              f"settle={summary['settle_time_s']:>6.3f}s "
              f"overshoot={summary['overshoot_g']:>7.3f}G "
              f"osc={summary['oscillating']} "
              f"lag={summary['lag_q_s'] if summary['lag_valid'] else float('nan'):>7.4f}s "
              f"({summary['wall_time_s']:.2f}s)")

    # --- 3구간 분류: 같은 filt_hz 의 k_scale=K_REF 를 기준으로 ---
    ref = {r["filt_hz"]: r for r in rows if r["k_scale"] == K_REF}
    counts = {b: 0 for b in BAND_ORDER}
    for r in rows:
        R = ref[r["filt_hz"]]
        band, ratios = classify_band(r["overshoot_g"], r["settle_time_s"],
                                      r["rms_q_tracking_dps"],
                                      (R["overshoot_g"], R["settle_time_s"],
                                       R["rms_q_tracking_dps"]),
                                      r["oscillating"], r["g_exceeded"])
        r.update(ratios)
        r["ref_k_scale"] = K_REF
        r["band"] = band
        r["band_ko"] = BAND_KO[band]
        counts[band] += 1

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=OUT_HEADER)
        w.writeheader()
        w.writerows(rows)

    elapsed = time.perf_counter() - t_start
    print(f"\n[stability_filter_map] {len(combos)} combos in {elapsed:.1f}s -> " +
          ", ".join(f"{BAND_KO[b]} {counts[b]}" for b in BAND_ORDER))

    idx = {(r["filt_hz"], r["k_scale"]): r for r in rows}
    mark = {"stable": " S ", "degraded": " D ", "unstable": " X "}

    print("\n=== 구간 지도  (S=안정  D=열화  X=불안정) ===")
    print("filt_hz \\ k  " + "".join(f"{k:>6g}" for k in k_grid))
    for fz in filt_grid:
        print(f"{fz:>11g}  " + "".join(f"{mark[idx[(fz,k)]['band']]:>6}" for k in k_grid))

    print("\n=== 안정 경계 (마지막 '안정' k_scale / 첫 '불안정' k_scale) ===")
    print(f"{'filt_hz':>8}{'last_stable_k':>15}{'first_degraded_k':>18}{'first_unstable_k':>18}")
    for fz in filt_grid:
        ks = [k for k in k_grid]
        last_s = max([k for k in ks if idx[(fz, k)]["band"] == "stable"], default=None)
        first_d = min([k for k in ks if idx[(fz, k)]["band"] == "degraded"], default=None)
        first_u = min([k for k in ks if idx[(fz, k)]["band"] == "unstable"], default=None)
        print(f"{fz:>8g}{str(last_s):>15}{str(first_d):>18}{str(first_u):>18}")

    print("\n=== 지연시간 lag_q [ms] — 안정/열화 구간만 (맞교환 정량화) ===")
    print("filt_hz \\ k  " + "".join(f"{k:>8g}" for k in k_grid))
    for fz in filt_grid:
        line = f"{fz:>11g}  "
        for k in k_grid:
            r = idx[(fz, k)]
            line += (f"{1000*r['lag_q_s']:>8.1f}" if r["band"] != "unstable"
                     and r["lag_valid"] else f"{'-':>8}")
        print(line)

    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
