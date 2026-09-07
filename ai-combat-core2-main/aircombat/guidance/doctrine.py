"""BFM 교리 setpoint 상수 — Korean AF Basic Employment Manual, F-16C, Vol.5 (2005) Ch.4.

L2 조절(regulation)의 목표값. 이 수치들이 "감사가능(auditable) AI 전술"의 기준선이다
(제1세부 신뢰성 평가 기준). config/doctrine.yaml 로 외부화하여 튜닝한다.

출처 매핑(tmp/f16_bfm_control_architecture.md §4.2):
  코너 플래토 330–440 KCAS (4.3.3.7) · 파이팅 325–375kt (4.4.6.2.2) ·
  에너지우위 50–75kt (4.4.6.2.2) · 슬랜트 4,000–6,000ft (4.4.6.2.1) ·
  ATA 목표 35–50° (4.4.6.2.2) · 진입 450–480 KCAS (4.4.4.2) ·
  LV 적 POM 살짝 위 500–1,000ft (4.4.5.2) · 파워 MIL>400/AB<400kt (4.4.10.1.1) ·
  초기 당김 6–8G (4.4.5.2).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict

# 참가자 교리 튜닝 개방 여부 — 2026-08-17 개방(운영 결정, RULEBOOK §10 개정·공지 완료).
# 개방 전 스윕 검증: scripts/sweep_doctrine.py, 1,368경기(base 3종 × 극단 19 config ×
# red 3종). 판정: 지배 필드 없음(Δpts≥+6 를 base 2종 이상에서 넘는 필드 0) →
# 점잠금 없이 15필드 전면 개방. 결과 tmp/sweep_doctrine.json (2026-08-17).
TUNING_ENABLED = True

# 참가자 오버라이드 허용 범위 (필드: (lo, hi)) — 전부 교범 인용 대역.
# 검증(from_overrides)과 자동 문서(DOCTRINE_REFERENCE) 의 단일 진실.
DOCTRINE_BOUNDS = {
    "corner_kcas_lo": (330.0, 440.0),   # 4.3.3.7 코너 플래토
    "corner_kcas_hi": (330.0, 440.0),
    "fighting_kts_lo": (325.0, 375.0),  # 4.4.6.2.2 파이팅 속도
    "fighting_kts_hi": (325.0, 375.0),
    "energy_margin_lo": (50.0, 75.0),   # 4.4.6.2.2 에너지 우위
    "energy_margin_hi": (50.0, 75.0),
    "slant_ft_lo": (4000.0, 6000.0),    # 4.4.6.2.1 슬랜트 거리
    "slant_ft_hi": (4000.0, 6000.0),
    "ata_target_lo": (35.0, 50.0),      # 4.4.6.2.2 ATA 목표대역
    "ata_target_hi": (35.0, 50.0),
    "entry_kcas": (450.0, 480.0),       # 4.4.4.2 진입 속도
    "lv_above_ft": (500.0, 1000.0),     # 4.4.5.2 LV 수직여유
    "initial_pull_g": (6.0, 8.0),       # 4.4.5.2 초기 당김
    "g_fraction": (0.8, 0.95),          # 4.4.7.2 "리미터 살짝 아래"
    "g_min": (1.0, 1.5),
    # 2026-08-24 개방 — 구 하드코딩 게이트/계수 (bfm_guidance 참조)
    "initial_pull_aspect_deg": (90.0, 150.0),   # 4.4.5.2 머지 진입 판정 aspect
    "closure_saddle_ft": (600.0, 1500.0),       # 4.4.12.1 접근율 깔때기 새들(트레일 목표)
    "energy_backoff_floor": (0.3, 0.8),         # 4.4.6.2.2 저속 G 감쇠 바닥
    "cz_close_t_s": (2.0, 8.0),                 # control_zone 거리오차 수렴 시상수
}

# lo ≤ hi 교차 검증 대상 대역 필드
_BAND_FIELDS = ("corner_kcas", "fighting_kts", "energy_margin", "slant_ft", "ata_target")


@dataclass
class Doctrine:
    # 코너 플래토 [KCAS] — 최고 순간선회 영역
    corner_kcas_lo: float = 330.0
    corner_kcas_hi: float = 440.0
    # 파이팅 속도 [kt] — 지속선회 최적, L2 속도 조절 목표대역
    fighting_kts_lo: float = 325.0
    fighting_kts_hi: float = 375.0
    # 에너지 우위 유지 [kt]
    energy_margin_lo: float = 50.0
    energy_margin_hi: float = 75.0
    # 슬랜트 거리 목표 [ft]
    slant_ft_lo: float = 4000.0
    slant_ft_hi: float = 6000.0
    # ATA 목표대역 [deg] ("2 HUDs high")
    ata_target_lo: float = 35.0
    ata_target_hi: float = 50.0
    # 진입 속도 [KCAS]
    entry_kcas: float = 465.0
    # 리프트벡터: 적 POM 살짝 위 수직여유 [ft]
    lv_above_ft: float = 750.0
    # 초기 당김 [G]
    initial_pull_g: float = 7.0
    # "리미터 살짝 아래" — 명목 G 상한 = 가용 G × 이 비율 (D6, 4.4.7.2)
    g_fraction: float = 0.95
    # 최소 유지 G (수평)
    g_min: float = 1.0
    # 머지 진입 판정 aspect [deg] — 초기 당김·LV 수직여유 자동적용의 공통 게이트 (4.4.5.2)
    initial_pull_aspect_deg: float = 120.0
    # 건 접근 허용 접근율 깔때기가 0 으로 수렴하는 트레일 거리 [ft] (4.4.12.1)
    closure_saddle_ft: float = 900.0
    # 파이팅 하한 미만 G 감쇠의 바닥 비율 (4.4.6.2.2)
    energy_backoff_floor: float = 0.5
    # control_zone 거리오차 수렴 시상수 [s]
    cz_close_t_s: float = 4.0

    def to_yaml_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_overrides(cls, overrides: dict | None) -> "Doctrine":
        """참가자 에이전트 YAML 의 doctrine: 블록 → Doctrine.

        미개방(TUNING_ENABLED=False)이면 거부. 미지 키·범위 밖 값은 조용히
        삼키지 않고 ValueError — DSL 화이트리스트 철학과 동일.
        """
        if not overrides:
            return cls()
        if not TUNING_ENABLED:
            raise ValueError(
                "doctrine 블록은 아직 개방되지 않았습니다 "
                "(올해 규정: L1 전술 트리만 수정 가능)")
        errors = []
        clean = {}
        for k, v in overrides.items():
            if k not in DOCTRINE_BOUNDS:
                errors.append(f"미지 교리 필드 {k!r}")
                continue
            lo, hi = DOCTRINE_BOUNDS[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) \
                    or not (lo <= float(v) <= hi):
                errors.append(f"{k}={v!r} — 교범 허용 범위 [{lo}, {hi}]")
            else:
                clean[k] = float(v)
        if not errors:
            d = cls(**clean)
            for base in _BAND_FIELDS:
                if getattr(d, f"{base}_lo") > getattr(d, f"{base}_hi"):
                    errors.append(f"{base}: lo > hi")
            if not errors:
                return d
        raise ValueError("doctrine 검증 실패: " + "; ".join(errors))

    @classmethod
    def from_yaml(cls, path: str) -> "Doctrine":
        """config/doctrine.yaml 이 있으면 로드, 없으면 기본값. (yaml 없어도 동작)"""
        if not os.path.isfile(path):
            return cls()
        try:
            import yaml  # optional dependency
        except ImportError:
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        known = {k: data[k] for k in asdict(cls()).keys() if k in data}
        return cls(**known)
