"""P7 설계 계산: 실제형 센서·구동기에서 INDI 피치 루프의 안정 여유 (선형 이산 모형, 교전 0판).

  python p7_design.py      # → p7_design_output.md

모형은 시뮬레이터의 실제 틱 순서를 따른다(2026-10-21 실측: 이번 틱 입력 u_k 가 다음 틱의 각가속도 a_{k+1} 에 나타나고,
각속도는 ω_{k+1} = ω_k + dt·a_k 로 한 틱 늦게 적분된다).
  a = G z⁻¹ A u,   ω = dt z⁻¹ a / (1 − z⁻¹)
  A(z): 구동기. 이상(지금 키트) A = 1, 실제형 A = β / (1 − (1 − β) z⁻¹), β = 1 − exp(−ω_a dt), ω_a = 20.2 rad/s
  각가속도 측정: 참값 a_k (지금 키트) 또는 자이로 미분 (ω_k − ω_{k−1})/dt = a_{k−1} (실제형)
  구동기 측정 u_meas: 지금 키트는 직전 명령 u_{k−1}, 실제형은 각가속도 추정과 시간을 맞춘 구동기 위치 x_{k−2}
  INDI: u_k = H u_meas + G⁻¹(K(ω_sp − H D ω) − H D a_meas),  D: 측정 비동기 지연(소수 틱은 이웃 두 틱 보간, run.apply_knobs 와 같음)
루프를 구동기 입력에서 끊은 되돌림 T(z) 로 특성식 1 − T = 0 을 만든다. 여유는 L = −T 의 나이퀴스트에서 읽는다.
"""
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DT = 1.0 / 120.0
WA = 20.2                       # 실제형 구동기 대역 [rad/s]


def lpf(fc, zi):
    """aircombat.control.indi.SecondOrderLPF 와 같은 Tustin 2차 저역 통과 (ζ 0.7071). zi = z⁻¹."""
    wc = 2 * np.pi * fc
    n = 2.0 / DT
    d = n * n + 2 * 0.7071 * wc * n + wc * wc
    b = np.array([wc * wc, 2 * wc * wc, wc * wc]) / d
    a = np.array([1.0, (2 * wc * wc - 2 * n * n) / d, (n * n - 2 * 0.7071 * wc * n + wc * wc) / d])
    return (b[0] + b[1] * zi + b[2] * zi ** 2) / (a[0] + a[1] * zi + a[2] * zi ** 2)


def loop_T(zi, fc, K, real, delay=0.0):
    H = lpf(fc, zi)
    e = np.exp(-WA * DT)
    A = (1 - e) / (1 - e * zi) if real else 1.0
    n0, fr = int(np.floor(delay)), delay - np.floor(delay)
    D = (1 - fr) * zi ** n0 + fr * zi ** (n0 + 1)
    acc = zi ** 2 if real else zi            # 측정 각가속도 / (G·A·u): 미분이면 한 틱 더 늦다
    umeas = zi ** 2 if real else zi          # 구동기 측정 / (A·u) (이상: 직전 명령 = z⁻¹ u)
    omega = DT * zi ** 2 / (1 - zi)          # ω / (G·A·u)
    return H * umeas * A - K * H * D * omega * A - H * D * acc * A


def margins(fc, K, real, delay=0.0):
    th = np.linspace(1e-4, np.pi - 1e-4, 200000)
    L = -loop_T(np.exp(-1j * th), fc, K, real, delay)
    mag, ph = np.abs(L), np.unwrap(np.angle(L))
    gm = np.inf
    # 위상 교차: 위상이 −180°(mod 360°)를 지나는 곳
    phm = np.mod(np.degrees(ph) + 180.0, 360.0) - 180.0     # (−180, 180]
    cross_p = np.where((np.abs(phm[:-1]) > 170) & (np.sign(phm[:-1]) != np.sign(phm[1:])))[0]
    for i in cross_p:
        gm = min(gm, 1.0 / mag[i])
    cross_g = np.where(np.diff(np.sign(mag - 1.0)) != 0)[0]
    pm = np.inf
    wc = None
    for i in cross_g:
        p = 180.0 + phm[i]
        p = p if p <= 180 else p - 360
        if abs(p) < abs(pm):
            pm, wc = p, th[i] / DT
    return 20 * np.log10(gm) if np.isfinite(gm) else np.inf, pm, wc


