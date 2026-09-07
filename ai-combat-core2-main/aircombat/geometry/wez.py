"""
Health Gauge 시스템

논문 "공대공 전투 모의를 위한 규칙기반 AI 교전 모델 개발" 기반
WEZ (Weapon Engagement Zone) 내 체류 시 데미지 누적

BEM 근거·의도적 편차 (Korean AF BEM Vol.5, 2005 대조 — 2026-07 재검토):
- BEM §4.5.31 유효 gunshot 3요소 = lead·range·POM. 본 모델은 range+ATA만 모델링
  — 현재 표적 위치 기준 ATA(리드 판정 없음)의 **의도적 단순화**.
  ATA 는 BEM §4.8.2.4 정의대로 **기수(boresight) 기준** (2026-07-17 — 구 구현은
  속도벡터 기준이었으나 교범·룰북 문언("내 기수 원뿔")에 정합하도록 전환).
  리드 판정 도입 시 리드 포인트(p_t + v_t·TOF, TOF=거리/탄속) 기준 ATA 로 확장 가능.
- min 500 ft: BEM §4.4.14 은 "gun 최소사거리 없음"이나 frag/FOD 회피 권고
  → 과접근 페널티 게임 규칙.
- max 3,000 ft 균일: BEM §4.4.14.3.2.2 funnel bottom 2,500–4,000 ft 범위 내 고정값.
  고Vc 스냅샷(4–5k ft, §4.4.15.1)은 미모델.
- ATA 상한 30°: 리드 미반영 단순화 하에서의 최대 리드각(~20° = EEGS 표적 최대
  지속선회 20°/s × 탄 TOF ~1 s, §4.4.14.3.2.3) + 분산(6 mil)·안정화(0.25 s,
  §4.4.14.3.2.4) 여유. 이를 넘는 기수-표적 편차는 어떤 기동에서도 유효 사격해가
  아니다. 리드 판정 도입 시 원뿔은 리드 포인트 기준 ~5–10°로 좁히는 것이 맞다.
- 데미지율 50 HP/s: BEM §4.4.14.2 lethal burst 1–2 s → 정조준 2 s 격추.
"""

from .combat_geometry import CombatGeometry
from .units import (WEZ_MIN_RANGE_M, WEZ_MAX_RANGE_M, WEZ_MAX_ANGLE_DEG, WEZ_ATA_TIERS,
                    OVERTIME_MAX_RANGE_M, OVERTIME_MAX_ANGLE_DEG, OVERTIME_ATA_TIERS)

DPS_MAX = 50.0   # 정조준(ATA<2°) 최대 데미지 [HP/s] — BEM lethal burst 1–2 s 근거


