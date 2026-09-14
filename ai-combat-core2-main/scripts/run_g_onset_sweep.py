"""[5] 순간 기동(G onset) 시험 — 3초 급당김에서 목표 G 에 도달하는가.

corner_pull 계열(12초 지속 선회)이 "유지할 수 있는 G" 를 보는 시험이라면, 이건
**순간 봉투** 시험이다. 3초 안에 목표 G 까지 얼마나 빨리 도달하는지, 그리고
9G 가 실제로 도달 가능한지를 본다.

지속 시험과 다른 점
-------------------
· t_total = 3.0초 (지속 시험 12초). 정상상태가 아니라 **상승 구간**이 전부다.
· 뱅크 스텝이 없다 — 순수 당김. 리프트벡터 배치 없이 q 축만 지령하므로 뱅크를
  걸었을 때의 요축 문제(러더 포화)가 섞이지 않는다.
· 스로틀 full AB — 3초 안에 속도 손실이 결과를 좌우하지 않게.
· 판정 지표가 settle/overshoot 가 아니라 **도달 여부 + 상승률(dG/dt)** 이다.
· **하중배수를 두 가지로 동시에 기록한다.** corner_pull 계열은 기구학 근사
    n_act = q*V/g + cos(phi)cos(theta)
  를 쓰는데, 이건 비행경로각이 기체와 같이 도는(gamma_dot = q - alpha_dot) 정상
  선회에서만 맞다. 3초 급당김은 alpha_dot 가 큰 구간이 전부라 이 근사가 과대
  평가할 수 있다. 그래서 JSBSim 이 직접 내는 accelerations/Nz 를 nz_jsb 로 같이
  기록하고 둘을 비교한다(nz_gap = n_act_peak - nz_peak). **도달 판정은 nz_jsb
  기준**이며 n_act 는 기존 실험과의 비교용으로만 남긴다.

지령
----
run_corner_pull_sweep.py 와 같은 방식으로 목표 G 를 pitch-rate 로 환산해 직접 지령:
    q_cmd = (min(g_target, g_allowed) - cos(phi)cos(theta)) * g / V
g_allowed = CombinedLimiter.max_load_factor(kcas) = min(9G, 공력한계(동압)).
즉 **리미터가 허용하는 순간 봉투 안에서** 목표 G 를 지령한다. 9G 목표가 도달
불가로 나온다면 그 원인이 (a) 리미터의 공력 상한, (b) 조종면 포화, (c) 응답
지연 중 어느 것인지 구분할 수 있도록 셋 다 기록한다.

격자
----
g_target : 3 / 5 / 7 / 9                    (4수준)
k_scale  : 0.5 / 0.75 / 1.0 / 1.5 / 2.0     (5수준)
filt_hz  : 10 / 15 / 25 / 35 / 50           (5수준)
조건     : 15000ft, 400 KCAS 및 450 KCAS    (--kcas)

사용
----
  python scripts/run_g_onset_sweep.py                  # 15000ft / 400KCAS
  python scripts/run_g_onset_sweep.py --kcas 450
  python scripts/run_g_onset_sweep.py --quick
출력: results/g_onset_sweep_15k<KCAS>/{timeseries,summary}.csv
      + results/g_onset_15k<KCAS>_summary.csv (요약 사본)
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
from aircombat.fdm.plant import F16Plant
from aircombat.control.indi import INDIRateController, identify_G0
from aircombat.control.attitude import QuaternionAttitudeShim, euler_to_quat, quat_mul
from aircombat.control.limiter import CombinedLimiter, LimiterConfig, G_FT_S2
from sweep_diagnostics import oscillation_metrics, envelope_violation, xcorr_lag_s

# Windows 콘솔(cp949)에서 한글/em-dash 출력이 죽지 않게 — 파일 출력은 항상 UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DT = 1.0 / 120.0
T_TOTAL = 3.0                 # 순간 기동 — 3초
ALT_FT = 15000.0
KCAS_DEFAULT = 400.0

K_RATE_BASE = (9.0, 9.0, 6.0)
G_TARGET_GRID = (3.0, 5.0, 7.0, 9.0)
K_SCALE_GRID = (0.5, 0.75, 1.0, 1.5, 2.0)
FILT_HZ_GRID = (10.0, 15.0, 25.0, 35.0, 50.0)
FILT_HZ_DEFAULT = 25.0

REACH_TOL = 0.95              # 목표의 95% 이상을 "도달" 로 본다

TS_HEADER = [
    "run_id", "g_target", "k_scale", "filt_hz", "kcas_ic", "t",
    "omega_sp_q_dps", "omega_q_dps", "n_act", "nz_jsb", "g_cmd", "g_allowed",
    "cmd_aileron", "cmd_elevator", "cmd_rudder",
    "alpha_deg", "qbar_psf", "kcas", "vt_fps",
    "q_limited", "q_max_dps",
]

SUMMARY_HEADER = [
    "run_id", "g_target", "k_scale", "filt_hz", "alt_ft", "kcas_ic",
    "k_rate_p", "k_rate_q", "k_rate_r",
    # --- 도달 (판정은 nz_jsb 기준) ---
    "nz_peak", "nz_final", "reached_target", "reach_frac",
    "t_to_90pct_s", "t_to_target_s",
    # --- 기구학 근사와의 비교 (기존 corner_pull 지표) ---
    "g_peak_kinematic", "g_final_kinematic", "nz_gap_peak",
    # --- 상승률 ---
    "onset_rate_max_gps", "onset_rate_10_90_gps", "t_10_90_s",
    # --- 왜 못 갔나 ---
    "g_allowed_mean", "g_allowed_min", "limiter_capped", "q_limited_pct",
    "sat_elevator_pct", "sat_any_pct", "max_alpha_deg",
    "kcas_final", "kcas_loss", "rms_q_tracking_dps", "lag_q_s", "lag_valid",
    # --- 건전성 ---
    "p2p_q_dps_last1s", "signchg_elev_hz", "oscillating",
    "g_exceeded", "max_g_exceed_pos",
    "n_steps", "wall_time_s",
]


def run_one(g_target: float, k_scale: float, filt_hz: float, kcas_ic: float,
            dt: float = DT, t_total: float = T_TOTAL):
    t0 = time.perf_counter()
    run_id = f"G{g_target:g}_k{k_scale:g}_f{filt_hz:g}"
    k_rate = tuple(k * k_scale for k in K_RATE_BASE)

    p = F16Plant(dt=dt)
    p.set_ic(alt_ft=ALT_FT, vc_kts=kcas_ic)
    p["fcs/throttle-cmd-norm"] = 1.0          # full AB — 3초 속도 손실 최소화
    p.trim()

    G0, qbar_ref = identify_G0(p.fdm)
    indi = INDIRateController(dt, G0, qbar_ref, k_rate=k_rate, filt_hz=filt_hz)
    indi.reset(u0=[p["fcs/aileron-cmd-norm"], p["fcs/elevator-cmd-norm"],
                   p["fcs/rudder-cmd-norm"]])
    shim = QuaternionAttitudeShim(k_att=4.0, k_yaw_damp=1.5,
                                  rate_limit_dps=(180.0, 60.0, 30.0))
    limiter = CombinedLimiter(LimiterConfig())
    phi_hold = p["attitude/phi-rad"]           # 순수 당김 — 현재 뱅크 유지

    n = int(t_total / dt)
    rows = []
    q_err2 = 0.0
    sat_count = np.zeros(3)
    sat_any_count = 0
    lim_q_count = 0
    g_allowed_sum = 0.0
    g_allowed_min = 1e9
    max_alpha = -1e9
    kcas_final = kcas_ic

    for k in range(n):
        t = k * dt
        phi, theta = p["attitude/phi-rad"], p["attitude/theta-rad"]
        psi = p["attitude/psi-rad"]
        pqr = np.array([p["velocities/p-rad_sec"], p["velocities/q-rad_sec"],
                        p["velocities/r-rad_sec"]])
        v_fps, kcas = p["velocities/vt-fps"], p["velocities/vc-kts"]
        g_lift = float(np.cos(phi) * np.cos(theta))

        g_allowed = limiter.max_load_factor(kcas)
        g_cmd = min(g_target, g_allowed)
        q_cmd = (g_cmd - g_lift) * G_FT_S2 / max(v_fps, 1.0)

        q_cur = euler_to_quat(phi, theta, psi)
        q_des = quat_mul(q_cur, euler_to_quat(phi_hold - phi, 0.0, 0.0))
        omega_sp = shim.rate_setpoint(q_cur, q_des, r_cur=pqr[2])
        omega_sp[1] = q_cmd
        omega_sp, flags = limiter.limit_omega_sp(omega_sp, v_fps, kcas, g_lift=g_lift)

        ang_acc = [p["accelerations/pdot-rad_sec2"], p["accelerations/qdot-rad_sec2"],
                   p["accelerations/rdot-rad_sec2"]]
        u = indi.update(pqr, omega_sp, p["aero/qbar-psf"], ang_accel=ang_acc)
        p.set_input([1.0, u[1], u[0], u[2]])
        p.step(1)

        q_act = p["velocities/q-rad_sec"]
        n_act = q_act * p["velocities/vt-fps"] / G_FT_S2 + g_lift   # 기구학 근사
        nz_jsb = float(p["accelerations/Nz"])                        # JSBSim 직접값
        alpha_deg = float(np.degrees(p["aero/alpha-rad"]))
        kcas_final = p["velocities/vc-kts"]

        rows.append([
            run_id, g_target, k_scale, filt_hz, kcas_ic, round(t, 6),
            round(float(np.rad2deg(omega_sp[1])), 6),
            round(float(np.rad2deg(pqr[1])), 6),
            round(float(n_act), 6), round(float(nz_jsb), 6),
            round(float(g_cmd), 6), round(float(g_allowed), 6),
            round(float(u[0]), 6), round(float(u[1]), 6), round(float(u[2]), 6),
            round(alpha_deg, 6), round(float(p["aero/qbar-psf"]), 6),
            round(float(kcas_final), 6), round(float(p["velocities/vt-fps"]), 6),
            flags["q_limited"], round(np.rad2deg(flags["q_max"]), 4),
        ])

        sat_now = np.abs(u) > 0.999
        sat_count += sat_now
        sat_any_count += int(np.any(sat_now))
        lim_q_count += int(flags["q_limited"])
        g_allowed_sum += g_allowed
        g_allowed_min = min(g_allowed_min, g_allowed)
        max_alpha = max(max_alpha, alpha_deg)
        q_err2 += (omega_sp[1] - q_act) ** 2

    # t, sp_q, q, n_act(기구학), nz(JSBSim)
    arr = np.asarray([[r[5], r[6], r[7], r[8], r[9]] for r in rows], float)
    t_arr, kin_arr, n_arr = arr[:, 0], arr[:, 3], arr[:, 4]

    g_peak = float(n_arr.max())              # 판정 기준 = JSBSim Nz
    g_final = float(n_arr[-1])
    kin_peak = float(kin_arr.max())
    reach_frac = g_peak / g_target
    reached = int(reach_frac >= REACH_TOL)

    def first_cross(level):
        idx = np.nonzero(n_arr >= level)[0]
        return float(t_arr[idx[0]]) if len(idx) else float("nan")

    n0 = float(n_arr[0])
    t90 = first_cross(0.90 * g_target)
    t_tgt = first_cross(g_target)
    t10 = first_cross(n0 + 0.10 * (g_target - n0))
    t90r = first_cross(n0 + 0.90 * (g_target - n0))
    rate_10_90 = ((0.80 * (g_target - n0)) / (t90r - t10)
                  if np.isfinite(t10) and np.isfinite(t90r) and t90r > t10 else float("nan"))
    dgdt = np.gradient(n_arr, DT)
    lag = xcorr_lag_s(arr[:, 1], arr[:, 2], DT, max_lag_s=0.5)

    osc = oscillation_metrics(t_arr, np.zeros(len(t_arr)), arr[:, 2],
                              np.zeros(len(t_arr)), n_arr,
                              [r[11] for r in rows], [r[12] for r in rows],
                              [r[13] for r in rows], window_s=1.0)
    env = envelope_violation(n_arr, DT)

    summary = {
        "run_id": run_id, "g_target": g_target, "k_scale": k_scale, "filt_hz": filt_hz,
        "alt_ft": ALT_FT, "kcas_ic": kcas_ic,
        "k_rate_p": k_rate[0], "k_rate_q": k_rate[1], "k_rate_r": k_rate[2],
        "nz_peak": round(g_peak, 4), "nz_final": round(g_final, 4),
        "g_peak_kinematic": round(kin_peak, 4),
        "g_final_kinematic": round(float(kin_arr[-1]), 4),
        "nz_gap_peak": round(kin_peak - g_peak, 4),
        "reached_target": reached, "reach_frac": round(reach_frac, 4),
        "t_to_90pct_s": round(t90, 4) if np.isfinite(t90) else "",
        "t_to_target_s": round(t_tgt, 4) if np.isfinite(t_tgt) else "",
        "onset_rate_max_gps": round(float(dgdt.max()), 4),
        "onset_rate_10_90_gps": round(rate_10_90, 4) if np.isfinite(rate_10_90) else "",
        "t_10_90_s": round(t90r - t10, 4) if np.isfinite(t10) and np.isfinite(t90r) else "",
        "g_allowed_mean": round(g_allowed_sum / n, 4),
        "g_allowed_min": round(g_allowed_min, 4),
        # 리미터가 목표를 잘랐는가 (공력 한계 < 목표 G)
        "limiter_capped": int(g_allowed_min < g_target - 1e-6),
        "q_limited_pct": round(100.0 * lim_q_count / n, 2),
        "sat_elevator_pct": round(100.0 * float(sat_count[1]) / n, 2),
        "sat_any_pct": round(100.0 * sat_any_count / n, 2),
        "max_alpha_deg": round(max_alpha, 4),
        "kcas_final": round(float(kcas_final), 3),
        "kcas_loss": round(float(kcas_ic - kcas_final), 3),
        "rms_q_tracking_dps": round(float(np.rad2deg(np.sqrt(q_err2 / n))), 4),
        "lag_q_s": lag["lag_s"], "lag_valid": lag["lag_valid"],
        "p2p_q_dps_last1s": osc["p2p_q_dps_last3s"],
        "signchg_elev_hz": osc["signchg_elev_hz"],
        "oscillating": osc["oscillating"],
        "g_exceeded": env["g_exceeded"], "max_g_exceed_pos": env["max_g_exceed_pos"],
        "n_steps": n, "wall_time_s": round(time.perf_counter() - t0, 3),
    }
    return rows, summary


def iter_grid(quick: bool):
    if quick:
        for g in (G_TARGET_GRID[0], G_TARGET_GRID[-1]):
            for k in K_SCALE_GRID[2:3]:
                yield g, k, FILT_HZ_DEFAULT
    else:
        for g in G_TARGET_GRID:
            for k in K_SCALE_GRID:
                for f in FILT_HZ_GRID:
                    yield g, k, f


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--kcas", type=float, default=KCAS_DEFAULT)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    tag = f"15k{args.kcas:g}"
    out_dir = args.out_dir or os.path.join(REPO_ROOT, "results", f"g_onset_sweep_{tag}")
    os.makedirs(out_dir, exist_ok=True)
    ts_path = os.path.join(out_dir, "timeseries.csv")
    sum_path = os.path.join(out_dir, "summary.csv")
    copy_path = os.path.join(REPO_ROOT, "results", f"g_onset_{tag}_summary.csv")

    combos = list(iter_grid(args.quick))
    print(f"[g_onset_sweep] {len(combos)} combos, {ALT_FT:g}ft / {args.kcas:g}KCAS, "
          f"{T_TOTAL:g}s pull -> {out_dir}")

    t_start = time.perf_counter()
    rows_all = []
    with open(ts_path, "w", newline="", encoding="utf-8") as f_ts, \
            open(sum_path, "w", newline="", encoding="utf-8-sig") as f_sum:
        w_ts = csv.writer(f_ts)
        w_ts.writerow(TS_HEADER)
        w_sum = csv.DictWriter(f_sum, fieldnames=SUMMARY_HEADER)
        w_sum.writeheader()
        for i, (g, k, fz) in enumerate(combos, 1):
            ts, s = run_one(g, k, fz, args.kcas)
            w_ts.writerows(ts)
            w_sum.writerow(s)
            f_ts.flush(); f_sum.flush()
            rows_all.append(s)
            print(f"  [{i}/{len(combos)}] {s['run_id']}: nz={s['nz_peak']:>6.3f}G "
                  f"({100*s['reach_frac']:>5.1f}%) kin={s['g_peak_kinematic']:>6.3f}G "
                  f"reached={s['reached_target']} "
                  f"t90={str(s['t_to_90pct_s']):>6} "
                  f"onset={s['onset_rate_max_gps']:>7.2f}G/s "
                  f"satEle={s['sat_elevator_pct']:>5.1f}% "
                  f"alpha={s['max_alpha_deg']:>5.1f}deg ({s['wall_time_s']:.2f}s)")

    with open(copy_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_HEADER)
        w.writeheader()
        w.writerows(rows_all)

    elapsed = time.perf_counter() - t_start
    print(f"\n[g_onset_sweep] {len(combos)} combos in {elapsed:.1f}s")

    # --- 요약 표: 목표 G 별 도달률 ---
    print(f"\n=== 목표 G 별 도달 (reach_frac = 달성피크/목표), {args.kcas:g}KCAS ===")
    print(f"{'g_target':>9}{'n':>4}{'reached':>9}{'nz_max':>10}{'nz_min':>10}"
          f"{'reach_frac_max':>16}{'limiter_capped':>16}")
    for g in sorted({r["g_target"] for r in rows_all}):
        sub = [r for r in rows_all if r["g_target"] == g]
        print(f"{g:>9g}{len(sub):>4}{sum(r['reached_target'] for r in sub):>9}"
              f"{max(r['nz_peak'] for r in sub):>10.3f}{min(r['nz_peak'] for r in sub):>10.3f}"
              f"{max(r['reach_frac'] for r in sub):>16.3f}"
              f"{sum(r['limiter_capped'] for r in sub):>16}")

    print(f"\n=== 도달 피크 Nz 지도 (목표 9G), 행=k_scale 열=filt_hz ===")
    nine = {(r["k_scale"], r["filt_hz"]): r for r in rows_all if r["g_target"] == 9.0}
    if nine:
        fs = sorted({f for _, f in nine})
        print(f"{'k_scale':>8}" + "".join(f"{f:>9g}" for f in fs))
        for k in sorted({kk for kk, _ in nine}):
            print(f"{k:>8g}" + "".join(f"{nine[(k, f)]['nz_peak']:>9.3f}" for f in fs))
    print(f"\n-> {sum_path}\n-> {copy_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