def stable(fc, K, real, delay=0.0):
    """특성 다항식의 근으로 직접 확인 (소수 지연 포함). z⁻¹ 의 다항식으로 전개해 근의 크기를 본다."""
    # 1 − T(x) = 0 을 x = z⁻¹ 의 유리식으로 놓고 분자를 수치적으로 얻는다(충분한 차수의 다항식 적합 대신 직접 전개)
    from numpy.polynomial import polynomial as Pn
    wc = 2 * np.pi * fc
    n = 2.0 / DT
    d = n * n + 2 * 0.7071 * wc * n + wc * wc
    hb = np.array([wc * wc, 2 * wc * wc, wc * wc]) / d
    ha = np.array([1.0, (2 * wc * wc - 2 * n * n) / d, (n * n - 2 * 0.7071 * wc * n + wc * wc) / d])
    beta = 1 - np.exp(-WA * DT)
    ab, aa = (np.array([beta]), np.array([1.0, -(1 - beta)])) if real else (np.array([1.0]), np.array([1.0]))
    n0, fr = int(np.floor(delay)), delay - np.floor(delay)
    Dn = np.zeros(n0 + 2); Dn[n0] += 1 - fr; Dn[n0 + 1] += fr
    xk = lambda k: np.eye(1, k + 1, k)[0]                    # x^k
    acc = xk(2) if real else xk(1)
    um = xk(2) if real else xk(1)
    # T = H·A·[um − K·D·dt·x²/(1 − x) − D·acc]  → 공통 분모 ha·aa·(1 − x)
    one_m_x = np.array([1.0, -1.0])
    inner = Pn.polysub(Pn.polysub(Pn.polymul(um, one_m_x), K * DT * Pn.polymul(Dn, xk(2))), Pn.polymul(Pn.polymul(Dn, acc), one_m_x))
    num_T = Pn.polymul(Pn.polymul(hb, ab), inner)
    den = Pn.polymul(Pn.polymul(ha, aa), one_m_x)
    char = Pn.polysub(den, num_T)                              # x 오름차순
    roots_x = Pn.polyroots(char)
    roots_x = roots_x[np.abs(roots_x) > 1e-12]
    return bool(np.all(np.abs(1.0 / roots_x) < 1.0 - 1e-9))


def delay_margin(fc, K, real, step=0.05, maxd=12.0):
    d = 0.0
    if not stable(fc, K, real, 0.0):
        return 0.0
    while d < maxd:
        if not stable(fc, K, real, d + step):
            return d
        d += step
    return maxd


if __name__ == "__main__":
    L = ["# P7 설계 계산 (선형 이산 모형, 교전 0판)\n",
         "## 1. 모형 검증: 지금 키트(이상 구동기·참값 각가속도)의 임계 비동기 지연 대 기존 벤치\n",
         "| 필터 | 모형 지연 여유 [틱] | 벤치 임계 지연 (J/J₀ > 2, 15,000 ft 350 kt) |", "|---|---|---|"]
    import json
    bs = {(r["fc"], r["alt"], r["kcas"]): r["crit_ticks"] for r in json.load(open(os.path.join(HERE, "..", "out", "margin", "bench_summary.json"), encoding="utf-8"))}
    for fc in (25.0, 12.0, 8.0, 5.0, 3.0):
        L.append(f"| {fc:g} Hz | {delay_margin(fc, 9.0, False):.2f} | {bs.get((fc, 15000.0, 350.0))} |")
    L += ["", "## 2. 실제형 (구동기 20.2 rad/s, 자이로 미분, 구동기 위치 측정): 공칭 여유와 비동기 지연 여유\n",
          "| 필터 | K | 이득 여유 [dB] | 위상 여유 [°] | 교차 [rad/s] | 비동기 지연 여유 [틱] | 지금 키트의 지연 여유 [틱] |", "|---|---|---|---|---|---|---|"]
    for fc in (25.0, 12.0, 8.0, 5.0):
        for K in (9.0, 6.0, 4.0):
            gm, pm, wc = margins(fc, K, True)
            L.append(f"| {fc:g} | {K:g} | {gm:.1f} | {pm:.1f} | {wc if wc is None else round(wc, 2)} | {delay_margin(fc, K, True):.2f} | {delay_margin(fc, K, False):.2f} |")
    txt = "\n".join(L) + "\n"
    open(os.path.join(HERE, "p7_design_output.md"), "w", encoding="utf-8").write(txt)
    print(txt)
