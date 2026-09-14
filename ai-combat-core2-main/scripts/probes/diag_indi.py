"""왜 요 요구 모멘트가 작은데 러더가 100% 포화인가 — INDI 배분 내부 계측."""
import os, sys
import numpy as np
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)
from aircombat.fdm.plant import F16Plant
from aircombat.control.indi import INDIRateController, identify_G0
from aircombat.control.attitude import QuaternionAttitudeShim
from aircombat.control.limiter import CombinedLimiter, LimiterConfig, G_FT_S2

DT = 1/120.
K_RATE = np.array([9., 9., 6.])


def run(bank_deg, yaw_ff, kcas=400., alt=15000., T=10.0):
    p = F16Plant(dt=DT); p.set_ic(alt_ft=alt, vc_kts=kcas)
    p["fcs/throttle-cmd-norm"] = 0.8; p.trim()
    G0, qref = identify_G0(p.fdm)
    rate = INDIRateController(DT, G0, qref, k_rate=K_RATE, filt_hz=25.)
    rate.reset(u0=[p["fcs/aileron-cmd-norm"], p["fcs/elevator-cmd-norm"],
                   p["fcs/rudder-cmd-norm"]])
    shim = QuaternionAttitudeShim(k_att=4.5, k_yaw_damp=1.5)
    lim = CombinedLimiter(LimiterConfig())
    th0 = p["attitude/theta-rad"]; phi_sp = np.deg2rad(bank_deg)
    n = int(T/DT)
    out = []
    for k in range(n):
        phi = p["attitude/phi-rad"]; th = p["attitude/theta-rad"]; psi = p["attitude/psi-rad"]
        om = np.array([p["velocities/p-rad_sec"], p["velocities/q-rad_sec"], p["velocities/r-rad_sec"]])
        v, kc = p["velocities/vt-fps"], p["velocities/vc-kts"]
        qbar = p["aero/qbar-psf"]
        aa = np.array([p["accelerations/pdot-rad_sec2"], p["accelerations/qdot-rad_sec2"],
                       p["accelerations/rdot-rad_sec2"]])
        sp = shim.rate_setpoint_euler(phi, th, psi, phi_sp, th0, psi, r_cur=om[2])
        sp[2] = (G_FT_S2*np.sin(phi)*np.cos(th)/max(v,1.) if yaw_ff == "sin"
                 else G_FT_S2*np.tan(phi)/max(v,1.))
        sp, _ = lim.limit_omega_sp(sp, v, kc, g_lift=float(np.cos(phi)*np.cos(th)))
        # --- INDI 내부 재현 (update 와 동일 순서) ---
        alpha_f = rate.f_acc(aa)
        u_f = rate.f_act(rate.u_prev)
        om_f = rate.f_rate(om)
        nu = K_RATE*(sp - om_f)
        G = (max(qbar, rate.qbar_min)/qref)*rate.G0
        du = np.linalg.solve(G, nu - alpha_f)
        u = np.clip(u_f + du, -1, 1)
        rate.u_prev = u; rate.omega_prev = om
        p["fcs/aileron-cmd-norm"] = u[0]; p["fcs/elevator-cmd-norm"] = u[1]
        p["fcs/rudder-cmd-norm"] = u[2]
        p.step(1)
        out.append(dict(t=k*DT, nu=nu.copy(), alpha=alpha_f.copy(), du=du.copy(),
                        u=u.copy(), uf=u_f.copy(), sp=sp.copy(), om=om.copy(),
                        beta=p["aero/beta-rad"], qbar=qbar))
    return out, G0, qref, p


for yff in ("tan", "sin"):
    out, G0, qref, p = run(60., yff)
    np.set_printoptions(precision=4, suppress=True)
    print(f"\n===== bank60 400KCAS yaw_ff={yff} =====")
    print("G0=\n", G0, "\nG0^-1=\n", np.linalg.inv(G0))
    for row in out[-3:]:
        print(f"t={row['t']:.2f}")
        print("   sp(dps) =", np.rad2deg(row['sp']).round(3),
              " om(dps) =", np.rad2deg(row['om']).round(3))
        print("   nu      =", row['nu'].round(5), " alpha_f =", row['alpha'].round(5),
              " nu-alpha=", (row['nu']-row['alpha']).round(5))
        print("   du      =", row['du'].round(5), " u_f =", row['uf'].round(4),
              " u =", row['u'].round(4))
    # du 의 각 축 기여도 분해: du = Ginv @ e ; 러더 성분 = Ginv[2,:] * e
    Ginv = np.linalg.inv((out[-1]['qbar']/qref)*G0)
    e = out[-1]['nu'] - out[-1]['alpha']
    print("   rudder du 기여 분해 (Ginv[2,j]*e_j):", (Ginv[2, :]*e).round(5),
          " 합=", float(Ginv[2, :] @ e).round(5))
    print("   aileron du 기여 분해:", (Ginv[0, :]*e).round(5))
