"""합성 L2 기동 — docs/PREREGISTRATION.md §5 의 정의를 그대로 코드로 옮긴 것.

모든 기동은 1.0초 트림 유지 뒤 시작한다(`HOLD_S`). 창 W 는 기동 시작부터 끝까지이며
각 기동이 `window()` 로 [t0, t1) 을 돌려준다.

명령식은 `harness.gcmd`: dphi = φ_target − φ, q_cmd = (Nz_target − cosφcosθ)·g/V, thrust 1.0.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .harness import gcmd, GuidanceCommand

HOLD_S = 1.0


@dataclass
class Maneuver:
    name: str = "base"
    duration_s: float = 0.0
    per_tick: bool = False

    def window(self) -> tuple[float, float]:
        return (HOLD_S, self.duration_s)

    def command(self, t: float, k: int, st: dict) -> GuidanceCommand:
        raise NotImplementedError


@dataclass
class Hold(Maneuver):
    """트림 유지 (뱅크 0, Nz 1)."""
    name: str = "hold"
    duration_s: float = 3.0

    def command(self, t, k, st):
        return gcmd(0.0 - st["phi"], 1.0, st)


@dataclass
class M1NzCapture(Maneuver):
    """뱅크 0 유지, Nz 목표 = nz_target 계단 후 유지. 1 + 5 s."""
    nz_target: float = 3.0
    name: str = "M1"
    duration_s: float = HOLD_S + 5.0

    def command(self, t, k, st):
        nz = 1.0 if t < HOLD_S else self.nz_target
        return gcmd(0.0 - st["phi"], nz, st)


@dataclass
class M2RollReversal(Maneuver):
    """뱅크 0 → +60° (3 s) → −60° (3 s). Nz 목표 = 1/cosφ (수평 유지 요구). 1 + 6 s."""
    bank_deg: float = 60.0
    name: str = "M2"
    duration_s: float = HOLD_S + 6.0

    def command(self, t, k, st):
        if t < HOLD_S:
            target = 0.0
        elif t < HOLD_S + 3.0:
            target = np.deg2rad(self.bank_deg)
        else:
            target = -np.deg2rad(self.bank_deg)
        nz = 1.0 / max(float(np.cos(st["phi"])), 0.2)
        return gcmd(target - st["phi"], nz, st)


@dataclass
class M3RollingPull(Maneuver):
    """뱅크 0 → 70° 와 동시에 Nz 목표 = nz_target. 1 + 6 s."""
    nz_target: float = 4.0
    bank_deg: float = 70.0
    name: str = "M3"
    duration_s: float = HOLD_S + 6.0

    def command(self, t, k, st):
        if t < HOLD_S:
            return gcmd(0.0 - st["phi"], 1.0, st)
        return gcmd(np.deg2rad(self.bank_deg) - st["phi"], self.nz_target, st)


@dataclass
class M4Multisine(Maneuver):
    """트림 주변 p 또는 q 지령에 0.1~5 Hz 합성파(피크 peak_dps). 1 + 20 s.

    q 축: q_cmd 에 직접 더한다. p 축: shim 이 p_sp ≈ 2·k_att·sin(dphi/2) ≈ k_att·dphi 로
    만들므로 dphi_cmd = p_des / k_att 로 넣는다(소각 근사, k_att = 배치값 4.0).
    """
    axis: str = "q"
    peak_dps: float = 10.0
    freqs_hz: tuple = (0.1, 0.2, 0.35, 0.5, 0.8, 1.2, 1.8, 2.7, 3.8, 5.0)
    k_att: float = 4.0
    name: str = "M4"
    duration_s: float = HOLD_S + 20.0
    _phases: np.ndarray = field(default=None, repr=False)

    def __post_init__(self):
        n = len(self.freqs_hz)
        # 슈뢰더 위상 — 결정론적이며 파고율이 낮다.
        self._phases = np.array([-np.pi * i * (i - 1) / n for i in range(1, n + 1)])

    def signal(self, t: float) -> float:
        x = sum(np.sin(2 * np.pi * f * t + ph) for f, ph in zip(self.freqs_hz, self._phases))
        return np.deg2rad(self.peak_dps) * x / len(self.freqs_hz) * 2.0

    def command(self, t, k, st):
        s = self.signal(t - HOLD_S) if t >= HOLD_S else 0.0
        g = gcmd(0.0 - st["phi"], 1.0, st)
        if self.axis == "q":
            g.q_cmd += s
        else:
            g.dphi_cmd += s / self.k_att
        return g


@dataclass
class Replay(Maneuver):
    """기록된 GuidanceCommand 를 틱마다 그대로 재생 (게이트 G3)."""
    commands: list = field(default_factory=list)
    name: str = "replay"
    per_tick: bool = True

    def __post_init__(self):
        self.duration_s = len(self.commands) * (1.0 / 120.0)

    def command(self, t, k, st):
        return self.commands[k]


@dataclass
class LegacyCornerPull(Maneuver):
    """탐색 단계 run_corner_pull_sweep.run_one 과 같은 기동(게이트 G5 전용).

    80° 뱅크, Nz 목표 = min(g_target, 리미터 순간 봉투), 12 s, 트림 유지 없음.
    """
    g_target: float = 5.0
    g_allowed_fn: object = None
    name: str = "legacy_corner"
    duration_s: float = 12.0

    def window(self):
        return (0.0, self.duration_s)

    def command(self, t, k, st):
        g_cmd = min(self.g_target, self.g_allowed_fn(st["kcas"]))
        return gcmd(np.deg2rad(80.0) - st["phi"], g_cmd, st)
