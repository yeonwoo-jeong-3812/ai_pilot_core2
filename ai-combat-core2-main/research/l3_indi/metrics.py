"""사전등록 지표 — docs/PREREGISTRATION.md §3, §4, §7, §8.

입력은 전부 `harness.run` 의 참 상태 시계열이다. 잡음 섞인 측정값은 쓰지 않는다.
"""
from __future__ import annotations

import numpy as np

G_FT_S2 = 32.174                  # aircombat.control.limiter.G_FT_S2 와 같은 값 (G9 에서 대조)
J_FLOOR_DPS = 2.0                # §3.1 분모 하한
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


NZ_SETTLE_BAND_G = 0.3             # 개정 A13-1 (G5 와 같은 밴드)
NZ_SETTLE_BAND_FRAC = 0.05
RATIO_FLOOR = {"nz_overshoot": 0.05, "bank_overshoot_deg": 1.0,      # 개정 A13-2
               "nz_settle_s": 0.25, "bank_settle_s": 0.25}


def nz_settle(ts: dict, window, nz_target: float) -> float:
    """개정 A13-1: 창 시작부터 |Nz−목표| > max(0.3, 5%) 인 마지막 틱까지 + Δt. 한 번도 밴드에 못 들면 NaN."""
    m = window_mask(ts, window)
    t, nz = ts["t"][m], ts["nz"][m]
    band = max(NZ_SETTLE_BAND_G, NZ_SETTLE_BAND_FRAC * abs(nz_target))
    out = np.nonzero(np.abs(nz - nz_target) > band)[0]
    if len(out) == len(nz):
        return float("nan")
    if len(out) == 0:
        return 0.0
    return float(t[out[-1]] - window[0] + (t[1] - t[0]))


def floored_ratio(key: str, value: float, ref: float) -> float:
    """개정 A13-2: ρ = max(x, f)/max(기준, f). NaN(미정착)은 ∞. 기준이 NaN 이면 NaN."""
    f = RATIO_FLOOR.get(key, 0.0)
    if not np.isfinite(ref):
        return float("nan")
    if not np.isfinite(value):
        return float("inf")
    den = max(ref, f)
    if den <= 0:
        return 1.0 if max(value, f) <= 0 else float("inf")
    return max(value, f) / den


def nz_exceeds_cap(ts: dict, window, c_nz: float) -> int:
    """개정 A9: 창 안 Nz 가 C_nz 를 넘었는지 (검열하지 않고 플래그만)."""
    return int(np.nanmax(ts["nz"][window_mask(ts, window)]) > c_nz)


# ======================================================================================
# 개정 A10-1 시간척도 분리 잔차 ε
# ======================================================================================
QBAR_MIN = 20.0                    # INDIRateController 기본 qbar_min 과 같은 값
TSS_BIN_ALPHA_DEG = 2.0
TSS_BIN_NZ = 0.5
TSS_MIN_TICKS = 120


def tss_terms(ts: dict, window, G0_true, qbar_ref: float, qbar_min: float = QBAR_MIN):
    """틱별 (|r|, |Δω̇|, α[deg], Nz) — 틱 k, k−1 이 모두 창 안인 틱만.

    Δω̇_k = ω̇_k − ω̇_{k−1},  Δu_k = u_k − u_{k−1} (플랜트에 걸린 cmd_*),
    G_k = (max(q̄_k, q̄_min)/q̄_ref)·G0_true,  r_k = Δω̇_k − G_k·Δu_k
    """
    m = window_mask(ts, window)
    pair = m[1:] & m[:-1]
    idx = np.nonzero(pair)[0] + 1
    wd = np.stack([ts["pdot"], ts["qdot"], ts["rdot"]], axis=1)
    u = np.stack([ts["cmd_ail"], ts["cmd_ele"], ts["cmd_rud"]], axis=1)
    dwd = wd[idx] - wd[idx - 1]
    du = u[idx] - u[idx - 1]
    scale = np.maximum(ts["qbar"][idx], qbar_min) / qbar_ref
    pred = scale[:, None] * (du @ np.asarray(G0_true, float).T)
    r = dwd - pred
    return np.abs(r), np.abs(dwd), np.rad2deg(ts["alpha"][idx]), ts["nz"][idx]


def tss_residual(ts: dict, window, G0_true, qbar_ref: float, qbar_min: float = QBAR_MIN) -> dict:
    """런 요약 ε_i = Σ|r_i| / Σ|Δω̇_i| (축별)."""
    ar, ad, _, _ = tss_terms(ts, window, G0_true, qbar_ref, qbar_min)
    out = {}
    for i, a in enumerate("pqr"):
        den = float(np.sum(ad[:, i]))
        out[f"eps_{a}"] = float(np.sum(ar[:, i]) / den) if den >= 1e-9 else float("nan")
    return out


def tss_accumulate(acc: dict | None, ts: dict, window, G0_true, qbar_ref: float) -> dict:
    """히트맵용 누적: 칸 (α 2°, Nz 0.5G) 별 Σ|r_i|, Σ|Δω̇_i|, 틱 수."""
    acc = acc if acc is not None else {}
    ar, ad, al, nz = tss_terms(ts, window, G0_true, qbar_ref)
    ia = np.floor(al / TSS_BIN_ALPHA_DEG).astype(int)
    iz = np.floor(nz / TSS_BIN_NZ).astype(int)
    for k in range(len(ia)):
        key = (int(ia[k]), int(iz[k]))
        c = acc.setdefault(key, [np.zeros(3), np.zeros(3), 0])
        c[0] += ar[k]; c[1] += ad[k]; c[2] += 1
    return acc


