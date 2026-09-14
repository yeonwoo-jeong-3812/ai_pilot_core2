"""L3 INDI 스텝 배치 스윕 — run_indi_step.py 기반, 뱅크각×k_rate×filt_hz 그리드.

run_indi_step.py(45도 뱅크 1케이스, 회귀 판정용)는 그대로 둔다. 이 스크립트는 같은
검증 루프(트림→G0 식별→쿼터니언 shim→INDI rate 제어)를 파라미터 그리드로 반복해
매 스텝 시계열과 조합별 요약을 CSV 로 남긴다.

그리드
------
bank_deg : 0 / 15 / 30 / 45 / 60          (뱅크 스텝 목표)
k_scale  : 0.5 / 0.75 / 1.0 / 1.5 / 2.0   (운용값 k_rate=(9,9,6) 에 곱하는 배율)
filt_hz  : 10 / 15 / 25 / 35 / 50         (INDI 동기화 필터 컷오프)

저장
----
<out_dir>/timeseries.csv  매 스텝: t, omega_sp(p,q,r), omega(p,q,r), 조종면 명령
                          (ail,ele,rud), alpha, qbar — run_id 로 조합 식별(long format).
<out_dir>/summary.csv     조합별: 도달시간, 오버슈트, 추종 RMS(축별+종합),
                          조종면 포화율(축별+종합), 최종뱅크, 실행시간(wall clock).

사용
----
  python scripts/run_indi_step_sweep.py            # 전체 5x5x5=125 조합
  python scripts/run_indi_step_sweep.py --quick     # bank_deg x k_scale 2x2 (filt_hz 고정) 동작확인
  python scripts/run_indi_step_sweep.py --out-dir results/my_sweep
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
from aircombat.control.attitude import QuaternionAttitudeShim
from aircombat.control.limiter import CombinedLimiter, LimiterConfig, G_FT_S2
from sweep_diagnostics import oscillation_metrics, envelope_violation

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DT = 1.0 / 120.0
T_TOTAL = 8.0
ALT_FT, VC_KTS = 10000.0, 350.0

K_RATE_BASE = (9.0, 9.0, 6.0)          # 실제 운용값 (run_indi_step.py 와 동일)
BANK_DEG_GRID = (0.0, 15.0, 30.0, 45.0, 60.0)
K_SCALE_GRID = (0.5, 0.75, 1.0, 1.5, 2.0)
FILT_HZ_GRID = (10.0, 15.0, 25.0, 35.0, 50.0)
FILT_HZ_DEFAULT = 25.0                  # run_indi_step.py 의 기본값 (quick 모드 고정값)

TS_HEADER = [
    "run_id", "bank_deg", "k_scale", "filt_hz", "limiter", "t",
    "omega_sp_p_dps", "omega_sp_q_dps", "omega_sp_r_dps",
    "omega_p_dps", "omega_q_dps", "omega_r_dps",
    "cmd_aileron", "cmd_elevator", "cmd_rudder",
    "alpha_deg", "qbar_psf", "v_fps", "kcas", "g_lift", "n_act",
    "p_limited", "q_limited", "r_limited", "g_max", "g_min", "q_max_dps", "q_min_dps",
]

SUMMARY_HEADER = [
    "run_id", "bank_deg", "k_scale", "filt_hz", "limiter",
    "k_rate_p", "k_rate_q", "k_rate_r",
    "settle_time_s", "overshoot_deg", "final_bank_deg",
    "rms_p_dps", "rms_q_dps", "rms_r_dps", "rms_total_dps",
    "sat_aileron_pct", "sat_elevator_pct", "sat_rudder_pct", "sat_any_pct",
    "p_limited_pct", "q_limited_pct", "r_limited_pct", "g_max_mean",
    "p2p_p_dps_last3s", "std_p_dps_last3s", "p2p_q_dps_last3s", "std_q_dps_last3s",
    "p2p_r_dps_last3s", "std_r_dps_last3s", "p2p_n_act_last3s", "std_n_act_last3s",
    "signchg_ail_hz", "signchg_elev_hz", "signchg_rud_hz", "oscillating",
    "g_exceeded", "frac_time_g_exceeded", "max_g_exceed_pos", "max_g_exceed_neg",
    "n_steps", "wall_time_s",
]


def run_one(bank_deg: float, k_scale: float, filt_hz: float,
            dt: float = DT, t_total: float = T_TOTAL, use_limiter: bool = True):
    """run_indi_step.py 의 검증 루프를 파라미터화해 1회 실행.

    실 스택(Pilot.control_step)과 동일하게 shim -> limiter -> INDI 순서로 돌린다
    (use_limiter=False 는 리미터 유무 비교용 옵션 — 기본은 항상 True).

    returns (rows, summary) — rows 는 timeseries.csv 에 쓸 행 리스트,
    summary 는 summary.csv 에 쓸 행 하나(dict).
    """
    t0 = time.perf_counter()
    run_id = f"bank{bank_deg:g}_k{k_scale:g}_f{filt_hz:g}" + ("" if use_limiter else "_nolim")
    k_rate = tuple(k * k_scale for k in K_RATE_BASE)

    p = F16Plant(dt=dt)
    p.set_ic(alt_ft=ALT_FT, vc_kts=VC_KTS)
    p["fcs/throttle-cmd-norm"] = 0.8
    p.trim()

    G0, qbar_ref = identify_G0(p.fdm)
    rate = INDIRateController(dt, G0, qbar_ref, k_rate=k_rate, filt_hz=filt_hz)
    rate.reset(u0=[p["fcs/aileron-cmd-norm"],
                   p["fcs/elevator-cmd-norm"],
                   p["fcs/rudder-cmd-norm"]])

    shim = QuaternionAttitudeShim(k_att=4.5, k_yaw_damp=1.5)
    limiter = CombinedLimiter(LimiterConfig()) if use_limiter else None
    theta_trim = p["attitude/theta-rad"]
    phi_sp = np.deg2rad(bank_deg)

    n = int(t_total / dt)
    band_deg = max(2.0, 0.05 * abs(bank_deg))   # 도달 판정 밴드 (0도 표적 포함)

    rows = []
    err2 = np.zeros(3)
    sat_count = np.zeros(3)
    sat_any_count = 0
    peak_bank = -1e9
    last_out_of_band = 0.0
    lim_count = np.zeros(3)   # p,q,r 리미터 개입 스텝수
    g_max_sum = 0.0

    for k in range(n):
        t = k * dt
        phi = p["attitude/phi-rad"]; theta = p["attitude/theta-rad"]
        omega = np.array([p["velocities/p-rad_sec"],
                          p["velocities/q-rad_sec"],
                          p["velocities/r-rad_sec"]])
        qbar = p["aero/qbar-psf"]
        v_fps, kcas = p["velocities/vt-fps"], p["velocities/vc-kts"]
        ang_acc = [p["accelerations/pdot-rad_sec2"],
                   p["accelerations/qdot-rad_sec2"],
                   p["accelerations/rdot-rad_sec2"]]

        psi = p["attitude/psi-rad"]
        omega_sp = shim.rate_setpoint_euler(phi, theta, psi,
                                            phi_sp, theta_trim, psi, r_cur=omega[2])

        g_lift = float(np.cos(phi) * np.cos(theta))
        # 실 스택과 동일: shim -> limiter -> INDI (pilot.control_step 참고).
        if use_limiter:
            omega_sp, flags = limiter.limit_omega_sp(omega_sp, v_fps, kcas, g_lift=g_lift)
        else:
            flags = {"p_limited": False, "q_limited": False, "r_limited": False,
                     "g_max": float("nan"), "g_min": float("nan"),
                     "q_max": float("nan"), "q_min": float("nan")}

        u = rate.update(omega, omega_sp, qbar, ang_accel=ang_acc)
        p["fcs/aileron-cmd-norm"] = u[0]
        p["fcs/elevator-cmd-norm"] = u[1]
        p["fcs/rudder-cmd-norm"] = u[2]
        p.step(1)

        bank_now = np.rad2deg(p["attitude/phi-rad"])
        alpha_deg = np.rad2deg(p["aero/alpha-rad"])
        q_act = p["velocities/q-rad_sec"]
        n_act = q_act * p["velocities/vt-fps"] / G_FT_S2 + g_lift

        rows.append([
            run_id, bank_deg, k_scale, filt_hz, use_limiter, round(t, 6),
            *np.rad2deg(omega_sp).round(6),
            *np.rad2deg(omega).round(6),
            round(float(u[0]), 6), round(float(u[1]), 6), round(float(u[2]), 6),
            round(float(alpha_deg), 6), round(float(qbar), 6),
            round(float(v_fps), 4), round(float(kcas), 4), round(g_lift, 6), round(float(n_act), 6),
            flags["p_limited"], flags["q_limited"], flags["r_limited"],
            round(flags["g_max"], 4) if flags["g_max"] == flags["g_max"] else "",
            round(flags["g_min"], 4) if flags["g_min"] == flags["g_min"] else "",
            round(np.rad2deg(flags["q_max"]), 4) if flags["q_max"] == flags["q_max"] else "",
            round(np.rad2deg(flags["q_min"]), 4) if flags["q_min"] == flags["q_min"] else "",
        ])

        err2 += (omega_sp - omega) ** 2
        sat_now = np.abs(u) > 0.999
        sat_count += sat_now
        sat_any_count += int(np.any(sat_now))
        peak_bank = max(peak_bank, bank_now)
        if abs(bank_now - bank_deg) > band_deg:
            last_out_of_band = t + dt
        lim_count += [flags["p_limited"], flags["q_limited"], flags["r_limited"]]
        if use_limiter:
            g_max_sum += flags["g_max"]

    rms = np.rad2deg(np.sqrt(err2 / n))
    final_bank = np.rad2deg(p["attitude/phi-rad"])
    overshoot = max(0.0, peak_bank - bank_deg)
    sat_pct = 100.0 * sat_count / n
    sat_any_pct = 100.0 * sat_any_count / n
    lim_pct = 100.0 * lim_count / n

    t_arr = [r[5] for r in rows]
    n_act_arr = [r[20] for r in rows]
    osc = oscillation_metrics(t_arr, [r[9] for r in rows], [r[10] for r in rows],
                              [r[11] for r in rows], n_act_arr,
                              [r[12] for r in rows], [r[13] for r in rows], [r[14] for r in rows])
    env = envelope_violation(n_act_arr, dt)

    summary = {
        "run_id": run_id, "bank_deg": bank_deg, "k_scale": k_scale, "filt_hz": filt_hz,
        "limiter": use_limiter,
        "k_rate_p": k_rate[0], "k_rate_q": k_rate[1], "k_rate_r": k_rate[2],
        "settle_time_s": round(last_out_of_band, 4),
        "overshoot_deg": round(float(overshoot), 4),
        "final_bank_deg": round(float(final_bank), 4),
        "rms_p_dps": round(float(rms[0]), 4),
        "rms_q_dps": round(float(rms[1]), 4),
        "rms_r_dps": round(float(rms[2]), 4),
        "rms_total_dps": round(float(np.linalg.norm(rms)), 4),
        "sat_aileron_pct": round(float(sat_pct[0]), 2),
        "sat_elevator_pct": round(float(sat_pct[1]), 2),
        "sat_rudder_pct": round(float(sat_pct[2]), 2),
        "sat_any_pct": round(sat_any_pct, 2),
        "p_limited_pct": round(float(lim_pct[0]), 2),
        "q_limited_pct": round(float(lim_pct[1]), 2),
        "r_limited_pct": round(float(lim_pct[2]), 2),
        "g_max_mean": round(g_max_sum / n, 4) if use_limiter else "",
        **osc,
        **env,
        "n_steps": n,
        "wall_time_s": round(time.perf_counter() - t0, 3),
    }
    return rows, summary


def iter_grid(quick: bool):
    if quick:
        for bank_deg in BANK_DEG_GRID[:2]:
            for k_scale in K_SCALE_GRID[:2]:
                yield bank_deg, k_scale, FILT_HZ_DEFAULT
    else:
        for bank_deg in BANK_DEG_GRID:
            for k_scale in K_SCALE_GRID:
                for filt_hz in FILT_HZ_GRID:
                    yield bank_deg, k_scale, filt_hz


LIMITER_COMPARE_BANKS = (15.0, 45.0, 60.0)   # 리미터 유무 비교용 (k_scale=1.0, filt_hz=25 고정)


def run_limiter_compare(out_dir: str) -> int:
    """뱅크 15/45/60도에서 리미터 유무 두 버전을 비교, 결과 차이를 기록."""
    os.makedirs(out_dir, exist_ok=True)
    ts_path = os.path.join(out_dir, "timeseries.csv")
    sum_path = os.path.join(out_dir, "summary.csv")

    rows_by_bank = {}
    with open(ts_path, "w", newline="") as f_ts, open(sum_path, "w", newline="") as f_sum:
        w_ts = csv.writer(f_ts)
        w_ts.writerow(TS_HEADER)
        w_sum = csv.DictWriter(f_sum, fieldnames=SUMMARY_HEADER)
        w_sum.writeheader()

        for bank_deg in LIMITER_COMPARE_BANKS:
            pair = {}
            for use_limiter in (True, False):
                rows, summary = run_one(bank_deg, 1.0, FILT_HZ_DEFAULT, use_limiter=use_limiter)
                w_ts.writerows(rows)
                w_sum.writerow(summary)
                pair[use_limiter] = summary
            rows_by_bank[bank_deg] = pair
            f_ts.flush(); f_sum.flush()

    print(f"[run_indi_step_sweep --limiter-compare] -> {out_dir}\n")
    print(f"{'bank':>6} {'field':>16} {'limiter=ON':>12} {'limiter=OFF':>12} {'diff':>10}")
    print("-" * 62)
    diff_fields = ["settle_time_s", "overshoot_deg", "final_bank_deg",
                   "rms_total_dps", "sat_any_pct"]
    any_diff = False
    for bank_deg in LIMITER_COMPARE_BANKS:
        on, off = rows_by_bank[bank_deg][True], rows_by_bank[bank_deg][False]
        for field in diff_fields:
            d = float(on[field]) - float(off[field])
            if abs(d) > 1e-9:
                any_diff = True
            print(f"{bank_deg:>6.0f} {field:>16} {on[field]:>12} {off[field]:>12} {d:>10.4f}")
    print()
    if any_diff:
        print("[run_indi_step_sweep --limiter-compare] 결과: 리미터 유무에 따라 값이 달라짐 "
              "(위 diff != 0 인 항목 참고).")
    else:
        print("[run_indi_step_sweep --limiter-compare] 결과: 뱅크 15/45/60도, k_scale=1.0, "
              "filt_hz=25Hz 조건에서는 리미터 유무가 summary 지표에 차이를 만들지 않음 "
              "(이 뱅크 스텝은 요구 G가 낮아 q/p/r 한계에 걸리지 않기 때문).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true",
                     help=f"동작확인용 2x2(bank_deg x k_scale), filt_hz={FILT_HZ_DEFAULT:g}Hz 고정")
    ap.add_argument("--out-dir", default=None, help="출력 디렉터리 (기본: results/indi_step_sweep[_quick])")
    ap.add_argument("--no-limiter", action="store_true",
                     help="CombinedLimiter 를 끄고 실행 (기본은 실 스택과 동일하게 항상 켬)")
    ap.add_argument("--limiter-compare", action="store_true",
                     help=f"뱅크 {LIMITER_COMPARE_BANKS} 도에서 리미터 유무 두 버전을 비교 "
                          "(k_scale=1.0, filt_hz=25Hz 고정), 다른 그리드 옵션 무시")
    args = ap.parse_args()

    if args.limiter_compare:
        out_dir = args.out_dir or os.path.join(REPO_ROOT, "results", "indi_step_limiter_compare")
        return run_limiter_compare(out_dir)

    use_limiter = not args.no_limiter
    out_dir = args.out_dir or os.path.join(
        REPO_ROOT, "results", "indi_step_sweep_quick" if args.quick else "indi_step_sweep")
    os.makedirs(out_dir, exist_ok=True)
    ts_path = os.path.join(out_dir, "timeseries.csv")
    sum_path = os.path.join(out_dir, "summary.csv")

    combos = list(iter_grid(args.quick))
    print(f"[run_indi_step_sweep] {len(combos)} combos (limiter={use_limiter}) -> {out_dir}")

    t_start = time.perf_counter()
    with open(ts_path, "w", newline="") as f_ts, open(sum_path, "w", newline="") as f_sum:
        w_ts = csv.writer(f_ts)
        w_ts.writerow(TS_HEADER)
        w_sum = csv.DictWriter(f_sum, fieldnames=SUMMARY_HEADER)
        w_sum.writeheader()

        for i, (bank_deg, k_scale, filt_hz) in enumerate(combos, 1):
            rows, summary = run_one(bank_deg, k_scale, filt_hz, use_limiter=use_limiter)
            w_ts.writerows(rows)
            w_sum.writerow(summary)
            f_ts.flush(); f_sum.flush()
            print(f"  [{i}/{len(combos)}] {summary['run_id']}: "
                  f"settle={summary['settle_time_s']:.2f}s "
                  f"overshoot={summary['overshoot_deg']:.2f}deg "
                  f"rms_total={summary['rms_total_dps']:.2f}deg/s "
                  f"sat_any={summary['sat_any_pct']:.0f}% "
                  f"({summary['wall_time_s']:.2f}s)")

    elapsed = time.perf_counter() - t_start
    avg = elapsed / max(len(combos), 1)
    full_n = len(BANK_DEG_GRID) * len(K_SCALE_GRID) * len(FILT_HZ_GRID)
    print(f"\n[run_indi_step_sweep] {len(combos)} combos done in {elapsed:.1f}s "
          f"(avg {avg:.2f}s/run)")
    print(f"[run_indi_step_sweep] full grid = {full_n} combos "
          f"-> estimated {full_n * avg:.0f}s ({full_n * avg / 60.0:.1f} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
