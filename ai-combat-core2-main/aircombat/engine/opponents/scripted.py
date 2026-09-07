"""스크립트 적기(대항군) — 운동학 모델. 결정론.

JSBSim 없이 로컬 NED 평면에서 정해진 기동을 적분한다(정속선회/직진/연장/방어브레이크).
Pilot 과 동일하게 state()→KinState 를 제공하므로 match 가 대칭으로 다룬다.
자가대전(self-play)은 이 자리에 Pilot 을 꽂으면 되도록 인터페이스를 맞춘다.
"""
from __future__ import annotations

import math

import numpy as np

from ..state import KinState, G_FT_S2

KT_TO_FPS = 1.68781
FPS_TO_KCAS_15K = 0.80   # 15,000ft 근사 TAS→KCAS (시각화·에너지용 근사)


class ScriptedOpponent:
    """수평 기동 운동학 적기. maneuver ∈ {straight, turn, extend, break}."""

    def __init__(self, init_pos_ned=(6000.0, 3000.0, -15000.0),
                 speed_kts: float = 350.0, heading_deg: float = 0.0,
                 maneuver: str = "turn", turn_rate_dps: float = 6.0,
                 color: str = "Red", name: str = "F-16"):
        self._pos = np.array(init_pos_ned, float)
        self.v_fps = speed_kts * KT_TO_FPS
        self.psi = math.radians(heading_deg)
        self.maneuver = maneuver
        self.turn_rate = math.radians(turn_rate_dps)
        self.color = color
        self.name = name
        self.health = 100.0

    def step(self, dt: float) -> None:
        m = self.maneuver
        if m == "turn":
            self.psi += self.turn_rate * dt
        elif m == "break":
            self.psi += 3.0 * self.turn_rate * dt          # 급선회
        elif m == "extend":
            self.v_fps = min(self.v_fps + 20.0 * dt, 500.0 * KT_TO_FPS)  # 가속
        # straight: 변화 없음
        self.psi = (self.psi + math.pi) % (2 * math.pi) - math.pi
        vel = self._velocity()
        self._pos = self._pos + vel * dt

    def _velocity(self) -> np.ndarray:
        return np.array([self.v_fps * math.cos(self.psi),
                         self.v_fps * math.sin(self.psi), 0.0])

    def _bank(self) -> float:
        """정상선회 뱅크각(시각화용): tan φ = V·ω/g."""
        if abs(self.turn_rate) < 1e-9 or self.maneuver in ("straight", "extend"):
            return 0.0
        rate = self.turn_rate * (3.0 if self.maneuver == "break" else 1.0)
        return math.atan(self.v_fps * rate / G_FT_S2) * (1.0 if rate > 0 else -1.0)

    # ── Pilot 과 동일 인터페이스 ──
    def state(self) -> KinState:
        return KinState(
            pos_ned=self._pos.copy(), vel_ned=self._velocity(),
            phi=self._bank(), theta=0.0, psi=self.psi,
            v_fps=self.v_fps, kcas=self.v_fps * FPS_TO_KCAS_15K,
            alt_ft=-self._pos[2], health=self.health)

    # match 가 동일 루프로 호출 (JSBSim 파일럿과 시그니처 통일)
    def setup(self):
        return self

    def tactic_step(self, foe):
        pass

    def guidance_step(self, foe):
        pass

    def control_step(self, foe):
        pass

    def step_physics(self):
        self.step(1.0 / 120.0)

    def telemetry(self) -> None:
        """운동학 적기는 조종면이 없다 — 합성값을 억지로 넣지 않고 None.
        match._log_frame 이 None 이면 조종 속성을 ACMI 에 기록하지 않는다."""
        return None
