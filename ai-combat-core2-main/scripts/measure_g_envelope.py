"""G(α, qbar) 실측 — INDI 의 `G = (qbar/qbar_ref)·G0` 가정을 봉투 전역에서 검증.

배경: control/indi.py 는 제어효과를 동압만의 함수로 스케줄한다(고정익 INDI 표준,
AIAA 2022-1597 Eq.37/39). 그 유도는 **맨 기체**(입력=조종면 편각) 전제다. 그런데
이 플랜트의 입력은 F-16 native FLCS 의 스틱 명령이고, FLCS 는 자체 게인 스케줄을
갖는다 — 특히 피치는 α 스케줄(f16.xml: α=0°→1.0, 28.6°→0.11, 30°→0.0)을 곱한다.
따라서 qbar 만으로 스케줄하면 α 가 높은 곳에서 모델 오차가 생긴다.

이 스크립트는 가정을 검증만 한다 (비행 코드 무변경):
  study 1  봉투 격자에서 G 실측 → qbar 법칙 예측 대비 비율
  study 2  settle(섭동 후 대기 틱) 민감도 — 짧으면 FLCS 되먹임이 기울기를 갉아먹는다
  study 3  identify_G0 반복재현성 — 섭동 사이 상태 미복원의 영향

ratio = G_실측 / G_모델.  <1 = 모델 과대추정(증분 과소 → 둔함),
                          >1 = 모델 과소추정(증분 과잉 → 진동 경향).
"""
from __future__ import annotations
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.fdm.plant import F16Plant
from aircombat.control.indi import identify_G0

DT = 1.0 / 120.0
REF_ALT_FT, REF_KCAS = 15000.0, 350.0      # engine/factory.py make_pilot 의 트림 조건
AXES = ("roll(ail)", "pitch(ele)", "yaw(rud)")


def trimmed_plant(alt_ft: float, kcas: float) -> F16Plant | None:
    """make_pilot 과 동일 절차로 트림. 실패하면 None."""
    try:
        p = F16Plant(dt=DT)
        p.set_ic(alt_ft=alt_ft, vc_kts=kcas)
        p["fcs/throttle-cmd-norm"] = 0.85
        p.trim()
        return p
    except Exception:
        return None


def probe(alt_ft: float, kcas: float, settle: int = 3):
    """트림 → G0 식별. returns (G0, qbar, alpha_deg) 또는 None."""
    p = trimmed_plant(alt_ft, kcas)
    if p is None:
        return None
    G0, qbar = identify_G0(p.fdm, settle=settle)
    return G0, qbar, float(np.degrees(p["aero/alpha-rad"]))


def study_envelope():
    print("=" * 78)
    print("study 1 — 봉투 격자 G 실측 vs qbar 법칙 예측")
    print("=" * 78)
    ref = probe(REF_ALT_FT, REF_KCAS)
    if ref is None:
        print("기준점 트림 실패 — 중단")
        return
    G_ref, qbar_ref, a_ref = ref
    print(f"기준점 {REF_ALT_FT:.0f}ft / {REF_KCAS:.0f}KCAS: "
          f"qbar={qbar_ref:.1f}psf  alpha={a_ref:.2f}deg")
    print(f"  G0_ref diag = {np.diag(G_ref).round(3)}\n")

    hdr = f"{'alt':>6} {'kcas':>5} {'alpha':>6} {'qbar':>7} | " + " ".join(
        f"{n:>21}" for n in AXES)
    print(hdr)
    print(f"{'':>6} {'':>5} {'deg':>6} {'psf':>7} | " + " ".join(
        f"{'meas / model  ratio':>21}" for _ in AXES))
    print("-" * len(hdr))
    for alt in (10000.0, 15000.0, 25000.0):
        for kcas in (200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0):
            r = probe(alt, kcas)
            if r is None:
                print(f"{alt:>6.0f} {kcas:>5.0f} {'trim fail':>50}")
                continue
            G, qbar, alpha = r
            cells = []
            for i in range(3):
                meas = G[i, i]
                model = (qbar / qbar_ref) * G_ref[i, i]
                ratio = meas / model if abs(model) > 1e-9 else float("nan")
                cells.append(f"{meas:>7.2f} /{model:>7.2f} {ratio:>5.2f}")
            print(f"{alt:>6.0f} {kcas:>5.0f} {alpha:>6.2f} {qbar:>7.1f} | "
                  + " ".join(cells))
    print()


