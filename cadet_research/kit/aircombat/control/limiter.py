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
· AoA→G 스케줄: **실측 α 로 허용 G 를 직접 깎는다** (실기 F-16 FLCS 의 AOA/G 리미터,
  T.O. 1F-16C-1 Fig 1-58 CAT I 을 3점 선형보간으로 단순화). α≤15°=9G, 25°=1G.
  2026-09-06 신설: 그전까지 α 보호는 f16.xml 내장 FLCS(elevator-scheduler 의 α 게인 +
  alpha-limiter-norm)가 하고 있었는데, 그 내장 FLCS 는 우리 INDI 와 **직렬로 겹친 두
  번째 레이트 루프**라 풀스틱에서도 달성 G 가 4.5–7.2G 에 묶였다(실측). 내장 FLCS 를
  `fcs/fbw-override=1` 로 우회하면서(plant.trim) α 보호를 여기로 가져왔다.
  **`max_load_factor` 안에 넣는 것이 요점이다.** L3 클램프만 걸면 거동은 같지만
  가이던스가 보는 g_avail(=ACMI 의 Gavail)이 여전히 속도만의 함수라, "Gavail 은 9 인데
  실제로는 못 낸다"는 계측 불일치가 축소된 형태로 남는다(2026-09-06 실측: 두 배치의
  달성 G·α·선회율이 6 속도에서 소수점까지 동일). 참가자가 읽는 숫자를 진실하게 만드는
  쪽을 택했다.
  하한(min_load_factor)에는 걸지 않는다 — 고α 에서 기수를 내리는 것은 언제나 허용해야
  한다. 별도의 하드 게이트(22°→25° 로 pitch-up 권한을 0 으로)는 실측에서 발동률
  0–1.8% 에 결과가 동일해 기각했다 — 이 스케줄이 이미 α 를 잡는다.
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

from ..aircraft import DEFAULT_AIRCRAFT_MODEL, resolve_aircraft_model

G_FT_S2 = 32.174  # 중력가속도 [ft/s^2]

# 지속 G(Ps=0) 실측표 — scripts/measure_g_envelope.py sustained. 기체 모델별로 다르다
# (F16Plant 의 AIRCOMBAT_F16_MODEL 과 같은 키). docs/5_피델리티_EM.md §5.3.
# 2026-09-11 재측정 (같은 날 두 번): ①기어 내림 결함(plant.set_ic, CD +0.027) 수정,
# ②내장 FLCS 요 채널 결함(댐퍼 washout 없음 + PID 출력이 러더 위치를 덮어씀) 수정과 플래퍼론
# 혼합기 교정, 러더를 내장 채널에 맡김. 그 전 표(2026-09-06, 15kft 피크 5.04G)는 무효.
# f16은 upstream PW-220 표를 사용한다. 기존 PW-229 표는 f16_229로 보존한다.
# f16_229(-229, GW 20,630) 400KCAS 7.00G 피크, f16_220(연구용 -220, GW 22,000) 450KCAS 6.18G.
# 교범 Table 4.9 의 Ps=0 은 250/300/350/400/450 에서 약 3.3/4.3/5.2/6.0/6.7G — f16_220 이 그 안에 있다.
#   구 표 15kft: (3.90, 4.60, 4.93, 5.04, 4.46) / 25kft: (3.55, 4.04, 4.09, 3.65, 2.47)
SUSTAINED_KCAS = (250.0, 300.0, 350.0, 400.0, 450.0)
SUSTAINED_G = {
    "f16":     {15000.0: (3.96, 4.65, 5.25, 5.84, 5.72), 25000.0: (3.62, 4.10, 4.55, 4.31, 4.20)},
    "f16_229": {15000.0: (4.57, 5.47, 6.29, 7.00, 7.00), 25000.0: (4.18, 4.93, 5.37, 5.13, 5.24)},
    "f16_220": {15000.0: (3.21, 4.09, 5.01, 5.95, 6.18), 25000.0: (3.10, 4.00, 4.66, 4.66, 4.77)},
}
# Compatibility exports only; live guidance reads its instance's model below.
SUSTAINED_G_15K = SUSTAINED_G[DEFAULT_AIRCRAFT_MODEL][15000.0]
SUSTAINED_G_25K = SUSTAINED_G[DEFAULT_AIRCRAFT_MODEL][25000.0]

# AoA→허용 G 스케줄 (실기 F-16 CAT I). 15° 까지는 개입 없음, 25° 에서 사실상 차단.
# 이 모델의 실측 CL_max 지점(α 20–24°, CL 1.4–1.7)과도 정합 — 그 위는 CL 이 더 안 늘고
# 항력만 늘어 에너지만 잃는다. np.interp 는 표 밖을 양끝값으로 고정하므로 α>25° 도 1G.
AOA_G_SCHED_DEG = (0.0, 15.0, 25.0)
AOA_G_SCHED_G = (9.0, 9.0, 1.0)


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


