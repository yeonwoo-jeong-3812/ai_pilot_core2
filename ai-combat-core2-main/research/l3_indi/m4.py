"""M4 주파수응답 — 개정 A11-7·A14-5.

사용: python research/l3_indi/m4.py <RQ1 분석 폴더 (tuned.json)>
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO            # noqa: E402

WINDOW = (6.0, 21.0)


def bandwidth_3db(freqs, gains_db) -> float:
    for i in range(len(freqs)):
        if gains_db[i] < -3.0:
            if i == 0:
                return float(freqs[0])
            f0, f1, g0, g1 = np.log(freqs[i - 1]), np.log(freqs[i]), gains_db[i - 1], gains_db[i]
            return float(np.exp(f0 + (-3.0 - g0) * (f1 - f0) / (g1 - g0)))
    return float("inf")


def phase_at_1hz(freqs, phases_deg) -> float:
    ph = np.rad2deg(np.unwrap(np.deg2rad(np.asarray(phases_deg, float))))
    i = list(freqs).index(0.8)
    f0, f1 = np.log(0.8), np.log(1.2)
    return float(ph[i] + (ph[i + 1] - ph[i]) * (np.log(1.0) - f0) / (f1 - f0))


def job_fn(job):
    from l3_indi.harness import build, run, Condition, Params, DT
    from l3_indi.maneuvers import M4Multisine
    from l3_indi import metrics as M
    cond = Condition(job["alt_ft"], job["kcas"])
    man = M4Multisine(axis=job["axis"])
    with contextlib.redirect_stdout(io.StringIO()):
        rig = build(cond, Params(k_scale=(job["kp"], job["kq"], job["kr"]), filt_hz=25.0))
        ts = run(rig, man)
    fr = M.freq_response(ts, job["axis"], man.freqs_hz, WINDOW, DT)
    freqs = sorted(fr)
    g = [fr[f][0] for f in freqs]
    p = [fr[f][1] for f in freqs]
    row = dict(job)
    row.update({f"gain_db_{f:g}": fr[f][0] for f in freqs})
    row.update({f"phase_deg_{f:g}": fr[f][1] for f in freqs})
    row["bw_3db_hz"] = bandwidth_3db(freqs, g)
    row["phase_1hz_deg"] = phase_at_1hz(freqs, p)
    row.update(M.oscillation(ts, DT))
    row["departure"] = M.departure(ts)
    return row


def main():
    tuned = json.load(open(os.path.join(sys.argv[1], "tuned.json"), encoding="utf-8"))["tuned"]
    from l3_indi.design import rq1_conditions
    from l3_indi.runner import run_experiment
    gains = {"base": (1.0, 1.0, 1.0), "tuned": tuple(tuned[:3])}
    js = []
    for cond in rq1_conditions(0):
        for axis in ("p", "q"):
            for gname, k in gains.items():
                js.append({"alt_ft": cond.alt_ft, "kcas": cond.kcas, "axis": axis, "gain": gname,
                           "kp": k[0], "kq": k[1], "kr": k[2]})
    out = run_experiment("m4", js, job_fn, os.path.join(REPO, "results", "paper"))
    import csv
    rows = list(csv.DictReader(open(os.path.join(out, "runs.csv"), encoding="utf-8")))
    commit = os.path.basename(os.path.normpath(out))
    L = [f"# M4 주파수응답 — 실험 커밋 {commit}\n",
         f"- FLCS on, 무잡음, filt 25 Hz, 멀티사인 피크 10 deg/s, 창 {WINDOW} s. 규칙: 개정 A14-5. 튜닝 k = {tuple(tuned[:3])}\n",
         "| 조건 | 축 | 게인 | −3 dB 대역폭 [Hz] | 1 Hz 위상 [deg] | 불안정 | 이탈 |", "|---|---|---|---|---|---|---|"]
    rows.sort(key=lambda r: (float(r["alt_ft"]), float(r["kcas"]), r["axis"], r["gain"]))
    for r in rows:
        bw = float(r["bw_3db_hz"])
        L.append(f"| {int(float(r['alt_ft'])/1000)}k/{int(float(r['kcas']))} | {r['axis']} | {r['gain']} | "
                 f"{'> 5' if not np.isfinite(bw) else f'{bw:.2f}'} | {float(r['phase_1hz_deg']):.1f} | "
                 f"{r['oscillating']} | {r['departure']} |")
    rep = os.path.join(HERE, "reports", f"M4_{commit}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", out, rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
