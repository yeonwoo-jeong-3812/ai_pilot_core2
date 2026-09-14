"""L3 INDI 스텝 배치 스윕(협조선회 버전) — run_indi_step_sweep.py 의 요축 정의만 교체.

run_indi_step_sweep.py 는 shim.rate_setpoint_euler(..., psi_des=psi_cur, ...) 를 쓰는데,
QuaternionAttitudeShim.rate_setpoint 은 애초에 psi_des 를 무시하고 r_sp=-k_yaw_damp*r_cur
(요레이트를 0으로 감쇠)로 덮어쓴다(aircombat/control/attitude.py:81). 즉 이 스텝은 "뱅크는
걸되 턴은 하지 마라"를 강제하는데, 실제 뱅크 turn 은 협조선회라 몸체 요레이트가
r ≈ g·tanφ/V 로 자연히 0이 아니다(2026-09-14 조사, run_indi_step_sweep 러더 포화율
15°=81%/30°=93%/45°=97%/60°=99.5% 의 원인이 정상상태에서도 사라지지 않는 걸로 확인).

여기서는 shim 이 만든 omega_sp 의 r 성분만 협조선회 목표값으로 덮어쓴다
(run_corner_pull_sweep.py 가 omega_sp[1] 을 q_cmd 로 덮어쓰는 것과 같은 패턴).
나머지(트림→G0 식별→shim→limiter→INDI, 그리드, 저장 포맷)는 run_indi_step_sweep.py 와
100% 동일 — 원본 파일은 손대지 않고 이 파일만 남긴다.

2026-09-14 수정 2건
-------------------
(a) heading_rate_dps 가 psi wrap 때문에 전부 -360deg/T 만큼 치우쳐 있었다. JSBSim
    attitude/psi-rad 은 [0, 2pi) 로 감기고 트림 직후 psi0 = 2pi(=360deg) 이므로
    (psi_final - psi0) 가 항상 -360deg 를 덤으로 달고 나왔다(뱅크0 에서 -45.0dps
    = -360/8). np.unwrap 으로 고치고, 독립 측정치인 velocities/psidot-rad_sec 의
    정상상태 평균(psidot_ss_dps)을 함께 기록해 교차검증한다.
    검증: scripts/verify_heading_rate.py / results/heading_rate_verification.csv.
(b) 요 피드포워드 식을 --yaw-ff 로 선택할 수 있게 했다. 기존 식 tan 은 g*tan(phi)/V
    인데 이는 **선회율 psidot** 이지 **body 요레이트 r** 이 아니다. 협조선회 기구학은
    r = psidot*cos(theta)*cos(phi) 이므로 올바른 피드포워드는 g*sin(phi)*cos(theta)/V
    (=sin). 기존 식은 뱅크 60도에서 이론값의 2.41배를 지령해 러더를 96.8% 포화시켰다.
    기본값은 재현성을 위해 tan(원본 그대로) 로 둔다.

그리드
------
bank_deg : 0 / 15 / 30 / 45 / 60          (뱅크 스텝 목표)
k_scale  : 0.5 / 0.75 / 1.0 / 1.5 / 2.0   (운용값 k_rate=(9,9,6) 에 곱하는 배율)
filt_hz  : 10 / 15 / 25 / 35 / 50         (INDI 동기화 필터 컷오프)

사용
----
  python scripts/run_indi_step_sweep_coordinated.py            # 전체 5x5x5=125 조합
  python scripts/run_indi_step_sweep_coordinated.py --quick
  python scripts/run_indi_step_sweep_coordinated.py --out-dir results/my_sweep
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

# Windows 콘솔(cp949)에서 한글/em-dash 출력이 죽지 않게 — 파일 출력은 항상 UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DT = 1.0 / 120.0
T_TOTAL = 8.0
ALT_FT, VC_KTS = 10000.0, 350.0

K_RATE_BASE = (9.0, 9.0, 6.0)
BANK_DEG_GRID = (0.0, 15.0, 30.0, 45.0, 60.0)
K_SCALE_GRID = (0.5, 0.75, 1.0, 1.5, 2.0)
FILT_HZ_GRID = (10.0, 15.0, 25.0, 35.0, 50.0)
FILT_HZ_DEFAULT = 25.0

TS_HEADER = [
    "run_id", "bank_deg", "k_scale", "filt_hz", "t",
    "omega_sp_p_dps", "omega_sp_q_dps", "omega_sp_r_dps",
    "omega_p_dps", "omega_q_dps", "omega_r_dps",
    "cmd_aileron", "cmd_elevator", "cmd_rudder",
    "alpha_deg", "qbar_psf", "beta_deg", "heading_deg",
    "p_limited", "q_limited", "r_limited", "g_max", "g_min", "q_max_dps", "q_min_dps",
]

SUMMARY_HEADER = [
    "run_id", "bank_deg", "k_scale", "filt_hz",
    "k_rate_p", "k_rate_q", "k_rate_r",
    "settle_time_s", "overshoot_deg", "final_bank_deg",
    "rms_p_dps", "rms_q_dps", "rms_r_dps", "rms_total_dps",
    "sat_aileron_pct", "sat_elevator_pct", "sat_rudder_pct", "sat_any_pct",
    "mean_abs_beta_deg", "heading_rate_dps", "heading_rate_naive_dps", "psidot_ss_dps",
    "alt_ft", "kcas_ic", "yaw_ff",
    "p_limited_pct", "q_limited_pct", "r_limited_pct", "g_max_mean",
    "n_steps", "wall_time_s",
]


def run_one(bank_deg: float, k_scale: float, filt_hz: float,
            dt: float = DT, t_total: float = T_TOTAL,
            alt_ft: float = ALT_FT, kcas: float = VC_KTS, yaw_ff: str = "tan"):
    """run_indi_step_sweep.run_one 과 동일하되 r_sp 만 협조선회값으로 덮어쓴다."""
    t0 = time.perf_counter()
    run_id = f"bank{bank_deg:g}_k{k_scale:g}_f{filt_hz:g}"
    k_rate = tuple(k * k_scale for k in K_RATE_BASE)

    kcas_ic = float(kcas)          # 아래 루프에서 kcas 가 현재값으로 덮어써지므로 IC 는 따로 보관
    p = F16Plant(dt=dt)
    p.set_ic(alt_ft=alt_ft, vc_kts=kcas_ic)
    p["fcs/throttle-cmd-norm"] = 0.8
    p.trim()

    G0, qbar_ref = identify_G0(p.fdm)
    rate = INDIRateController(dt, G0, qbar_ref, k_rate=k_rate, filt_hz=filt_hz)
    rate.reset(u0=[p["fcs/aileron-cmd-norm"],
                   p["fcs/elevator-cmd-norm"],
                   p["fcs/rudder-cmd-norm"]])

    shim = QuaternionAttitudeShim(k_att=4.5, k_yaw_damp=1.5)
    limiter = CombinedLimiter(LimiterConfig())
    theta_trim = p["attitude/theta-rad"]
    phi_sp = np.deg2rad(bank_deg)
    psi0 = p["attitude/psi-rad"]

    n = int(t_total / dt)
    band_deg = max(2.0, 0.05 * abs(bank_deg))

    rows = []
    err2 = np.zeros(3)
    sat_count = np.zeros(3)
    sat_any_count = 0
    peak_bank = -1e9
    last_out_of_band = 0.0
    lim_count = np.zeros(3)
    g_max_sum = 0.0
    beta_abs_sum = 0.0
    psi_log = np.zeros(n)
    psidot_log = np.zeros(n)

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
        # 협조선회 요레이트로 덮어쓴다: r = g*tan(phi)/V (표준 선회율 근사, 현재 뱅크 기준
        # 피드포워드 — phi=0 이면 r=0 로 자연스럽게 원래 동작과 일치한다).
        if yaw_ff == "sin":
            # 협조선회 body 요레이트: r = psidot*cos(theta)*cos(phi), psidot=g*tan(phi)/V
            omega_sp[2] = G_FT_S2 * np.sin(phi) * np.cos(theta) / max(v_fps, 1.0)
        else:
            omega_sp[2] = G_FT_S2 * np.tan(phi) / max(v_fps, 1.0)

        g_lift = float(np.cos(phi) * np.cos(theta))
        omega_sp, flags = limiter.limit_omega_sp(omega_sp, v_fps, kcas, g_lift=g_lift)

        u = rate.update(omega, omega_sp, qbar, ang_accel=ang_acc)
        p["fcs/aileron-cmd-norm"] = u[0]
        p["fcs/elevator-cmd-norm"] = u[1]
        p["fcs/rudder-cmd-norm"] = u[2]
        p.step(1)

        psi_log[k] = p["attitude/psi-rad"]
        psidot_log[k] = p["velocities/psidot-rad_sec"]
        bank_now = np.rad2deg(p["attitude/phi-rad"])
        alpha_deg = np.rad2deg(p["aero/alpha-rad"])
        beta_deg = np.rad2deg(p["aero/beta-rad"])

        rows.append([
            run_id, bank_deg, k_scale, filt_hz, round(t, 6),
            *np.rad2deg(omega_sp).round(6),
            *np.rad2deg(omega).round(6),
            round(float(u[0]), 6), round(float(u[1]), 6), round(float(u[2]), 6),
            round(float(alpha_deg), 6), round(float(qbar), 6),
            round(float(beta_deg), 6), round(float(np.rad2deg(psi)), 6),
            flags["p_limited"], flags["q_limited"], flags["r_limited"],
            round(flags["g_max"], 4), round(flags["g_min"], 4),
            round(np.rad2deg(flags["q_max"]), 4), round(np.rad2deg(flags["q_min"]), 4),
        ])

        err2 += (omega_sp - omega) ** 2
        sat_now = np.abs(u) > 0.999
        sat_count += sat_now
        sat_any_count += int(np.any(sat_now))
        peak_bank = max(peak_bank, bank_now)
        if abs(bank_now - bank_deg) > band_deg:
            last_out_of_band = t + dt
        lim_count += [flags["p_limited"], flags["q_limited"], flags["r_limited"]]
        g_max_sum += flags["g_max"]
        beta_abs_sum += abs(beta_deg)

    rms = np.rad2deg(np.sqrt(err2 / n))
    final_bank = np.rad2deg(p["attitude/phi-rad"])
    # psi wrap 보정: JSBSim psi 는 [0,2pi) 이고 트림 직후 psi0=2pi 라 naive 차분은
    # 항상 -360deg 만큼 치우친다. unwrap 후 차분한다.
    psi_un = np.unwrap(np.concatenate(([psi0], psi_log)))
    heading_rate = np.rad2deg(psi_un[-1] - psi_un[0]) / t_total
    heading_rate_naive = (np.rad2deg(p["attitude/psi-rad"]) - np.rad2deg(psi0)) / t_total
    ss = int(n * 0.75)          # 마지막 25% 를 정상상태로 본다
    psidot_ss = float(np.rad2deg(psidot_log[ss:].mean()))
    overshoot = max(0.0, peak_bank - bank_deg)
    sat_pct = 100.0 * sat_count / n
    sat_any_pct = 100.0 * sat_any_count / n
    lim_pct = 100.0 * lim_count / n

    summary = {
        "run_id": run_id, "bank_deg": bank_deg, "k_scale": k_scale, "filt_hz": filt_hz,
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
        "mean_abs_beta_deg": round(beta_abs_sum / n, 4),
        "heading_rate_dps": round(float(heading_rate), 4),
        "heading_rate_naive_dps": round(float(heading_rate_naive), 4),
        "psidot_ss_dps": round(psidot_ss, 4),
        "alt_ft": alt_ft, "kcas_ic": kcas_ic, "yaw_ff": yaw_ff,
        "p_limited_pct": round(float(lim_pct[0]), 2),
        "q_limited_pct": round(float(lim_pct[1]), 2),
        "r_limited_pct": round(float(lim_pct[2]), 2),
        "g_max_mean": round(g_max_sum / n, 4),
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out-dir", default=None,
                     help="출력 디렉터리 (기본: results/indi_step_sweep_coordinated[_quick])")
    ap.add_argument("--alt-ft", type=float, default=ALT_FT,
                     help=f"초기 고도 [ft] (기본 {ALT_FT:g})")
    ap.add_argument("--kcas", type=float, default=VC_KTS,
                     help=f"초기 교정대기속도 [KCAS] (기본 {VC_KTS:g})")
    ap.add_argument("--yaw-ff", choices=("tan", "sin"), default="tan",
                     help="요 피드포워드 식: tan=g*tan(phi)/V(원본), "
                          "sin=g*sin(phi)*cos(theta)/V(협조선회 body r 이론값)")
    args = ap.parse_args()

    tag = f"_{args.alt_ft/1000:g}k{args.kcas:g}" if (args.alt_ft != ALT_FT or args.kcas != VC_KTS) else ""
    tag += "" if args.yaw_ff == "tan" else f"_{args.yaw_ff}"
    out_dir = args.out_dir or os.path.join(
        REPO_ROOT, "results",
        ("indi_step_sweep_coordinated_quick" if args.quick
         else "indi_step_sweep_coordinated") + tag)
    os.makedirs(out_dir, exist_ok=True)
    ts_path = os.path.join(out_dir, "timeseries.csv")
    sum_path = os.path.join(out_dir, "summary.csv")

    combos = list(iter_grid(args.quick))
    print(f"[run_indi_step_sweep_coordinated] {len(combos)} combos -> {out_dir}")
    print(f"[run_indi_step_sweep_coordinated] IC: {args.alt_ft:g}ft / {args.kcas:g}KCAS, "
          f"yaw_ff={args.yaw_ff}")

    t_start = time.perf_counter()
    with open(ts_path, "w", newline="") as f_ts, open(sum_path, "w", newline="") as f_sum:
        w_ts = csv.writer(f_ts)
        w_ts.writerow(TS_HEADER)
        w_sum = csv.DictWriter(f_sum, fieldnames=SUMMARY_HEADER)
        w_sum.writeheader()

        for i, (bank_deg, k_scale, filt_hz) in enumerate(combos, 1):
            rows, summary = run_one(bank_deg, k_scale, filt_hz,
                                    alt_ft=args.alt_ft, kcas=args.kcas,
                                    yaw_ff=args.yaw_ff)
            w_ts.writerows(rows)
            w_sum.writerow(summary)
            f_ts.flush(); f_sum.flush()
            print(f"  [{i}/{len(combos)}] {summary['run_id']}: "
                  f"settle={summary['settle_time_s']:.2f}s "
                  f"overshoot={summary['overshoot_deg']:.2f}deg "
                  f"rms_total={summary['rms_total_dps']:.2f}deg/s "
                  f"sat_rud={summary['sat_rudder_pct']:.0f}% "
                  f"psidot_ss={summary['psidot_ss_dps']:.2f}deg/s "
                  f"({summary['wall_time_s']:.2f}s)")

    elapsed = time.perf_counter() - t_start
    avg = elapsed / max(len(combos), 1)
    full_n = len(BANK_DEG_GRID) * len(K_SCALE_GRID) * len(FILT_HZ_GRID)
    print(f"\n[run_indi_step_sweep_coordinated] {len(combos)} combos done in {elapsed:.1f}s "
          f"(avg {avg:.2f}s/run)")
    print(f"[run_indi_step_sweep_coordinated] full grid = {full_n} combos "
          f"-> estimated {full_n * avg:.0f}s ({full_n * avg / 60.0:.1f} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
