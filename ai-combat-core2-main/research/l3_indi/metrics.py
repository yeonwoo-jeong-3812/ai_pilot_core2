"""사전등록 지표 — docs/PREREGISTRATION.md §3, §4, §7, §8.

입력은 전부 `harness.run` 의 참 상태 시계열이다. 잡음 섞인 측정값은 쓰지 않는다.
"""
from __future__ import annotations

import numpy as np

J_FLOOR_DPS = 2.0                 # §3.1 분모 하한
BAND_THRESH = 1.5                 # §7.1
BAND_SENSITIVITY = (1.3, 2.0)     # §7.1 병기
OSC_RATE_P2P_DPS = 3.0            # §7.1 = sweep_diagnostics 와 같은 값
OSC_NZ_P2P = 3.0
OSC_SIGNCHG_HZ = 1.0
OSC_WINDOW_S = 3.0
SIGN_DEADBAND = 0.02              # §7.1 추가 규칙 (명령 부호반전 판정 데드밴드)
G_ENV_MAX, G_ENV_MIN = 9.0, -3.0
CAPABILITY_FRAC = 0.95            # §3.2 능력 제한 판정
CAPABILITY_TIME_FRAC = 0.10
DEPART_ALPHA_DEG = 30.0           # §8
DEPART_KCAS = 150.0


def heading_unwrapped_deg(psi_rad) -> np.ndarray:
    """§2.3 JSBSim psi 는 [0, 2π) 로 감긴다(트림 직후 psi0 = 2π). 반드시 unwrap 후 차분."""
    return np.rad2deg(np.unwrap(np.asarray(psi_rad, float)))


def window_mask(ts: dict, window: tuple[float, float]) -> np.ndarray:
    t = ts["t"]
    return (t >= window[0] - 1e-9) & (t < window[1] - 1e-9)


def tracking_J(ts: dict, axis: str, window) -> float:
    """§3.1 축별 정규화 각속도 추종 오차 (무차원)."""
    m = window_mask(ts, window)
    sp = np.rad2deg(ts[f"sp_{axis}"][m])
    w = np.rad2deg(ts[axis][m])
    num = np.sqrt(np.mean((sp - w) ** 2))
    den = max(np.sqrt(np.mean(sp ** 2)), J_FLOOR_DPS)
    return float(num / den)


def sign_change_hz(u: np.ndarray, trim: float, dt: float, deadband: float = SIGN_DEADBAND) -> float:
    """트림을 뺀 명령의 부호반전율. |x| <= deadband 구간은 직전 부호를 유지(히스테리시스)."""
    x = np.asarray(u, float) - trim
    if len(x) < 2:
        return 0.0
    state = 0
    changes = 0
    for v in x:
        s = 1 if v > deadband else (-1 if v < -deadband else 0)
        if s == 0:
            continue
        if state != 0 and s != state:
            changes += 1
        state = s
    dur = (len(x) - 1) * dt
    return changes / dur if dur > 0 else 0.0


OSC_SIGNCHG_MIN_RATE_P2P_DPS = 0.5   # 개정 A3: 기체 각속도 p2p 가 이 이상일 때만 부호반전 기준 적용


def oscillation(ts: dict, dt: float, window_s: float = OSC_WINDOW_S,
                deadband: float = SIGN_DEADBAND) -> dict:
    """§7.1 + 개정 A3 리밋사이클 판정 — 마지막 window_s 초, 참 상태 기준.

    반환:
      oscillating      개정 A3 규칙 (부호반전 기준은 각속도 p2p ≥ 0.5 deg/s 일 때만)
      osc_v1           사전등록 원문 규칙 (부호반전 기준 무조건 적용)
      osc_signchg_only 원문 규칙에서 부호반전 기준만 참 (각속도·Nz 기준은 거짓)
    """
    t = ts["t"]
    m = t >= t[-1] - window_s
    p2p = lambda a: float(np.nanmax(a[m]) - np.nanmin(a[m]))
    p2p_rate = max(p2p(np.rad2deg(ts[a])) for a in ("p", "q", "r"))
    p2p_nz = p2p(ts["nz"])
    trims = {c: ts[c][0] for c in ("u_ail", "u_ele", "u_rud")}
    sc = max(sign_change_hz(ts[c][m], trims[c], dt, deadband) for c in trims)
    motion = p2p_rate > OSC_RATE_P2P_DPS or p2p_nz > OSC_NZ_P2P
    sc_hit = sc > OSC_SIGNCHG_HZ
    osc_v1 = int(motion or sc_hit)
    osc = int(motion or (sc_hit and p2p_rate >= OSC_SIGNCHG_MIN_RATE_P2P_DPS))
    return {"p2p_rate_dps": p2p_rate, "p2p_nz": p2p_nz, "signchg_hz": sc,
            "oscillating": osc, "osc_v1": osc_v1,
            "osc_signchg_only": int(sc_hit and not motion)}


def envelope(ts: dict) -> dict:
    nz = ts["nz"]
    exc = (nz > G_ENV_MAX) | (nz < G_ENV_MIN)
    return {"g_exceeded": int(np.any(exc)), "nz_max": float(np.nanmax(nz)),
            "nz_min": float(np.nanmin(nz))}


