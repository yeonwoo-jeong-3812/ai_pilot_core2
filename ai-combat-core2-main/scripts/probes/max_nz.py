"""INDI 없이 생(raw) 풀 애프트 스틱 — 이 플랜트가 낼 수 있는 최대 Nz."""
import os
import sys
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from aircombat.fdm.plant import F16Plant

print(f"{'alt':>7}{'kcas':>6}{'stick':>7}{'T':>5}{'nz_peak':>9}{'nz_end':>8}"
      f"{'alpha_max':>11}{'q_max_dps':>11}{'kcas_end':>10}{'ele_pos_deg':>13}")
for alt, kcas in ((15000., 400.), (15000., 450.), (15000., 350.), (15000., 300.)):
    for T in (3.0, 8.0):
        p = F16Plant(dt=1/120.)
        p.set_ic(alt_ft=alt, vc_kts=kcas)
        p["fcs/throttle-cmd-norm"] = 1.0
        p.trim(); p.step(1)
        nz = a = q = 0.0
        ele = 0.0
        for k in range(int(T*120)):
            p["fcs/elevator-cmd-norm"] = -1.0      # 풀 애프트 (당김)
            p["fcs/aileron-cmd-norm"] = 0.0
            p["fcs/rudder-cmd-norm"] = 0.0
            p.fdm.run()
            nz = max(nz, p["accelerations/Nz"])
            a = max(a, np.rad2deg(p["aero/alpha-rad"]))
            q = max(q, np.rad2deg(p["velocities/q-rad_sec"]))
            ele = min(ele, np.rad2deg(p["fcs/elevator-pos-rad"]))
        print(f"{alt:>7.0f}{kcas:>6.0f}{-1.0:>7.1f}{T:>5.0f}{nz:>9.3f}"
              f"{p['accelerations/Nz']:>8.3f}{a:>11.2f}{q:>11.2f}"
              f"{p['velocities/vc-kts']:>10.1f}{ele:>13.2f}")
