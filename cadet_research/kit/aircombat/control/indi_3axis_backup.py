"""Frozen backup of the original three-axis INDI rate controller.

This module preserves the pre-2026-09-12 controller that inverted the complete
3x3 [p,q,r] / [aileron,elevator,rudder] effectiveness matrix. It is not imported
by the production control path. Use it only for A/B experiments against the new
two-axis INDI + native-yaw-FLCS baseline.

The synchronization filter is shared with ``aircombat.control.indi``; the
controller state update and full 3x3 allocation below are the frozen legacy law.
"""

from __future__ import annotations

import numpy as np

from aircombat.control.indi import SecondOrderLPF


class INDIRateController3AxisBackup:
    """Legacy full-axis INDI controller retained for controlled comparisons."""

    def __init__(self, dt, G0, qbar_ref, k_rate=(8.0, 8.0, 6.0),
                 u_min=(-1, -1, -1), u_max=(1, 1, 1),
                 filt_hz=20.0, qbar_min=20.0):
        self.dt = float(dt)
        self.G0 = np.asarray(G0, float).reshape(3, 3)
        self.qbar_ref = float(qbar_ref)
        self.k_rate = np.asarray(k_rate, float)
        self.u_min = np.asarray(u_min, float)
        self.u_max = np.asarray(u_max, float)
        self.qbar_min = float(qbar_min)
        fs = 1.0 / self.dt
        self.f_acc = SecondOrderLPF(filt_hz, fs, 3)
        self.f_act = SecondOrderLPF(filt_hz, fs, 3)
        self.f_rate = SecondOrderLPF(filt_hz, fs, 3)
        self.u_prev = np.zeros(3)
        self.omega_prev = np.zeros(3)
        self._primed = False

    def reset(self, u0=(0, 0, 0), omega0=(0, 0, 0)):
        u0 = np.asarray(u0, float)
        omega0 = np.asarray(omega0, float)
        self.u_prev = u0.copy()
        self.omega_prev = omega0.copy()
        self.f_acc.reset(0.0)
        self.f_act.reset(u0)
        self.f_rate.reset(omega0)
        self._primed = True

    def update(self, omega, omega_sp, qbar, ang_accel=None, omega_sp_dot=None):
        omega = np.asarray(omega, float)
        omega_sp = np.asarray(omega_sp, float)
        if not self._primed:
            self.reset(self.u_prev, omega)

        if ang_accel is None:
            alpha_raw = (omega - self.omega_prev) / self.dt
        else:
            alpha_raw = np.asarray(ang_accel, float)
        alpha_f = self.f_acc(alpha_raw)
        u_f = self.f_act(self.u_prev)
        omega_f = self.f_rate(omega)

        nu = self.k_rate * (omega_sp - omega_f)
        if omega_sp_dot is not None:
            nu = nu + np.asarray(omega_sp_dot, float)

        G = (max(qbar, self.qbar_min) / self.qbar_ref) * self.G0
        du = (np.linalg.solve(G, nu - alpha_f)
              if abs(np.linalg.det(G)) > 1e-9
              else np.linalg.pinv(G) @ (nu - alpha_f))
        u = np.clip(u_f + du, self.u_min, self.u_max)

        self.u_prev = u
        self.omega_prev = omega
        return u


__all__ = ["INDIRateController3AxisBackup"]
