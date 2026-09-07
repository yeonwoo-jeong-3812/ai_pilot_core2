"""L2 검증 — 스크립트 표적에 대한 BFM 조절 추적 (전체 체인 통합).

체인: geometry → BFMGuidance → 쿼터니언 shim → CombinedLimiter → INDI → JSBSim.
아군은 JSBSim F-16, 표적은 로컬 NED 등속 점(스크립트). 아군 위치는 JSBSim NED
속도를 적분해 표적과 동일 프레임으로 추적한다.

감사 판정:
  · ATA 가 초기값보다 줄고 교리대역 부근으로 몰림 (기수를 조준점으로).
  · 속도가 파괴적으로 소진되지 않음(파이팅 대역 관리).
  · 조절 G 가 항상 리미터 이하 (당김은 조절, 반사적 max-G 아님 — D6).
"""
from __future__ import annotations
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.fdm.plant import F16Plant
from aircombat.control.indi import INDIRateController, identify_G0
from aircombat.control.limiter import CombinedLimiter
from aircombat.control.attitude import QuaternionAttitudeShim, euler_to_quat, quat_mul
from aircombat.guidance.bfm_guidance import BFMGuidance, AircraftKinematics, FT_S_TO_KT


def main() -> int:
    DT = 1.0 / 120.0
    p = F16Plant(dt=DT)
    p.set_ic(alt_ft=15000.0, vc_kts=350.0)
    p["fcs/throttle-cmd-norm"] = 0.85
    p.trim()
    G0, qbar_ref = identify_G0(p.fdm)

    indi = INDIRateController(DT, G0, qbar_ref, k_rate=(9.0, 9.0, 6.0), filt_hz=25.0)
    indi.reset(u0=[p["fcs/aileron-cmd-norm"], p["fcs/elevator-cmd-norm"],
                   p["fcs/rudder-cmd-norm"]])
    limiter = CombinedLimiter()
    shim = QuaternionAttitudeShim(k_att=4.0, k_yaw_damp=1.5, rate_limit_dps=(180, 60, 30))
    guid = BFMGuidance(limiter=limiter)

    # 로컬 NED (ft). 아군 원점 북향, 표적 우전방 등속 북향.
    own_pos = np.array([0.0, 0.0, -15000.0])
    foe_pos = np.array([3000.0, 3000.0, -15000.0])   # ATA≈45°
    foe_vel = np.array([320.0 * 1.68781, 0.0, 0.0])  # 320kt 북향 직진

    T = 25.0
    n = int(T / DT)
    ata0 = None
    ata_min = float("inf"); kcas_min = float("inf"); g_invariant = True
    log = []
    for k in range(n):
        phi = p["attitude/phi-rad"]; theta = p["attitude/theta-rad"]; psi = p["attitude/psi-rad"]
        pqr = np.array([p["velocities/p-rad_sec"], p["velocities/q-rad_sec"],
                        p["velocities/r-rad_sec"]])
        v_ned = np.array([p["velocities/v-north-fps"], p["velocities/v-east-fps"],
                          p["velocities/v-down-fps"]])
        v_fps = p["velocities/vt-fps"]; kcas = p["velocities/vc-kts"]; qbar = p["aero/qbar-psf"]
        ang = [p["accelerations/pdot-rad_sec2"], p["accelerations/qdot-rad_sec2"],
               p["accelerations/rdot-rad_sec2"]]

        own_pos = own_pos + v_ned * DT
        foe_pos = foe_pos + foe_vel * DT

        me = AircraftKinematics(own_pos, v_ned, phi, theta, psi, v_fps, kcas)
        gc = guid.compute(me, foe_pos, foe_vel, pursuit="lead")

        # 조립: roll 은 shim(dphi 증분), pitch 는 당김 G-rate, yaw 는 감쇠
        q_cur = euler_to_quat(phi, theta, psi)
        q_des = quat_mul(q_cur, euler_to_quat(gc.dphi_cmd, 0.0, 0.0))
        omega_sp = shim.rate_setpoint(q_cur, q_des, r_cur=pqr[2])
        omega_sp[1] = gc.q_cmd
        omega_sp, flags = limiter.limit_omega_sp(omega_sp, v_fps, kcas)

        u = indi.update(pqr, omega_sp, qbar, ang_accel=ang)
        p.set_input([gc.thrust_cmd, u[1], u[0], u[2]])  # [thr, elev, ail, rud]
        p.step(1)

        a = gc.audit
        if ata0 is None:
            ata0 = a["ata_deg"]
        ata_min = min(ata_min, a["ata_deg"])
        kcas_min = min(kcas_min, a["kcas"])
        g_invariant = g_invariant and (gc.g_target <= a["g_avail"] + 1e-6)
        if k % int(2.5 / DT) == 0 or k == n - 1:
            log.append((k * DT, a["ata_deg"], a["kcas"], a["g_target"],
                        a["g_avail"], a["range_ft"]))

    print(" t[s]  ATA[deg]  KCAS  G_tgt  G_avail  range[ft]")
    for t, ata, vk, gt, ga, rng in log:
        print("%5.1f   %6.1f  %4.0f  %5.2f   %5.2f   %7.0f" % (t, ata, vk, gt, ga, rng))

    print("\ninitial ATA=%.1f  min ATA=%.1f  min KCAS=%.0f" % (ata0, ata_min, kcas_min))
    # L2 범위 판정: 조절이 기수를 조준점으로 몰고(min ATA↓), G 가 리미터 이하이며,
    # 에너지가 파괴적으로 소진되지 않음. (지속 추적·오버슈트 방지는 L1 전술=5단계 몫.)
    ok = (ata_min < 15.0) and g_invariant and (kcas_min > 250.0)
    print("VERDICT:", "PASS" if ok else "FAIL",
          "(min ATA<15° 조절성공, G≤limiter 항상, KCAS>250)")
    print("주: 후반 ATA 급증은 아군이 표적을 추월한 것 — lag 전환은 L1(5단계) 담당.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