def tss_heatmap(acc: dict) -> list[dict]:
    """누적 → 칸별 ε_i 행 목록. 틱 < 120 칸은 제외."""
    rows = []
    for (ia, iz), (sr, sd, n) in sorted(acc.items()):
        if n < TSS_MIN_TICKS:
            continue
        row = {"alpha_lo_deg": ia * TSS_BIN_ALPHA_DEG, "nz_lo": iz * TSS_BIN_NZ, "ticks": n}
        for i, a in enumerate("pqr"):
            row[f"eps_{a}"] = float(sr[i] / sd[i]) if sd[i] >= 1e-9 else float("nan")
        rows.append(row)
    return rows


# ======================================================================================
# 개정 A10-2 기동 실현도 F_i
# ======================================================================================
def _body_axes_ned(phi, theta, psi):
    """동체 x, z 축의 NED 성분 (3-2-1 오일러)."""
    cph, sph, cth, sth, cps, sps = np.cos(phi), np.sin(phi), np.cos(theta), np.sin(theta), np.cos(psi), np.sin(psi)
    xb = np.stack([cth * cps, cth * sps, -sth], axis=-1)
    zb = np.stack([cph * sth * cps + sph * sps, cph * sth * sps - sph * cps, cph * cth], axis=-1)
    return xb, zb


def wind_geometry(ts: dict) -> dict:
    """틱별 V̂(NED), 양력 반대방향 z_w(속도에 수직으로 투영), γ, μ, V[ft/s]."""
    v = np.stack([ts["vn"], ts["ve"], ts["vd"]], axis=1)
    V = np.linalg.norm(v, axis=1)
    vh = v / V[:, None]
    xb, zb = _body_axes_ned(ts["phi"], ts["theta"], ts["psi"])
    al = ts["alpha"][:, None]
    zw = -np.sin(al) * xb + np.cos(al) * zb
    zw = zw - np.sum(zw * vh, axis=1)[:, None] * vh
    zw = zw / np.linalg.norm(zw, axis=1)[:, None]
    gamma = np.arcsin(np.clip(-vh[:, 2], -1, 1))
    chi = np.arctan2(vh[:, 1], vh[:, 0])
    y0 = np.stack([-np.sin(chi), np.cos(chi), np.zeros_like(chi)], axis=1)
    z0 = np.stack([np.sin(gamma) * np.cos(chi), np.sin(gamma) * np.sin(chi), np.cos(gamma)], axis=1)
    mu = np.arctan2(-np.sum(zw * y0, axis=1), np.sum(zw * z0, axis=1))
    return {"vhat": vh, "zw": zw, "gamma": gamma, "mu": mu, "V": V}


def path_rates(ts: dict, n_target) -> tuple[np.ndarray, np.ndarray]:
    """틱별 (Ω_act, Ω_ideal) [rad/s]. Ω_act[0] = NaN.

    Ω_ideal = |수직성분(−n_t·g·z_w + g·ê_down)| / V  ≡  (g/V)·√(n_t² − 2n_t cosμ cosγ + cos²γ)
    """
    w = wind_geometry(ts)
    vh, zw, V = w["vhat"], w["zw"], w["V"]
    cr = np.linalg.norm(np.cross(vh[:-1], vh[1:]), axis=1)
    dt = np.diff(ts["t"])
    act = np.concatenate(([np.nan], np.arctan2(cr, np.sum(vh[:-1] * vh[1:], axis=1)) / dt))
    n_t = np.broadcast_to(np.asarray(n_target, float), V.shape)
    down = np.array([0.0, 0.0, 1.0])
    a = -n_t[:, None] * G_FT_S2 * zw + G_FT_S2 * down
    a = a - np.sum(a * vh, axis=1)[:, None] * vh
    ideal = np.linalg.norm(a, axis=1) / V
    return act, ideal


def path_realization(ts: dict, window, n_target=None) -> float:
    """F_i = Σ_W Ω_act / Σ_W Ω_ideal (틱 k, k−1 모두 창 안). n_target 기본값 = gc_g 열."""
    act, ideal = path_rates(ts, ts["gc_g"] if n_target is None else n_target)
    m = window_mask(ts, window)
    pair = np.concatenate(([False], m[1:] & m[:-1]))
    den = float(np.sum(ideal[pair]))
    return float(np.sum(act[pair]) / den) if den > 1e-12 else float("nan")


# ======================================================================================
# 개정 A10-2 T→M 전이: 선형 vs 힌지 (BIC 차 ≥ 10 이면 임계형)
# ======================================================================================
TRANSFER_BIC_DELTA = 10.0


def transfer_fit(d_t, d_m) -> dict:
    x, y = np.asarray(d_t, float), np.asarray(d_m, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 5:
        return {"n": n, "verdict": "insufficient"}

    def bic(sse, k):
        return n * np.log(max(sse, 1e-300) / n) + k * np.log(n)

    a_lin = float(np.dot(x, y) / np.dot(x, x)) if np.dot(x, x) > 0 else 0.0
    sse_lin = float(np.sum((y - a_lin * x) ** 2))
    best = (np.inf, None, None)
    for x0 in np.unique(np.percentile(x, np.arange(1, 100))):
        h = np.maximum(0.0, x - x0)
        hh = float(np.dot(h, h))
        if hh <= 0:
            continue
        a = float(np.dot(h, y) / hh)
        sse = float(np.sum((y - a * h) ** 2))
        if sse < best[0]:
            best = (sse, float(x0), a)
    b_lin, b_h = bic(sse_lin, 1), bic(best[0], 2)
    verdict = "threshold" if (b_lin - b_h) >= TRANSFER_BIC_DELTA else "linear"
    return {"n": n, "a_linear": a_lin, "bic_linear": float(b_lin), "x0": best[1], "a_hinge": best[2],
            "bic_hinge": float(b_h), "delta_bic": float(b_lin - b_h), "verdict": verdict}


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
