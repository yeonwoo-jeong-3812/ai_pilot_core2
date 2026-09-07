"""L3 코너 검증 — 지속 최대G 선회에서 INDI 가 지령 q 를 따라가는가.

run_indi_step.py 는 1G·45° 뱅크 스텝(트림 근방)만 본다. 그런데 BFM 은 α 10–15°,
지속 최대G 에서 벌어지고, 거기서는

  · f16.xml elevator-scheduler 의 α 게인이 1.0 → 0.5 로 떨어지고
  · pitch-scheduler 가 ±1 로 포화한다

즉 INDI 가 쓰는 모델 `G = (qbar/qbar_ref)·G0`(트림 α≈1° 에서 식별) 이 실제
제어효과를 크게 과대추정하는 영역이다. INDI 의 주장은 "측정 각가속도가 그걸
흡수한다" 이므로, **그 주장이 코너에서 성립하는지**를 여기서 확인한다.

판정: 과도 구간 이후 q 추종 오차와, 리미터가 허용한 G 대비 실제 달성 G.
"""
from __future__ import annotations
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.fdm.plant import F16Plant
from aircombat.control.indi import INDIRateController, identify_G0
from aircombat.control.attitude import QuaternionAttitudeShim, euler_to_quat, quat_mul
from aircombat.control.limiter import CombinedLimiter, LimiterConfig, G_FT_S2

DT = 1.0 / 120.0
BANK_DEG = 80.0        # 지속 선회 뱅크
T_TOTAL = 12.0
T_SETTLE = 4.0         # 이 시각 이후를 정상상태로 본다


def sustained_turn(kcas0: float, alt_ft: float = 15000.0, t_total: float = T_TOTAL):
    """지속 최대G 선회를 실제 L3 스택으로 돌리고 정상상태 요약을 돌려준다."""
    p = F16Plant(dt=DT)
    p.set_ic(alt_ft=alt_ft, vc_kts=kcas0)
    p["fcs/throttle-cmd-norm"] = 1.0
    p.trim()
    G0, qbar_ref = identify_G0(p.fdm)
    indi = INDIRateController(DT, G0, qbar_ref, k_rate=(9.0, 9.0, 6.0), filt_hz=25.0)
    indi.reset(u0=[p["fcs/aileron-cmd-norm"], p["fcs/elevator-cmd-norm"],
                   p["fcs/rudder-cmd-norm"]])
    shim = QuaternionAttitudeShim(k_att=4.0, k_yaw_damp=1.5,
                                  rate_limit_dps=(180.0, 60.0, 30.0))
    limiter = CombinedLimiter(LimiterConfig())
    phi_target = np.radians(BANK_DEG)
    rows = []
    for k in range(int(t_total / DT)):
        phi, theta = p["attitude/phi-rad"], p["attitude/theta-rad"]
        psi = p["attitude/psi-rad"]
        pqr = np.array([p["velocities/p-rad_sec"], p["velocities/q-rad_sec"],
                        p["velocities/r-rad_sec"]])
        v_fps, kcas = p["velocities/vt-fps"], p["velocities/vc-kts"]
        g_lift = float(np.cos(phi) * np.cos(theta))
        g_target = limiter.max_load_factor(kcas)
        q_cmd = (g_target - g_lift) * G_FT_S2 / max(v_fps, 1.0)
        q_cur = euler_to_quat(phi, theta, psi)
        q_des = quat_mul(q_cur, euler_to_quat(phi_target - phi, 0.0, 0.0))
        omega_sp = shim.rate_setpoint(q_cur, q_des, r_cur=pqr[2])
        omega_sp[1] = q_cmd
        omega_sp, _ = limiter.limit_omega_sp(omega_sp, v_fps, kcas, g_lift=g_lift)
        u = indi.update(pqr, omega_sp, p["aero/qbar-psf"], ang_accel=[
            p["accelerations/pdot-rad_sec2"], p["accelerations/qdot-rad_sec2"],
            p["accelerations/rdot-rad_sec2"]])
        p.set_input([1.0, u[1], u[0], u[2]])
        p.step(1)
        # 달성 G 는 q 에서 환산(부호 규약 무관): n = q·V/g + cosφcosθ
        q_act = p["velocities/q-rad_sec"]
        n_act = q_act * p["velocities/vt-fps"] / G_FT_S2 + g_lift
        rows.append((k * DT, omega_sp[1], q_act, np.degrees(p["aero/alpha-rad"]),
                     p["velocities/vc-kts"], n_act, g_target,
                     np.degrees(p["attitude/phi-rad"]), u[1]))
    a = np.array(rows)
    return a[a[:, 0] >= T_SETTLE], np.diag(G0), float(np.degrees(p["aero/alpha-rad"]))


def sweep() -> int:
    """속도별 실제 달성 가능 G — 리미터의 코너 플래토 모델을 실측 대조."""
    print("지속 80° 뱅크 최대G 선회, 15,000ft, full AB. G_달성 은 q 에서 환산.")
    print(f"{'KCAS0':>6} {'KCAS_ss':>8} {'alpha':>6} {'G_리미터':>9} {'G_달성':>8}"
          f" {'q지령':>7} {'q실제':>7} {'elev포화':>9}")
    print("-" * 70)
    for kcas0 in (300.0, 350.0, 400.0, 450.0, 500.0, 550.0):
        ss, _, _ = sustained_turn(kcas0)
        print(f"{kcas0:>6.0f} {np.mean(ss[:, 4]):>8.1f} {np.mean(ss[:, 3]):>6.2f}"
              f" {np.mean(ss[:, 6]):>9.2f} {np.mean(ss[:, 5]):>8.2f}"
              f" {np.degrees(np.mean(ss[:, 1])):>7.2f}"
              f" {np.degrees(np.mean(ss[:, 2])):>7.2f}"
              f" {100.0 * np.mean(np.abs(ss[:, 8]) > 0.999):>8.0f}%")
    return 0


