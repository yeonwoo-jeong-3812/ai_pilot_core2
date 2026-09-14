"""[3] 45~60도 러더 포화가 **기체 방향타의 물리적 한계**인지 검증.

물어야 할 것
------------
협조선회 스텝(run_indi_step_sweep_coordinated.py)에서 러더가 뱅크 45~60도 구간의
95~99% 시간을 스톱에 물려 있다. 원인 후보는 둘뿐이다.
  (H1) 기체 한계 : 협조선회에 필요한 요모멘트 > 러더 최대 편향이 낼 수 있는 요모멘트.
  (H2) 지령 오류 : 필요한 요모멘트는 작은데 제어기가 물리적으로 불가능한 r 을 지령.

설계
----
뱅크 30/35/40/45/50/55/60 x 속도 400/450 KCAS x **요축 법칙 5종** 을 모두 돌린다.
요축 법칙만 바꾸고 기체/고도/동압/다른 축은 전부 동일하게 두는 대조 실험이다.

  tan    r_sp = g*tan(phi)/V              현행. 이건 사실 **선회율 psidot** 이지
                                          body 요레이트가 아니다.
  sin    r_sp = g*sin(phi)*cos(theta)/V   협조선회 body 요레이트 이론값.
                                          (r = psidot*cos(theta)*cos(phi),
                                           psidot = g*tan(phi)/V 에서 유도)
  kin    r_sp = psidot_meas*cos(theta)*cos(phi)
                                          **실측 선회율** 로 만든 기구학 정합 지령.
                                          sin 은 "수평 선회" 를 가정하는데 이 시험은
                                          theta 를 트림값에 고정하므로 실제 선회는
                                          수평이 아니다(psidot_act < g*tan(phi)/V).
                                          kin 은 그 가정마저 제거한다 — 달성 불가능한
                                          성분이 0 이 되는 유일한 지령.
  beta0  러더를 INDI 에서 떼어내고 beta->0 PI 로 직접 몬다.
                                          "협조선회에 실제로 필요한 러더 편향" 을
                                          가정 없이 **실측** 한다. 이 값이 N_required.
  zero   러더 고정 0. 러더가 아예 없을 때 협조선회가 얼마나 깨지는지 = 러더의
                                          기여분 상한.

판정
----
· H1 이 참이면: 속도를 올릴 때(동압 +27%) 포화가 뚜렷이 완화되어야 하고,
  beta0 의 정상상태 러더 편향이 스톱 근처여야 한다.
· H2 가 참이면: beta0 의 러더 편향이 작고(여유 큼), 요축 법칙만 바꿔도 포화가
  사라지며, 속도 증가는 거의 효과가 없다.

요모멘트 환산
-------------
INDI 의 G0 는 d(pdot,qdot,rdot)/du 라서 G0[2,2] 가 곧 "러더 1 단위당 요각가속도"
[rad/s^2] 다. 여기에 I_zz 를 곱하면 요모멘트 [ft-lbf] 가 된다.
    N_rud_max = I_zz * |G0[2,2]| * (qbar/qbar_ref) * 1.0     (전타, 현재 동압)
    N_required = 같은 (bank, kcas) 의 **beta0** 런에서 실측한 정상상태 |rudder|
                 를 같은 식으로 환산
    authority_margin = N_rud_max / N_required
I_xz 연성(-1060 slug-ft^2, I_zz 의 1.6%)은 무시한다.

사용
----
  python scripts/run_rudder_authority.py
출력: results/rudder_authority_analysis.csv
"""
from __future__ import annotations

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
T_TOTAL = 10.0
T_SS = 7.0                      # 이 시각 이후를 정상상태로 본다
ALT_FT = 15000.0
K_RATE = (9.0, 9.0, 6.0)        # k_scale = 1.0 (운용값)
FILT_HZ = 25.0

BANK_GRID = (30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0)
KCAS_GRID = (400.0, 450.0)
YAW_LAW_GRID = ("tan", "sin", "kin", "beta0", "zero")

# beta->0 PI 이득 (beta0 모드 전용).
# 부호: bdot ~= Y/(m V) + p*alpha - r 이므로 r 을 키우면 beta 가 준다.
# G0[2,2] < 0 (러더 + 명령 -> 요각가속도 -) 이므로 r 을 키우려면 rudder 는 음수.
# 따라서 beta>0 에 대해 delta_r < 0 → delta_r = -(kp*beta + ki*int beta).
BETA_KP, BETA_KI = 3.0, 6.0