def study_settle():
    print("=" * 78)
    print("study 2 — settle 민감도 (기준점). 값이 settle 에 따라 움직이면")
    print("          FLCS 자체 되먹임이 식별 기울기를 갉아먹고 있다는 뜻이다.")
    print("=" * 78)
    print(f"{'settle':>7} {'ms':>6} | " + " ".join(f"{n:>12}" for n in AXES))
    print("-" * 52)
    for settle in (1, 2, 3, 5, 10, 20):
        r = probe(REF_ALT_FT, REF_KCAS, settle=settle)
        if r is None:
            continue
        G = r[0]
        print(f"{settle:>7d} {settle * DT * 1e3:>6.1f} | "
              + " ".join(f"{G[i, i]:>12.3f}" for i in range(3)))
    print()


def study_repeatability():
    print("=" * 78)
    print("study 3 — identify_G0 반복재현성 (같은 기체에 연속 3회)")
    print("          섭동 사이 상태를 복원하지 않으면 회차마다 값이 흐른다.")
    print("=" * 78)
    p = trimmed_plant(REF_ALT_FT, REF_KCAS)
    if p is None:
        print("트림 실패 — 중단")
        return
    first = None
    for k in range(3):
        G, _ = identify_G0(p.fdm)
        d = np.diag(G)
        if first is None:
            first = d.copy()
            print(f"  run {k + 1}: diag = {d.round(3)}")
        else:
            drift = 100.0 * (d - first) / np.where(np.abs(first) > 1e-9, first, 1.0)
            print(f"  run {k + 1}: diag = {d.round(3)}   1회차 대비 {drift.round(1)} %")
    print()


def probe_pulling(alt_ft: float, kcas: float, target_alpha_deg: float,
                  elev_cmd: float = -1.0, max_s: float = 25.0):
    """트림 후 풀 당김 → 목표 α 도달 시점에 G 식별 (기동 중 실측).

    1g 트림은 α 를 6° 남짓까지밖에 못 올린다. BFM 이 사는 α 12–20° 구간은
    당기면서만 측정 가능하다. elev_cmd 음수 = 기수 상승(f16.xml: −1 이 +9G 쪽).
    """
    p = trimmed_plant(alt_ft, kcas)
    if p is None:
        return None
    p["fcs/elevator-cmd-norm"] = elev_cmd
    for _ in range(int(max_s / DT)):
        p.step(1)
        if np.degrees(p["aero/alpha-rad"]) >= target_alpha_deg:
            break
    else:
        return None                       # 목표 α 도달 실패
    G0, qbar = identify_G0(p.fdm)
    return (G0, qbar, float(np.degrees(p["aero/alpha-rad"])),
            float(p["velocities/vc-kts"]))


def study_alpha():
    print("=" * 78)
    print("study 4 — 기동 중 고α 에서의 G (1g 트림으로는 못 가는 BFM 영역)")
    print("          f16.xml elevator-scheduler 표: α=0°→1.0, 28.6°→0.11, 30°→0.0")
    print("=" * 78)
    ref = probe(REF_ALT_FT, REF_KCAS)
    if ref is None:
        print("기준점 트림 실패 — 중단")
        return
    G_ref, qbar_ref, _ = ref
    print(f"{'target':>7} {'alpha':>6} {'kcas':>6} {'qbar':>7} | "
          f"{'meas':>8} {'model':>8} {'ratio':>6}   {'FLCS표 예측':>10}")
    print("-" * 70)
    for target in (8.0, 12.0, 15.0, 18.0, 21.0, 25.0):
        r = probe_pulling(REF_ALT_FT, REF_KCAS, target)
        if r is None:
            print(f"{target:>7.0f} {'도달 실패':>20}")
            continue
        G, qbar, alpha, kcas = r
        meas = G[1, 1]
        model = (qbar / qbar_ref) * G_ref[1, 1]
        # f16.xml 표의 선형보간 (0 rad→1.0, 0.5 rad→0.11) — 예측 비율
        sched = 1.0 + (min(abs(np.radians(alpha)), 0.5) / 0.5) * (0.11 - 1.0)
        print(f"{target:>7.0f} {alpha:>6.2f} {kcas:>6.1f} {qbar:>7.1f} | "
              f"{meas:>8.2f} {model:>8.2f} {meas / model:>6.2f}   {sched:>10.2f}")
    print()


