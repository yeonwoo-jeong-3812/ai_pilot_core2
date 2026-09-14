"""러더 명령(-1..1) -> 실제 타면 각도. native FLCS 가 동압으로 트래블을 줄이는지 확인."""
import os
import sys
import numpy as np
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)
from aircombat.fdm.plant import F16Plant

for alt, kcas in [(15000., 400.), (15000., 450.), (15000., 250.), (10000., 350.)]:
    p = F16Plant(dt=1/120.)
    p.set_ic(alt_ft=alt, vc_kts=kcas)
    p["fcs/throttle-cmd-norm"] = 0.8
    p.trim()
    p.step(1)
    qbar = p["aero/qbar-psf"]
    out = []
    for cmd in (0.25, 0.5, 1.0):
        p["fcs/rudder-cmd-norm"] = cmd
        for _ in range(120):          # 1초 안정화
            p.fdm.run()
        out.append((cmd, p["fcs/rudder-pos-deg"], p["aero/beta-rad"]*57.2958))
    print(f"alt={alt:.0f}ft kcas={kcas:.0f} qbar={qbar:.1f}psf  " +
          "  ".join(f"cmd{c:g}->{d:6.2f}deg(b={b:5.2f})" for c, d, b in out))
