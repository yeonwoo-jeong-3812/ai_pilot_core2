"""Aircraft-to-aircraft collision geometry.

The flight model exposes each aircraft as a rigid pose, not a triangle mesh. A
small compound OBB approximates the F-16 fuselage and wing volume closely enough
for the 120 Hz referee while avoiding the empty corners of one large box.
"""
from __future__ import annotations

import numpy as np

from ..engine.state import KinState


# Body axes are forward, right, down [ft]. Dimensions follow the F-16C outer
# envelope (49.3 ft long, 32.8 ft span).
_PARTS = (
    (np.array((0.0, 0.0, 0.0)), np.array((24.65, 3.0, 4.2))),
    (np.array((-2.0, 0.0, 0.0)), np.array((9.0, 16.4, 0.9))),
    (np.array((-17.0, 0.0, 0.0)), np.array((6.0, 10.0, 0.8))),
    (np.array((-16.0, 0.0, -5.8)), np.array((7.0, 0.9, 3.8))),
)
_SAT_EPS = 1e-9


def body_to_ned(phi: float, theta: float, psi: float) -> np.ndarray:
    """Body-to-NED direction cosine matrix for aviation 3-2-1 Euler angles."""
    cp, sp = np.cos(phi), np.sin(phi)
    ct, st = np.cos(theta), np.sin(theta)
    cy, sy = np.cos(psi), np.sin(psi)
    c_bn = np.array([
        [ct * cy, ct * sy, -st],
        [sp * st * cy - cp * sy, sp * st * sy + cp * cy, sp * ct],
        [cp * st * cy + sp * sy, cp * st * sy - sp * cy, cp * ct],
    ])
    return c_bn.T


def obb_intersects(ca: np.ndarray, aa: np.ndarray, ea: np.ndarray,
                   cb: np.ndarray, ab: np.ndarray, eb: np.ndarray) -> bool:
    """Separating-axis test for two oriented boxes; boundary contact counts."""
    r = aa.T @ ab
    ar = np.abs(r) + _SAT_EPS
    t = aa.T @ (cb - ca)

    for i in range(3):
        if abs(t[i]) > ea[i] + float(np.dot(eb, ar[i, :])):
            return False
    for j in range(3):
        if abs(float(np.dot(t, r[:, j]))) > eb[j] + float(np.dot(ea, ar[:, j])):
            return False
    for i in range(3):
        i1, i2 = (i + 1) % 3, (i + 2) % 3
        for j in range(3):
            j1, j2 = (j + 1) % 3, (j + 2) % 3
            distance = abs(t[i2] * r[i1, j] - t[i1] * r[i2, j])
            radius_a = ea[i1] * ar[i2, j] + ea[i2] * ar[i1, j]
            radius_b = eb[j1] * ar[i, j2] + eb[j2] * ar[i, j1]
            if distance > radius_a + radius_b:
                return False
    return True


def aircraft_collide(a: KinState, b: KinState) -> bool:
    """Return True when any fuselage/wing OBB pair overlaps."""
    axes_a = body_to_ned(a.phi, a.theta, a.psi)
    axes_b = body_to_ned(b.phi, b.theta, b.psi)
    pa = np.asarray(a.pos_ned, dtype=float)
    pb = np.asarray(b.pos_ned, dtype=float)
    for offset_a, extent_a in _PARTS:
        center_a = pa + axes_a @ offset_a
        for offset_b, extent_b in _PARTS:
            center_b = pb + axes_b @ offset_b
            if obb_intersects(center_a, axes_a, extent_a,
                              center_b, axes_b, extent_b):
                return True
    return False


def _angle_lerp(a: float, b: float, fraction: float) -> float:
    delta = (b - a + np.pi) % (2.0 * np.pi) - np.pi
    return float(a + fraction * delta)


def _state_lerp(a: KinState, b: KinState, fraction: float) -> KinState:
    """Interpolate one 120 Hz step for collision-time visualization."""
    mix = lambda x, y: float(x + fraction * (y - x))
    return KinState(
        pos_ned=a.pos_ned + fraction * (b.pos_ned - a.pos_ned),
        vel_ned=a.vel_ned + fraction * (b.vel_ned - a.vel_ned),
        phi=_angle_lerp(a.phi, b.phi, fraction),
        theta=_angle_lerp(a.theta, b.theta, fraction),
        psi=_angle_lerp(a.psi, b.psi, fraction),
        v_fps=mix(a.v_fps, b.v_fps), kcas=mix(a.kcas, b.kcas),
        alt_ft=mix(a.alt_ft, b.alt_ft), health=mix(a.health, b.health),
    )


def contact_states(a0: KinState, b0: KinState, a1: KinState, b1: KinState,
                   iterations: int = 28) -> tuple[KinState, KinState]:
    """Return the first touching poses between a non-contact and contact sample.

    The referee still advances physics at 120 Hz. Bisection removes the small
    one-tick penetration from the terminal ACMI frame so solid aircraft do not
    appear to pass through each other in replay.
    """
    if aircraft_collide(a0, b0):
        return a0, b0
    if not aircraft_collide(a1, b1):
        return a1, b1
    lo, hi = 0.0, 1.0
    for _ in range(iterations):
        mid = (lo + hi) * 0.5
        am, bm = _state_lerp(a0, a1, mid), _state_lerp(b0, b1, mid)
        if aircraft_collide(am, bm):
            hi = mid
        else:
            lo = mid
    return _state_lerp(a0, a1, hi), _state_lerp(b0, b1, hi)