class CombinedLimiter:
    """코너 플래토 + AoA→G ∩ 9G 를 각속도 setpoint 에 씌우는 안전 실행기."""

    def __init__(self, config: LimiterConfig | None = None, *, model: str | None = None):
        self.cfg = config or LimiterConfig()
        self.bind_aircraft(model)

    def bind_aircraft(self, model: str | None) -> None:
        """Bind the sustained-performance table to the actual plant model."""
        self.model = resolve_aircraft_model(model)
        self._sustained_g = SUSTAINED_G[self.model]

    def _g_aero(self, kcas: float) -> float:
        """동압이 낼 수 있는 G 크기 (부호 없음)."""
        c = self.cfg
        return c.g_struct_max * (max(kcas, 0.0) / c.kcas_corner_lo) ** 2

    def max_load_factor(self, kcas: float, alpha_rad: float = 0.0) -> float:
        """허용 최대 하중배수 = min(구조 9G, 공력 G(동압), AoA→G). **순간** 봉투다.

        alpha_rad 를 주면 AOA/G 리미터가 함께 걸린다(미지정=0rad → 9G 라 무간섭).
        속도항(_g_aero)은 **예측**("이 속도면 얼마까지 가능"), α 항은 **실측**("지금
        이 자세에서 얼마까지 허용") — 둘은 같은 CL_max 경계의 다른 표현이라 중복이
        아니라 상보다. 가이던스는 예측이 필요하고 리미터는 실측이 필요하다.
        """
        return float(min(self.cfg.g_struct_max, self._g_aero(kcas),
                         self.alpha_g_cap(alpha_rad)))

    def sustained_load_factor(self, kcas: float, alt_ft: float = 15000.0) -> float:
        """Ps=0 지속 하중배수 — "계속 유지할 수 있는" G (순간 봉투와 다르다).

        순간 봉투는 맞다(실측 피크 9.1G). 하지만 그걸 **상시** 지령하면 기체는
        스톱에 물린 채 에너지 언덕을 굴러내린다 — 실전 계측에서 elevator 명령이
        당김 구간의 97% 를 포화 상태로 보냈고 지령 8.0G / 달성 5.9G 였다.
        여기 표는 수평 지속 선회에서 dKCAS/dt=0 이 되는 지점의 **달성** G 실측치다
        (scripts/measure_g_envelope.py sustained, 2026-09-06 재측정).
        고도는 2점 선형보간, 표 밖은 np.interp 가 양끝값으로 고정.
        """
        g15 = np.interp(kcas, SUSTAINED_KCAS, self._sustained_g[15000.0])
        g25 = np.interp(kcas, SUSTAINED_KCAS, self._sustained_g[25000.0])
        return float(np.interp(alt_ft, (15000.0, 25000.0), (g15, g25)))

    def alpha_g_cap(self, alpha_rad: float) -> float:
        """현재 받음각에서 FLCS 가 허용하는 최대 G (AOA/G 리미터).

        α가 25° 이상이면 요구 G 상한을 1로 낮춘다. 명령 제한이므로 실제 G나
        받음각의 순간 초과를 보장하지 않는다. 저속·복합 기동은 동역학 시험이 필요하다.
        """
        return float(np.interp(np.degrees(alpha_rad), AOA_G_SCHED_DEG, AOA_G_SCHED_G))

    def min_load_factor(self, kcas: float) -> float:
        """허용 최소(음의) 하중배수 = max(구조 -3G, -공력 G(동압))."""
        return float(max(self.cfg.g_struct_min, -self._g_aero(kcas)))

    def max_pitch_rate(self, v_fps: float, kcas: float,
                       g_lift: float = 0.0, alpha_rad: float = 0.0) -> float:
        """최대 G 에 대응하는 body pitch-rate 상한 [rad/s]  (q = (n−g_lift)·g/V).

        g_lift = cosφ·cosθ (중력의 양력방향 성분; +1 수평정립, −1 배면, 0 나이프에지).
        """
        v = max(float(v_fps), 1.0)
        return max(0.0, (self.max_load_factor(kcas, alpha_rad) - g_lift) * G_FT_S2 / v)

    def min_pitch_rate(self, v_fps: float, kcas: float,
                       g_lift: float = 0.0) -> float:
        """음의 G 한계에 대응하는 pitch-rate 하한 [rad/s] (음수)."""
        v = max(float(v_fps), 1.0)
        return min(0.0, (self.min_load_factor(kcas) - g_lift) * G_FT_S2 / v)

    def limit_omega_sp(self, omega_sp, v_fps: float, kcas: float,
                       g_lift: float = 0.0, alpha_rad: float | None = None):
        """omega_sp=[p,q,r] (rad/s) 를 기체 한계로 클램프.

        alpha_rad 를 주면 AOA/G 리미터가 함께 걸린다(미지정이면 무간섭 — 기존
        호출자·테스트 호환).

        returns (clamped omega_sp, flags). flags 는 어떤 축이 포화됐는지 +
        현재 허용 최대 G(g_max) 를 담는다 (감사 로그용). g_max 는 α 항까지 반영한
        **실제** 허용치다 — 속도만의 값을 보고하면 감사 로그가 거짓말을 한다.
        """
        c = self.cfg
        omega_sp = np.asarray(omega_sp, float)
        a = 0.0 if alpha_rad is None else float(alpha_rad)
        q_max = self.max_pitch_rate(v_fps, kcas, g_lift, a)
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
            "g_max": self.max_load_factor(kcas, a),
            "g_min": self.min_load_factor(kcas),
            "q_max": float(q_max),
            "q_min": float(q_min),
            # α 항이 구속항인가 (속도·구조보다 먼저 물렸는가) — 감사 로그
            "alpha_limited": bool(self.alpha_g_cap(a)
                                  < min(self.cfg.g_struct_max, self._g_aero(kcas))),
        }
        return clamped, flags