def departure(ts: dict) -> int:
    return int(np.any(np.rad2deg(ts["alpha"]) > DEPART_ALPHA_DEG)
               or np.any(ts["kcas"] < DEPART_KCAS)
               or np.any(~np.isfinite(ts["nz"])))


def nz_metrics(ts: dict, window, nz_target: float, hold_from_s: float | None = None) -> dict:
    """§4 Nz 실현율 / 상승시간(10→90%) / 오버슈트."""
    m = window_mask(ts, window)
    t, nz = ts["t"][m], ts["nz"][m]
    n0 = float(nz[0])
    def first(level):
        idx = np.nonzero(nz >= level)[0]
        return float(t[idx[0]]) if len(idx) else float("nan")
    t10 = first(n0 + 0.1 * (nz_target - n0))
    t90 = first(n0 + 0.9 * (nz_target - n0))
    hm = t >= (hold_from_s if hold_from_s is not None else window[0] + 0.5 * (window[1] - window[0]))
    return {"nz_realization": float(np.mean(nz[hm]) / nz_target),
            "nz_rise_s": (t90 - t10) if np.isfinite(t10) and np.isfinite(t90) else float("nan"),
            "nz_overshoot": max(0.0, float(np.max(nz)) - nz_target)}


def bank_metrics(ts: dict, t_start: float, t_end: float, target_deg: float) -> dict:
    """§4 뱅크 도달·오버슈트·정착 (밴드 max(2°, 5%))."""
    t = ts["t"]
    m = (t >= t_start) & (t < t_end)
    ph = np.rad2deg(ts["phi"][m])
    tt = t[m]
    band = max(2.0, 0.05 * abs(target_deg))
    sgn = np.sign(target_deg) if target_deg != 0 else 1.0
    err = ph - target_deg
    inside = np.abs(err) <= band
    reach = np.nonzero(inside)[0]
    out_idx = np.nonzero(~inside)[0]
    settle = float(tt[out_idx[-1]] - t_start + (tt[1] - tt[0])) if len(out_idx) else 0.0
    return {"bank_reach_s": float(tt[reach[0]] - t_start) if len(reach) else float("nan"),
            "bank_overshoot_deg": max(0.0, float(np.max(sgn * err))),
            "bank_settle_s": settle if len(out_idx) < len(tt) else float("nan")}


def capability_limited(ts: dict, window, cap_p_dps: float) -> int:
    """§3.2 능력 제한 런: |p_sp| > 0.95·C_p 인 시간이 창의 10% 초과."""
    m = window_mask(ts, window)
    over = np.abs(np.rad2deg(ts["sp_p"][m])) > CAPABILITY_FRAC * cap_p_dps
    return int(np.mean(over) > CAPABILITY_TIME_FRAC)


def saturation(ts: dict, window) -> dict:
    m = window_mask(ts, window)
    return {f"sat_{a}_pct": float(100 * np.mean(np.abs(ts[f"u_{a}"][m]) > 0.999))
            for a in ("ail", "ele", "rud")} | {
        "rud_pos_max_deg": float(np.max(np.abs(ts["pos_rud_deg"][m]))),
        "beta_abs_mean_deg": float(np.mean(np.abs(np.rad2deg(ts["beta"][m])))),
        "beta_abs_max_deg": float(np.max(np.abs(np.rad2deg(ts["beta"][m])))),
    }


def classify_band(metrics: dict, ref: dict, keys: tuple, osc: int, g_exceeded: int,
                  thresh: float = BAND_THRESH) -> tuple[str, dict]:
    """§7.1 3구간. ref = 같은 조건·기동·filt·잡음의 k 배율 1.0 런의 지표."""
    def ratio(a, b):
        a, b = float(a), float(b)
        if not np.isfinite(a) or not np.isfinite(b):
            return float("inf") if not np.isfinite(a) and np.isfinite(b) else 1.0
        if abs(b) < 1e-12:
            return 1.0 if abs(a) < 1e-12 else float("inf")
        return a / b
    rho = {f"rho_{k}": ratio(metrics[k], ref[k]) for k in keys}
    if osc or g_exceeded:
        return "unstable", rho
    if max(rho.values()) > thresh:
        return "degraded", rho
    return "stable", rho


def freq_response(ts: dict, axis: str, freqs_hz, window, dt: float) -> dict:
    """§4 M4: 멀티사인 주파수에서 H = W(f)/SP(f). 반환 {f: (gain_db, phase_deg)}.

    창 길이를 정수 주기로 맞추지 않은 누설은 해닝 창으로 줄인다.
    """
    m = window_mask(ts, window)
    sp = ts[f"sp_{axis}"][m] - np.mean(ts[f"sp_{axis}"][m])
    w = ts[axis][m] - np.mean(ts[axis][m])
    win = np.hanning(len(sp))
    Fs, Fw = np.fft.rfft(sp * win), np.fft.rfft(w * win)
    f = np.fft.rfftfreq(len(sp), dt)
    res = {}
    for fr in freqs_hz:
        i = int(np.argmin(np.abs(f - fr)))
        H = Fw[i] / Fs[i]
        res[float(fr)] = (float(20 * np.log10(np.abs(H))), float(np.rad2deg(np.angle(H))))
    return res
