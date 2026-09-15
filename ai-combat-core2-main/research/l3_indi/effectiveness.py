"""개정 A10-3 — 실전 궤적의 실효 제어효과 Ĉ 추정 (오프라인, 제어에 영향 없음).

* G0 복원: 궤적에 G0·q̄_ref 가 없으므로 `traces.play` 와 같은 순서(load_policy → initial_conditions →
  make_pilot)로 조립하고 `Pilot.setup()` 을 호출해 경기 시작 시 식별값을 다시 얻는다 (게이트 G10a).
* ω̇: 기록 ω(float32) 의 중심차분 (게이트 G10b).
* 창 1.0 s, 보폭 0.5 s, 축 i 마다 Ĉ_i = Σ φ_i Δω̇_i / Σ φ_i²,  φ = G_k·Δu_k,  λ_real = 1/Ĉ.
"""
from __future__ import annotations

import contextlib
import io
import os

import numpy as np

from .harness import REPO, DT
from .metrics import QBAR_MIN

WIN_TICKS = 120
STRIDE_TICKS = 60
EXCITE_TOP = 0.50
EXCITE_SENS = (0.25, 0.75)


def restore_g0(job: dict) -> dict:
    """{'blue': (G0, qbar_ref), 'red': (G0, qbar_ref)} — 경기 시작 시 Pilot.setup() 식별값."""
    from aircombat.engine.factory import load_policy, make_pilot
    from aircombat.engine.scenarios import initial_conditions
    cwd = os.getcwd()
    os.chdir(REPO)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            sides = [load_policy(job["participant"]), load_policy(job["red_path"])]
            ic = initial_conditions(job["scenario"], seed=job["seed"])
            out = {}
            for side, color, pol in (("blue", "Blue", sides[0]), ("red", "Red", sides[1])):
                p = make_pilot(color, ic[side], *pol)
                p.setup()
                out[side] = (np.array(p.indi.G0, copy=True), float(p.indi.qbar_ref))
    finally:
        os.chdir(cwd)
    return out


def omega_dot_central(omega: np.ndarray, dt: float = DT) -> np.ndarray:
    """(n,3) → (n,3), 양 끝은 NaN.  ω̇_k = (ω_{k+1} − ω_{k−1}) / 2Δt."""
    w = np.asarray(omega, float)
    out = np.full_like(w, np.nan)
    out[1:-1] = (w[2:] - w[:-2]) / (2.0 * dt)
    return out


def windows(omega_dot: np.ndarray, u: np.ndarray, qbar: np.ndarray, G0, qbar_ref: float,
            mask: np.ndarray | None = None, win: int = WIN_TICKS, stride: int = STRIDE_TICKS) -> dict:
    """창별 Ĉ(축), RMS(φ), ε(A10-1 식). 창의 모든 틱이 mask 이고 값이 유한할 때만 쓴다."""
    wd = np.asarray(omega_dot, float)
    u = np.asarray(u, float)
    n = len(wd)
    dwd = np.full_like(wd, np.nan)
    dwd[1:] = wd[1:] - wd[:-1]
    du = np.zeros_like(u)
    du[1:] = u[1:] - u[:-1]
    scale = np.maximum(np.asarray(qbar, float), QBAR_MIN) / qbar_ref
    phi = scale[:, None] * (du @ np.asarray(G0, float).T)
    valid = np.isfinite(dwd).all(axis=1) & np.isfinite(phi).all(axis=1)
    valid[0] = False
    if mask is not None:
        valid &= np.asarray(mask, bool)
    C, R, E, S = [], [], [], []
    for s in range(0, n - win + 1, stride):
        sl = slice(s, s + win)
        if not valid[sl].all():
            continue
        ph, y = phi[sl], dwd[sl]
        pp = np.sum(ph * ph, axis=0)
        C.append(np.where(pp > 0, np.sum(ph * y, axis=0) / np.where(pp > 0, pp, 1.0), np.nan))
        R.append(np.sqrt(np.mean(ph * ph, axis=0)))
        den = np.sum(np.abs(y), axis=0)
        E.append(np.where(den >= 1e-9, np.sum(np.abs(y - ph), axis=0) / np.where(den >= 1e-9, den, 1.0), np.nan))
        S.append(s)
    shape = (len(S), 3)
    return {"C": np.asarray(C, float).reshape(shape), "rms_phi": np.asarray(R, float).reshape(shape),
            "eps": np.asarray(E, float).reshape(shape), "start": np.asarray(S, int)}


def excited(rms_phi: np.ndarray, top: float = EXCITE_TOP) -> np.ndarray:
    """축별로 RMS(φ) 가 상위 top 비율인 창 마스크 (n,3)."""
    r = np.asarray(rms_phi, float)
    if len(r) == 0:
        return np.zeros_like(r, bool)
    thr = np.nanpercentile(r, 100.0 * (1.0 - top), axis=0)
    return r >= thr[None, :]
