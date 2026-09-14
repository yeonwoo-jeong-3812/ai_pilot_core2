"""실제 자가대전 1경기에서 L3 지령(omega_sp) 분포 계측 — 엔진 무수정(외부 래핑)."""
import os, sys, time, io, contextlib
import numpy as np
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, R); os.chdir(R)
os.environ.setdefault("AICOMBAT_ALLOW_CUSTOM", "1")
from aircombat.engine.factory import load_policy, make_pilot
from aircombat.engine.match import Match
from aircombat.engine.scenarios import initial_conditions

ic = initial_conditions("duel", seed=1)
pilots = {}
for c, y in (("Blue", "examples/textbook_headon.yaml"), ("Red", "examples/starter.yaml")):
    pol, doc = load_policy(y)
    pilots[c] = make_pilot(c, ic[c.lower()], pol, doc)

logs = {c: [] for c in pilots}
for c, pl in pilots.items():
    orig = pl.limiter.limit_omega_sp
    def wrap(omega_sp, v, kcas, g_lift=0.0, _o=orig, _c=c, _p=pl):
        out, fl = _o(omega_sp, v, kcas, g_lift=g_lift)
        P = _p.plant
        logs[_c].append((P["velocities/p-rad_sec"], P["velocities/q-rad_sec"], P["velocities/r-rad_sec"],
                         *out, P["accelerations/Nz"], np.rad2deg(P["aero/alpha-rad"]), kcas,
                         P["position/h-sl-ft"], np.rad2deg(P["attitude/phi-rad"]),
                         P["fcs/elevator-cmd-norm"], P["fcs/rudder-cmd-norm"], P["fcs/aileron-cmd-norm"]))
        return out, fl
    pl.limiter.limit_omega_sp = wrap

t0 = time.perf_counter()
with contextlib.redirect_stdout(io.StringIO()):
    res = Match(pilots["Blue"], pilots["Red"], duration_s=120.0, log_hz=0, wall_limit_s=600).run()
wall = time.perf_counter() - t0
print(f"match 120s sim -> wall {wall:.1f}s  result={getattr(res,'winner',None)}/{getattr(res,'condition',None)}  t_end={getattr(res,'t',None)}")
for c, L in logs.items():
    a = np.array(L)
    if len(a) == 0: continue
    d = np.rad2deg
    p, q, r, psp, qsp, rsp = (a[:, i] for i in range(6))
    nz, al, kc, h, ph, ele, rud, ail = (a[:, i] for i in range(6, 14))
    pct = lambda x: np.percentile(np.abs(x), [50, 95, 99])
    print(f"\n[{c}] {len(a)} L3 ticks ({len(a)/120:.1f}s)")
    print("  |p_sp| dps p50/95/99:", d(pct(psp)).round(1), "  |q_sp|:", d(pct(qsp)).round(1), "  |r_sp|:", d(pct(rsp)).round(2))
    print("  Nz p50/95/99:", np.percentile(nz, [50, 95, 99]).round(2), " max", nz.max().round(2), " min", nz.min().round(2))
    print("  alpha p95/max:", np.percentile(al, 95).round(1), al.max().round(1), "  KCAS range:", kc.min().round(0), kc.max().round(0),
          "  alt range:", h.min().round(0), h.max().round(0))
    print("  |bank| p50/95:", np.percentile(np.abs(ph), [50, 95]).round(0),
          "  sat ele/ail/rud %:", (100*np.mean(np.abs(ele) > .999)).round(1), (100*np.mean(np.abs(ail) > .999)).round(1),
          (100*np.mean(np.abs(rud) > .999)).round(1))
    # 지령 대역폭: q_sp 파워스펙트럼 95% 누적 주파수
    x = qsp - qsp.mean(); F = np.abs(np.fft.rfft(x))**2; f = np.fft.rfftfreq(len(x), 1/120.)
    c95 = f[np.searchsorted(np.cumsum(F)/F.sum(), 0.95)]
    xp = psp - psp.mean(); Fp = np.abs(np.fft.rfft(xp))**2
    print(f"  cmd bandwidth (95% power): q_sp {c95:.2f} Hz, p_sp {f[np.searchsorted(np.cumsum(Fp)/Fp.sum(), 0.95)]:.2f} Hz")
    print(f"  rms rate tracking err dps: p {d(np.sqrt(np.mean((psp-p)**2))):.2f}  q {d(np.sqrt(np.mean((qsp-q)**2))):.2f}  r {d(np.sqrt(np.mean((rsp-r)**2))):.2f}")
