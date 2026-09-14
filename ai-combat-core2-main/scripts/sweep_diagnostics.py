"""스윕 스크립트 공용 진단 — 리밋사이클(진동) 감지 + 사후 포락선(G) 초과 검증.

run_indi_step_sweep.py / run_corner_pull_sweep.py 양쪽에서 동일한 정의로 써야
"오실레이팅"과 "G 초과"가 실험 간에 비교 가능하다. 그래서 여기 한 곳에 둔다.

임계값 근거(2026-09-14 조사, corner_pull G5_k2_f25 대 G5_k1_f25/indi_step
bank60_k1_f25 로 캘리브레이션):
  - 안정 케이스 마지막 3초 구간 p2p: p<=0.36dps, q<=0.075dps, r<=0.04dps,
    액추에이터 부호반전 0회/s.
  - 리밋사이클 케이스(corner_pull G5_k2_f25): q p2p=34.7dps(안정 대비 460배),
    elevator 부호반전 5.0회/s, overshoot_g=6.55G(피크~+11.5G, 저점~-6G → G
    p2p~17G, 안정 케이스는 overshoot_g<=0.14G).
  둘 사이에 1~2 자릿수 마진이 있어 아래 임계값은 안정 케이스를 절대 오검출하지
  않으면서 리밋사이클은 확실히 잡아낸다.
"""
from __future__ import annotations

import numpy as np

OSC_RATE_P2P_DPS = 3.0      # 마지막 3초 p/q/r 각속도 peak-to-peak 상한 [deg/s]
OSC_SIGNCHG_HZ = 1.0        # 마지막 3초 조종면 명령 부호반전 상한 [회/s]
OSC_G_P2P = 3.0              # 마지막 3초 n_act(달성 G) peak-to-peak 상한 [G]

G_STRUCT_MAX = 9.0            # LimiterConfig 기본값과 동일 — 구조 상한 [G]
G_STRUCT_MIN = -3.0           # LimiterConfig 기본값과 동일 — 구조 하한 [G]


def oscillation_metrics(t, p_dps, q_dps, r_dps, n_act,
                        cmd_ail, cmd_ele, cmd_rud, window_s: float = 3.0) -> dict:
    """마지막 window_s 초 구간의 리밋사이클 지표 + oscillating 플래그(0/1).

    판정: 아래 중 하나라도 걸리면 oscillating=1.
      (a) max(p2p_p, p2p_q, p2p_r) > OSC_RATE_P2P_DPS
      (b) max(부호반전율_ail/ele/rud) > OSC_SIGNCHG_HZ
      (c) p2p(n_act) > OSC_G_P2P
    """
    t = np.asarray(t, float)
    tmax = t[-1] if len(t) else 0.0
    mask = t >= (tmax - window_s)
    dur = float(t[mask][-1] - t[mask][0]) if np.sum(mask) > 1 else 0.0

    def p2p_std(arr):
        v = np.asarray(arr, float)[mask]
        if len(v) == 0:
            return 0.0, 0.0
        return float(v.max() - v.min()), float(v.std())

    def signchg_hz(arr):
        v = np.asarray(arr, float)[mask]
        if len(v) < 2 or dur <= 0:
            return 0.0
        s = np.sign(v)
        s[s == 0] = 1.0
        return float(np.sum(np.diff(s) != 0) / dur)

    p2p_p, std_p = p2p_std(p_dps)
    p2p_q, std_q = p2p_std(q_dps)
    p2p_r, std_r = p2p_std(r_dps)
    p2p_n, std_n = p2p_std(n_act)
    sc_ail = signchg_hz(cmd_ail)
    sc_ele = signchg_hz(cmd_ele)
    sc_rud = signchg_hz(cmd_rud)

    oscillating = int(
        max(p2p_p, p2p_q, p2p_r) > OSC_RATE_P2P_DPS
        or max(sc_ail, sc_ele, sc_rud) > OSC_SIGNCHG_HZ
        or p2p_n > OSC_G_P2P
    )

    return {
        "p2p_p_dps_last3s": round(p2p_p, 4), "std_p_dps_last3s": round(std_p, 4),
        "p2p_q_dps_last3s": round(p2p_q, 4), "std_q_dps_last3s": round(std_q, 4),
        "p2p_r_dps_last3s": round(p2p_r, 4), "std_r_dps_last3s": round(std_r, 4),
        "p2p_n_act_last3s": round(p2p_n, 4), "std_n_act_last3s": round(std_n, 4),
        "signchg_ail_hz": round(sc_ail, 3), "signchg_elev_hz": round(sc_ele, 3),
        "signchg_rud_hz": round(sc_rud, 3),
        "oscillating": oscillating,
    }


