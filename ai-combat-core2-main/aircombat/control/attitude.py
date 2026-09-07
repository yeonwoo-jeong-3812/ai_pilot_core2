"""쿼터니언 자세→각속도 shim (D3) — Euler `AttitudeToRate` 대체.

근거(tmp/f16_bfm_control_architecture.md D3): Euler φ/θ 는 θ≈±90°(루프·수직기동
= BFM 이 실제로 벌어지는 곳)에서 특이(gimbal lock). 쿼터니언 오차 → 각속도 명령으로
특이점을 제거한다.

제어 법칙(표준 쿼터니언 피드백):
    q_err     = conj(q_cur) ⊗ q_des       # body 프레임 상대회전
    [p_sp,q_sp] = 2·K·vec(q_err)[roll,pitch]  # (shortest-path: q_err.w<0 이면 부호 반전)
    r_sp      = -k_yaw_damp · r            # yaw 는 자세 추종이 아님(고정익)
q 는 항법(NED)→기체(body) 회전을 나타내는 [w,x,y,z] 규약(항공 3-2-1: yaw-pitch-roll).
yaw(r)를 쿼터니언으로 추종하지 않는 이유: BFM 에서 heading 은 L2 의 리프트벡터·뱅크
배치로 간접 제어되는 결과다. yaw 축은 협조선회/sideslip(여기선 r→0 감쇠)에 맡긴다.
출력 ω_sp 는 body rate [p,q,r] 로 L3 INDI(INDIRateController)로 직접 들어간다.
"""
from __future__ import annotations

import numpy as np


# ----------------------------------------------------------------------------
# 쿼터니언 유틸 ([w, x, y, z], 항법→기체, 3-2-1 aerospace sequence)
# ----------------------------------------------------------------------------
def euler_to_quat(phi: float, theta: float, psi: float) -> np.ndarray:
    cr, sr = np.cos(phi / 2), np.sin(phi / 2)
    cp, sp = np.cos(theta / 2), np.sin(theta / 2)
    cy, sy = np.cos(psi / 2), np.sin(psi / 2)
    q = np.array([
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    ])
    return q / np.linalg.norm(q)


def quat_conj(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, float)
    return np.array([q[0], -q[1], -q[2], -q[3]])


def quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    ])


def quat_to_euler(q: np.ndarray) -> tuple[float, float, float]:
    w, x, y, z = np.asarray(q, float)
    phi = np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    t = np.clip(2 * (w * y - z * x), -1.0, 1.0)
    theta = np.arcsin(t)
    psi = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return float(phi), float(theta), float(psi)


# ----------------------------------------------------------------------------
# 자세 shim: 목표 자세 → body-rate setpoint (특이점 없음)
# ----------------------------------------------------------------------------
class QuaternionAttitudeShim:
    """목표 쿼터니언 → ω_sp. L2 가 준 리프트벡터/뱅크 자세를 L3 rate 지령으로 변환."""

    def __init__(self, k_att: float = 4.5, k_yaw_damp: float = 1.5,
                 rate_limit_dps=(120.0, 60.0, 30.0)):
        self.k_att = float(k_att)
        self.k_yaw_damp = float(k_yaw_damp)
        self.rate_limit = np.deg2rad(np.asarray(rate_limit_dps, float))

    def rate_setpoint(self, q_cur: np.ndarray, q_des: np.ndarray,
                      r_cur: float = 0.0) -> np.ndarray:
        """q_cur, q_des ([w,x,y,z]) → ω_sp=[p,q,r] (rad/s)."""
        q_err = quat_mul(quat_conj(q_cur), q_des)
        if q_err[0] < 0.0:            # shortest path (q 와 -q 는 같은 자세)
            q_err = -q_err
        omega_sp = 2.0 * self.k_att * q_err[1:4]
        omega_sp[2] = -self.k_yaw_damp * float(r_cur)   # yaw: 추종 아닌 감쇠(q_err_z 무시)
        return np.clip(omega_sp, -self.rate_limit, self.rate_limit)

    def rate_setpoint_euler(self, phi, theta, psi,
                            phi_des, theta_des, psi_des, r_cur: float = 0.0) -> np.ndarray:
        """현재/목표를 Euler 로 받는 편의 래퍼 (내부는 쿼터니언)."""
        return self.rate_setpoint(euler_to_quat(phi, theta, psi),
                                  euler_to_quat(phi_des, theta_des, psi_des), r_cur)