class WeaponEngagementZone:
    """가상 공격 영역 (Weapon Engagement Zone) - Gun Only

    Gun WEZ 기준 (경기 규칙, RULEBOOK §4):
    - 사거리 500–3,000 ft **균일**(거리계수 없음), <500ft·>3,000ft = 데미지 0.
    - 데미지 = 50 HP/s × 각도계수. 각도계수는 ATA tier(units.WEZ_ATA_TIERS):
      ATA<2°=1.0 / <10°=0.75 / <20°=0.5 / <30°=0.25 / ≥30°=0.
    - 시간 완화 없음(전 시각 동일).
    """

    MAX_ANGLE_DEG = WEZ_MAX_ANGLE_DEG  # 30.0° (최외곽 tier)
    MIN_RANGE_M = WEZ_MIN_RANGE_M      # 152.4 m (500 ft)
    MAX_RANGE_M = WEZ_MAX_RANGE_M      # 914.4 m (3,000 ft)

    # 오버타임 완화값은 **인자로 흘린다 — 클래스 상수를 덮어쓰지 않는다.**
    # Lambda 러너는 프로세스를 재사용하므로 전역 변이가 다음 매치로 샌다
    # (배터리 40경기가 OT 규칙으로 채점되는 사고).
    @staticmethod
    def _spec(overtime: bool) -> tuple[float, tuple]:
        """(사거리 상한 m, ATA tier) — 정규/오버타임 두 구성뿐이라 bool 로 고른다."""
        return ((OVERTIME_MAX_RANGE_M, OVERTIME_ATA_TIERS) if overtime
                else (WEZ_MAX_RANGE_M, WEZ_ATA_TIERS))

    @staticmethod
    def _in_range(distance: float, max_range_m: float = WEZ_MAX_RANGE_M) -> bool:
        return WeaponEngagementZone.MIN_RANGE_M <= distance <= max_range_m

    @staticmethod
    def _angle_coef(ata: float, tiers: tuple = WEZ_ATA_TIERS) -> float:
        """ATA tier 각도계수 — 위에서부터 첫 충족 tier, 어디에도 안 들면 0."""
        for max_ata, coef in tiers:
            if ata < max_ata:
                return coef
        return 0.0

    @staticmethod
    def is_in_wez(geometry: CombatGeometry, overtime: bool = False) -> bool:
        """공격 유효 영역(사거리 내 + ATA 원뿔 안) 판단."""
        max_range_m, tiers = WeaponEngagementZone._spec(overtime)
        return (WeaponEngagementZone._in_range(geometry.distance(), max_range_m)
                and WeaponEngagementZone._angle_coef(geometry.ata_deg(), tiers) > 0.0)

    @staticmethod
    def calculate_damage(geometry: CombatGeometry, dt: float = 0.2,
                         overtime: bool = False) -> float:
        """데미지 = 50 HP/s × 각도계수 × dt (사거리 대역 안에서 균일).

        Args:
            geometry: CombatGeometry 객체
            dt: 시간 간격 (초)
            overtime: True 면 OT 완화 WEZ (6,000 ft / 45° 원뿔)

        Returns:
            float: 데미지 (정조준 ATA<2° 에서 최대 50 HP/s × dt)
        """
        max_range_m, tiers = WeaponEngagementZone._spec(overtime)
        if not WeaponEngagementZone._in_range(geometry.distance(), max_range_m):
            return 0.0
        return DPS_MAX * WeaponEngagementZone._angle_coef(geometry.ata_deg(), tiers) * dt


class HealthGauge:
    """체력 관리 시스템
    
    논문 기준:
    - 초기 체력: 100 HP
    - WEZ 내 체류 시 데미지 누적
    - 체력 0 시 패배
    """
    
    def __init__(self, initial_health: float = 100.0):
        """초기화
        
        Args:
            initial_health: 초기 체력 (기본값 100 HP)
        """
        self.max_health = initial_health
        self.current_health = initial_health
        self.damage_history = []
        self.total_damage_taken = 0.0
        self.total_damage_dealt = 0.0
    
    def take_damage(self, damage: float, step: int):
        """데미지 받기
        
        Args:
            damage: 데미지 양
            step: 현재 스텝
        """
        if damage <= 0:
            return
        
        self.current_health = max(0.0, self.current_health - damage)
        self.total_damage_taken += damage
        
        self.damage_history.append({
            'step': step,
            'damage': damage,
            'remaining': self.current_health
        })
    
    def deal_damage(self, damage: float):
        """데미지 가하기 (통계용)
        
        Args:
            damage: 가한 데미지 양
        """
        if damage > 0:
            self.total_damage_dealt += damage
    
    def is_alive(self) -> bool:
        """생존 여부
        
        Returns:
            bool: 생존 여부
        """
        return self.current_health > 0.0
    
    def get_health_ratio(self) -> float:
        """체력 비율
        
        Returns:
            float: 체력 비율 (0.0 ~ 1.0)
        """
        return self.current_health / self.max_health
    
    def reset(self):
        """체력 초기화"""
        self.current_health = self.max_health
        self.damage_history.clear()
        self.total_damage_taken = 0.0
        self.total_damage_dealt = 0.0
    
    def get_stats(self) -> dict:
        """통계 정보 반환
        
        Returns:
            dict: 체력 통계
        """
        return {
            'current_health': self.current_health,
            'max_health': self.max_health,
            'health_ratio': self.get_health_ratio(),
            'total_damage_taken': self.total_damage_taken,
            'total_damage_dealt': self.total_damage_dealt,
            'is_alive': self.is_alive(),
            'damage_events': len(self.damage_history)
        }
