"""교전 관측 교환 상태 — pilot ↔ opponent 공통 인터페이스.

로컬 NED(ft) 평면에서 두 기체를 관리한다(교전 범위 <5NM 에선 평면근사 충분).
JSBSim 절대 lat/long 대신 공통 로컬 원점을 쓰므로 상대기하가 일관된다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

FT_TO_M = 0.3048
G_FT_S2 = 32.174
FT_S_TO_KT = 0.592484


@dataclass
class ControlTelemetry:
    """조종 텔레메트리 — ACMI Control Position 애드온용(조종입력 + 서보 실제위치)."""
    throttle: float
    ail_cmd: float
    elev_cmd: float
    rud_cmd: float
    ail_pos: float
    elev_pos: float
    rud_pos: float


@dataclass
class KinState:
    pos_ned: np.ndarray   # [N, E, D] ft (D 아래 양수)
    vel_ned: np.ndarray   # [vN, vE, vD] ft/s
    phi: float            # rad
    theta: float
    psi: float
    v_fps: float
    kcas: float
    alt_ft: float
    health: float = 100.0

    def specific_energy_ft(self) -> float:
        """비에너지 E = h + V²/2g [ft]."""
        return self.alt_ft + self.v_fps ** 2 / (2.0 * G_FT_S2)


def ned_to_lonlat(pos_ned, lon0: float = 127.0, lat0: float = 37.0):
    """로컬 NED(ft) → (lon, lat, alt_m). ACMI 출력용 평면근사."""
    n, e, d = float(pos_ned[0]), float(pos_ned[1]), float(pos_ned[2])
    lat = lat0 + (n * FT_TO_M) / 111320.0
    lon = lon0 + (e * FT_TO_M) / (111320.0 * math.cos(math.radians(lat0)))
    return lon, lat, -d * FT_TO_M
