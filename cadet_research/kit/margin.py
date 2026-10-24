"""지연 여유 사전 예측 — 교전 결과를 보기 전에 제어기만으로 임계 지연을 정한다.

  python margin.py linear          # (a) 선형 이론: 이상 플랜트 + 동기화 필터 + 비동기 지연
  python margin.py bench --procs 20 # (b) 비선형 벤치: F-16 한 대(피치·롤 내장 FLCS 우회, 교전과 같은 구성), 피치 명령 추종

(a) 피치 한 축 120 Hz 이산 모델. INDI가 플랜트 역모델을 정확히 안다고 두면 남는 것은 필터와 지연뿐이다.
    가속도 a = z⁻¹·v (v = G·u, 이번 틱 입력이 다음 틱 가속도), 각속도 ω = dt·a / (1 − z⁻¹).
    측정은 n틱 늦고 조종 입력 되먹임은 늦지 않는다(비동기). 법칙 u = H·u + G⁻¹(K(ω_sp − H z⁻ⁿ ω) − H z⁻ⁿ a).
    정리하면 특성식 1 + z⁻ⁿ L(z) = 0,  L(z) = H z⁻¹ (1 + K dt/(1 − z⁻¹)) / (1 − H).
    지연 여유 n_max = min(위상여유 / 교차 주파수) [틱]. 정수 n 에서 특성근으로 교차 확인한다.
(b) 같은 지연을 실제 JSBSim F-16(교전과 같은 구성: 피치·롤 내장 FLCS 법칙 우회, 구동기 속도 제한·명령 클립 포함)에 걸고 피치각속도 이중펄스 추종 오차 J 를 잰다.
    임계 지연 = J/J₀ 가 2를 처음 넘는 지연. 선형 예측과 다르면 그 차이가 작동기 동특성·명령 클립·비선형 공력의 몫이다.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)

DT = 1.0 / 120.0
K_RATE = 9.0
FILTERS = [3.0, 5.0, 8.0, 12.0, 25.0, 50.0]


def butter_coeffs(fc, fs=120.0, damping=0.7071):
    """aircombat.control.indi.SecondOrderLPF 와 같은 계수 (Tustin)."""
    wc = 2 * np.pi * fc
    n = 2.0 * fs
    d = n * n + 2 * damping * wc * n + wc * wc
    b = np.array([wc * wc, 2 * wc * wc, wc * wc]) / d
    a = np.array([1.0, (2 * wc * wc - 2 * n * n) / d, (n * n - 2 * damping * wc * n + wc * wc) / d])
    return b, a


def open_loop(fc, theta):
    """L(e^{jθ}). θ = ω·dt [rad/틱]."""
    zi = np.exp(-1j * theta)                 # z⁻¹
    b, a = butter_coeffs(fc)
    H = (b[0] + b[1] * zi + b[2] * zi ** 2) / (a[0] + a[1] * zi + a[2] * zi ** 2)
    return H * zi * (1 + K_RATE * DT / (1 - zi)) / (1 - H)


def delay_margin(fc):
    th = np.linspace(1e-4, np.pi, 200000)
    L = open_loop(fc, th)
    mag = np.abs(L)
    cross = np.where(np.diff(np.sign(mag - 1.0)) != 0)[0]
    best = np.inf
    for i in cross:
        pm = np.pi + np.angle(L[i])          # 1 + e^{-jnθ}L = 0 이 되려면 위상이 −π 까지 nθ 만큼 더 돌아야 한다
        pm = pm % (2 * np.pi)
        best = min(best, pm / th[i])
    return best


def char_stable(fc, n):
    """정수 n 틱에서 폐루프 특성근이 단위원 안에 있는가 (선형 예측의 교차 확인)."""
    B, A = butter_coeffs(fc)                 # H = B(x)/A(x), x = z⁻¹, 계수는 x 오름차순
    # 특성식에 A(x)(1 − x)를 곱하면 (A − B)(1 − x) + x^{n+1} B ((1 + K dt) − x) = 0.
    term1 = np.convolve(A - B, [1.0, -1.0])
    term2 = np.concatenate([np.zeros(n + 1), np.convolve(B, [1.0 + K_RATE * DT, -1.0])])
    poly = np.zeros(max(len(term1), len(term2)))
    poly[:len(term1)] += term1
    poly[:len(term2)] += term2
    # x 오름차순 계수에 z^m 을 곱하면 그대로 z 내림차순 계수다
    return bool(np.all(np.abs(np.roots(poly)) < 1.0 - 1e-9))


def linear():
    rows = []
    print("필터 [Hz] | 선형 지연 여유 [틱] | [ms] | τ·f_c | 정수 지연 안정 여부 (0..8틱)")
    for fc in FILTERS:
        # 위상여유/교차주파수 공식은 지연 0에서 폐루프가 안정할 때만 의미가 있다. 아니면 여유를 정의하지 않는다
        # (2026-10-19 검토 의견 v1 §7: 50 Hz 의 4.149틱은 이 전제가 깨진 값이었다. 이상 플랜트 모형에서 50 Hz 는
        #  나이퀴스트 60 Hz 에 가까워 지연 0 에서도 불안정하다. 비선형 벤치에서는 지연 0 추종이 정상이다).
        stable0 = char_stable(fc, 0)
        n = delay_margin(fc) if stable0 else float("nan")
        st = "".join("O" if char_stable(fc, k) else "x" for k in range(9))
        note = "" if stable0 else "  ← 지연 0 에서 이미 불안정: 여유 정의 불가 (이상 플랜트 모형의 한계)"
        print(f"{fc:9.0f} | {n:18.2f} | {n * DT * 1e3:5.1f} | {n * DT * fc:5.3f} | {st}{note}")
        rows.append({"fc": fc, "stable_at_0": stable0, "n_max_ticks": None if not stable0 else n,
                     "tau_ms": None if not stable0 else n * DT * 1e3, "tau_fc": None if not stable0 else n * DT * fc,
                     "stable_int_0_8": st})
    out = os.path.join(KIT, "out", "margin")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "linear.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print("기록:", os.path.join(out, "linear.json"))


# ---------------------------------------------------------------- (b) 비선형 벤치
FLIGHT_POINTS = [(15000.0, 350.0), (15000.0, 250.0), (10000.0, 450.0)]
DELAYS = [x / 4 for x in range(0, 33)]          # 0 – 8틱, 0.25틱 간격


def bench_one(job):
    fc, alt, kcas, delay = job
    import run                                   # 소수 지연 보간을 run.apply_knobs 와 같은 코드로 쓴다
    from aircombat.fdm.plant import F16Plant
    from aircombat.engine.pilot import Pilot
    plant = F16Plant(dt=DT)
    plant.set_ic(alt_ft=alt, vc_kts=kcas, psi_deg=0.0)
    plant["fcs/throttle-cmd-norm"] = 0.85
    plant.trim()
    pilot = Pilot(plant, color="Bench")
    run._orig_setup(pilot)                       # 원래 setup (주입 없이)
    knobs = {"filt_hz": fc}
    if delay:
        knobs["delay_async"] = delay
    run.TRACE.clear()
    run.apply_knobs(pilot, knobs, ("bench", fc, alt, kcas, delay))
    indi = pilot.indi
    T, A = 6.0, np.radians(5.0)                  # 이중펄스: 1–2 s +5 °/s, 2–3 s −5 °/s, 이후 0 유지
    err = ref = 0.0
    diverged = False
    for k in range(int(T / DT)):
        t = k * DT
        q_cmd = A if 1.0 <= t < 2.0 else (-A if 2.0 <= t < 3.0 else 0.0)
        pqr = np.array([plant["velocities/p-rad_sec"], plant["velocities/q-rad_sec"],
                        plant["velocities/r-rad_sec"]])
        u = indi.update(pqr, np.array([0.0, q_cmd, 0.0]), plant["aero/qbar-psf"], ang_accel=[
            plant["accelerations/pdot-rad_sec2"], plant["accelerations/qdot-rad_sec2"],
            plant["accelerations/rdot-rad_sec2"]])
        plant.set_input([0.85, u[1], u[0], 0.0])
        plant.step(1)
        q = plant["velocities/q-rad_sec"]
        err += (q_cmd - q) ** 2
        ref += q_cmd ** 2
        if not np.isfinite(q) or abs(q) > np.radians(60):
            diverged = True
            break
    J = float(np.sqrt(err / ref)) if not diverged else float("inf")
    return {"fc": fc, "alt": alt, "kcas": kcas, "delay": delay, "J": J}


def bench(procs):
    import multiprocessing as mp
    jobs = [(fc, alt, kcas, d) for fc in FILTERS for alt, kcas in FLIGHT_POINTS for d in DELAYS]
    with mp.Pool(procs) as pool:
        res = pool.map(bench_one, jobs, chunksize=4)
    out = os.path.join(KIT, "out", "margin")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "bench.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    lin = {r["fc"]: r for r in json.load(open(os.path.join(out, "linear.json"), encoding="utf-8"))} \
        if os.path.isfile(os.path.join(out, "linear.json")) else {}
    print("필터 | 비행점 | J₀ | 임계 지연 (J/J₀ > 2) [틱] | τ·f_c | 선형 예측 [틱]")
    summary = []
    for fc in FILTERS:
        for alt, kcas in FLIGHT_POINTS:
            rs = sorted([r for r in res if r["fc"] == fc and r["alt"] == alt and r["kcas"] == kcas],
                        key=lambda r: r["delay"])
            j0 = rs[0]["J"]
            crit = next((r["delay"] for r in rs if r["J"] > 2 * j0), None)
            summary.append({"fc": fc, "alt": alt, "kcas": kcas, "J0": j0, "crit_ticks": crit})
            lp = lin.get(fc, {}).get("n_max_ticks")
            print(f"{fc:4.0f} | {alt:.0f} ft {kcas:.0f} kt | {j0:.3f} | "
                  f"{'>8' if crit is None else f'{crit:.2f}'} | "
                  f"{'-' if crit is None else f'{crit * DT * fc:.3f}'} | {'-' if lp is None else f'{lp:.2f}'}")
    with open(os.path.join(out, "bench_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "linear"
    if mode == "linear":
        linear()
    else:
        procs = int(sys.argv[sys.argv.index("--procs") + 1]) if "--procs" in sys.argv else 8
        bench(procs)