def study_residual():
    print("=" * 78)
    print("study 5 — identify_G0 가 남기는 잔류 상태 (Pilot.setup 은 매치 t=0 직전에")
    print("          이걸 돌린다. indi.reset(omega0=) 기본값이 0 인 게 맞는지 확인)")
    print("=" * 78)
    p = trimmed_plant(REF_ALT_FT, REF_KCAS)
    if p is None:
        return
    RATES = ("velocities/p-rad_sec", "velocities/q-rad_sec", "velocities/r-rad_sec")
    before = np.array([p[r] for r in RATES])
    identify_G0(p.fdm)
    after = np.array([p[r] for r in RATES])
    print(f"  식별 전 pqr [deg/s] = {np.degrees(before).round(4)}")
    print(f"  식별 후 pqr [deg/s] = {np.degrees(after).round(4)}")
    print(f"  잔류 변화  [deg/s] = {np.degrees(after - before).round(4)}")
    print()


def _level_turn_dvdt(alt_ft: float, kcas0: float, n_target: float,
                     t_total: float = 12.0, t_win: float = 4.0) -> float | None:
    """하중배수 n 으로 수평 지속 선회 → 마지막 t_win 구간의 dKCAS/dt [kt/s].

    수평 선회 조건: 뱅크 φ = arccos(1/n) 이면 양력의 수직성분이 무게와 균형.
    dV/dt > 0 = 그 n 은 지속 가능(추력 여유), < 0 = 에너지 적자.
    실제 L3 스택(shim+리미터+INDI)을 그대로 쓴다 — 봉투가 아니라 스택의 지속 능력 측정.
    """
    from aircombat.control.attitude import QuaternionAttitudeShim, euler_to_quat, quat_mul
    from aircombat.control.indi import INDIRateController
    from aircombat.control.limiter import CombinedLimiter, LimiterConfig, G_FT_S2

    p = trimmed_plant(alt_ft, kcas0)
    if p is None:
        return None
    p["fcs/throttle-cmd-norm"] = 1.0                     # full AB
    G0, qbar_ref = identify_G0(p.fdm)
    indi = INDIRateController(DT, G0, qbar_ref, k_rate=(9.0, 9.0, 6.0), filt_hz=25.0)
    indi.reset(u0=[p["fcs/aileron-cmd-norm"], p["fcs/elevator-cmd-norm"],
                   p["fcs/rudder-cmd-norm"]])
    shim = QuaternionAttitudeShim(k_att=4.0, k_yaw_damp=1.5,
                                  rate_limit_dps=(180.0, 60.0, 30.0))
    limiter = CombinedLimiter(LimiterConfig())
    phi_target = float(np.arccos(np.clip(1.0 / n_target, -1.0, 1.0)))

    hist = []
    for k in range(int(t_total / DT)):
        phi, theta = p["attitude/phi-rad"], p["attitude/theta-rad"]
        psi = p["attitude/psi-rad"]
        pqr = np.array([p["velocities/p-rad_sec"], p["velocities/q-rad_sec"],
                        p["velocities/r-rad_sec"]])
        v_fps = p["velocities/vt-fps"]
        g_lift = float(np.cos(phi) * np.cos(theta))
        q_cmd = (n_target - g_lift) * G_FT_S2 / max(v_fps, 1.0)
        q_cur = euler_to_quat(phi, theta, psi)
        q_des = quat_mul(q_cur, euler_to_quat(phi_target - phi, 0.0, 0.0))
        omega_sp = shim.rate_setpoint(q_cur, q_des, r_cur=pqr[2])
        omega_sp[1] = q_cmd
        omega_sp, _ = limiter.limit_omega_sp(omega_sp, v_fps,
                                             p["velocities/vc-kts"], g_lift=g_lift)
        u = indi.update(pqr, omega_sp, p["aero/qbar-psf"], ang_accel=[
            p["accelerations/pdot-rad_sec2"], p["accelerations/qdot-rad_sec2"],
            p["accelerations/rdot-rad_sec2"]])
        p.set_input([1.0, u[1], u[0], u[2]])
        p.step(1)
        # 달성 G 를 같이 기록한다. 지령 n 을 그대로 쓰면 포화 구간에서
        # "지령 7.4G 로 가속" 같은 허깨비가 나온다 — 실제로는 4G 밖에 안 나온다.
        n_act = (p["velocities/q-rad_sec"] * p["velocities/vt-fps"] / G_FT_S2
                 + float(np.cos(p["attitude/phi-rad"]) * np.cos(p["attitude/theta-rad"])))
        hist.append((k * DT, p["velocities/vc-kts"], n_act))
    a = np.array(hist)
    w = a[a[:, 0] >= t_total - t_win]
    return (float(np.polyfit(w[:, 0], w[:, 1], 1)[0]),    # dKCAS/dt [kt/s]
            float(np.mean(w[:, 2])))                      # 달성 G


