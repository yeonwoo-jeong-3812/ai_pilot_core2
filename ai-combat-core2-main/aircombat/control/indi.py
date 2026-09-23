"""
indi_fixedwing.py
=================
Incremental Nonlinear Dynamic Inversion (INDI) inner-loop *body-rate* controller
for a fixed-wing aircraft, written for a JSBSim-based F-16 driven from Python.

LICENSING NOTE (read this first)
--------------------------------
This file is an ORIGINAL, clean-room implementation written only from the
published INDI *algorithm* (the equations in Smeur, Chu & de Croon, "Adaptive
Incremental Nonlinear Dynamic Inversion for Attitude Control of Micro Air
Vehicles", J. Guidance, Control & Dynamics, 2016, and related papers). No source
code from Paparazzi (GPLv2), ArduPilot (GPLv3) or any other copyleft project was
read or copied. Algorithms/mathematics are not copyrightable; only a specific
code *expression* is. You may therefore license THIS file however your program
requires (e.g. keep it proprietary, or BSD-3-Clause to match a PX4-based stack).

The only third-party runtime dependency is `numpy`. The optional demo at the
bottom additionally imports `jsbsim` (LGPL-2.1) which you *link against* rather
than derive from, so it does not impose copyleft on your own code.

THE CONTROL LAW (fixed-wing inner loop)
---------------------------------------
Rotational dynamics:  J*omega_dot = M(u, qbar, ...) - omega x J*omega
INDI replaces all the hard-to-model terms with a *measured* angular
acceleration and only needs the input effectiveness G = d(omega_dot)/d(u):

    nu      = K_rate * (omega_sp - omega)            # desired angular accel
    G(qbar) = (qbar / qbar_ref) * G0                 # aero effectiveness scales with q-bar
    du      = G^+ * (nu - alpha_meas)                # required control increment
    u_k     = u_filt_{k-1} + du                      # increment the (filtered) actuator state

The key fixed-wing twist vs. the multirotor INDI literature: control
effectiveness scales (approximately) with dynamic pressure qbar = 0.5*rho*V^2,
so G is gain-scheduled on qbar. Because alpha is *measured*, G only has to be
roughly correct in direction and scale.

A second-order low-pass filter is applied to BOTH the angular-acceleration
estimate and the actuator command with identical dynamics, so the two signals
are time-aligned (this synchronization is the crux of a working INDI loop).
"""

from __future__ import annotations
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class INDIConfig:
    """L3 튜닝 노브 (연구: paper.md §7-C). 기본값 = 기존 하드코딩과 비트 동일.

    k_p/k_q/k_r : 각속도 오차 → 원하는 각가속도 게인 [1/s]
    filt_hz     : 동기화 LPF 차단주파수 [Hz]
    k_att       : 쿼터니언 shim 자세 게인 [1/s]
    k_ff        : 각속도 명령 피드포워드 이득 (0 = 끔)
    lam         : Δu 정칙화 (0 = 끔 — 정방 역행렬 그대로)
    """
    k_p: float = 9.0
    k_q: float = 9.0
    k_r: float = 6.0
    filt_hz: float = 25.0
    k_att: float = 4.0
    k_ff: float = 0.0
    lam: float = 0.0


@dataclass(frozen=True)
class SensorConfig:
    """INDI 측정 모델 (평가 조건 — 튜닝 변수 아님). 기본 "truth" = 기존 동작.

    kind            : "truth" = JSBSim 참값 p,q,r + pdot,qdot,rdot
                      "gyro"  = 자이로 p,q,r + 백색잡음, 각가속도는 INDI 내부 차분 추정
                      (논문 4·5 처럼 잡음이 있어야 filt_hz·λ 의 잡음↔지연 상충이 생긴다)
    gyro_sigma_dps  : 자이로 백색잡음 1σ [deg/s] (120 Hz 샘플 기준)
    delay_ticks     : 측정 지연 [물리 틱 = 1/120 s] (논문 2·5 지연 강건성)
    seed            : 잡음 시드 (결정론 — 같은 seed 는 같은 잡음열)
    """
    kind: str = "truth"
    gyro_sigma_dps: float = 0.1
    delay_ticks: int = 0
    seed: int = 0


class RateSensor:
    """SensorConfig → 측정 (pqr, ang_accel|None). ang_accel=None 이면 INDI 가 차분 추정."""

    def __init__(self, cfg: SensorConfig | None = None, salt: int = 0):
        self.cfg = cfg or SensorConfig()
        if self.cfg.kind not in ("truth", "gyro"):
            raise ValueError(f"sensor kind 는 truth|gyro: {self.cfg.kind!r}")
        self._rng = np.random.default_rng([self.cfg.seed, salt]) \
            if self.cfg.kind == "gyro" else None
        self._buf = []

    def __call__(self, pqr_true, acc_true):
        pqr = np.asarray(pqr_true, float)
        acc = np.asarray(acc_true, float)
        if self._rng is not None:
            pqr = pqr + self._rng.normal(0.0, np.deg2rad(self.cfg.gyro_sigma_dps), 3)
            acc = None
        if not self.cfg.delay_ticks:
            return pqr, acc
        self._buf.append((pqr, acc))
        if len(self._buf) > self.cfg.delay_ticks + 1:
            self._buf.pop(0)
        return self._buf[0]          # 버퍼가 차기 전(시작 직후)엔 가장 오래된 값