HEADER = [
    "run_id", "bank_deg", "kcas_ic", "alt_ft", "yaw_law",
    "final_bank_deg", "theta_ss_deg", "v_fps_ss", "kcas_ss", "qbar_ss_psf",
    # --- 요축 기구학 ---
    "psidot_ss_dps", "r_sp_cmd_ss_dps", "r_theory_ss_dps", "r_actual_ss_dps",
    "r_cmd_over_theory", "r_err_ss_dps",
    # --- 러더 사용량 / 포화 ---
    "rud_ss_mean", "rud_ss_abs_mean", "sat_rudder_pct", "sat_rudder_pct_ss",
    "beta_ss_deg", "beta_abs_mean_deg", "beta_abs_max_deg",
    # --- 실제 타면 각도 (명령 != 타면) ---
    "rud_pos_ss_deg", "rud_pos_max_deg", "rud_travel_frac_of_30deg",
    # --- 요모멘트 수지 [ft-lbf] ---
    "izz_slugft2", "G0_rdot_drud", "qbar_ref_psf",
    "rdot_max_rud_rads2", "N_rud_max_ftlb", "N_used_ss_ftlb",
    "N_required_ftlb", "authority_margin", "rud_required_frac",
    "n_steps", "wall_time_s",
]


def run_one(bank_deg: float, kcas_ic: float, yaw_law: str):
    t0 = time.perf_counter()
    run_id = f"bank{bank_deg:g}_{kcas_ic:g}kcas_{yaw_law}"

    p = F16Plant(dt=DT)
    p.set_ic(alt_ft=ALT_FT, vc_kts=kcas_ic)
    p["fcs/throttle-cmd-norm"] = 0.8
    p.trim()

    G0, qbar_ref = identify_G0(p.fdm)
    izz = float(p["inertia/izz-slugs_ft2"])
    g0_rud = float(G0[2, 2])                    # d(rdot)/d(rudder cmd) [rad/s^2]

    rate = INDIRateController(DT, G0, qbar_ref, k_rate=K_RATE, filt_hz=FILT_HZ)
    rate.reset(u0=[p["fcs/aileron-cmd-norm"], p["fcs/elevator-cmd-norm"],
                   p["fcs/rudder-cmd-norm"]])
    shim = QuaternionAttitudeShim(k_att=4.5, k_yaw_damp=1.5)
    limiter = CombinedLimiter(LimiterConfig())
    theta_trim = p["attitude/theta-rad"]
    phi_sp = np.deg2rad(bank_deg)

    n = int(T_TOTAL / DT)
    keys = ("t", "phi", "theta", "psidot", "v", "kcas", "qbar",
            "r_sp", "r_act", "beta", "rud", "sat", "rud_pos_deg")
    log = {k: np.zeros(n) for k in keys}
    beta_int = 0.0

    for k in range(n):
        phi = p["attitude/phi-rad"]
        theta = p["attitude/theta-rad"]
        psi = p["attitude/psi-rad"]
        omega = np.array([p["velocities/p-rad_sec"], p["velocities/q-rad_sec"],
                          p["velocities/r-rad_sec"]])
        v_fps, kcas = p["velocities/vt-fps"], p["velocities/vc-kts"]
        qbar = p["aero/qbar-psf"]
        beta = p["aero/beta-rad"]
        psidot = p["velocities/psidot-rad_sec"]
        ang_acc = [p["accelerations/pdot-rad_sec2"], p["accelerations/qdot-rad_sec2"],
                   p["accelerations/rdot-rad_sec2"]]

        omega_sp = shim.rate_setpoint_euler(phi, theta, psi, phi_sp, theta_trim, psi,
                                            r_cur=omega[2])
        if yaw_law == "sin":
            omega_sp[2] = G_FT_S2 * np.sin(phi) * np.cos(theta) / max(v_fps, 1.0)
        elif yaw_law == "kin":
            omega_sp[2] = psidot * np.cos(theta) * np.cos(phi)
        elif yaw_law in ("beta0", "zero"):
            omega_sp[2] = 0.0            # 요축은 아래에서 직접 덮어쓴다
        else:                            # "tan" — 현행
            omega_sp[2] = G_FT_S2 * np.tan(phi) / max(v_fps, 1.0)
        g_lift = float(np.cos(phi) * np.cos(theta))
        omega_sp, _ = limiter.limit_omega_sp(omega_sp, v_fps, kcas, g_lift=g_lift)

        u = rate.update(omega, omega_sp, qbar, ang_accel=ang_acc)

        if yaw_law == "beta0":
            beta_int = float(np.clip(beta_int + beta * DT, -1.0, 1.0))
            u[2] = float(np.clip(-(BETA_KP * beta + BETA_KI * beta_int), -1.0, 1.0))
            rate.u_prev = u              # INDI 내부 상태를 실제 지령과 일치시킨다
        elif yaw_law == "zero":
            u[2] = 0.0
            rate.u_prev = u

        p["fcs/aileron-cmd-norm"] = u[0]
        p["fcs/elevator-cmd-norm"] = u[1]
        p["fcs/rudder-cmd-norm"] = u[2]
        p.step(1)

        log["t"][k] = k * DT
        log["phi"][k] = p["attitude/phi-rad"]
        log["theta"][k] = p["attitude/theta-rad"]
        log["psidot"][k] = p["velocities/psidot-rad_sec"]
        log["v"][k] = p["velocities/vt-fps"]
        log["kcas"][k] = p["velocities/vc-kts"]
        log["qbar"][k] = p["aero/qbar-psf"]
        log["r_sp"][k] = omega_sp[2]
        log["r_act"][k] = p["velocities/r-rad_sec"]
        log["beta"][k] = p["aero/beta-rad"]
        log["rud"][k] = float(u[2])
        log["sat"][k] = float(abs(u[2]) > 0.999)
        # 명령(-1..1)이 아니라 native FLCS 를 통과한 **실제 타면 각도**.
        # f16.xml aerosurface_scale fcs/rudder-control 의 range 는 +-0.524rad(=+-30deg).
        log["rud_pos_deg"][k] = p["fcs/rudder-pos-deg"]

    ss = log["t"] >= T_SS
    d = np.rad2deg

    def m(key):
        return float(log[key][ss].mean())

    phi_ss, theta_ss = m("phi"), m("theta")
    psidot_ss, v_ss, qbar_ss = m("psidot"), m("v"), m("qbar")
    r_theory = psidot_ss * np.cos(theta_ss) * np.cos(phi_ss)
    r_sp_ss, r_act_ss = m("r_sp"), m("r_act")
    rud_ss = m("rud")
    rud_abs_ss = float(np.abs(log["rud"][ss]).mean())

    # 요모멘트 (현재 동압으로 스케줄된 effectiveness)
    eff = abs(g0_rud) * (qbar_ss / qbar_ref)          # 러더 1 단위당 요각가속도
    rdot_max = eff * 1.0                               # 전타 [rad/s^2]
    n_rud_max = izz * rdot_max                         # [ft-lbf]
    n_used = izz * eff * rud_abs_ss

    return {
        "run_id": run_id, "bank_deg": bank_deg, "kcas_ic": kcas_ic, "alt_ft": ALT_FT,
        "yaw_law": yaw_law,
        "final_bank_deg": round(d(float(log["phi"][-1])), 3),
        "theta_ss_deg": round(d(theta_ss), 3),
        "v_fps_ss": round(v_ss, 2), "kcas_ss": round(m("kcas"), 2),
        "qbar_ss_psf": round(qbar_ss, 2),
        "psidot_ss_dps": round(d(psidot_ss), 4),
        "r_sp_cmd_ss_dps": round(d(r_sp_ss), 4),
        "r_theory_ss_dps": round(d(r_theory), 4),
        "r_actual_ss_dps": round(d(r_act_ss), 4),
        "r_cmd_over_theory": round(r_sp_ss / r_theory, 4) if abs(r_theory) > 1e-9 else "",
        "r_err_ss_dps": round(d(r_sp_ss - r_act_ss), 4),
        "rud_ss_mean": round(rud_ss, 4),
        "rud_ss_abs_mean": round(rud_abs_ss, 4),
        "sat_rudder_pct": round(100.0 * float(log["sat"].mean()), 2),
        "sat_rudder_pct_ss": round(100.0 * float(log["sat"][ss].mean()), 2),
        "beta_ss_deg": round(d(m("beta")), 4),
        "beta_abs_mean_deg": round(d(float(np.abs(log["beta"]).mean())), 4),
        "beta_abs_max_deg": round(d(float(np.abs(log["beta"]).max())), 4),
        "rud_pos_ss_deg": round(m("rud_pos_deg"), 4),
        "rud_pos_max_deg": round(float(np.abs(log["rud_pos_deg"]).max()), 4),
        "rud_travel_frac_of_30deg": round(float(np.abs(log["rud_pos_deg"]).max()) / 30.0, 4),
        "izz_slugft2": round(izz, 1),
        "G0_rdot_drud": round(g0_rud, 5),
        "qbar_ref_psf": round(float(qbar_ref), 2),
        "rdot_max_rud_rads2": round(rdot_max, 5),
        "N_rud_max_ftlb": round(n_rud_max, 1),
        "N_used_ss_ftlb": round(n_used, 1),
        # 아래 3개는 같은 (bank,kcas) 의 beta0 런을 기준으로 main() 에서 채운다
        "N_required_ftlb": "", "authority_margin": "", "rud_required_frac": "",
        "n_steps": n,
        "wall_time_s": round(time.perf_counter() - t0, 3),
    }