def sustained_g(alt_ft: float, kcas: float, lo: float = 1.5, hi: float = 9.0,
                iters: int = 6) -> float | None:
    """dKCAS/dt = 0 이 되는 하중배수를 이분법으로 — 곧 Ps=0 지속 G.

    상한은 **봉투**로 묶는다. 안 묶으면 리미터가 q 를 클램프하는 저속에서
    아무리 큰 n 을 줘도 실제 G 가 안 올라가 계속 가속 → 이분법이 상한으로
    수렴하는 허깨비 값이 나온다(250KCAS 에서 8.94G 같은).
    """
    from aircombat.control.limiter import CombinedLimiter
    hi = min(hi, CombinedLimiter().max_load_factor(kcas))
    if hi <= lo:
        return None
    r_lo = _level_turn_dvdt(alt_ft, kcas, lo)
    if r_lo is None or r_lo[0] < 0:
        return None                       # 최저 G 에서도 감속 = 이 속도는 유지 불가
    r_hi = _level_turn_dvdt(alt_ft, kcas, hi)
    if r_hi is not None and r_hi[0] > 0:
        return r_hi[1]                    # 봉투 상한에서도 가속 → 달성 G 가 지속 한계
    g_at_zero = r_hi[1] if r_hi else 0.0
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        r = _level_turn_dvdt(alt_ft, kcas, mid)
        if r is None:
            return None
        if r[0] > 0:
            lo = mid
        else:
            hi, g_at_zero = mid, r[1]     # dV/dt≤0 쪽의 **달성** G 를 답으로 든다
    return g_at_zero


def study_sustained():
    print("=" * 78)
    print("study 6 — 지속 G (Ps=0). 수평 지속 선회에서 dKCAS/dt=0 이 되는 하중배수.")
    print("          리미터의 순간 봉투(9G)와 달리 '계속 유지할 수 있는' G 다.")
    print("=" * 78)
    print(f"{'alt':>7} {'KCAS':>6} {'지속 G':>8} {'리미터 g_max':>13} {'비율':>6}")
    print("-" * 46)
    from aircombat.control.limiter import CombinedLimiter
    lim = CombinedLimiter()
    for alt in (15000.0, 25000.0):
        for kcas in (250.0, 300.0, 350.0, 400.0, 450.0):
            n = sustained_g(alt, kcas)
            gm = lim.max_load_factor(kcas)
            if n is None:
                print(f"{alt:>7.0f} {kcas:>6.0f} {'유지 불가':>10} {gm:>13.2f}")
            else:
                print(f"{alt:>7.0f} {kcas:>6.0f} {n:>8.2f} {gm:>13.2f} {n / gm:>6.2f}")
    print()


def main() -> int:
    np.set_printoptions(precision=3, suppress=True, sign="+")
    only = set(sys.argv[1:])
    studies = {"envelope": study_envelope, "settle": study_settle,
               "repeat": study_repeatability, "alpha": study_alpha,
               "residual": study_residual, "sustained": study_sustained}
    for name, fn in studies.items():
        if not only or name in only:
            fn()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
