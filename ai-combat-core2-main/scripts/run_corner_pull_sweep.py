"""L3 코너 당김 배치 스윕 — run_corner_pull.py 기반, 목표G×k_rate×filt_hz 그리드.

run_corner_pull.py(80도 지속 선회, 리미터가 허용하는 최대G 를 그대로 지령)는
그대로 둔다. 이 스크립트는 같은 검증 루프(트림→G0 식별→쿼터니언 shim→코너
리미터→INDI rate 제어)를 파라미터 그리드로 반복하되, **목표 G 를 직접 지령**한다
(단, CombinedLimiter 가 허용하는 순간 봉투 g_max=min(9G, 공력한계) 는 항상 안전
상한으로 유지 — g_cmd = min(목표G, g_max)).

그리드
------
g_target : 3 / 5 / 7 / 9                  (지령 목표 G)
k_scale  : 0.5 / 0.75 / 1.0 / 1.5 / 2.0   (운용값 k_rate=(9,9,6) 에 곱하는 배율)
filt_hz  : 10 / 15 / 25 / 35 / 50         (INDI 동기화 필터 컷오프)

저장
----
<out_dir>/timeseries.csv  매 스텝: t, omega_sp(p,q,r), omega(p,q,r), 조종면 명령
                          (ail,ele,rud), alpha, qbar — run_id 로 조합 식별(long format).
<out_dir>/summary.csv     조합별: 도달시간, 오버슈트, 정상상태 q 추종 RMS, 조종면
                          포화율(축별+종합), 최종뱅크, **도달 최대 받음각**, 실행시간.

사용
----
  python scripts/run_corner_pull_sweep.py            # 전체 4x5x5=100 조합
  python scripts/run_corner_pull_sweep.py --quick     # g_target x k_scale 2x2 (filt_hz 고정) 동작확인
  python scripts/run_corner_pull_sweep.py --out-dir results/my_sweep
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.fdm.plant import F16Plant
from aircombat.control.indi import INDIRateController, identify_G0
from aircombat.control.attitude import QuaternionAttitudeShim, euler_to_quat, quat_mul
from aircombat.control.limiter import CombinedLimiter, LimiterConfig, G_FT_S2
from sweep_diagnostics import oscillation_metrics, envelope_violation

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DT = 1.0 / 120.0
BANK_DEG = 80.0          # 지속 선회 뱅크 (run_corner_pull.py 와 동일)
T_TOTAL = 12.0
T_SETTLE = 4.0            # 이 시각 이후를 정상상태로 본다 (run_corner_pull.py 와 동일)
ALT_FT, VC_KTS = 15000.0, 400.0

K_RATE_BASE = (9.0, 9.0, 6.0)          # 실제 운용값 (run_corner_pull.py 와 동일)
G_TARGET_GRID = (3.0, 5.0, 7.0, 9.0)
K_SCALE_GRID = (0.5, 0.75, 1.0, 1.5, 2.0)
FILT_HZ_GRID = (10.0, 15.0, 25.0, 35.0, 50.0)
FILT_HZ_DEFAULT = 25.0                  # run_corner_pull.py 의 기본값 (quick 모드 고정값)

TS_HEADER = [
    "run_id", "g_target", "k_scale", "filt_hz", "t",
    "omega_sp_p_dps", "omega_sp_q_dps", "omega_sp_r_dps",
    "omega_p_dps", "omega_q_dps", "omega_r_dps",
    "cmd_aileron", "cmd_elevator", "cmd_rudder",
    "alpha_deg", "qbar_psf", "n_act",
    "p_limited", "q_limited", "r_limited", "g_max", "g_min", "q_max_dps", "q_min_dps",
]

SUMMARY_HEADER = [
    "run_id", "g_target", "k_scale", "filt_hz",
    "k_rate_p", "k_rate_q", "k_rate_r",
    "settle_time_s", "overshoot_g", "final_bank_deg", "g_achieved_final",
    "rms_q_tracking_dps",
    "sat_aileron_pct", "sat_elevator_pct", "sat_rudder_pct", "sat_any_pct",
    "p_limited_pct", "q_limited_pct", "r_limited_pct", "g_max_mean",
    "p2p_p_dps_last3s", "std_p_dps_last3s", "p2p_q_dps_last3s", "std_q_dps_last3s",
    "p2p_r_dps_last3s", "std_r_dps_last3s", "p2p_n_act_last3s", "std_n_act_last3s",
    "signchg_ail_hz", "signchg_elev_hz", "signchg_rud_hz", "oscillating",
    "g_exceeded", "frac_time_g_exceeded", "max_g_exceed_pos", "max_g_exceed_neg",
    "max_alpha_deg", "n_steps", "wall_time_s",
]


def run_one(g_target: float, k_scale: float, filt_hz: float,
            dt: float = DT, t_total: float = T_TOTAL, t_settle: float = T_SETTLE):
    """run_corner_pull.py 의 검증 루프를 파라미터화해 1회 실행.

    returns (rows, summary) — rows 는 timeseries.csv 에 쓸 행 리스트,
    summary 는 summary.csv 에 쓸 행 하나(dict).
    """
    t0 = time.perf_counter()
    run_id = f"G{g_target:g}_k{k_scale:g}_f{filt_hz:g}"
    k_rate = tuple(k * k_scale for k in K_RATE_BASE)

    p = F16Plant(dt=dt)
    p.set_ic(alt_ft=ALT_FT, vc_kts=VC_KTS)
    p["fcs/throttle-cmd-norm"] = 1.0        # full AB — 지속 선회 속도 유지
    p.trim()

    G0, qbar_ref = identify_G0(p.fdm)
    indi = INDIRateController(dt, G0, qbar_ref, k_rate=k_rate, filt_hz=filt_hz)
    indi.reset(u0=[p["fcs/aileron-cmd-norm"], p["fcs/elevator-cmd-norm"],
                   p["fcs/rudder-cmd-norm"]])
    shim = QuaternionAttitudeShim(k_att=4.0, k_yaw_damp=1.5,
                                  rate_limit_dps=(180.0, 60.0, 30.0))
    limiter = CombinedLimiter(LimiterConfig())
    phi_target = np.radians(BANK_DEG)

    n = int(t_total / dt)
    band_g = max(0.3, 0.05 * g_target)   # 도달 판정 밴드

    rows = []
    q_err2 = 0.0
    n_settle = 0
    sat_count = np.zeros(3)
    sat_any_count = 0
    peak_g = -1e9
    max_alpha = -1e9
    last_out_of_band = 0.0
    n_act = 0.0
    lim_count = np.zeros(3)
    g_max_sum = 0.0

    for k in range(n):
        t = k * dt
        phi, theta = p["attitude/phi-rad"], p["attitude/theta-rad"]
        psi = p["attitude/psi-rad"]
        pqr = np.array([p["velocities/p-rad_sec"], p["velocities/q-rad_sec"],
                        p["velocities/r-rad_sec"]])
        v_fps, kcas = p["velocities/vt-fps"], p["velocities/vc-kts"]
        g_lift = float(np.cos(phi) * np.cos(theta))

        g_allowed = limiter.max_load_factor(kcas)
        g_cmd = min(g_target, g_allowed)     # 안전 상한(리미터) 안에서 목표G 지령
        q_cmd = (g_cmd - g_lift) * G_FT_S2 / max(v_fps, 1.0)

        q_cur = euler_to_quat(phi, theta, psi)
        q_des = quat_mul(q_cur, euler_to_quat(phi_target - phi, 0.0, 0.0))
        omega_sp = shim.rate_setpoint(q_cur, q_des, r_cur=pqr[2])
        omega_sp[1] = q_cmd
        omega_sp, flags = limiter.limit_omega_sp(omega_sp, v_fps, kcas, g_lift=g_lift)

        ang_acc = [p["accelerations/pdot-rad_sec2"], p["accelerations/qdot-rad_sec2"],
                   p["accelerations/rdot-rad_sec2"]]
        u = indi.update(pqr, omega_sp, p["aero/qbar-psf"], ang_accel=ang_acc)
        p.set_input([1.0, u[1], u[0], u[2]])
        p.step(1)

        q_act = p["velocities/q-rad_sec"]
        n_act = q_act * p["velocities/vt-fps"] / G_FT_S2 + g_lift
        alpha_deg = float(np.degrees(p["aero/alpha-rad"]))
        qbar = p["aero/qbar-psf"]

        rows.append([
            run_id, g_target, k_scale, filt_hz, round(t, 6),
            *np.rad2deg(omega_sp).round(6),
            *np.rad2deg(pqr).round(6),
            round(float(u[0]), 6), round(float(u[1]), 6), round(float(u[2]), 6),
            round(alpha_deg, 6), round(float(qbar), 6), round(float(n_act), 6),
            flags["p_limited"], flags["q_limited"], flags["r_limited"],
            round(flags["g_max"], 4), round(flags["g_min"], 4),
            round(np.rad2deg(flags["q_max"]), 4), round(np.rad2deg(flags["q_min"]), 4),
        ])

        sat_now = np.abs(u) > 0.999
        sat_count += sat_now
        sat_any_count += int(np.any(sat_now))
        peak_g = max(peak_g, n_act)
        max_alpha = max(max_alpha, alpha_deg)
        if abs(n_act - g_target) > band_g:
            last_out_of_band = t + dt
        if t >= t_settle:
            q_err2 += (omega_sp[1] - q_act) ** 2
            n_settle += 1
        lim_count += [flags["p_limited"], flags["q_limited"], flags["r_limited"]]
        g_max_sum += flags["g_max"]

    rms_q_ss = np.rad2deg(np.sqrt(q_err2 / max(n_settle, 1)))
    overshoot = max(0.0, peak_g - g_target)
    sat_pct = 100.0 * sat_count / n
    sat_any_pct = 100.0 * sat_any_count / n
    lim_pct = 100.0 * lim_count / n

    t_arr = [r[4] for r in rows]
    n_act_arr = [r[16] for r in rows]
    osc = oscillation_metrics(t_arr, [r[8] for r in rows], [r[9] for r in rows],
                              [r[10] for r in rows], n_act_arr,
                              [r[11] for r in rows], [r[12] for r in rows], [r[13] for r in rows])
    env = envelope_violation(n_act_arr, dt)

    summary = {
        "run_id": run_id, "g_target": g_target, "k_scale": k_scale, "filt_hz": filt_hz,
        "k_rate_p": k_rate[0], "k_rate_q": k_rate[1], "k_rate_r": k_rate[2],
        "settle_time_s": round(last_out_of_band, 4),
        "overshoot_g": round(float(overshoot), 4),
        "final_bank_deg": round(float(np.degrees(p["attitude/phi-rad"])), 4),
        "g_achieved_final": round(float(n_act), 4),
        "rms_q_tracking_dps": round(float(rms_q_ss), 4),
        "sat_aileron_pct": round(float(sat_pct[0]), 2),
        "sat_elevator_pct": round(float(sat_pct[1]), 2),
        "sat_rudder_pct": round(float(sat_pct[2]), 2),
        "sat_any_pct": round(sat_any_pct, 2),
        "p_limited_pct": round(float(lim_pct[0]), 2),
        "q_limited_pct": round(float(lim_pct[1]), 2),
        "r_limited_pct": round(float(lim_pct[2]), 2),
        "g_max_mean": round(g_max_sum / n, 4),
        **osc,
        **env,
        "max_alpha_deg": round(float(max_alpha), 4),
        "n_steps": n,
        "wall_time_s": round(time.perf_counter() - t0, 3),
    }
    return rows, summary


def iter_grid(quick: bool):
    if quick:
        for g_target in G_TARGET_GRID[:2]:
            for k_scale in K_SCALE_GRID[:2]:
                yield g_target, k_scale, FILT_HZ_DEFAULT
    else:
        for g_target in G_TARGET_GRID:
            for k_scale in K_SCALE_GRID:
                for filt_hz in FILT_HZ_GRID:
                    yield g_target, k_scale, filt_hz


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true",
                     help=f"동작확인용 2x2(g_target x k_scale), filt_hz={FILT_HZ_DEFAULT:g}Hz 고정")
    ap.add_argument("--out-dir", default=None, help="출력 디렉터리 (기본: results/corner_pull_sweep[_quick])")
    args = ap.parse_args()

    out_dir = args.out_dir or os.path.join(
        REPO_ROOT, "results", "corner_pull_sweep_quick" if args.quick else "corner_pull_sweep")
    os.makedirs(out_dir, exist_ok=True)
    ts_path = os.path.join(out_dir, "timeseries.csv")
    sum_path = os.path.join(out_dir, "summary.csv")

    combos = list(iter_grid(args.quick))
    print(f"[run_corner_pull_sweep] {len(combos)} combos -> {out_dir}")

    t_start = time.perf_counter()
    with open(ts_path, "w", newline="") as f_ts, open(sum_path, "w", newline="") as f_sum:
        w_ts = csv.writer(f_ts)
        w_ts.writerow(TS_HEADER)
        w_sum = csv.DictWriter(f_sum, fieldnames=SUMMARY_HEADER)
        w_sum.writeheader()

        for i, (g_target, k_scale, filt_hz) in enumerate(combos, 1):
            rows, summary = run_one(g_target, k_scale, filt_hz)
            w_ts.writerows(rows)
            w_sum.writerow(summary)
            f_ts.flush(); f_sum.flush()
            print(f"  [{i}/{len(combos)}] {summary['run_id']}: "
                  f"settle={summary['settle_time_s']:.2f}s "
                  f"overshoot={summary['overshoot_g']:.2f}G "
                  f"rms_q={summary['rms_q_tracking_dps']:.2f}deg/s "
                  f"sat_any={summary['sat_any_pct']:.0f}% "
                  f"max_alpha={summary['max_alpha_deg']:.1f}deg "
                  f"({summary['wall_time_s']:.2f}s)")

    elapsed = time.perf_counter() - t_start
    avg = elapsed / max(len(combos), 1)
    full_n = len(G_TARGET_GRID) * len(K_SCALE_GRID) * len(FILT_HZ_GRID)
    print(f"\n[run_corner_pull_sweep] {len(combos)} combos done in {elapsed:.1f}s "
          f"(avg {avg:.2f}s/run)")
    print(f"[run_corner_pull_sweep] full grid = {full_n} combos "
          f"-> estimated {full_n * avg:.0f}s ({full_n * avg / 60.0:.1f} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
