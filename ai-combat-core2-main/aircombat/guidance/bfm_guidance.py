"""L2 BFM 가이드 — 교리 기반 조절(regulation).

docs/ARCHITECTURE.md §4.3 (교정된 당김 법칙):
  1. 제어 대상 = 기하 오차(aspect·ATA·range), 목표 = 교리 setpoint.
     "표적에 정렬"이 아니라 "변수를 WEZ 로 몰아감".
  2. G_target = f(기하오차, 에너지), 상한 = 코너 플래토 + 결합 리미터.
     명목 "리미터 살짝 아래", 저aspect/거리손실 시 백오프,
     머지 진입 시 초기 당김(initial_pull_g, 4.4.5.2).
  3. 에너지 하드 제약: 파이팅 속도 유지, 파워 스케줄
     (원거리 진입 가속 entry_kcas + 에너지 마진 유지 energy_margin, 4.4.6.2.2).
  4. 상황별 버스트 (L1 이 g_burst 로 지속↔순간 봉투 천장을 지정).
  5. 수직 기동 = 조준점 수직 오프셋(aim_above_ft): 오프셋된 3D 조준점이
     dphi(리프트벡터 배치)로 실행되므로 L3/L4 무변경 (4.4.6.2.3 요요).
     L1 미지정 시 머지 진입 기하에서 교리 자동(+lv_above_ft, 4.4.5.2).

출력(GuidanceCommand):
  · dphi_cmd : 리프트벡터 배치 롤 증분 [rad] (현재 body 프레임, 특이점 없음)
  · q_cmd    : 당김 pitch rate [rad/s]  (= G_target·g/V)
  · thrust_cmd, G_target, audit(감사 로그)

파이프라인(pilot/scheduler 가 조립):
  q_des = q_cur ⊗ quat(roll=dphi_cmd)  → shim → ω_sp;  ω_sp[pitch]=q_cmd
  → limiter → INDI.  yaw 는 shim 이 감쇠.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..geometry.combat_geometry import CombatGeometry
from ..control.limiter import CombinedLimiter, LimiterConfig, G_FT_S2
from .doctrine import Doctrine

FT_S_TO_KT = 0.592484

# 스로틀 명령 캘리브레이션 — f16.xml FCS 가 pos = 2×cmd 로 확장(augmethod=2:
# pos 0–1 드라이, 1–2 AB). 실측(15kft/350kt): cmd 0.5=MIL 11.2klbs(연료 2.1pps),
# 0.6 부터 AB 점화(7.6pps), 1.0=full AB 21.6klbs, 0.0=idle(순추력 음수).
THR_IDLE = 0.0
THR_DECEL = 0.2   # MIL 미만 감속용 (구 0.6 은 실제로는 min-AB 였음)
THR_MIL = 0.5
THR_AB = 1.0

# L1 이 mode 로 트리거하는 국면 전술 모드 파라미터 (기본 mode=None 은 무영향).
# stable: 포인팅 추적 — 표적을 body forward 축에 정렬(수평 우선 롤 + 부호있는 pitch).
STABLE_BANK_MAX = np.radians(45.0)   # 목표 뱅크 상한 — 수평 우선(정면 표적이면 0=수평 복귀)
STABLE_K_BANK = 1.0                  # 방위→목표 뱅크 이득(정면 근처 완만, 벗어나면 상한까지)
STABLE_K_Q = 3.0                     # 상하각→pitch rate 이득 [1/s] — ATA 수렴(매끄러움 유지)
STABLE_Q_MAX = np.radians(35.0)      # stable pitch rate 상한 [rad/s] (리미터가 추가로 캡)
CZ_RANGE_FT = 2500.0                  # control_zone: 목표 슬랜트 거리 기본값 — BEM CZ(2,000~3,000ft) 중앙 (L1 cz_range_ft 로 오버라이드)
CZ_MAX_CLOSURE = 120.0               # control_zone: 목표 접근율 상한 [fps]
CZ_LAG_TRIP_RATIO = 1.2              # control_zone: 목표거리×비율 안쪽+접근이면 lag 편향(오버슈트 방지)

# L1 액션 파라미터 미지정 시의 기본값 (2026-08-24 개방). 의도적으로 "무난하지만
# 최적은 아닌" 값이다 — 생략하면 평범, 명시하면 강함. max_g 폐지로 이진 특권이
# 사라졌으므로 공격성은 g_burst × g_full_ata_deg 조합으로 설계한다.
G_BURST_DEFAULT = 0.0                # 지속 봉투 유지 = 에너지 보존 (구 max_g:false 보다도 순함)
# 창 기본값은 구 하드코딩(2500/30)과 같고, **상한은 WEZ(3,000ft·30°)와 일치**한다.
# 실측 도달률: 2500/30 = 0.80% · 5000/50 ≈ 9%. 상한을 WEZ 밖으로 열었더니(5000/50)
# 배터리 40전 전승 만점의 지배 전략이 됐다(2026-08-25 t4 실측) — track_lock 은 순간
# 봉투를 쓰는 경로라 WEZ 밖 창은 '건 추적'이 아니라 max_g 의 재림이다. 참가자 튜닝은
# 창을 **좁히는** 방향(에너지 절약)이 주가 된다.
TRACK_RNG_FT = 2500.0                # 건 추적 하한 G 발동 사거리 [ft]
TRACK_ATA_DEG = 30.0                 # 동 ATA 게이트 [deg]


@dataclass
class AircraftKinematics:
    """L2 입력 — 로컬 NED(ft, ft/s) + 자세(rad) + 속도(fps/KCAS)."""
    pos_ned: np.ndarray   # [N, E, D] ft  (D = 아래 양수)
    vel_ned: np.ndarray   # [vN, vE, vD] ft/s
    phi: float
    theta: float
    psi: float
    v_fps: float
    kcas: float
    q: float = 0.0        # body pitch rate [rad/s] — 감사용 달성 G 환산에만 쓴다


@dataclass
class GuidanceCommand:
    dphi_cmd: float          # 리프트벡터 배치 롤 증분 [rad]
    q_cmd: float             # 당김 pitch rate [rad/s]
    thrust_cmd: float        # [0,1]
    g_target: float          # 조절된 목표 G (감사)
    audit: dict = field(default_factory=dict)


def _ned_to_body(v_ned: np.ndarray, phi: float, theta: float, psi: float) -> np.ndarray:
    """NED 벡터 → body 프레임 (항공 3-2-1 C_bn)."""
    cp, sp = np.cos(phi), np.sin(phi)
    ct, st = np.cos(theta), np.sin(theta)
    cy, sy = np.cos(psi), np.sin(psi)
    C = np.array([
        [ct * cy,               ct * sy,              -st],
        [sp * st * cy - cp * sy, sp * st * sy + cp * cy, sp * ct],
        [cp * st * cy + sp * sy, cp * st * sy - sp * cy, cp * ct],
    ])
    return C @ np.asarray(v_ned, float)


class BFMGuidance:
    """추격유형별 조준점 → 리프트벡터 배치 + G 조절. 반사적 max-G 아님(D6)."""

    def __init__(self, doctrine: Doctrine | None = None,
                 limiter: CombinedLimiter | None = None,
                 lead_time_s: float = 1.5, lag_dist_ft: float = 1500.0):
        self.doc = doctrine or Doctrine()
        # 코너 플래토는 교리가 단일 진실 — 미주입 시 doctrine 으로 리미터 생성
        # (LimiterConfig 기본값과의 이중 정의 제거; Pilot 은 guid.limiter 공유).
        self.limiter = limiter or CombinedLimiter(LimiterConfig(
            kcas_corner_lo=self.doc.corner_kcas_lo,
            kcas_corner_hi=self.doc.corner_kcas_hi))
        self.lead_time_s = float(lead_time_s)
        self.lag_dist_ft = float(lag_dist_ft)

    # ── 조준점 (추격유형 + 수직 오프셋) ───────────────────────────────
    def _aim_point(self, foe_pos: np.ndarray, foe_vel: np.ndarray, pursuit: str,
                   aim_above_ft: float = 0.0,
                   lead_time_s: float | None = None,
                   lag_dist_ft: float | None = None):
        lead_t = self.lead_time_s if lead_time_s is None else float(lead_time_s)
        lag_d = self.lag_dist_ft if lag_dist_ft is None else float(lag_dist_ft)
        if pursuit == "lead":
            aim = foe_pos + foe_vel * lead_t                     # 미래 위치
        elif pursuit == "lag":
            sp = np.linalg.norm(foe_vel)
            vhat = foe_vel / sp if sp > 1e-6 else np.zeros(3)
            aim = foe_pos - vhat * lag_d                         # 적 뒤(turn circle 안쪽)
        else:
            aim = np.asarray(foe_pos, float).copy()              # pure = 현재 위치
        # 수직 오프셋: NED 에서 위 = D 감소. 오프셋된 조준점은 dphi(리프트벡터
        # 배치)로 실행 — 요요의 "적 POM 위/아래 당김"이 L3 무변경으로 성립.
        aim = np.asarray(aim, float)
        aim[2] -= float(aim_above_ft)
        return aim

    # ── G 조절 (조절 법칙 §4.3.2) ──────────────────────────────────────
    def _regulate_g(self, ata_deg: float, v_kts: float, g_avail: float,
                    g_burst: float | None = None, aspect_deg: float = 0.0,
                    rng_ft: float = 1e9, omega_los: float = 0.0,
                    v_fps: float = 0.0, g_sustained: float = 1e9,
                    aim_ata_deg: float | None = None,
                    g_full_ata_deg: float | None = None,
                    track_rng_ft: float | None = None,
                    track_ata_deg: float | None = None) -> tuple[float, str]:
        doc = self.doc
        # 비례 조절의 오차항은 **조준점까지의 각도**다 (ata_deg 는 적까지 — 사격 게이트용).
        # 미지정이면 적 기준으로 폴백(조준점 오프셋이 없는 호출자·테스트 호환).
        err_deg = ata_deg if aim_ata_deg is None else float(aim_ata_deg)
        # DSL 이 [0,1] 을 보증하지만 research 직접 호출 경로는 무방비 — 방어 클램프
        gb = G_BURST_DEFAULT if g_burst is None else min(1.0, max(0.0, float(g_burst)))
        # 포화 각도 기본값 = 교리 ATA 목표대역 상단 (4.4.6.2.2 "2 HUDs high").
        # 액션이 g_full_ata_deg 로 국면별 오버라이드한다. g_burst 와 같은 방어 —
        # DSL 은 20~90 을 보증하지만 직접 호출이 0 을 주면 k 나눗셈이 터진다.
        ata_full = doc.ata_target_hi if g_full_ata_deg is None \
            else max(1e-6, float(g_full_ata_deg))
        tr_rng = TRACK_RNG_FT if track_rng_ft is None else float(track_rng_ft)
        tr_ata = TRACK_ATA_DEG if track_ata_deg is None else float(track_ata_deg)
        # 천장은 **지속↔순간 봉투 보간**이다 (2026-08-24, 구 max_g 이진 특권의 대체).
        # 순간 봉투(g_avail)를 상시 지령하면 스틱이 스톱에 물린 채(실측: 당김 구간 97%)
        # 에너지만 잃고 지령 G 는 로그에만 존재한다 — 그래서 지속 봉투가 기본 천장이다.
        # g_burst 는 그 천장을 순간 봉투 쪽으로 얼마나 밀지를 참가자가 정하는 연속 노브.
        # max(0.0, ·) 는 고고도에서 g_sustained > g_avail 일 때 보간이 뒤집히는 것을 막는다.
        ceiling = g_sustained + max(0.0, g_avail - g_sustained) * gb
        g_nom = min(g_avail * doc.g_fraction, ceiling)
        # ATA 목표대역(4.4.6.2.2) 안쪽 = 원하는 turning room 에 접근한 상태 → burst 를
        # **선형 감쇠**한다 (4.4.7.2 "DO NOT stay on the limiter"). 절벽(대역 경계에서
        # 즉시 지속 봉투로 강등)은 기각 — A/B 실측(JesterL 12경기×3구성)에서 수렴 원뿔
        # (오차 25~35°)의 마무리 당김을 죽여 무접촉 6/12 를 만들었다(감쇠 없앤 B 는 2/12).
        # 감쇠는 오차→0 에서만 지속 봉투에 수렴해, 조준 상태의 고G 상시화만 막는다.
        if err_deg < doc.ata_target_lo:
            g_nom = min(g_nom, g_sustained
                        + max(0.0, g_nom - g_sustained) * err_deg / doc.ata_target_lo)
        # 비례(획득 법칙): 기수가 **조준점**에서 멀수록 강하게 당겨 리드 확보,
        # 조준에 가까우면 백오프(오버슈트 방지, 4.4.7.2 "DO NOT stay on limiter").
        #
        # 오차항이 조준점 기준인 것이 핵심이다(2026-08-24). 종전에는 적까지의 ATA 로
        # 쟀는데, L1 이 지령하는 것은 aim_above_ft 가 적용된 **조준점**이다. 둘이 어긋나는
        # 국면 — 요요, 그리고 조준선을 문 채 상승하는 하드덱 회복(조준점은 4,000ft 위인데
        # 적 기준 각도는 ≈0°) — 에서 조절기가 "이미 도착했다"고 오판해 1G 로 주저앉았다.
        # max_g 가 존재해야 했던 이유가 이 불일치였다. 조준점 기준으로 재면 회복 기하는
        # 각도가 크게 나와 자연스럽게 강하게 당기고, **조준이 맞은 상태에서 고G 를 유지하는
        # 것은 원리적으로 불가능**해진다(그때는 오차가 0 이다) — 상수 하한 노브가 필요 없다.
        k = g_nom / ata_full
        g = float(np.clip(k * err_deg, doc.g_min, g_nom))
        mode = "regulate"
        # 추적 하한(추적 법칙, 4.4.10.2/4.4.12.1 건 추적): 건 접근 기하에선
        # 표적 LOS 회전율을 따라잡는 G(n=V·ω/g)가 하한 — ATA 비례 백오프만으로는
        # 근거리 선회 표적에서 WEZ 원뿔 직전 평형에 갇힌다(획득≠추적).
        # aspect<90(후미) 게이트는 2026-08-17 제거 — 실측 유도 tick 4,310건 중
        # 후미 진입이 0건이라(전 교전 고aspect) 분기가 영구 사문화됐고, 그 결과
        # 사격 기하에서 세게 당기는 유일한 경로가 max_g 뿐이었다(참가자 트리의
        # max_g 이진 선택이 승부를 지배). 거리 창 확대는 무효 실증(448경기 비트
        # 동일, 2026-08-01) — 병목은 거리가 아니라 이 게이트였다.
        # 창(track_rng_ft/track_ata_deg)은 2026-08-24 참가자 개방. 여기는 순간 봉투를
        # 그대로 쓰므로, g_burst=0 인 에너지 보존형도 사격 국면만 크게 당길 수 있다.
        if rng_ft < tr_rng and ata_deg < tr_ata:
            # 건 추적은 "지금 쏘려고 에너지를 쓰는" 국면 → 순간 봉투 사용(지속 천장 아님)
            g_tr = min(omega_los * v_fps / G_FT_S2 * 1.15, g_avail)  # 15% 여유, 상한 유지(D6)
            if g_tr > g:
                g, mode = g_tr, "track_lock"
        # 초기 당김(4.4.5.2): 머지 진입 기하(고aspect·슬랜트 이내)면 6–8G 급 당김.
        # 매 tick 기하 재유도(무상태) — 리미터·g_fraction 상한 유지(D6).
        if (aspect_deg > doc.initial_pull_aspect_deg
                and doc.slant_ft_lo <= rng_ft <= doc.slant_ft_hi):
            g_ip = min(doc.initial_pull_g, g_avail)   # 머지 초기 당김도 순간 봉투(교리 4.4.5.2)
            if g_ip > g:
                g, mode = g_ip, "initial_pull"
        # 에너지 백오프: 파이팅 하한 미만이면 G 낮춰 속도 보존(Ps 관리).
        if v_kts < doc.fighting_kts_lo:
            g *= max(doc.energy_backoff_floor, v_kts / doc.fighting_kts_lo)
            mode = "energy_backoff"
        return g, mode

    # ── 파워 스케줄 (진입 가속 + closure 조절 + 파이팅 대역 + 에너지 마진) ──
    def _power(self, v_kts: float, rng_ft: float | None = None,
               adv_kt: float | None = None, aspect_deg: float | None = None,
               closure_fps: float | None = None) -> tuple[float, str]:
        doc = self.doc
        # 진입 가속(4.4.4.2): 원거리(슬랜트 상한×2 밖)에서 진입속도 미달이면 AB.
        if rng_ft is not None and rng_ft > 2.0 * doc.slant_ft_hi and v_kts < doc.entry_kcas:
            return THR_AB, "AB_entry"
        # 건 접근 closure 조절(4.4.12.1 "modulate power to control closure",
        # 4.4.13.1 idle 까지): 후방 반구·건 접근 국면에서 과잉 접근율만 MIL→idle 로
        # 비례 컷. 허용 접근율은 새들(900ft 트레일)로 갈수록 0 에 수렴하는 깔때기 —
        # 원거리에서 접근 자체를 죽이지 않도록(사거리 밖 동결 방지).
        # 파이팅 하한 위에서만(하한 미만은 4.4.6.2.2 가속이 우선).
        if (rng_ft is not None and aspect_deg is not None and closure_fps is not None
                and rng_ft < 2500.0 and aspect_deg < 90.0
                and v_kts > doc.fighting_kts_lo):
            # 새들(허용 접근율 0 인 트레일 거리)은 교리 파라미터 — 2026-08-24 개방
            allow_fps = max(0.0, (rng_ft - doc.closure_saddle_ft) / 10.0)  # 2500ft→160fps, 새들→0
            excess = closure_fps - allow_fps
            if excess > 0.0:
                frac = min(excess / 150.0, 1.0)             # 150fps 초과분이면 idle
                return float(THR_MIL * (1.0 - frac)), "closure_ctl"
        if v_kts < doc.fighting_kts_lo:
            return THR_AB, "AB_accel"                            # 가속(파이팅 하한 회복)
        if v_kts > doc.fighting_kts_hi:
            return THR_DECEL, "decel"                            # 감속(파이팅 상한 초과)
        # 대역 내: 에너지 마진 유지(4.4.6.2.2) — 상대 TAS 우위 50kt 미달이면 AB 로 증속,
        # 50–75kt 는 AB→MIL 선형 블렌드, 75kt 이상이면 MIL 유지.
        if adv_kt is not None and adv_kt < doc.energy_margin_hi:
            if adv_kt <= doc.energy_margin_lo:
                return THR_AB, "margin_regain"
            frac = (adv_kt - doc.energy_margin_lo) / (doc.energy_margin_hi - doc.energy_margin_lo)
            return float(THR_AB - (THR_AB - THR_MIL) * frac), "margin_regain"
        return THR_MIL, "MIL_hold"                               # 대역 유지(실 MIL)

    # ── control_zone 파워: range 오차 → 목표 접근율 → 파워로 접근율 조절 ──
    def _control_zone_power(self, rng_ft: float, closure_fps: float,
                            cz_range_ft: float | None = None) -> tuple[float, str]:
        """컨트롤존 유지 — 목표 거리(기본 CZ_RANGE_FT)로 접근율을 수렴(닫힘 0).
        멀면 붙이고(접근 허용), 목표거리·접근이면 파워 컷. 오버슈트 대신 존 체류.
        """
        cz_ft = CZ_RANGE_FT if cz_range_ft is None else float(cz_range_ft)
        des_closure = float(np.clip((rng_ft - cz_ft) / self.doc.cz_close_t_s,
                                    -CZ_MAX_CLOSURE, CZ_MAX_CLOSURE))
        err = closure_fps - des_closure          # >0 = 목표보다 빨리 접근
        thr = THR_MIL - err / 200.0              # 비례: 200fps 오차 = MIL 전량 스윙
        return float(np.clip(thr, THR_IDLE, THR_AB)), "control_zone"

    # ── 메인 ──────────────────────────────────────────────────────────
    def compute(self, me: AircraftKinematics, foe_pos_ned, foe_vel_ned,
                pursuit: str = "pure", g_burst: float | None = None,
                aim_above_ft: float | None = None,
                lead_time_s: float | None = None,
                lag_dist_ft: float | None = None,
                mode: str | None = None,
                cz_range_ft: float | None = None,
                g_full_ata_deg: float | None = None,
                track_rng_ft: float | None = None,
                track_ata_deg: float | None = None,
                foe_theta: float = 0.0, foe_psi: float = 0.0) -> GuidanceCommand:
        foe_pos = np.asarray(foe_pos_ned, float)
        foe_vel = np.asarray(foe_vel_ned, float)

        # 기하(각도·closure) — CombatGeometry 는 스케일 불변이라 ft 로 먹여도 각도 정상.
        # ATA/AA 는 BEM 종축 기준이라 양측 자세를 전달 (2026-07-17).
        geom = CombatGeometry(me.pos_ned, foe_pos, me.vel_ned, foe_vel,
                              me.phi, me.theta, me.psi, foe_theta, foe_psi)
        ata = geom.ata_deg()
        aspect = geom.aa_deg()
        los = foe_pos - me.pos_ned
        rng_ft = float(np.linalg.norm(los))
        closure_fps = geom.closure_rate()
        adv_kt = (me.v_fps - float(np.linalg.norm(foe_vel))) * FT_S_TO_KT
        # 표적 LOS 회전율 [rad/s] — 추적 하한 G(track_lock)의 기준
        v_rel = foe_vel - me.vel_ned
        u_los = los / max(rng_ft, 1.0)
        omega_los = float(np.linalg.norm(v_rel - np.dot(v_rel, u_los) * u_los)) / max(rng_ft, 1.0)

        # 수직 오프셋 해소: L1 명시값(0 포함)이 항상 우선. 미지정(None)이면
        # 머지 진입 기하에서 교리 자동 +lv_above_ft ("적 POM 살짝 위", 4.4.5.2).
        # 게이트가 initial_pull(_regulate_g)과 **의도적으로 다르다**: G 쪽은 슬랜트
        # 대역(lo~hi)이지만 LV 오프셋은 하한 없이 rng<hi — 근접 머지에서도 조준점을
        # 살짝 위에 둬야 충돌 회피 여유가 생긴다(t4/t7 실측 606경기가 이 상태의 측정).
        # 단 stable/control_zone 은 자동 LV 오프셋 억제(안정 추적·존 유지가 우선).
        entry_geom = (aspect > self.doc.initial_pull_aspect_deg
                      and rng_ft < self.doc.slant_ft_hi)
        if aim_above_ft is not None:
            aim_above = float(aim_above_ft)
        elif mode in ("stable", "control_zone"):
            aim_above = 0.0
        else:
            aim_above = self.doc.lv_above_ft if entry_geom else 0.0

        # control_zone: 근접+접근이면 lag 편향으로 오버슈트(적기 앞 이탈) 방지.
        pursuit_eff = pursuit
        cz_ft = CZ_RANGE_FT if cz_range_ft is None else float(cz_range_ft)
        if mode == "control_zone" and rng_ft < cz_ft * CZ_LAG_TRIP_RATIO and closure_fps > 40.0:
            pursuit_eff = "lag"

        # 리프트벡터 배치: 조준점을 body 프레임에서 pull-plane(기수-리프트벡터 면)으로.
        aim = self._aim_point(foe_pos, foe_vel, pursuit_eff, aim_above_ft=aim_above,
                              lead_time_s=lead_time_s, lag_dist_ft=lag_dist_ft)
        aim_los = aim - me.pos_ned
        n = np.linalg.norm(aim_los)
        aim_body = _ned_to_body(aim_los / n, me.phi, me.theta, me.psi) if n > 1e-6 \
            else np.array([1.0, 0.0, 0.0])
        # 기수→**조준점** 각도 — G 조절의 오차항(적까지의 ata 는 사격 게이트 전용).
        # aim_body 는 단위벡터라 x 성분이 곧 cos(각).
        aim_ata = float(np.degrees(np.arccos(np.clip(aim_body[0], -1.0, 1.0))))
        g_avail = self.limiter.max_load_factor(me.kcas)          # 순간 봉투
        # 지속 봉투 — 로컬 NED 는 D = -고도 (engine/scenarios.py IC 규약)
        g_sus = self.limiter.sustained_load_factor(me.kcas, float(-me.pos_ned[2]))
        if mode == "stable":
            # 포인팅 추적: 표적을 body forward 축에 정렬. **수평 우선**(부분 뱅크 phi_target)
            # + **부호있는 pitch**(위·아래 모두). 정면 표적이면 phi_target=0 = 수평 복귀 →
            # 헤드온 노즈온 안정(구 stable 은 롤 클램프+상향-only G 라 저표적서 ATA null 실패).
            fwd = max(float(aim_body[0]), 1e-6)
            bearing = float(np.arctan2(aim_body[1], fwd))               # 표적 수평 방위(우+)
            el = float(np.arctan2(-aim_body[2],
                                  np.hypot(aim_body[0], aim_body[1])))  # 표적 상하각(위+)
            phi_target = float(np.clip(STABLE_K_BANK * bearing,
                                       -STABLE_BANK_MAX, STABLE_BANK_MAX))
            dphi_cmd = phi_target - me.phi                              # 목표 뱅크로(증분)
            # 부호있는 pitch. 상한은 stable 튜닝값(STABLE_Q_MAX)과 **기체 봉투** 중
            # 좁은 쪽. 봉투를 안 보면 밀기 명령이 −16G 급까지 나가는데(감사 실측),
            # 실기 F-16 은 −3G 가 기골 설계 하중이라 그런 명령은 존재할 수 없다.
            g_lift = float(np.cos(me.phi) * np.cos(me.theta))   # 중력의 양력방향 성분
            q_hi = min(STABLE_Q_MAX,
                       self.limiter.max_pitch_rate(me.v_fps, me.kcas, g_lift))
            q_lo = max(-STABLE_Q_MAX,
                       self.limiter.min_pitch_rate(me.v_fps, me.kcas, g_lift))
            q_cmd = float(np.clip(STABLE_K_Q * el, q_lo, q_hi))
            g_target, g_mode = q_cmd * max(me.v_fps, 1.0) / G_FT_S2, "stable_track"  # audit 등가 G
        else:
            # dphi: 조준점의 body y(우)·-z(위)로 롤 — 리프트벡터(-z)를 조준점 쪽으로.
            dphi_cmd = float(np.arctan2(aim_body[1], -aim_body[2]))
            g_target, g_mode = self._regulate_g(ata, me.kcas, g_avail, g_burst,
                                                aspect_deg=aspect, rng_ft=rng_ft,
                                                omega_los=omega_los, v_fps=me.v_fps,
                                                g_sustained=g_sus,
                                                aim_ata_deg=aim_ata,
                                                g_full_ata_deg=g_full_ata_deg,
                                                track_rng_ft=track_rng_ft,
                                                track_ata_deg=track_ata_deg)
            # 조절 G 도 봉투 안으로(음수쪽은 _regulate_g 가 내지 않지만 계약을 명시).
            g_target = float(np.clip(g_target,
                                     self.limiter.min_load_factor(me.kcas), g_avail))
            # 중력항 포함: q = (n − cosφcosθ)·g/V. 수평 정립에서 1G 는 중력이 상쇄한다.
            g_lift = float(np.cos(me.phi) * np.cos(me.theta))
            q_cmd = (g_target - g_lift) * G_FT_S2 / max(me.v_fps, 1.0)  # rate 는 TAS 기준
        # control_zone: 파워를 접근율 조절기로 대체(존 체류). 그 외는 교리 파워 스케줄.
        if mode == "control_zone":
            thrust, pwr_mode = self._control_zone_power(rng_ft, closure_fps, cz_ft)
        else:
            thrust, pwr_mode = self._power(me.kcas, rng_ft=rng_ft, adv_kt=adv_kt,
                                           aspect_deg=aspect, closure_fps=closure_fps)

        # 감사 정직성: 지령 G 옆에 **실제 달성 G** 를 같이 남긴다 (n = q·V/g + cosφcosθ).
        # 지령만 기록하면 봉투 밖 지령이 로그상 성공처럼 보인다 — 실측 결과 당김 구간에서
        # 지령 8.0G / 달성 5.9G (격차 −2.1G) 였다. g_deficit 이 그 갭의 상시 계측기다.
        g_achieved = (me.q * me.v_fps / G_FT_S2
                      + float(np.cos(me.phi) * np.cos(me.theta)))
        audit = {
            "g_achieved": g_achieved, "g_deficit": g_achieved - g_target,
            "pursuit": pursuit_eff, "mode": mode or "-", "ata_deg": ata, "aspect_deg": aspect,
            "range_ft": rng_ft, "closure_fps": closure_fps,
            "kcas": me.kcas, "tas_kts": me.v_fps * FT_S_TO_KT,
            "g_avail": g_avail, "g_sustained": g_sus,
            "g_target": g_target, "g_mode": g_mode,
            "power_mode": pwr_mode, "dphi_deg": np.degrees(dphi_cmd),
            "aim_above_ft": aim_above,                         # 실적용 오프셋
            "lead_time_s": self.lead_time_s if lead_time_s is None else float(lead_time_s),
            "lag_dist_ft": self.lag_dist_ft if lag_dist_ft is None else float(lag_dist_ft),
            "g_burst": G_BURST_DEFAULT if g_burst is None else float(g_burst),
            "aim_ata_deg": aim_ata,          # G 조절 오차항 (적 기준 ata_deg 와 구분)
            "adv_kt": adv_kt, "entry_phase": pwr_mode == "AB_entry",
            "in_slant_band": self.doc.slant_ft_lo <= rng_ft <= self.doc.slant_ft_hi,
            "in_ata_band": self.doc.ata_target_lo <= ata <= self.doc.ata_target_hi,
        }
        return GuidanceCommand(dphi_cmd=dphi_cmd, q_cmd=q_cmd,
                               thrust_cmd=thrust, g_target=g_target, audit=audit)
