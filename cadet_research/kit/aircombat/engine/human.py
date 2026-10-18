"""사람 조종: 스틱의 당김·기울임을 피치·롤 2축 INDI에 전달한다.

당김은 현재 속도·받음각의 허용 범위에 비례한다. 자동 조종과 같은 제한기에
실측 받음각을 전달하고, 롤 명령 상한도 같은 180 deg/s를 사용한다.
중립은 피치 회전 속도 0을 요구한다. 고도 유지 자동조종이나 실기 CAS 전체가 아니다.

페달은 내장 요 FLCS에 직접 전달한다. 자동 조종의 페달 중립과 다른 입력 권한이며,
사용하지 않는 INDI 요 명령의 30 deg/s 값이 실제 러더 운동을 제한하지는 않는다.
실시간 세션은 입력 만료 시 회전 명령과 방아쇠를 해제하고 스로틀 설정을 유지한다.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

import numpy as np

from .pilot import Pilot

# Pilot 의 QuaternionAttitudeShim(rate_limit_dps=...) 과 **같은 값이어야 한다**.
RATE_LIMIT_DPS = (180.0, 60.0, 30.0)


@dataclass(frozen=True)
class StickInput:
    """정규화 조종 입력. roll +우 / pitch +당김 / rudder +우 / throttle 0..1.

    fire 는 방아쇠 유지 상태다. 에이전트는 사격 해법이 서면 자동으로 쏘지만
    사람은 직접 당겨야 한다 — 유·무인 대결의 본질적 비대칭이라 그대로 둔다.
    """
    roll: float = 0.0
    pitch: float = 0.0
    throttle: float = 0.85
    rudder: float = 0.0
    fire: bool = False


def _clamp(x: float, lo: float, hi: float) -> float:
    x = float(x)
    if not math.isfinite(x):
        raise ValueError("Control inputs must be finite numbers")
    return lo if x < lo else (hi if x > hi else x)


class HumanPilot(Pilot):
    """Pilot 과 동일 인터페이스 — Match 는 이 클래스를 구별하지 않는다."""

    def __init__(self, plant, color: str = "Blue",
                 init_pos_ned=(0.0, 0.0, -15000.0), dt_phys: float = 1.0 / 120.0,
                 name: str = "F-16"):
        super().__init__(plant, color=color, init_pos_ned=init_pos_ned,
                         dt_phys=dt_phys, name=name)
        # ACMI Tactic 표기: match._log_frame 은 _cmd 가 None 이면 .maneuver 로 떨어진다.
        self._cmd = None
        self._gc = None
        self.maneuver = "HUMAN"
        self._input = StickInput()
        self._lock = threading.Lock()   # 입력은 네트워크 스레드가, 소비는 매치 스레드가
        self._last_input_time = time.monotonic()
        self.input_timeout_s: float | None = None  # live sessions enable a wall-clock watchdog
        self.input_stale = False

    # ── 조종 입력 (외부 스레드에서 호출) ──
    def set_input(self, roll: float, pitch: float, throttle: float,
                  rudder: float = 0.0, fire: bool = False) -> None:
        with self._lock:
            self._input = StickInput(_clamp(roll, -1.0, 1.0),
                                     _clamp(pitch, -1.0, 1.0),
                                     _clamp(throttle, 0.0, 1.0),
                                     _clamp(rudder, -1.0, 1.0),
                                     bool(fire))
            self._last_input_time = time.monotonic()
            self.input_stale = False

    def neutralize_input(self) -> None:
        """Release rotation commands and trigger, retaining the throttle setting."""
        with self._lock:
            self._input = StickInput(throttle=self._input.throttle)
            self.input_stale = True

    # ── 방아쇠 ──
    def trigger(self, has_solution: bool) -> bool:
        """사람은 해법이 서도 **직접 당겨야** 쏜다(Pilot 은 자동)."""
        return self.stick.fire

    @property
    def stick(self) -> StickInput:
        with self._lock:
            if (self.input_timeout_s is not None
                    and time.monotonic() - self._last_input_time > self.input_timeout_s):
                self._input = StickInput(throttle=self._input.throttle)
                self.input_stale = True
            return self._input

    # ── L1/L2 없음 — 그 판단이 사람이다 ──
    def tactic_step(self, foe) -> None:
        return None

    def guidance_step(self, foe) -> None:
        return None

    # ── L3 (120Hz): 스틱 → omega_sp → 리미터 → INDI ──
    def control_step(self, foe) -> None:
        p = self.plant
        phi = p["attitude/phi-rad"]; theta = p["attitude/theta-rad"]
        pqr = np.array([p["velocities/p-rad_sec"], p["velocities/q-rad_sec"],
                        p["velocities/r-rad_sec"]])
        v_ned = np.array([p["velocities/v-north-fps"], p["velocities/v-east-fps"],
                          p["velocities/v-down-fps"]])
        self._pos = self._pos + v_ned * self.dt_phys      # 위치 적분 (Pilot 과 동일)

        stick = self.stick
        v_fps = p["velocities/vt-fps"]; kcas = p["velocities/vc-kts"]
        alpha = p["aero/alpha-rad"]
        g_lift = float(np.cos(phi) * np.cos(theta))
        # 봉투 정규화: +스틱은 최대 당김 G, −스틱은 최소(음의) G 쪽으로 비례.
        q_max = self.limiter.max_pitch_rate(v_fps, kcas, g_lift, alpha_rad=alpha)
        q_min = self.limiter.min_pitch_rate(v_fps, kcas, g_lift)   # 음수
        q_sp = stick.pitch * (q_max if stick.pitch >= 0.0 else -q_min)

        # INDI는 피치·롤만 소유한다. 페달은 아래에서 내장 요 채널에 전달한다.
        omega_sp = np.array([np.deg2rad(RATE_LIMIT_DPS[0]) * stick.roll,
                             q_sp, 0.0])
        lim = np.deg2rad(np.asarray(RATE_LIMIT_DPS, float))
        omega_sp = np.clip(omega_sp, -lim, lim)           # shim 과 동일한 레이트 클립
        omega_sp, self.last_flags = self.limiter.limit_omega_sp(
            omega_sp, v_fps, kcas, g_lift=g_lift, alpha_rad=alpha)

        u = self.indi.update(pqr, omega_sp, p["aero/qbar-psf"], ang_accel=[
            p["accelerations/pdot-rad_sec2"], p["accelerations/qdot-rad_sec2"],
            p["accelerations/rdot-rad_sec2"]])
        # 러더: 페달값을 그대로 내장 FLCS 요 채널(washout 댐퍼 + 측방가속도 되먹임)에 준다.
        # 중립이면 0 — 협조는 FLCS 몫이다(pilot.py 와 동일, 2026-09-11 docs/5_피델리티_EM.md §3.4).
        # INDI 는 pitch/roll 2축만 풀고, rudder 는 내장 FLCS 가 단독 소유한다.
        p.set_input([stick.throttle, u[1], u[0], stick.rudder])   # [thr, elev, ail, rud]