def main() -> int:
    if "sweep" in sys.argv[1:]:
        return sweep()
    p = F16Plant(dt=DT)
    p.set_ic(alt_ft=15000.0, vc_kts=400.0)
    p["fcs/throttle-cmd-norm"] = 1.0        # full AB — 지속 선회 속도 유지
    p.trim()

    # Pilot.setup() 과 동일 구성
    G0, qbar_ref = identify_G0(p.fdm)
    indi = INDIRateController(DT, G0, qbar_ref, k_rate=(9.0, 9.0, 6.0), filt_hz=25.0)
    indi.reset(u0=[p["fcs/aileron-cmd-norm"], p["fcs/elevator-cmd-norm"],
                   p["fcs/rudder-cmd-norm"]])
    shim = QuaternionAttitudeShim(k_att=4.0, k_yaw_damp=1.5,
                                  rate_limit_dps=(180.0, 60.0, 30.0))
    limiter = CombinedLimiter(LimiterConfig())
    print(f"G0 diag(트림 α={np.degrees(p['aero/alpha-rad']):.2f}°) = "
          f"{np.diag(G0).round(3)}  qbar_ref={qbar_ref:.1f}")

    phi_target = np.radians(BANK_DEG)
    rows = []
    for k in range(int(T_TOTAL / DT)):
        phi, theta = p["attitude/phi-rad"], p["attitude/theta-rad"]
        psi = p["attitude/psi-rad"]
        pqr = np.array([p["velocities/p-rad_sec"], p["velocities/q-rad_sec"],
                        p["velocities/r-rad_sec"]])
        v_fps, kcas = p["velocities/vt-fps"], p["velocities/vc-kts"]
        g_lift = float(np.cos(phi) * np.cos(theta))

        # L2 대역: 뱅크 배치 + 리미터가 허용하는 최대 G 당김 (guidance 의 max_g 국면)
        g_target = limiter.max_load_factor(kcas)
        q_cmd = (g_target - g_lift) * G_FT_S2 / max(v_fps, 1.0)

        q_cur = euler_to_quat(phi, theta, psi)
        q_des = quat_mul(q_cur, euler_to_quat(phi_target - phi, 0.0, 0.0))
        omega_sp = shim.rate_setpoint(q_cur, q_des, r_cur=pqr[2])
        omega_sp[1] = q_cmd
        omega_sp, flags = limiter.limit_omega_sp(omega_sp, v_fps, kcas, g_lift=g_lift)

        u = indi.update(pqr, omega_sp, p["aero/qbar-psf"], ang_accel=[
            p["accelerations/pdot-rad_sec2"], p["accelerations/qdot-rad_sec2"],
            p["accelerations/rdot-rad_sec2"]])
        p.set_input([1.0, u[1], u[0], u[2]])
        p.step(1)

        rows.append((k * DT, omega_sp[1], p["velocities/q-rad_sec"],
                     np.degrees(p["aero/alpha-rad"]), p["velocities/vc-kts"],
                     p["accelerations/n-pilot-z-norm"], flags["g_max"],
                     np.degrees(p["attitude/phi-rad"]), u[1]))

    a = np.array(rows)
    ss = a[a[:, 0] >= T_SETTLE]
    q_sp, q_act = ss[:, 1], ss[:, 2]
    rms = np.degrees(np.sqrt(np.mean((q_sp - q_act) ** 2)))
    bias = 100.0 * np.mean(q_act - q_sp) / max(abs(np.mean(q_sp)), 1e-9)

    print(f"\n정상상태(t≥{T_SETTLE:.0f}s, n={len(ss)}):")
    print(f"  뱅크        {np.mean(ss[:, 7]):>7.1f} deg (지령 {BANK_DEG:.0f})")
    print(f"  alpha       {np.mean(ss[:, 3]):>7.2f} deg   KCAS {np.mean(ss[:, 4]):>6.1f}")
    print(f"  q 지령/실제 {np.degrees(np.mean(q_sp)):>7.2f} / "
          f"{np.degrees(np.mean(q_act)):>6.2f} deg/s")
    print(f"  q 추종 RMS  {rms:>7.2f} deg/s   편향 {bias:>+6.1f} %")
    print(f"  G 허용/달성 {np.mean(ss[:, 6]):>7.2f} / {np.mean(ss[:, 5]):>6.2f}")
    print(f"  elevator u  {np.mean(ss[:, 8]):>7.3f} "
          f"(포화 비율 {100.0 * np.mean(np.abs(ss[:, 8]) > 0.999):.0f}%)")

    # 판정: 코너에서도 지령 q 를 따라가야 한다. 편향 20% 이내를 회귀 상한으로 둔다.
    ok = abs(bias) < 20.0
    print("\nVERDICT:", "PASS" if ok else "FAIL — 코너에서 q 추종 실패")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