def envelope_violation(n_act, dt: float, g_max: float = G_STRUCT_MAX,
                       g_min: float = G_STRUCT_MIN) -> dict:
    """물리 스텝 이후 실제 달성 G(n_act) 를 구조 포락선(+9/-3G)과 재비교.

    limiter.limit_omega_sp 는 명령(omega_sp)만 클램프하고 결과를 재검증하지
    않으므로(2026-09-14 조사), 이 함수가 사후 검증을 담당한다.
    """
    n = np.asarray(n_act, float)
    if len(n) == 0:
        return {"g_exceeded": 0, "frac_time_g_exceeded": 0.0,
                "max_g_exceed_pos": 0.0, "max_g_exceed_neg": 0.0}
    over_pos = np.maximum(0.0, n - g_max)
    over_neg = np.maximum(0.0, g_min - n)
    exceeded = (over_pos > 0.0) | (over_neg > 0.0)
    return {
        "g_exceeded": int(np.any(exceeded)),
        "frac_time_g_exceeded": round(float(np.mean(exceeded)) * 100.0, 3),
        "max_g_exceed_pos": round(float(over_pos.max()), 4),
        "max_g_exceed_neg": round(float(over_neg.max()), 4),
    }


# ============================================================================
# 3구간 분류 (안정 / 열화 / 불안정)  — 2026-09-14 추가
# ============================================================================
# 왜 필요한가
# -----------
# oscillating 은 **마지막 3초**만 본다. 즉 "정상상태 리밋사이클" 검출기다. 그래서
# 과도응답에서 크게 튀었다가 결국 가라앉는 케이스를 전부 놓친다. 실측 예:
#   stability_boundary G5_k1.6_f50 : oscillating=0 인데 overshoot_g=2.906
#     (같은 filt_hz 의 k_scale=1.0 기준 0.1499 의 19.4배), settle 5.81s(14.8배),
#     rms_q 1.722dps(8.6배). 가라앉기는 하지만 정상이라고 부를 수 없다.
#
# 기준의 근거 — 왜 "같은 filt_hz 의 최저 이득(k_scale=1.0)" 으로 정규화하는가
# ------------------------------------------------------------------------
# overshoot_g 의 절대값은 filt_hz 에 따라 기준선 자체가 다르다(k=1.0 에서
# f10=0.1175 … f50=0.1499, 28% 차이). 절대 임계를 쓰면 이 기준선 차이가 판정에
#섞여 들어간다. 같은 filt_hz 안에서 이득만 올린 비(ratio)를 쓰면 필터 효과가
# 소거되고 "이득을 올려서 나빠진 양"만 남는다.
#
# 임계 1.5 의 근거 — 실측 분포의 빈 구간(gap)
# -------------------------------------------
# stability_boundary 30조합 중 oscillating=0 인 23개의 rho_overshoot 분포:
#   1.00 1.00 1.00 1.00 1.00 1.02 1.02 1.03 1.03 1.04 1.05 1.05 1.07
#   1.09 1.09 1.13 1.14 1.19 | 2.00 3.07 6.67 7.95 19.39
# 1.19 와 2.00 사이가 완전히 비어 있다(1.7배 간극). 1.5 는 그 간극의 한가운데로,
# 아래로 1.26배 / 위로 1.33배 마진을 갖는다 — 임계값을 ±25% 움직여도 분류가
# 바뀌지 않는다. 물리적으로도 1.5배는 2차계에서 감쇠비가 확실히 떨어졌다는
# 뜻이다(오버슈트 1.19배는 zeta 변화 수% 수준, 2배는 수십%).
#
# settle_time / rms_q 를 같이 보는 이유
# -------------------------------------
# 위 표에서 rho_settle 은 열화 구간에서도 대부분 1 미만이다 — 이득을 올리면
# **불안정 직전까지 응답이 계속 빨라지기** 때문이다. rho_rms 도 8.64(k1.6_f50)
# 하나를 빼면 전부 ~1.00 이다. 즉 **과도 감쇠(overshoot)가 가장 먼저 무너지고,
# 속응성과 정상상태 추종은 맨 마지막에 무너진다.** 그래서 overshoot 를 1차
# 지표로 쓰되, 나머지 둘도 같은 임계로 OR 걸어 심한 열화를 이중으로 잡는다.
BAND_RATIO_THRESH = 1.5     # 기준 대비 몇 배부터 "열화" 인가

