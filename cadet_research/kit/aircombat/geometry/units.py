"""
항공 표준 단위 변환 유틸리티

단위 시스템:
- 거리: NM (해리, Nautical Mile) 및 Feet
  - 1 NM = 1,852 m = 6,076 ft
  - 1 NM 이하는 Feet 사용
- 속도: Knot (노트)
  - 1 Knot = 1 NM/h = 0.514444 m/s
- 고도: Feet
"""

# 거리 변환 상수
M_TO_FT = 3.28084          # 미터 → 피트
FT_TO_M = 0.3048           # 피트 → 미터
M_TO_NM = 0.000539957      # 미터 → 해리
NM_TO_M = 1852.0           # 해리 → 미터
NM_TO_FT = 6076.0          # 해리 → 피트
FT_TO_NM = 1.0 / 6076.0    # 피트 → 해리

# 속도 변환 상수
MS_TO_KNOT = 1.94384       # m/s → 노트
KNOT_TO_MS = 0.514444      # 노트 → m/s
KNOT_TO_FT_S = 1.68781     # 노트 → ft/s
FT_S_TO_KNOT = 0.592484    # ft/s → 노트

# 임계값 (1 NM = 6,076 ft)
DISTANCE_THRESHOLD_FT = 6076.0  # 이 값 이하는 Feet 사용


def meters_to_feet(meters: float) -> float:
    """미터를 피트로 변환"""
    return meters * M_TO_FT


def feet_to_meters(feet: float) -> float:
    """피트를 미터로 변환"""
    return feet * FT_TO_M


def meters_to_nm(meters: float) -> float:
    """미터를 해리로 변환"""
    return meters * M_TO_NM


def nm_to_meters(nm: float) -> float:
    """해리를 미터로 변환"""
    return nm * NM_TO_M


def nm_to_feet(nm: float) -> float:
    """해리를 피트로 변환"""
    return nm * NM_TO_FT


def feet_to_nm(feet: float) -> float:
    """피트를 해리로 변환"""
    return feet * FT_TO_NM


def ms_to_knots(ms: float) -> float:
    """m/s를 노트로 변환"""
    return ms * MS_TO_KNOT


def knots_to_ms(knots: float) -> float:
    """노트를 m/s로 변환"""
    return knots * KNOT_TO_MS


def format_distance(meters: float) -> str:
    """
    거리를 적절한 단위로 포맷
    
    Args:
        meters: 미터 단위 거리
    
    Returns:
        포맷된 문자열 (1 NM 이하는 Feet, 이상은 NM)
    """
    feet = meters_to_feet(meters)
    
    if feet <= DISTANCE_THRESHOLD_FT:
        return f"{feet:.0f} ft"
    else:
        nm = meters_to_nm(meters)
        return f"{nm:.2f} NM"


def format_altitude(meters: float) -> str:
    """
    고도를 피트로 포맷
    
    Args:
        meters: 미터 단위 고도
    
    Returns:
        포맷된 문자열 (Feet)
    """
    feet = meters_to_feet(meters)
    return f"{feet:.0f} ft"


def format_speed(ms: float) -> str:
    """
    속도를 노트로 포맷
    
    Args:
        ms: m/s 단위 속도
    
    Returns:
        포맷된 문자열 (Knots)
    """
    knots = ms_to_knots(ms)
    return f"{knots:.0f} kts"


def parse_distance(value: float, unit: str) -> float:
    """
    거리를 미터로 파싱
    
    Args:
        value: 거리 값
        unit: 단위 ("ft", "feet", "nm", "m", "meter")
    
    Returns:
        미터 단위 거리
    """
    unit = unit.lower().strip()
    
    if unit in ["ft", "feet"]:
        return feet_to_meters(value)
    elif unit in ["nm", "nautical_mile"]:
        return nm_to_meters(value)
    elif unit in ["m", "meter", "meters"]:
        return value
    else:
        raise ValueError(f"Unknown distance unit: {unit}")


def parse_speed(value: float, unit: str) -> float:
    """
    속도를 m/s로 파싱
    
    Args:
        value: 속도 값
        unit: 단위 ("kts", "knots", "ms", "m/s")
    
    Returns:
        m/s 단위 속도
    """
    unit = unit.lower().strip()
    
    if unit in ["kts", "knot", "knots"]:
        return knots_to_ms(value)
    elif unit in ["ms", "m/s", "mps"]:
        return value
    else:
        raise ValueError(f"Unknown speed unit: {unit}")


# 자주 사용되는 상수 (미터 단위로 저장)
HARD_DECK_M = feet_to_meters(1000)      # 1,000 ft
WEZ_MIN_RANGE_M = feet_to_meters(500)   # 500 ft (Gun WEZ 최소 거리 — 미만은 데미지 0)
WEZ_MAX_RANGE_M = feet_to_meters(3000)  # 3,000 ft (Gun WEZ 최대 거리)
WEZ_MAX_ANGLE_DEG = 30.0                # ATA 30° (Gun WEZ 원뿔 상한 = 최외곽 tier)

# Gun WEZ 각도 tier — 데미지 = 50 HP/s × 각도계수 (거리계수·시간완화 없음).
# 500–3,000 ft 균일, <500ft = 0, >3,000ft = 0. ATA(정조준 0°)가 작을수록 큰 계수.
# (ATA 한계 deg, 계수) — 위에서부터 첫 충족 tier 적용. RULEBOOK §4 와 단일 진실.
WEZ_ATA_TIERS = (
    (2.0,  1.00),
    (10.0, 0.75),
    (20.0, 0.50),
    (30.0, 0.25),
)

# ── 오버타임 WEZ (RULEBOOK 「오버타임」) ────────────────────────────────
# 정규 300초에 승자가 안 나온 현장 단판만 120초를 더 뛴다. 결착률을 올리는 축은
# WEZ 하나뿐이다 — 교전구역·상승 하드덱은 트리가 관측할 수 없어 기각됐다
# (수평 절대좌표·경과시간이 관측 어휘에 없다). 각도계수 계단은 그대로 두고
# 최외곽 tier(0.25)만 45°까지 늘린다: "같은 데미지 구조, 넓은 원뿔".
OVERTIME_MAX_RANGE_M = feet_to_meters(6000)   # 3,000 → 6,000 ft
OVERTIME_MAX_ANGLE_DEG = 45.0                 # 30° → 45°
OVERTIME_ATA_TIERS = (
    (2.0,  1.00),
    (10.0, 0.75),
    (20.0, 0.50),
    (45.0, 0.25),
)
