"""[1] heading_rate_dps 검증 + 협조선회 요레이트(r_sp) 이론 대조.

배경
----
results/indi_step_coordinated_summary.csv 의 heading_rate_dps 가 뱅크 0도에서
-45.0 dps, 15도 -44.3, 60도 -41.3 로 나왔다. 물리적으로 (a) 뱅크 0에서 선회율이
0이 아니고 (b) 뱅크가 커질수록 선회율이 줄어드는, 두 가지가 모두 반대다.

이 스크립트는 같은 시뮬레이션을 돌리되 heading 을 세 가지 방법으로 동시에 측정해
어느 쪽이 맞는지 실측으로 가른다.
  A) naive   : (psi_final - psi_0)/T           ← 기존 코드와 동일 (wrap 미처리)
  B) unwrap  : np.unwrap 후 (psi_final - psi_0)/T
  C) psidot  : JSBSim velocities/psidot-rad_sec 의 정상상태 평균 (독립 측정)

동시에 요축 3종을 비교한다.
  r_sp_cmd    : 코드가 실제로 넣는 값        = g·tanφ/V
  r_theory    : 협조선회 body 요레이트 이론   = ψ̇·cosθ·cosφ = (g·sinφ/V)·(cosθ/1)
  r_actual    : JSBSim 이 낸 실제 body r
  q_theory    : 협조선회 body 피치레이트 이론 = ψ̇·cosθ·sinφ

사용
----
  python scripts/verify_heading_rate.py
출력: results/heading_rate_verification.csv (+ 콘솔 표)
"""
from __future__ import annotations

import csv
import os
import sys

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
T_SS = 6.0                     # 이 시각 이후를 정상상태로 본다
ALT_FT, VC_KTS = 10000.0, 350.0      # 기존 indi_step_coordinated 와 동일 조건
K_RATE = (9.0, 9.0, 6.0)             # k_scale=1.0
FILT_HZ = 25.0
BANK_GRID = (0.0, 15.0, 30.0, 45.0, 60.0)

HEADER = [
    "bank_deg", "final_bank_deg", "theta_ss_deg", "v_fps", "kcas_ss",
    "heading_rate_naive_dps", "heading_rate_unwrap_dps", "psidot_ss_dps",
    "psidot_theory_dps",
    "r_sp_cmd_ss_dps", "r_theory_ss_dps", "r_actual_ss_dps",
    "r_cmd_over_theory", "r_track_err_dps",
    "q_sp_cmd_ss_dps", "q_theory_ss_dps", "q_actual_ss_dps",
    "beta_ss_deg", "cmd_rudder_ss", "sat_rudder_pct",
]