# CSV 에는 ASCII 로 쓴다(엑셀/외부 도구 인코딩 사고 방지). 한글 표기는 BAND_KO.
BAND_STABLE = "stable"
BAND_DEGRADED = "degraded"
BAND_UNSTABLE = "unstable"
BAND_KO = {BAND_STABLE: "안정", BAND_DEGRADED: "열화", BAND_UNSTABLE: "불안정"}
BAND_ORDER = (BAND_STABLE, BAND_DEGRADED, BAND_UNSTABLE)


def classify_band(overshoot, settle_s, rms_track, ref, oscillating, g_exceeded=0,
                  thresh: float = BAND_RATIO_THRESH) -> tuple[str, dict]:
    """한 조합을 안정/열화/불안정 3구간으로 분류.

    ref : (overshoot_ref, settle_ref, rms_ref) — 같은 filt_hz 의 최저 이득 기준값.
    returns (band, ratios dict)

    판정 순서
      1. oscillating=1 또는 g_exceeded=1  -> 불안정
         (지속 리밋사이클이거나 구조 포락선 +9/-3G 를 실제로 넘김 — 둘 다 회복이
          아니라 발산/한계접촉이므로 다른 지표를 볼 필요가 없다)
      2. rho = 지표/기준 중 하나라도 thresh 초과 -> 열화
      3. 나머지 -> 안정
    """
    def ratio(x, r):
        x, r = float(x), float(r)
        if abs(r) < 1e-12:
            return 1.0 if abs(x) < 1e-12 else float("inf")
        return x / r

    ratios = {
        "rho_overshoot": round(ratio(overshoot, ref[0]), 4),
        "rho_settle": round(ratio(settle_s, ref[1]), 4),
        "rho_rms_track": round(ratio(rms_track, ref[2]), 4),
    }
    if int(oscillating) == 1 or int(g_exceeded) == 1:
        return BAND_UNSTABLE, ratios
    if max(ratios.values()) > thresh:
        return BAND_DEGRADED, ratios
    return BAND_STABLE, ratios


# ============================================================================
# 명령-실제 지연시간 (상호상관)  — 2026-09-14 추가
# ============================================================================
def xcorr_lag_s(cmd, act, dt: float, max_lag_s: float = 1.0) -> dict:
    """명령 신호와 실제 응답의 상호상관 최대점 지연 [s].

    두 신호에서 평균을 뺀 뒤 act 를 뒤로 미뤄가며(=cmd 가 앞서는 방향) 정규화
    상관을 최대화하는 지연을 찾는다. 반환 lag > 0 이면 **실제가 명령보다 늦다**.

    주의: 정상상태(둘 다 상수)에는 정보가 없다. 진폭(std)이 사실상 0 인 신호는
    지연이 정의되지 않으므로 lag=NaN, corr=0 으로 돌려준다 — 호출부에서
    그대로 기록하고 해석하지 말 것.

    피크 주변 3점 포물선 보간으로 샘플(1/120s=8.3ms)보다 미세한 해상도를 낸다.
    """
    c = np.asarray(cmd, float); a = np.asarray(act, float)
    n = min(len(c), len(a))
    c, a = c[:n] - np.mean(c[:n]), a[:n] - np.mean(a[:n])
    sc, sa = float(np.std(c)), float(np.std(a))
    if n < 8 or sc < 1e-9 or sa < 1e-9:
        return {"lag_s": float("nan"), "xcorr_peak": 0.0, "lag_valid": 0}

    max_lag = int(min(max_lag_s / dt, n - 2))
    lags = np.arange(0, max_lag + 1)
    vals = np.empty(len(lags))
    for i, L in enumerate(lags):
        x, y = c[: n - L], a[L:]
        d = np.std(x) * np.std(y) * len(x)
        vals[i] = float(np.dot(x - x.mean(), y - y.mean()) / d) if d > 1e-12 else 0.0

    i = int(np.argmax(vals))
    lag = float(lags[i])
    if 0 < i < len(vals) - 1:                     # 3점 포물선 보간
        y0, y1, y2 = vals[i - 1], vals[i], vals[i + 1]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-12:
            lag += 0.5 * (y0 - y2) / den
    return {"lag_s": round(lag * dt, 6), "xcorr_peak": round(float(vals[i]), 4),
            "lag_valid": 1}
