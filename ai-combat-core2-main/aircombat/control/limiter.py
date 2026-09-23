"""L3 결합 리미터 — 코너 플래토 + (AoA_max→G) ∩ 구조 9G.

INDI 앞단 안전 실행기 (tmp/f16_bfm_control_architecture.md 로드맵 §2, §4.3).
L2 가이드가 요청한 각속도 setpoint(특히 pitch q)를 기체 한계로 클램프한다.
당김은 조절(regulation)이며 상한은 코너 플래토라는 D6 불변식을 여기서 강제한다.

검사가능(auditable): limit_omega_sp 는 어떤 한계가 걸렸는지 플래그로 반환한다
(제1세부 "신뢰성 평가 기준"의 실행 로그).

한계 모델
---------
· 구조: **비대칭** — 양의 당김은 g_struct_max(F-16 +9G), 음의 밀기는 g_struct_min
  (−3G). 실기 한계는 대칭이 아니며, 음의 한계는 조종사 내성이 아니라 **기골 설계
  하중**이다(극한하중 −4.5G). 실기 FLCS 도 −3G 에서 명령을 자른다.
· 공력(AoA_max→G): 최대 양력계수에서 낼 수 있는 G 는 동압 ∝ V² 에 비례.
    G_aero(V) = g_struct_max · (KCAS / KCAS_corner_lo)²   (코너 하한에서 구조한계 도달)
  → 저속에선 AoA 한계가, 코너 플래토·고속에선 구조 한계가 지배.
· pitch-rate 환산 (중력 포함): 당김면 운동방정식은
    m·V·q = L − W·(중력의 양력방향 성분) 이고, 양력 방향(동체 −z)에 대한 중력 성분은
    cosφ·cosθ 다. 따라서  **q = (n − cosφ·cosθ)·g / V**.
    수평 정립(cosφcosθ=1): q=(n−1)g/V — 1G 는 중력이 이미 상쇄한다.
    배면 수평(=−1):        q=(n+1)g/V.
    나이프에지(=0):        q=n·g/V.
  이전 판은 중력항 없이 q=n·g/V 를 썼는데, 이는 나이프에지에서만 맞고 수평 비행에서는
  **양수쪽을 1G 관대하게(+9 의도→+10 허용), 음수쪽을 1G 엄격하게(−3 의도→−2 제한)**
  만들었다.
"""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np

G_FT_S2 = 32.174  # 중력가속도 [ft/s^2]

# 지속 G(Ps=0) 실측표 — scripts/measure_g_envelope.py sustained. 15kft 는 350–400KCAS
# 에서 4.8G 피크(실기 F-16 지속 ~5G 와 부합), 25kft 는 추력 감소로 3.9G 피크.
SUSTAINED_KCAS = (250.0, 300.0, 350.0, 400.0, 450.0)
SUSTAINED_G_15K = (3.59, 4.64, 4.79, 4.81, 3.68)
SUSTAINED_G_25K = (3.27, 3.88, 3.86, 3.27, 1.97)

# 교범 해석 봉투(envelope="manual") — MCH 11-F16 Vol.5 §4.6.5.2: 최대 AoA/G 선회반경은
# 170–330 KCAS 에서 일정(G ∝ V²), 330–440 은 선회율 플래토(G ∝ V), 최대 G 는 440 KCAS
# 에서 도달. 교범 고정값이라 교리(corner_kcas_*) 오버라이드와 무관하다 — 참가자가
# 코너를 낮춰 봉투를 넓히는 경로를 막는다. 교차검증: 350 KCAS → 7.16G (EEGS 9G
# 피퍼 가정 "350 KCAS 에서 7.3G"). 근거·결정: paper.md §6.
MANUAL_KCAS_TURN_RATE = 330.0   # 선회율 최고점
MANUAL_KCAS_MAX_G = 440.0       # 구조한계 G 도달


@dataclass
class LimiterConfig:
    g_struct_max: float = 9.0       # 양의 구조 한계 [g] (당김)
    # 음의 구조 한계 [g] (밀기). F-16 설계 한계 −3.0G / 극한하중 −4.5G.
    # 이전 판은 이 항이 없어 리미터가 ±9G 대칭으로 동작했고, 유도층은 감사 로그에
    # −16G 짜리 명령을 남겼다 — 실기에서는 기골이 부러지는 값이다.
    g_struct_min: float = -3.0
    kcas_corner_lo: float = 330.0   # 코너 플래토 하한 [KCAS] — 여기서 구조한계 G 도달
    kcas_corner_hi: float = 440.0   # 코너 플래토 상한 [KCAS] (참고; 상한은 구조로 이미 포화)
    p_max_dps: float = 220.0        # 롤율 상한 [deg/s]
    r_max_dps: float = 30.0         # 요율 상한 [deg/s]
    # 공력 G 봉투: "platform" = 코너 하한에서 구조한계 도달(기존), "manual" = 교범 해석.
    envelope: str = "platform"


