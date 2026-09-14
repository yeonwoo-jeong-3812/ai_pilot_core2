"""[2] 안정/열화/불안정 3구간 재분류 — 기존 스윕 summary.csv 를 그대로 재판정.

시뮬레이션을 다시 돌리지 않는다. 이미 있는 summary.csv 의 컬럼만 써서
sweep_diagnostics.classify_band 로 3구간을 붙인다(기준·근거는 그 모듈 주석 참조).

기준값(ref)은 **같은 filt_hz 안에서 k_scale 이 가장 작은 조합**을 쓴다. filt_hz
자체가 기준선을 28% 움직이므로(absolute 임계를 쓰면 필터 효과가 판정에 섞인다)
필터를 고정하고 이득만 올렸을 때의 악화 배수(rho)로 판정한다.

사용
----
  python scripts/classify_stability_bands.py                       # stability_boundary
  python scripts/classify_stability_bands.py --in <summary.csv> --out <out.csv>
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep_diagnostics import classify_band, BAND_KO, BAND_ORDER, BAND_RATIO_THRESH

# Windows 콘솔(cp949)에서 한글/em-dash 출력이 죽지 않게 — 파일 출력은 항상 UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# (overshoot, settle, rms_tracking) 컬럼명 — corner_pull 계열 / indi_step 계열
COLSETS = [
    ("overshoot_g", "settle_time_s", "rms_q_tracking_dps"),
    ("overshoot_deg", "settle_time_s", "rms_total_dps"),
]


def pick_cols(fieldnames):
    for cs in COLSETS:
        if all(c in fieldnames for c in cs):
            return cs
    raise SystemExit(f"지표 컬럼을 못 찾음. 있는 컬럼: {fieldnames}")


def classify_file(in_path: str, out_path: str, thresh: float = BAND_RATIO_THRESH):
    with open(in_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"빈 파일: {in_path}")
    c_os, c_st, c_rms = pick_cols(rows[0].keys())

    # filt_hz 별 최저 k_scale 행을 기준으로
    ref_row = {}
    for r in rows:
        f_hz = r["filt_hz"]
        if f_hz not in ref_row or float(r["k_scale"]) < float(ref_row[f_hz]["k_scale"]):
            ref_row[f_hz] = r

    out_rows = []
    counts = Counter()
    for r in rows:
        R = ref_row[r["filt_hz"]]
        ref = (R[c_os], R[c_st], R[c_rms])
        band, ratios = classify_band(r[c_os], r[c_st], r[c_rms], ref,
                                      r.get("oscillating", 0), r.get("g_exceeded", 0),
                                      thresh=thresh)
        out = dict(r)
        out.update(ratios)
        out["ref_k_scale"] = R["k_scale"]
        out["band"] = band
        out["band_ko"] = BAND_KO[band]
        out_rows.append(out)
        counts[band] += 1

    fields = list(rows[0].keys()) + ["rho_overshoot", "rho_settle", "rho_rms_track",
                                      "ref_k_scale", "band", "band_ko"]
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    return out_rows, counts, (c_os, c_st, c_rms)


def print_map(rows):
    """filt_hz(행) x k_scale(열) 구간 지도."""
    ks = sorted({float(r["k_scale"]) for r in rows})
    fs = sorted({float(r["filt_hz"]) for r in rows})
    cell = {(float(r["filt_hz"]), float(r["k_scale"])): r["band"] for r in rows}
    mark = {"stable": " S ", "degraded": " D ", "unstable": " X "}
    print("\n구간 지도  (S=안정  D=열화  X=불안정)")
    print("filt_hz \ k_scale " + "".join(f"{k:>6g}" for k in ks))
    for fz in fs:
        print(f"{fz:>14g}    " + "".join(f"{mark.get(cell.get((fz,k)),' . '):>6}" for k in ks))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_path",
                     default=os.path.join(REPO_ROOT, "results", "stability_boundary_summary.csv"))
    ap.add_argument("--out", dest="out_path", default=None)
    ap.add_argument("--thresh", type=float, default=BAND_RATIO_THRESH)
    args = ap.parse_args()

    out_path = args.out_path or args.in_path.replace(".csv", "_classified.csv")
    rows, counts, cols = classify_file(args.in_path, out_path, args.thresh)

    print(f"[classify] {args.in_path}")
    print(f"[classify] 지표: overshoot={cols[0]}  settle={cols[1]}  tracking={cols[2]}"
          f"  (임계 rho>{args.thresh:g})")
    print(f"[classify] {len(rows)} 조합 -> " +
          ", ".join(f"{BAND_KO[b]} {counts[b]}" for b in BAND_ORDER))

    w = max(len(r["run_id"]) for r in rows)
    print(f"\n{'run_id':<{w}} {'band':>9} {'rho_os':>8} {'rho_st':>8} {'rho_rms':>8} {'osc':>4} {'gexc':>5}")
    for r in rows:
        print(f"{r['run_id']:<{w}} {r['band']:>9} {r['rho_overshoot']:>8.2f} "
              f"{r['rho_settle']:>8.2f} {r['rho_rms_track']:>8.2f} "
              f"{r.get('oscillating',''):>4} {r.get('g_exceeded',''):>5}")
    print_map(rows)
    print(f"\n-> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
