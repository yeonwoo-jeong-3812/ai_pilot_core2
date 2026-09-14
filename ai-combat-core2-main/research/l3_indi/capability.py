"""조건별 능력표 — 개정 A6 의 측정 방법을 그대로 구현한다.

조건마다 트림 직후 t = 0 부터 3.0 s 씩 6가지 시험:
  nz_open        엘리베이터 명령 −1.0 고정(에일러론·러더 0), 피크 Nz (α>30°·KCAS<150 이전)
  nz_closed      배치 INDI, 뱅크 0 유지 + Nz 9.0 지령, 피크 Nz
  roll_open±     에일러론 명령 ±1.0 고정(엘리베이터 트림 유지), 지령 방향 롤율 피크
  roll_closed±   배치 INDI, 매 L2 틱 dphi = ±120°, q_cmd = 0, 지령 방향 롤율 피크
C_nz = min(max(nz_open, nz_closed), 9.0),  C_p± = max(open±, closed±),  C_p = min(C_p+, C_p−)

사용: python research/l3_indi/capability.py [--quick]
출력: results/paper/capability/<commit10>/{runs.csv, manifest.json, jobs.json}
      + research/l3_indi/reports/capability_<commit10>.csv (표만, 추적용)
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import build, Condition, DT, L15_DIV, gcmd, state_view, REPO   # noqa: E402

ALTS_KFT = (8, 10, 12, 14, 16, 18, 20, 22, 24)
KCAS = (200, 250, 300, 350, 400, 450, 500)
T_TEST = 3.0
ALPHA_LIMIT_DEG = 30.0
KCAS_FLOOR = 150.0
G_STRUCT = 9.0


def _valid_until(alpha_deg, kcas):
    """α>30° 또는 KCAS<150 이 처음 나타나기 전까지의 마스크 (개정 A6)."""
    bad = (alpha_deg > ALPHA_LIMIT_DEG) | (kcas < KCAS_FLOOR)
    idx = np.nonzero(bad)[0]
    m = np.ones(len(alpha_deg), bool)
    if len(idx):
        m[idx[0]:] = False
    return m, bool(len(idx))


def _open_loop(cond, elevator=None, aileron=None):
    with contextlib.redirect_stdout(io.StringIO()):
        rig = build(cond)
    P = rig.plant
    trim = {"nz": P["accelerations/Nz"], "p": np.rad2deg(P["velocities/p-rad_sec"]),
            "q": np.rad2deg(P["velocities/q-rad_sec"]), "alpha": np.rad2deg(P["aero/alpha-rad"])}
    u0 = list(P.get_input())                      # [thr, ele, ail, rud]
    n = int(round(T_TEST / DT))
    rec = {k: np.zeros(n) for k in ("nz", "p", "alpha", "kcas", "t")}
    for k in range(n):
        u = [1.0, u0[1] if elevator is None else elevator, 0.0 if aileron is None else aileron, 0.0]
        P.set_input(u)
        P.step(1)
        rec["nz"][k] = P["accelerations/Nz"]
        rec["p"][k] = np.rad2deg(P["velocities/p-rad_sec"])
        rec["alpha"][k] = np.rad2deg(P["aero/alpha-rad"])
        rec["kcas"][k] = P["velocities/vc-kts"]
        rec["t"][k] = (k + 1) * DT
    return rec, trim


class _CapPull:
    duration_s = T_TEST
    per_tick = False

    def command(self, t, k, st):
        return gcmd(0.0 - st["phi"], 9.0, st)


class _CapRoll:
    duration_s = T_TEST
    per_tick = False

    def __init__(self, sign):
        self.sign = sign

    def command(self, t, k, st):
        g = gcmd(self.sign * np.deg2rad(120.0), 0.0, st)
        g.q_cmd = 0.0
        return g


def _closed_loop(cond, maneuver):
    from l3_indi.harness import run
    with contextlib.redirect_stdout(io.StringIO()):
        rig = build(cond)
        ts = run(rig, maneuver)
    return {"nz": ts["nz"], "p": np.rad2deg(ts["p"]), "alpha": np.rad2deg(ts["alpha"]),
            "kcas": ts["kcas"], "t": ts["t"], "sp_p": np.rad2deg(ts["sp_p"])}


def _peak(rec, key, sign=1.0):
    m, cut = _valid_until(rec["alpha"], rec["kcas"])
    x = sign * rec[key][m]
    if len(x) == 0:
        return float("nan"), float("nan"), cut
    i = int(np.argmax(x))
    return float(x[i]), float(rec["t"][m][i]), cut


def measure(job: dict) -> dict:
    cond = Condition(alt_ft=job["alt_kft"] * 1000.0, kcas=float(job["kcas"]), fbw_override=job["fbw"])
    row = {"alt_kft": job["alt_kft"], "kcas": job["kcas"], "fbw_override": job["fbw"]}

    rec, trim = _open_loop(cond, elevator=-1.0)
    row.update({"trim_nz": trim["nz"], "trim_p_dps": trim["p"], "trim_q_dps": trim["q"],
                "trim_alpha_deg": trim["alpha"]})
    row["trim_valid"] = int(abs(trim["nz"] - 1.0) <= 0.1 and abs(trim["p"]) <= 1.0 and abs(trim["q"]) <= 1.0)
    row["nz_open"], row["nz_open_t"], row["nz_open_cut"] = _peak(rec, "nz")
    row["nz_open_alpha_at_peak"] = float(rec["alpha"][int(np.argmin(np.abs(rec["t"] - row["nz_open_t"])))]) \
        if np.isfinite(row["nz_open_t"]) else float("nan")

    rec = _closed_loop(cond, _CapPull())
    row["nz_closed"], row["nz_closed_t"], row["nz_closed_cut"] = _peak(rec, "nz")
    row["C_nz"] = float(min(np.nanmax([row["nz_open"], row["nz_closed"]]), G_STRUCT))

    for sgn, tag in ((1.0, "pos"), (-1.0, "neg")):
        rec, _ = _open_loop(cond, aileron=sgn)
        row[f"roll_open_{tag}"], row[f"roll_open_{tag}_t"], row[f"roll_open_{tag}_cut"] = _peak(rec, "p", sgn)
        rec = _closed_loop(cond, _CapRoll(sgn))
        row[f"roll_closed_{tag}"], row[f"roll_closed_{tag}_t"], row[f"roll_closed_{tag}_cut"] = _peak(rec, "p", sgn)
        row[f"roll_closed_{tag}_sp_max"] = float(np.nanmax(sgn * rec["sp_p"]))
        row[f"C_p_{tag}"] = float(np.nanmax([row[f"roll_open_{tag}"], row[f"roll_closed_{tag}"]]))
    row["C_p"] = float(min(row["C_p_pos"], row["C_p_neg"]))
    return row


def jobs(quick=False):
    alts = (16,) if quick else ALTS_KFT
    ks = (400,) if quick else KCAS
    return [{"alt_kft": a, "kcas": k, "fbw": f} for f in (0, 1) for a in alts for k in ks]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args()
    from l3_indi.runner import run_experiment
    out = run_experiment("capability" + ("_quick" if args.quick else ""), jobs(args.quick), measure,
                         os.path.join(REPO, "results", "paper"), allow_dirty=args.allow_dirty)
    print("->", out)
    rows = list(csv.DictReader(open(os.path.join(out, "runs.csv"), encoding="utf-8")))
    if not args.quick:
        rep = os.path.join(HERE, "reports")
        os.makedirs(rep, exist_ok=True)
        dst = os.path.join(rep, f"capability_{os.path.basename(out)}.csv")
        cols = ["fbw_override", "alt_kft", "kcas", "trim_valid", "C_nz", "nz_open", "nz_closed",
                "C_p", "C_p_pos", "C_p_neg", "roll_open_pos", "roll_closed_pos", "roll_open_neg",
                "roll_closed_neg", "roll_closed_pos_sp_max", "nz_open_cut", "nz_closed_cut"]
        rows.sort(key=lambda r: (int(r["fbw_override"]), int(r["alt_kft"]), int(r["kcas"])))
        with open(dst, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print("->", dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
