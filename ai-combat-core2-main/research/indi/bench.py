"""E1 — INDI 추종 벤치 (paper.md §7-B: 논문 3·4·5 공통 실험).

운용점 6개(250/350/450 KCAS × 15k/25k ft) × 시험 4종을 트림에서 새로 시작해 비행:
  bank     뱅크 더블릿 +60°(3 s) → −60°(3 s) → 0°(2 s)   — shim 경유 → k_att 평가
  p3211    롤레이트 3211, 60°/s, Δt 0.5 s               — 논문 5
  q_dbl    ΔG ±2 더블릿(각 1 s) + 2 s 유지              — 논문 4·5
  q_step   ΔG +4 스텝 3 s → 해제 2 s
제어 경로는 Pilot.control_step 과 동일: shim → 한계(manual 봉투) → 센서 → INDI. 모델 f16fix.
오차 기준은 **한계 통과 후 명령**(리미터 절단은 제어기 오차가 아님), bank 는 뱅크각.

    python research/indi/bench.py                 # 기준 INDIConfig, 명목 센서(gyro 0.1°/s)
    python research/indi/bench.py --k_q 14 --json out.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import zlib

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aircombat.control.attitude import QuaternionAttitudeShim, euler_to_quat, quat_mul
from aircombat.control.indi import INDIConfig, INDIRateController, RateSensor, SensorConfig, identify_G0
from aircombat.control.limiter import CombinedLimiter, LimiterConfig, G_FT_S2
from aircombat.fdm.plant import F16Plant
from limits import LimitMonitor
from runner import MODEL, NZ_PROTECT

DT = 1.0 / 120.0
POINTS = [(kcas, alt) for alt in (15000.0, 25000.0) for kcas in (250.0, 350.0, 450.0)]
TESTS = ("bank", "p3211", "q_dbl", "q_step")
NOMINAL_SENSOR = SensorConfig(kind="gyro", gyro_sigma_dps=0.1)   # plan.md 연구 기본 조건
BANK_DEG, P_DPS, DBL_G, STEP_G = 60.0, 60.0, 2.0, 4.0


def _profile(test: str, t: float) -> float:
    """시험 신호 (bank: deg, p3211: deg/s, q_*: ΔG)."""
    if test == "bank":
        return BANK_DEG if t < 3 else (-BANK_DEG if t < 6 else 0.0)
    if test == "p3211":
        u = t / 0.5
        return P_DPS * (1 if u < 3 else -1 if u < 5 else 1 if u < 6 else -1 if u < 7 else 0)
    if test == "q_dbl":
        return DBL_G if t < 1 else (-DBL_G if t < 2 else 0.0)
    return STEP_G if t < 3 else 0.0


DURATION = {"bank": 8.0, "p3211": 5.0, "q_dbl": 4.0, "q_step": 5.0}
AMP = {"bank": BANK_DEG, "p3211": P_DPS, "q_dbl": DBL_G, "q_step": STEP_G}


def run_test(cfg: INDIConfig, test: str, kcas: float, alt: float,
             sensor: SensorConfig = NOMINAL_SENSOR) -> dict:
    p = F16Plant(dt=DT, model=MODEL)
    p.set_ic(alt_ft=alt, vc_kts=kcas)
    p["fcs/throttle-cmd-norm"] = 0.85
    p.trim()
    G0, qbar_ref = identify_G0(p.fdm)
    indi = INDIRateController(DT, G0, qbar_ref, k_rate=(cfg.k_p, cfg.k_q, cfg.k_r),
                              filt_hz=cfg.filt_hz, k_ff=cfg.k_ff, lam=cfg.lam)
    indi.reset(u0=[p["fcs/aileron-cmd-norm"], p["fcs/elevator-cmd-norm"], p["fcs/rudder-cmd-norm"]])
    shim = QuaternionAttitudeShim(k_att=cfg.k_att, k_yaw_damp=1.5, rate_limit_dps=(180.0, 60.0, 30.0))
    lim = CombinedLimiter(LimiterConfig(envelope="manual", nz_protect=NZ_PROTECT is not None,
                                        **(NZ_PROTECT or {})))
    # 공통 난수(CRN): 같은 (시험, 운용점)은 config 와 무관하게 같은 잡음열 → 대응 비교.
    sen = RateSensor(dataclasses.replace(sensor, seed=zlib.crc32(f"{test}{kcas}{alt}".encode())))
    mon = LimitMonitor(p, DT)
    theta0 = p["attitude/theta-rad"]
    ref, y, us = [], [], []
    for k in range(int(DURATION[test] / DT)):
        t = k * DT
        phi, theta, psi = p["attitude/phi-rad"], p["attitude/theta-rad"], p["attitude/psi-rad"]
        pqr = np.array([p["velocities/p-rad_sec"], p["velocities/q-rad_sec"], p["velocities/r-rad_sec"]])
        v, kc = p["velocities/vt-fps"], p["velocities/vc-kts"]
        g_lift = float(np.cos(phi) * np.cos(theta))
        cmd = _profile(test, t)
        if test == "bank":
            sp = shim.rate_setpoint_euler(phi, theta, psi, np.radians(cmd), theta0, psi, r_cur=pqr[2])
        else:
            q_cur = euler_to_quat(phi, theta, psi)
            sp = shim.rate_setpoint(q_cur, quat_mul(q_cur, euler_to_quat(0.0, 0.0, 0.0)), r_cur=pqr[2])
            if test == "p3211":
                sp[0] = np.radians(cmd)
                sp[1] = 0.0
            else:   # ΔG 명령 → 양력면 pitch rate (중력 보상 포함, Pilot 과 동일 환산)
                sp[0] = 0.0
                sp[1] = (1.0 + cmd - g_lift) * G_FT_S2 / max(v, 1.0)
        sp, _ = lim.limit_omega_sp(sp, v, kc, g_lift=g_lift, nz=p["accelerations/Nz"], q_meas=float(pqr[1]))
        pqr_m, acc_m = sen(pqr, [p["accelerations/pdot-rad_sec2"], p["accelerations/qdot-rad_sec2"],
                                 p["accelerations/rdot-rad_sec2"]])
        u = indi.update(pqr_m, sp, p["aero/qbar-psf"], ang_accel=acc_m)
        p["fcs/aileron-cmd-norm"], p["fcs/elevator-cmd-norm"], p["fcs/rudder-cmd-norm"] = u
        p.step(1)
        mon.sample()
        us.append(u)
        if test == "bank":
            ref.append(cmd); y.append(np.degrees(p["attitude/phi-rad"]))
        elif test == "p3211":
            ref.append(np.degrees(sp[0])); y.append(np.degrees(p["velocities/p-rad_sec"]))
        else:   # 한계 통과 후 q 명령·응답을 ΔG 등가로 (V/g 스케일)
            s = v / G_FT_S2
            ref.append(sp[1] * s); y.append(p["velocities/q-rad_sec"] * s)
    ref, y, us = np.array(ref), np.array(y), np.array(us)
    amp = AMP[test]
    e = (y - ref) / amp
    out = dict(ise_n=float(np.mean(e ** 2)), rmse=float(np.sqrt(np.mean((y - ref) ** 2))),
               du_ail=float(np.abs(np.diff(us[:, 0])).mean()), du_elev=float(np.abs(np.diff(us[:, 1])).mean()))
    if test in ("bank", "q_step"):   # 첫 스텝 구간의 오버슈트·정착(±5% 진폭)
        n1 = int(3.0 / DT)
        seg_ref, seg_y = ref[:n1], y[:n1]
        final = seg_ref[-1]
        out["overshoot"] = float(max(0.0, (seg_y.max() - final) / amp)) if final > 0 else 0.0
        bad = np.nonzero(np.abs(seg_y - final) > 0.05 * amp)[0]
        out["settle_s"] = float((bad[-1] + 1) * DT) if len(bad) else 0.0
    out.update(mon.summary())
    return out


def evaluate(cfg: INDIConfig, sensor: SensorConfig = NOMINAL_SENSOR,
             points=POINTS, tests=TESTS) -> dict:
    """전 운용점·시험 → 집계. J = 평균 정규화 ISE (E4 비용의 추종 항), viol = Σ 봉투 초과 [G·s]."""
    rows = [dict(kcas=k, alt=a, test=t, **run_test(cfg, t, k, a, sensor))
            for k, a in points for t in tests]
    return dict(cfg=dataclasses.asdict(cfg), sensor=dataclasses.asdict(sensor),
                J=float(np.mean([r["ise_n"] for r in rows])),
                viol=float(sum(r["env_excess_int"] for r in rows)),
                disqualified=any(r["disqualified"] for r in rows),
                by_test={t: float(np.mean([r["ise_n"] for r in rows if r["test"] == t])) for t in tests},
                rows=rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for f in dataclasses.fields(INDIConfig):
        ap.add_argument(f"--{f.name}", type=float, default=f.default)
    ap.add_argument("--sensor", default=NOMINAL_SENSOR.kind, choices=("truth", "gyro"))
    ap.add_argument("--gyro_sigma_dps", type=float, default=NOMINAL_SENSOR.gyro_sigma_dps)
    ap.add_argument("--json")
    a = ap.parse_args()
    cfg = INDIConfig(**{f.name: getattr(a, f.name) for f in dataclasses.fields(INDIConfig)})
    res = evaluate(cfg, SensorConfig(a.sensor, a.gyro_sigma_dps))
    print(f"J={res['J']:.4f}  viol={res['viol']:.3f} G·s  DQ={res['disqualified']}  by_test=" +
          ", ".join(f"{k}:{v:.4f}" for k, v in res["by_test"].items()))
    print(f"{'kcas':>5} {'alt':>6} {'test':7} {'ise_n':>7} {'rmse':>6} {'ovs':>5} {'settle':>6} "
          f"{'du_ail':>7} {'du_elv':>7} {'nzmax':>5} {'exc':>5} {'sat':>5}")
    for r in res["rows"]:
        print(f"{r['kcas']:5.0f} {r['alt']:6.0f} {r['test']:7} {r['ise_n']:7.4f} {r['rmse']:6.2f} "
              f"{r.get('overshoot', float('nan')):5.2f} {r.get('settle_s', float('nan')):6.2f} "
              f"{r['du_ail']*1e3:7.2f} {r['du_elev']*1e3:7.2f} {r['nz_max']:5.2f} {r['env_excess_max']:5.2f} "
              f"{r['elev_sat_frac']:5.2f}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
