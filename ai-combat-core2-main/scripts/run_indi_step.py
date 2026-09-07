"""L3 INDI 검증 — F16Plant + INDIRateController 로 45° 뱅크 홀드 재현.

tmp/f16_bfm_control_architecture.md §5.2 기준:
  · 최종 뱅크 ~43.9° 수렴, 피크 오버슈트 ~1.8°
  · rate-tracking q·r RMS < 3.5°/s

자세→각속도(omega_sp) 변환은 D3 에 따라 쿼터니언 shim(aircombat/control/attitude.py)을
쓴다 (Euler 특이점 제거). 목표=45° 뱅크, theta_trim 유지, heading 자유.
"""
from __future__ import annotations
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.fdm.plant import F16Plant
from aircombat.control.indi import INDIRateController, identify_G0
from aircombat.control.attitude import QuaternionAttitudeShim


def main() -> int:
    DT = 1.0 / 120.0
    p = F16Plant(dt=DT)
    p.set_ic(alt_ft=10000.0, vc_kts=350.0)   # start_engines 포함
    p["fcs/throttle-cmd-norm"] = 0.8
    p.trim()

    # 트림에서 제어효과 행렬 식별 (비파괴; 원 명령 복원)
    G0, qbar_ref = identify_G0(p.fdm)
    np.set_printoptions(precision=4, suppress=True, sign="+")
    print("Identified G0 (rows p,q,r / cols ail,ele,rud) at qbar_ref=%.1f psf:" % qbar_ref)
    print(G0)

    rate = INDIRateController(DT, G0, qbar_ref, k_rate=(9.0, 9.0, 6.0), filt_hz=25.0)
    rate.reset(u0=[p["fcs/aileron-cmd-norm"],
                   p["fcs/elevator-cmd-norm"],
                   p["fcs/rudder-cmd-norm"]])

    # 자세→각속도: 쿼터니언 shim (D3). Euler AttitudeToRate 대체.
    shim = QuaternionAttitudeShim(k_att=4.5, k_yaw_damp=1.5)
    theta_trim = p["attitude/theta-rad"]
    phi_sp = np.deg2rad(45.0)

    T = 8.0
    n = int(T / DT)
    err2 = np.zeros(3)
    peak_bank = 0.0
    for _ in range(n):
        phi = p["attitude/phi-rad"]; theta = p["attitude/theta-rad"]
        omega = np.array([p["velocities/p-rad_sec"],
                          p["velocities/q-rad_sec"],
                          p["velocities/r-rad_sec"]])
        qbar = p["aero/qbar-psf"]
        ang_acc = [p["accelerations/pdot-rad_sec2"],
                   p["accelerations/qdot-rad_sec2"],
                   p["accelerations/rdot-rad_sec2"]]

        psi = p["attitude/psi-rad"]   # heading 은 잡지 않음(psi_des = psi_cur)
        omega_sp = shim.rate_setpoint_euler(phi, theta, psi,
                                            phi_sp, theta_trim, psi, r_cur=omega[2])

        u = rate.update(omega, omega_sp, qbar, ang_accel=ang_acc)
        p["fcs/aileron-cmd-norm"] = u[0]
        p["fcs/elevator-cmd-norm"] = u[1]
        p["fcs/rudder-cmd-norm"] = u[2]
        p.step(1)

        err2 += (omega_sp - omega) ** 2
        peak_bank = max(peak_bank, abs(np.rad2deg(p["attitude/phi-rad"])))

    rms = np.rad2deg(np.sqrt(err2 / n))
    final_bank = np.rad2deg(p["attitude/phi-rad"])
    print("Rate-tracking RMS [deg/s]  p=%.2f q=%.2f r=%.2f" % tuple(rms))
    print("Final bank=%.1f deg (cmd 45), peak bank=%.1f deg" % (final_bank, peak_bank))

    # tmp §5.2 재현 판정
    ok = (abs(final_bank - 45.0) < 3.0) and (rms[1] < 3.5) and (rms[2] < 3.5)
    print("VERDICT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
