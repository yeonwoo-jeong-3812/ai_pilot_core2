"""러더 명령 1.0 스텝의 과도 타면각 — 2.75deg 가 트래블 한계인지 FLCS 평형인지."""
import os
import sys
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from aircombat.fdm.plant import F16Plant

p = F16Plant(dt=1/120.)
p.set_ic(alt_ft=15000., vc_kts=400.)
p["fcs/throttle-cmd-norm"] = 0.8
p.trim(); p.step(1)
p["fcs/rudder-cmd-norm"] = 1.0
peak = 0.0
print(f"{'t':>6}{'rud_cmd':>9}{'rud_pos_deg':>13}{'rud_pos_norm':>14}{'yaw_pid':>10}{'beta':>8}{'r_dps':>8}")
for k in range(600):
    p.fdm.run()
    d = p["fcs/rudder-pos-deg"]
    peak = max(peak, abs(d))
    if k in (1, 3, 6, 12, 24, 48, 96, 180, 360, 599):
        print(f"{k/120.:>6.3f}{p['fcs/rudder-cmd-norm']:>9.2f}{d:>13.3f}"
              f"{p['fcs/rudder-pos-norm']:>14.4f}{p['fcs/yaw-load-pid']:>10.4f}"
              f"{np.rad2deg(p['aero/beta-rad']):>8.3f}"
              f"{np.rad2deg(p['velocities/r-rad_sec']):>8.3f}")
print(f"\npeak |rudder-pos| = {peak:.3f} deg   (aerosurface_scale range = +-30.0 deg)")
