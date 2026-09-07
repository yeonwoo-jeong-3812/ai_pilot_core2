"""
CombatGeometry - 공중전 기하학 계산

ATA, AA, HCA, RollOff 등의 교전 파라미터 계산

단위 시스템:
- 거리: NM (해리) 및 Feet (1 NM = 6,076 ft)
- 속도: Knot (노트)
- 고도: Feet
"""

import math
import numpy as np


def reduce_reflex_angle_deg(angle: float) -> float:
    """각도를 [-180, 180] 범위로 정규화
    
    Args:
        angle: 각도 (degrees)
        
    Returns:
        float: 정규화된 각도 [-180, 180] degrees
    """
    try:
        if not math.isfinite(angle):
            return 0.0
        new_angle = angle % 360
        if new_angle > 180:
            new_angle -= 360
        return new_angle
    except (TypeError, ValueError):
        return 0.0


class CombatGeometry:
    """공중전 기하학 계산 클래스

    3D 벡터 기반 positional geometry 계산
    ai-pilot-project의 CombatGeometry를 기반으로 개선

    각도 정의는 BEM(Korean AF BEM Vol.5, 2005) §4.3.3/§4.8.2 정합 — ATA/AA/HCA 는
    **종축(boresight/longitudinal axis)** 기준 (2026-07-17, 구 속도벡터 기준에서 전환).
    양 기체 자세(theta/psi, theta_t/psi_t)를 넘겨야 정확하다 — 기본값 0(북향·수평)은
    합성 테스트용. 산출값(ata/aa/hca/rolloff/closure)은 모두 프레임 무관이라 core2
    NED 에서 정상. (고도차·에너지·선회방향 flow 등 위치 기반 판단은 이 클래스가 아니라
    pilot._context(NED) 와 conditions.one_circle/two_circle 이 담당한다.)

    Nomenclature:
        - rho_a: Line-of-sight vector (적까지의 벡터)
        - v_a, v_t: Velocity vectors (아군, 적 속도 벡터 — closure 등에 사용)
        - roll/theta/psi: 아군 자세, theta_t/psi_t: 적 자세
        - lambda_a (ATA): Antenna Train Angle (아군 종축 기준)
        - epsilon (AA): Aspect Angle (적 종축 기준)
        - eta (HCA): Heading Crossing Angle (양 종축 사이 각)
        - rolloff: RollOff angle (표적 롤오프 각 — V1 명칭 TAU에서 개명, τ=시간 오독 방지)
    """
    
    def __init__(
        self,
        p_a: np.ndarray,
        p_t: np.ndarray,
        v_a: np.ndarray,
        v_t: np.ndarray,
        roll: float = 0.0,
        theta: float = 0.0,
        psi: float = 0.0,
        theta_t: float = 0.0,
        psi_t: float = 0.0,
    ):
        """
        Args:
            p_a: 아군 위치 [north, east, down] (m) - NED frame
            p_t: 적 위치 [north, east, down] (m) - NED frame
            v_a: 아군 속도 [v_north, v_east, v_down] (m/s)
            v_t: 적 속도 [v_north, v_east, v_down] (m/s)
            roll: 아군 롤 각도 φ (rad)
            theta: 아군 피치 각도 θ (rad) — ATA/HCA/RollOff 종축 산출
            psi: 아군 요 각도 ψ (rad) — (기본 0 = 북향·수평)
            theta_t: 적 피치 각도 (rad) — AA/HCA 의 적 종축 산출
            psi_t: 적 요 각도 (rad) — (기본 0 = 북향·수평)
        """
        self.p_a = np.array(p_a)
        self.p_t = np.array(p_t)
        self.v_a = np.array(v_a)
        self.v_t = np.array(v_t)
        self.roll = roll
        self.theta = theta
        self.psi = psi
        self.theta_t = theta_t
        self.psi_t = psi_t

        # Line-of-sight vector (적까지의 벡터)
        self.rho_a = self._subtraction(p_t, p_a)
        self.lambda_a = None  # ATA (계산 후 저장)

    @staticmethod
    def _body_x(theta: float, psi: float) -> np.ndarray:
        """종축(기수) 단위벡터 — NED. 롤은 종축에 영향 없음."""
        ct = math.cos(theta)
        return np.array([ct * math.cos(psi), ct * math.sin(psi), -math.sin(theta)])
        
    def distance(self) -> float:
        """거리 (m) - Line-of-sight 벡터의 크기"""
        return self._magnitude(self.rho_a)
    
    def ata_deg(self) -> float:
        """ATA (Antenna Train Angle) - 아군 **종축(boresight)**과 LOS 사이 각도 (deg)

        BEM §4.8.2.4: "the angle between the nose of the fighter and the radar
        LOS to the target … degrees the target is off the boresight."
        (2026-07-17 속도벡터 기준에서 교범 정합으로 전환 — 고AoA 에서 기수≠비행경로)

        Returns:
            0° = 정면조준, 180° = 후방
        """
        mag_rho = self._magnitude(self.rho_a)
        if mag_rho < 1e-6:
            self.lambda_a = 0.0
            return 0.0
        nose = self._body_x(self.theta, self.psi)
        cos_val = max(-1.0, min(1.0,
            self._dot_product(nose, self.rho_a) / mag_rho
        ))
        self.lambda_a = math.acos(cos_val) * 180 / math.pi
        return self.lambda_a

    def aa_deg(self) -> float:
        """AA (Aspect Angle) - 적(목표물)의 꼬리에서 아군(공격자)까지 측정한 각도 (deg)

        BEM §4.8.2.3: "the angle between the longitudinal axis of the target
        (projected rearward) and the LOS to the fighter, measured from the tail
        of the target. The fighter's heading is not a consideration."
        (2026-07-17 적 속도벡터 기준에서 적 **종축** 기준으로 교범 정합 전환)

            0°   = 아군이 적의 6시(정후방) - 공격 유리 위치
            90°  = 아군이 적의 빔(3/9시 방향)
            180° = 아군이 적의 12시(헤드온) - 적이 아군 정면 조준 중, 위협
        """
        # acos(dot(-x_t, -rho_a)) = acos(dot(x_t, rho_a))
        # 의미: 적 종축이 아군→적 LOS 와 같은 방향이면 적 꼬리가 아군을 향함(=아군이 적 6시)
        mag_rho = self._magnitude(self.rho_a)
        if mag_rho < 1e-6:
            return 0.0
        tail_axis = self._body_x(self.theta_t, self.psi_t)
        cos_val = max(-1.0, min(1.0,
            self._dot_product(tail_axis, self.rho_a) / mag_rho
        ))
        return math.acos(cos_val) * 180 / math.pi

    def hca_deg(self) -> float:
        """HCA (Heading Crossing Angle / Angle-Off) - 양 기체 **종축** 사이 각도 (deg)

        BEM §4.3.3.3: "the angular distance between the longitudinal axes of
        the attacker and the defender."
        (2026-07-17 속도벡터 기준에서 교범 정합 전환 — 3D 종축 각)

        Returns:
            0° = 같은 방향, 180° = 정면 대치
        """
        cos_val = max(-1.0, min(1.0, self._dot_product(
            self._body_x(self.theta, self.psi),
            self._body_x(self.theta_t, self.psi_t),
        )))
        return math.acos(cos_val) * 180 / math.pi
    
    def rolloff_deg(self) -> float:
        """RollOff — 표적 롤오프 각 (deg): 표적을 당김면(리프트벡터 면)에 올리려면 얼마나
        롤해야 하는가. +우롤 / −좌롤.

        자세(roll φ·pitch θ·yaw ψ) 기반 body-frame LOS 로 산출한다 — L2 유도의
        `dphi = atan2(aim_body_y, −aim_body_z)` 와 **같은 정의의 '순수 LOS 판'**
        (조준 오프셋·lead/lag 없음). raw RollOff vs 명령 Dphi 를 대비하면 조준 전략의
        효과가 드러난다(디브리프). 표적이 정면·바로 위면 0, 우측 90°, 바로 아래 ±180°.

        (구 정의는 East/Down 2D 투영 + roll 보정으로 기수 북향을 전제해 임의 헤딩에서
        왜곡됐다 — 자세 기반으로 교정. V1 명칭 `TAU`는 τ=시간(TCAS 등) 오독 소지로
        2026-07-15 RollOff 로 개명. V1 은 TAU 유지. 부호(+우)는 동일.)
        """
        mag = self._magnitude(self.rho_a)
        if mag < 1e-9:
            return 0.0
        los = self.rho_a / mag
        # NED → body (항공 3-2-1 C_bn) — guidance._ned_to_body 와 동일 변환. y, z 성분만.
        cp, sp = math.cos(self.roll), math.sin(self.roll)
        ct, st = math.cos(self.theta), math.sin(self.theta)
        cy, sy = math.cos(self.psi), math.sin(self.psi)
        y = (sp * st * cy - cp * sy) * los[0] + (sp * st * sy + cp * cy) * los[1] + (sp * ct) * los[2]
        z = (cp * st * cy + sp * sy) * los[0] + (cp * st * sy - sp * cy) * los[1] + (cp * ct) * los[2]
        # 보어사이트(표적 정면): 롤오프 특이 — 어느 롤이든 표적이 기수에 머무름 → 0.
        if abs(y) < 1e-9 and abs(z) < 1e-9:
            return 0.0
        return reduce_reflex_angle_deg(math.degrees(math.atan2(y, -z)))
    
    def closure_rate(self) -> float:
        """Closure Rate - 접근 속도 (m/s)
        
        양수 = 접근 중, 음수 = 멀어짐
        """
        rel_vel = self._subtraction(self.v_t, self.v_a)
        
        if self._magnitude(self.rho_a) < 1e-6:
            return 0.0
        
        rho_norm = self.rho_a / self._magnitude(self.rho_a)
        closure = -self._dot_product(rel_vel, rho_norm)

        return closure

    # 벡터 연산 헬퍼 메서드
    def _magnitude(self, v):
        """벡터의 크기 계산"""
        return math.sqrt(np.dot(v, v))

    def _dot_product(self, v_a, v_b):
        """두 벡터의 내적 계산"""
        return np.dot(v_a, v_b)

    def _subtraction(self, v_a, v_b):
        """두 벡터의 차 계산"""
        return np.subtract(v_a, v_b)
