"""런 1개 → 사전등록 지표 한 행. RQ1 / RQ1-N / RQ2 / 지연 실험이 같이 쓴다.

지표 정의: PREREGISTRATION §3·§4·§7·§8, 개정 A9·A10·A12·A13. 3구간 판정(기준 런 대비 비율)은 행을 모은 뒤
분석 단계(`analysis.py`)에서 한다 — 기준 런이 같은 실험 안에 있어야 하기 때문이다.
"""
from __future__ import annotations

import contextlib
import io
import os

import numpy as np

from . import metrics as M
from .design import capability
from .harness import build, run, Condition, Params, Uncertainty, DT, TRUTH_COLS
from .maneuvers import paper_maneuvers

M2_REVERSAL = (4.0, 7.0, -60.0)       # 개정 A13-1: 반전 구간과 목표
M3_BANK_DEG = 70.0


def maneuver_by_name(name: str, cap: dict):
    for m in paper_maneuvers(cap["C_nz"], cap["C_p"]):
        if m.name == name:
            return m
    raise KeyError(name)


def evaluate(job: dict, ts_dir: str | None = None) -> dict:
    """job: fbw, alt_ft, kcas, man, kp, kq, kr, filt, (선택) lam_p/lam_q/lam_r, sigma, seed, delay_n, sync."""
    cond = Condition(float(job["alt_ft"]), float(job["kcas"]), fbw_override=int(job["fbw"]))
    cap = capability(cond)
    man = maneuver_by_name(job["man"], cap)
    params = Params(k_scale=(float(job["kp"]), float(job["kq"]), float(job["kr"])), filt_hz=float(job["filt"]))
    unc = Uncertainty(g0_row_scale=(float(job.get("lam_p", 1.0)), float(job.get("lam_q", 1.0)),
                                    float(job.get("lam_r", 1.0))),
                      gyro_sigma_dps=float(job.get("sigma", 0.0)), seed=int(job.get("seed", 0)),
                      meas_delay_steps=int(job.get("delay_n", 0)), sync_act_delay=bool(job.get("sync", False)))
    with contextlib.redirect_stdout(io.StringIO()):
        rig = build(cond, params, unc)
        ts = run(rig, man)

    w = man.window()
    row = {k: v for k, v in job.items() if not k.startswith("_")}
    row["C_nz"], row["C_p"] = cap["C_nz"], cap["C_p"]
    row["departure"] = M.departure(ts)
    row.update(M.envelope(ts))
    row.update(M.oscillation(ts, DT))
    tail = ts["t"] >= ts["t"][-1] - 3.0                       # 개정 A19-10: 진동 주파수
    rates = {a: np.rad2deg(ts[a][tail]) for a in "pqr"}
    ax = max(rates, key=lambda a: np.ptp(rates[a]))
    x = (rates[ax] - rates[ax].mean()) * np.hanning(tail.sum())
    spec = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(tail.sum(), DT)
    row["osc_freq_hz"] = float(freqs[1 + int(np.argmax(spec[1:]))]) if len(spec) > 1 else float("nan")
    row["osc_freq_axis"] = ax
    row["capability_limited"] = M.capability_limited(ts, w, cap["C_p"])
    row.update(M.saturation(ts, w))
    for a in "pqr":
        row[f"J_{a}"] = M.tracking_J(ts, a, w)
    row.update(M.tss_residual(ts, w, rig.G0_true, rig.qbar_ref))
    row["nz_exceeds_cap"] = M.nz_exceeds_cap(ts, w, cap["C_nz"])

    name = job["man"]
    if name.startswith("M1") or name.startswith("M3"):
        target = man.nz_target
        nzm = M.nz_metrics(ts, w, target)
        row["nz_target"] = target
        row["nz_realization"] = nzm["nz_realization"]
        row["nz_rise_s"] = nzm["nz_rise_s"]
        row["nz_overshoot"] = nzm["nz_overshoot"]
        row["nz_settle_s"] = M.nz_settle(ts, w, target)
    if name.startswith("M1"):
        k3 = int(round(man.pull_start_s / DT)) - 1
        row["bank_pre_unsettled"] = int(abs(float(np.rad2deg(ts["phi"][k3])) - man.bank_deg) > 2.0)
    if name.startswith("M2"):
        b = M.bank_metrics(ts, M2_REVERSAL[0], M2_REVERSAL[1], M2_REVERSAL[2])
        row["bank_overshoot_deg"], row["bank_settle_s"], row["bank_reach_s"] = (
            b["bank_overshoot_deg"], b["bank_settle_s"], b["bank_reach_s"])
    if name.startswith("M3"):
        b = M.bank_metrics(ts, w[0], w[1], M3_BANK_DEG)
        row["bank_overshoot_deg"], row["bank_settle_s"], row["bank_reach_s"] = (
            b["bank_overshoot_deg"], b["bank_settle_s"], b["bank_reach_s"])
    row["unsettled"] = int(any(k in row and not np.isfinite(row[k]) for k in ("nz_settle_s", "bank_settle_s")))

    if ts_dir is not None:
        os.makedirs(ts_dir, exist_ok=True)
        fn = "__".join(f"{k}={job[k]}" for k in sorted(job) if not k.startswith("_")) + ".npz"
        np.savez_compressed(os.path.join(ts_dir, fn), **{c: ts[c] for c in TRUTH_COLS},
                            G0_true=rig.G0_true, qbar_ref=rig.qbar_ref)
    return row