# ----------------------------------------------------------------------------- 
# Second-order low-pass (Butterworth biquad), vectorised over channels.
# Used as the INDI "synchronization" filter on rates/accel and on actuators.
# ----------------------------------------------------------------------------- 
class SecondOrderLPF:
    def __init__(self, cutoff_hz: float, sample_rate_hz: float,
                 n_channels: int, damping: float = 0.7071, x0=0.0):
        wc = 2.0 * np.pi * cutoff_hz
        T = 1.0 / sample_rate_hz
        n = 2.0 / T                      # bilinear (Tustin) transform constant
        d = n * n + 2.0 * damping * wc * n + wc * wc
        self.b0 = wc * wc / d
        self.b1 = 2.0 * wc * wc / d
        self.b2 = wc * wc / d
        self.a1 = (2.0 * wc * wc - 2.0 * n * n) / d
        self.a2 = (n * n - 2.0 * damping * wc * n + wc * wc) / d
        x0 = np.broadcast_to(np.asarray(x0, float), (n_channels,)).astype(float)
        self.x1 = x0.copy(); self.x2 = x0.copy()
        self.y1 = x0.copy(); self.y2 = x0.copy()

    def reset(self, x0):
        x0 = np.broadcast_to(np.asarray(x0, float), self.x1.shape).astype(float)
        self.x1[:] = x0; self.x2[:] = x0; self.y1[:] = x0; self.y2[:] = x0

    def __call__(self, x):
        x = np.asarray(x, float)
        y = (self.b0 * x + self.b1 * self.x1 + self.b2 * self.x2
             - self.a1 * self.y1 - self.a2 * self.y2)
        self.x2[:] = self.x1; self.x1[:] = x
        self.y2[:] = self.y1; self.y1[:] = y
        return y