class CombinedLimiter:
    """코너 플래토 + AoA→G ∩ 9G 를 각속도 setpoint 에 씌우는 안전 실행기."""

    def __init__(self, config: LimiterConfig | None = None):
        self.cfg = config or LimiterConfig()
        if self.cfg.envelope not in ("platform", "manual"):
            raise ValueError(f"envelope 는 platform|manual: {self.cfg.envelope!r}")

    def _g_aero(self, kcas: float) -> float:
        """동압이 낼 수 있는 G 크기 (부호 없음)."""
        c = self.cfg
        v = max(kcas, 0.0)
        if c.envelope == "manual":
            if v >= MANUAL_KCAS_MAX_G:
                return c.g_struct_max
            if v >= MANUAL_KCAS_TURN_RATE:
                return c.g_struct_max * v / MANUAL_KCAS_MAX_G
            g_knee = c.g_struct_max * MANUAL_KCAS_TURN_RATE / MANUAL_KCAS_MAX_G
            return g_knee * (v / MANUAL_KCAS_TURN_RATE) ** 2
        return c.g_struct_max * (v / c.kcas_corner_lo) ** 2

    def max_load_factor(self, kcas: float) -> float:
        """허용 최대 하중배수 = min(구조 9G, 공력 G(동압)). **순간** 봉투다."""
        return float(min(self.cfg.g_struct_max, self._g_aero(kcas)))

    def sustained_load_factor(self, kcas: float, alt_ft: float = 15000.0) -> float:
        """Ps=0 지속 하중배수 — "계속 유지할 수 있는" G (순간 봉투와 다르다).

        순간 봉투는 맞다(실측 피크 9.1G). 하지만 그걸 **상시** 지령하면 기체는
        스톱에 물린 채 에너지 언덕을 굴러내린다 — 실전 계측에서 elevator 명령이
        당김 구간의 97% 를 포화 상태로 보냈고 지령 8.0G / 달성 5.9G 였다.
        여기 표는 수평 지속 선회에서 dKCAS/dt=0 이 되는 지점의 **달성** G 실측치다
        (scripts/measure_g_envelope.py sustained, 2026-07-28).
        고도는 2점 선형보간, 표 밖은 np.interp 가 양끝값으로 고정.
        """
        g15 = np.interp(kcas, SUSTAINED_KCAS, SUSTAINED_G_15K)
        g25 = np.interp(kcas, SUSTAINED_KCAS, SUSTAINED_G_25K)
        return float(np.interp(alt_ft, (15000.0, 25000.0), (g15, g25)))

    def min_load_factor(self, kcas: float) -> float:
        """허용 최소(음의) 하중배수 = max(구조 -3G, -공력 G(동압))."""
        return float(max(self.cfg.g_struct_min, -self._g_aero(kcas)))

    def max_pitch_rate(self, v_fps: float, kcas: float,
                       g_lift: float = 0.0) -> float:
        """최대 G 에 대응하는 body pitch-rate 상한 [rad/s]  (q = (n−g_lift)·g/V).

        g_lift = cosφ·cosθ (중력의 양력방향 성분; +1 수평정립, −1 배면, 0 나이프에지).
        """
        v = max(float(v_fps), 1.0)
        return max(0.0, (self.max_load_factor(kcas) - g_lift) * G_FT_S2 / v)

    def min_pitch_rate(self, v_fps: float, kcas: float,
                       g_lift: float = 0.0) -> float:
        """음의 G 한계에 대응하는 pitch-rate 하한 [rad/s] (음수)."""
        v = max(float(v_fps), 1.0)
        return min(0.0, (self.min_load_factor(kcas) - g_lift) * G_FT_S2 / v)

    def limit_omega_sp(self, omega_sp, v_fps: float, kcas: float,
                       g_lift: float = 0.0):
        """omega_sp=[p,q,r] (rad/s) 를 기체 한계로 클램프.

        returns (clamped omega_sp, flags). flags 는 어떤 축이 포화됐는지 +
        현재 허용 최대 G(g_max) 를 담는다 (감사 로그용).
        """
        c = self.cfg
        omega_sp = np.asarray(omega_sp, float)
        q_max = self.max_pitch_rate(v_fps, kcas, g_lift)
        q_min = self.min_pitch_rate(v_fps, kcas, g_lift)   # 음수 — 밀기 한계(비대칭)
        p_max = np.deg2rad(c.p_max_dps)
        r_max = np.deg2rad(c.r_max_dps)
        lo = np.array([-p_max, q_min, -r_max])
        hi = np.array([p_max, q_max, r_max])
        clamped = np.clip(omega_sp, lo, hi)
        flags = {
            "p_limited": bool(abs(omega_sp[0]) > p_max + 1e-9),
            "q_limited": bool(omega_sp[1] > q_max + 1e-9
                              or omega_sp[1] < q_min - 1e-9),
            "r_limited": bool(abs(omega_sp[2]) > r_max + 1e-9),
            "g_max": self.max_load_factor(kcas),
            "g_min": self.min_load_factor(kcas),
            "q_max": float(q_max),
            "q_min": float(q_min),
        }
        return clamped, flags