def main() -> int:
    out = os.path.join(REPO_ROOT, "results", "rudder_authority_analysis.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    combos = [(b, v, y) for y in YAW_LAW_GRID for v in KCAS_GRID for b in BANK_GRID]
    print(f"[rudder_authority] {len(combos)} combos, {ALT_FT:g}ft, "
          f"yaw_law={'/'.join(YAW_LAW_GRID)}")
    print(f"{'run_id':<28}{'satRud%':>8}{'satSS%':>8}{'r_sp':>8}{'r_theo':>8}"
          f"{'r_act':>8}{'rud_ss':>8}{'|beta|':>8}{'N_used':>10}{'N_max':>10}"
          f"{'pos_max':>9}")
    rows = []
    for bank, kcas, law in combos:
        r = run_one(bank, kcas, law)
        rows.append(r)
        print(f"{r['run_id']:<28}{r['sat_rudder_pct']:>8.1f}{r['sat_rudder_pct_ss']:>8.1f}"
              f"{r['r_sp_cmd_ss_dps']:>8.3f}{r['r_theory_ss_dps']:>8.3f}"
              f"{r['r_actual_ss_dps']:>8.3f}{r['rud_ss_mean']:>8.3f}"
              f"{r['beta_abs_mean_deg']:>8.3f}{r['N_used_ss_ftlb']:>10.0f}"
              f"{r['N_rud_max_ftlb']:>10.0f}{r['rud_pos_max_deg']:>9.2f}")

    # beta0 런을 "필요 요모멘트" 기준으로 삼아 여유를 채운다
    req = {(r["bank_deg"], r["kcas_ic"]): r for r in rows if r["yaw_law"] == "beta0"}
    for r in rows:
        b = req.get((r["bank_deg"], r["kcas_ic"]))
        if not b:
            continue
        r["N_required_ftlb"] = b["N_used_ss_ftlb"]
        r["rud_required_frac"] = b["rud_ss_abs_mean"]
        r["authority_margin"] = (round(r["N_rud_max_ftlb"] / b["N_used_ss_ftlb"], 2)
                                 if b["N_used_ss_ftlb"] > 1e-6 else "")

    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)

    print("\n=== 필요 러더(beta->0 실측) 대 전타 여유 ===")
    print(f"{'bank':>5}{'kcas':>7}{'rud_req':>10}{'N_req[ftlb]':>13}"
          f"{'N_max[ftlb]':>13}{'margin':>9}{'|beta|_beta0':>14}")
    for (bank, kcas), b in sorted(req.items()):
        print(f"{bank:>5g}{kcas:>7g}{b['rud_ss_abs_mean']:>10.4f}"
              f"{b['N_used_ss_ftlb']:>13.0f}{b['N_rud_max_ftlb']:>13.0f}"
              f"{b['N_rud_max_ftlb']/max(b['N_used_ss_ftlb'],1e-6):>9.1f}"
              f"{b['beta_abs_mean_deg']:>14.4f}")

    print("\n=== 포화율 지도  (행=뱅크, 열=요축법칙 x 속도) ===")
    laws = YAW_LAW_GRID
    print(f"{'bank':>5}" + "".join(f"{law+'/'+str(int(v)):>13}"
                                    for law in laws for v in KCAS_GRID))
    idx = {(r["bank_deg"], r["kcas_ic"], r["yaw_law"]): r for r in rows}
    for bank in BANK_GRID:
        line = f"{bank:>5g}"
        for law in laws:
            for v in KCAS_GRID:
                line += f"{idx[(bank, v, law)]['sat_rudder_pct']:>13.1f}"
        print(line)
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