# ----------------------------------------------------------------------------- 
# INDI inner-loop body-rate controller (roll/pitch/yaw rates p, q, r).
# ----------------------------------------------------------------------------- 
class INDIRateController:
    """
    Parameters
    ----------
    dt        : controller timestep [s]
    G0        : (3,3) control effectiveness d(pdot,qdot,rdot)/d(u) identified at
                qbar_ref. Columns = [aileron, elevator, rudder]; rows = [p,q,r].
    qbar_ref  : reference dynamic pressure at which G0 was identified [same units
                as the qbar you pass to update(), e.g. lbf/ft^2 for JSBSim].
    k_rate    : (3,) proportional gains on body-rate error -> desired angular
                accel [1/s]. Larger = faster, noisier. Typical 4-12.
    u_min/max : (3,) actuator command saturation (e.g. -1..1 normalised).
    filt_hz   : cutoff for the synchronization low-pass [Hz].
    qbar_min  : floor on qbar to keep G invertible at low airspeed.
    k_ff      : gain on the (sync-filtered) derivative of omega_sp, added to nu.
                Compensates the lag of a pure P rate law (aero damping). 0 = off.
    lam       : Levenberg-Marquardt regularisation of du, scaled per channel so it
                is qbar-invariant: du = (G^T G + lam*diag(G^T G))^-1 G^T e.
                Diagonal-dominant G -> each increment shrinks ~1/(1+lam). 0 = plain solve.
    """
    def __init__(self, dt, G0, qbar_ref, k_rate=(8.0, 8.0, 6.0),
                 u_min=(-1, -1, -1), u_max=(1, 1, 1),
                 filt_hz=20.0, qbar_min=20.0, k_ff=0.0, lam=0.0):
        self.dt = float(dt)
        self.G0 = np.asarray(G0, float).reshape(3, 3)
        self.qbar_ref = float(qbar_ref)
        self.k_rate = np.asarray(k_rate, float)
        self.u_min = np.asarray(u_min, float)
        self.u_max = np.asarray(u_max, float)
        self.qbar_min = float(qbar_min)
        self.k_ff = float(k_ff)
        self.lam = float(lam)
        fs = 1.0 / self.dt
        # Two filters with IDENTICAL dynamics so accel and actuator stay aligned.
        self.f_acc = SecondOrderLPF(filt_hz, fs, 3)
        self.f_act = SecondOrderLPF(filt_hz, fs, 3)
        self.f_rate = SecondOrderLPF(filt_hz, fs, 3)   # rate used in the error term
        self.f_sp = SecondOrderLPF(filt_hz, fs, 3)     # setpoint, for k_ff derivative
        self.u_prev = np.zeros(3)
        self.omega_prev = np.zeros(3)
        self.sp_prev = None                            # filtered setpoint (k_ff)
        self._primed = False

    def reset(self, u0=(0, 0, 0), omega0=(0, 0, 0)):
        u0 = np.asarray(u0, float); omega0 = np.asarray(omega0, float)
        self.u_prev = u0.copy(); self.omega_prev = omega0.copy()
        self.f_acc.reset(0.0); self.f_act.reset(u0); self.f_rate.reset(omega0)
        self.sp_prev = None
        self._primed = True

    def update(self, omega, omega_sp, qbar, ang_accel=None, omega_sp_dot=None):
        """
        omega        : (3,) measured body rates [p,q,r] (rad/s)
        omega_sp     : (3,) commanded body rates (rad/s)
        qbar         : scalar dynamic pressure (same units as qbar_ref)
        ang_accel    : (3,) measured angular acceleration [pdot,qdot,rdot]
                       (rad/s^2). In JSBSim read accelerations/pdot|qdot|rdot.
                       If None, it is estimated from a filtered finite difference
                       of omega (what you'd do on real hardware with only a gyro).
        omega_sp_dot : (3,) optional rate-setpoint feedforward (rad/s^2).
        returns u    : (3,) actuator command [aileron, elevator, rudder].
        """
        omega = np.asarray(omega, float)
        omega_sp = np.asarray(omega_sp, float)
        if not self._primed:
            self.reset(self.u_prev, omega)

        # --- measured angular acceleration, filtered ---
        if ang_accel is None:
            alpha_raw = (omega - self.omega_prev) / self.dt
        else:
            alpha_raw = np.asarray(ang_accel, float)
        alpha_f = self.f_acc(alpha_raw)

        # --- filtered actuator state (delay-matched to alpha_f) ---
        u_f = self.f_act(self.u_prev)

        # --- filtered rate for the feedback term ---
        omega_f = self.f_rate(omega)

        # --- desired angular acceleration (linear outer law on rate error) ---
        nu = self.k_rate * (omega_sp - omega_f)
        if omega_sp_dot is not None:
            nu = nu + np.asarray(omega_sp_dot, float)
        if self.k_ff:
            # 60Hz 계단 setpoint 를 그대로 미분하면 스파이크 — 동기화 LPF 로 평활 후 미분.
            if self.sp_prev is None:
                self.f_sp.reset(omega_sp)
                self.sp_prev = omega_sp.copy()
            sp_f = self.f_sp(omega_sp)
            nu = nu + self.k_ff * (sp_f - self.sp_prev) / self.dt
            self.sp_prev = sp_f

        # --- qbar-scheduled effectiveness and increment ---
        G = (max(qbar, self.qbar_min) / self.qbar_ref) * self.G0
        e = nu - alpha_f
        if self.lam:
            GtG = G.T @ G
            # 채널별 스케일(LM 형): 단일 tr(GᵀG) 스케일은 효과가 큰 roll 이 λ 를 정해
            # 효과가 작은 yaw 를 과도하게 억눌렀다(수렴 실패, test_indi_study).
            du = np.linalg.solve(GtG + self.lam * np.diag(np.diag(GtG)), G.T @ e)
        else:
            du = np.linalg.solve(G, e) if abs(np.linalg.det(G)) > 1e-9 \
                else np.linalg.pinv(G) @ e

        u = np.clip(u_f + du, self.u_min, self.u_max)

        self.u_prev = u
        self.omega_prev = omega
        return u


# NOTE: 자세→각속도(omega_sp) 변환은 여기 두지 않는다. tmp 원본의 Euler 기반
# `AttitudeToRate` shim 은 D3(쿼터니언)에 따라 aircombat/control/attitude.py 로 대체된다.


# -----------------------------------------------------------------------------
# JSBSim helper: identify G0 by perturbing each surface at the current trim.
# This gives you a real, aircraft/flight-condition-specific effectiveness matrix
# instead of hand-guessed numbers.
# ----------------------------------------------------------------------------- 
def identify_G0(fdm, delta=0.02, settle=3):
    """Perturb aileron/elevator/rudder by +-delta and measure d(angaccel)/du.
    Returns (G0 (3,3), qbar_ref). Call right after trimming. Non-destructive:
    restores the original commands afterwards."""
    CMD = ['fcs/aileron-cmd-norm', 'fcs/elevator-cmd-norm', 'fcs/rudder-cmd-norm']
    ACC = ['accelerations/pdot-rad_sec2', 'accelerations/qdot-rad_sec2',
           'accelerations/rdot-rad_sec2']
    u0 = np.array([fdm[c] for c in CMD])
    qbar_ref = fdm['aero/qbar-psf']

    def measure(u):
        for c, v in zip(CMD, u):
            fdm[c] = float(v)
        for _ in range(settle):
            fdm.run()
        return np.array([fdm[a] for a in ACC])

    G0 = np.zeros((3, 3))
    for j in range(3):
        up = u0.copy(); up[j] += delta
        um = u0.copy(); um[j] -= delta
        a_plus = measure(up)
        a_minus = measure(um)
        G0[:, j] = (a_plus - a_minus) / (2.0 * delta)   # central difference
    measure(u0)  # restore
    return G0, qbar_ref


# DEMO/검증(45° 뱅크 스텝, RMS)은 scripts/run_indi_step.py 로 분리됨.