def run_one(bank_deg: float):
    p = F16Plant(dt=DT)
    p.set_ic(alt_ft=ALT_FT, vc_kts=VC_KTS)
    p["fcs/throttle-cmd-norm"] = 0.8
    p.trim()

    G0, qbar_ref = identify_G0(p.fdm)
    rate = INDIRateController(DT, G0, qbar_ref, k_rate=K_RATE, filt_hz=FILT_HZ)
    rate.reset(u0=[p["fcs/aileron-cmd-norm"], p["fcs/elevator-cmd-norm"],
                   p["fcs/rudder-cmd-norm"]])
    shim = QuaternionAttitudeShim(k_att=4.5, k_yaw_damp=1.5)
    limiter = CombinedLimiter(LimiterConfig())
    theta_trim = p["attitude/theta-rad"]
    phi_sp = np.deg2rad(bank_deg)
    psi0 = p["attitude/psi-rad"]

    n = int(T_TOTAL / DT)
    log = {k: np.zeros(n) for k in
           ("t", "psi", "psidot", "phi", "theta", "v", "kcas",
            "r_sp", "q_sp", "p_act", "q_act", "r_act", "beta", "rud", "sat_rud")}

    for k in range(n):
        phi = p["attitude/phi-rad"]; theta = p["attitude/theta-rad"]
        psi = p["attitude/psi-rad"]
        omega = np.array([p["velocities/p-rad_sec"], p["velocities/q-rad_sec"],
                          p["velocities/r-rad_sec"]])
        v_fps, kcas = p["velocities/vt-fps"], p["velocities/vc-kts"]
        ang_acc = [p["accelerations/pdot-rad_sec2"], p["accelerations/qdot-rad_sec2"],
                   p["accelerations/rdot-rad_sec2"]]

        omega_sp = shim.rate_setpoint_euler(phi, theta, psi, phi_sp, theta_trim, psi,
                                            r_cur=omega[2])
        omega_sp[2] = G_FT_S2 * np.tan(phi) / max(v_fps, 1.0)   # ← 검증 대상 식(원본 그대로)
        g_lift = float(np.cos(phi) * np.cos(theta))
        omega_sp, _flags = limiter.limit_omega_sp(omega_sp, v_fps, kcas, g_lift=g_lift)

        u = rate.update(omega, omega_sp, p["aero/qbar-psf"], ang_accel=ang_acc)
        p["fcs/aileron-cmd-norm"] = u[0]
        p["fcs/elevator-cmd-norm"] = u[1]
        p["fcs/rudder-cmd-norm"] = u[2]
        p.step(1)

        log["t"][k] = k * DT
        log["psi"][k] = p["attitude/psi-rad"]
        log["psidot"][k] = p["velocities/psidot-rad_sec"]
        log["phi"][k] = p["attitude/phi-rad"]
        log["theta"][k] = p["attitude/theta-rad"]
        log["v"][k] = p["velocities/vt-fps"]
        log["kcas"][k] = p["velocities/vc-kts"]
        log["r_sp"][k] = omega_sp[2]
        log["q_sp"][k] = omega_sp[1]
        log["p_act"][k] = p["velocities/p-rad_sec"]
        log["q_act"][k] = p["velocities/q-rad_sec"]
        log["r_act"][k] = p["velocities/r-rad_sec"]
        log["beta"][k] = p["aero/beta-rad"]
        log["rud"][k] = float(u[2])
        log["sat_rud"][k] = float(abs(u[2]) > 0.999)

    ss = log["t"] >= T_SS
    d = np.rad2deg

    psi_naive = (d(log["psi"][-1]) - d(psi0)) / T_TOTAL
    psi_unwrap_arr = np.unwrap(np.concatenate(([psi0], log["psi"])))
    psi_unwrap = (d(psi_unwrap_arr[-1]) - d(psi_unwrap_arr[0])) / T_TOTAL

    phi_ss = float(log["phi"][ss].mean())
    theta_ss = float(log["theta"][ss].mean())
    v_ss = float(log["v"][ss].mean())
    psidot_ss = float(log["psidot"][ss].mean())
    psidot_theory = G_FT_S2 * np.tan(phi_ss) / v_ss
    r_theory = psidot_ss * np.cos(theta_ss) * np.cos(phi_ss)
    q_theory = psidot_ss * np.cos(theta_ss) * np.sin(phi_ss)
    r_sp_ss = float(log["r_sp"][ss].mean())
    r_act_ss = float(log["r_act"][ss].mean())

    return {
        "bank_deg": bank_deg,
        "final_bank_deg": round(d(float(log["phi"][-1])), 4),
        "theta_ss_deg": round(d(theta_ss), 4),
        "v_fps": round(v_ss, 2),
        "kcas_ss": round(float(log["kcas"][ss].mean()), 2),
        "heading_rate_naive_dps": round(psi_naive, 4),
        "heading_rate_unwrap_dps": round(psi_unwrap, 4),
        "psidot_ss_dps": round(d(psidot_ss), 4),
        "psidot_theory_dps": round(d(psidot_theory), 4),
        "r_sp_cmd_ss_dps": round(d(r_sp_ss), 4),
        "r_theory_ss_dps": round(d(r_theory), 4),
        "r_actual_ss_dps": round(d(r_act_ss), 4),
        "r_cmd_over_theory": round(d(r_sp_ss) / d(r_theory), 4) if abs(d(r_theory)) > 1e-3 else "",
        "r_track_err_dps": round(d(r_sp_ss - r_act_ss), 4),
        "q_sp_cmd_ss_dps": round(d(float(log["q_sp"][ss].mean())), 4),
        "q_theory_ss_dps": round(d(q_theory), 4),
        "q_actual_ss_dps": round(d(float(log["q_act"][ss].mean())), 4),
        "beta_ss_deg": round(d(float(log["beta"][ss].mean())), 4),
        "cmd_rudder_ss": round(float(log["rud"][ss].mean()), 4),
        "sat_rudder_pct": round(100.0 * float(log["sat_rud"].mean()), 2),
    }


def main() -> int:
    out = os.path.join(REPO_ROOT, "results", "heading_rate_verification.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    rows = []
    for bank in BANK_GRID:
        r = run_one(bank)
        rows.append(r)
        print(f"bank={bank:4.0f}deg  naive={r['heading_rate_naive_dps']:9.3f}  "
              f"unwrap={r['heading_rate_unwrap_dps']:8.3f}  psidot_ss={r['psidot_ss_dps']:7.3f}  "
              f"| r_sp={r['r_sp_cmd_ss_dps']:7.3f}  r_theory={r['r_theory_ss_dps']:7.3f}  "
              f"r_act={r['r_actual_ss_dps']:7.3f}  ratio={r['r_cmd_over_theory']}  "
              f"sat_rud={r['sat_rudder_pct']:5.1f}%  beta={r['beta_ss_deg']:6.3f}")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
