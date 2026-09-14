"""fbw-override=1(FLCS 우회) 플랜트 특성: 개루프 안정성, 최대 Nz, G0, INDI 폐루프."""
import os
import sys, io, contextlib
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from aircombat.fdm.plant import F16Plant
from aircombat.control.indi import INDIRateController, identify_G0
from aircombat.control.limiter import G_FT_S2
DT=1/120.

def mk(fbw, kcas=400.):
    p=F16Plant(dt=DT); p.set_ic(alt_ft=15000., vc_kts=kcas)
    p["fcs/throttle-cmd-norm"]=1.0; p["fcs/fbw-override"]=fbw; p.trim(); p.step(1)
    return p

np.set_printoptions(precision=3, suppress=True)
for fbw in (0,1):
    print(f"\n######## fbw-override={fbw} ########")
    # 1) 개루프: 트림 후 스틱 중립 유지 10초
    p=mk(fbw); th0=np.rad2deg(p["attitude/theta-rad"]); a0=np.rad2deg(p["aero/alpha-rad"])
    for _ in range(1200): p.fdm.run()
    print(f"개루프 10s: alpha {a0:.2f}->{np.rad2deg(p['aero/alpha-rad']):.2f}deg, "
          f"theta {th0:.2f}->{np.rad2deg(p['attitude/theta-rad']):.2f}deg, q={np.rad2deg(p['velocities/q-rad_sec']):.2f}dps")
    # 2) 풀애프트 3초 최대 Nz
    for kc in (400.,450.):
        p=mk(fbw,kc); nz=a=0.
        for _ in range(360):
            p["fcs/elevator-cmd-norm"]=-1.0; p.fdm.run()
            nz=max(nz,p["accelerations/Nz"]); a=max(a,np.rad2deg(p["aero/alpha-rad"]))
            if a>40: break
        print(f"풀애프트 3s @{kc:.0f}KCAS: Nz_peak={nz:.2f}  alpha_max={a:.1f}")
    # 3) G0 대각
    p=mk(fbw); G0,qr=identify_G0(p.fdm); print("G0 diag:", np.diag(G0), " qbar_ref", round(qr,1))
    # 4) INDI 폐루프: 목표 5G/7G 순수당김 3초, k=1 f=25
    for gt in (5.,7.,9.):
        p=mk(fbw); G0,qr=identify_G0(p.fdm)
        c=INDIRateController(DT,G0,qr,k_rate=(9,9,6),filt_hz=25.)
        c.reset(u0=[p["fcs/aileron-cmd-norm"],p["fcs/elevator-cmd-norm"],p["fcs/rudder-cmd-norm"]])
        nz=a=0.; osc=[]
        for k in range(360):
            phi,th=p["attitude/phi-rad"],p["attitude/theta-rad"]
            pqr=np.array([p["velocities/p-rad_sec"],p["velocities/q-rad_sec"],p["velocities/r-rad_sec"]])
            v=p["velocities/vt-fps"]; gl=np.cos(phi)*np.cos(th)
            sp=np.array([-4*phi,(gt-gl)*G_FT_S2/v,0.0])
            aa=[p["accelerations/pdot-rad_sec2"],p["accelerations/qdot-rad_sec2"],p["accelerations/rdot-rad_sec2"]]
            u=c.update(pqr,sp,p["aero/qbar-psf"],ang_accel=aa)
            p.set_input([1.0,u[1],u[0],u[2]]); p.fdm.run()
            nz=max(nz,p["accelerations/Nz"]); a=max(a,np.rad2deg(p["aero/alpha-rad"])); osc.append(p["accelerations/Nz"])
        last=np.array(osc[-120:])
        print(f"INDI 목표{gt:.0f}G: Nz_peak={nz:.2f} Nz_last1s mean={last.mean():.2f} p2p={last.max()-last.min():.2f} alpha_max={a:.1f}")
