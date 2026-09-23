"""F-16 물리 한계 준수 기록기 — 매치·벤치 공용 (paper.md §7-D).

기준 봉투는 교범 해석(envelope="manual", paper.md §6)으로 **고정** — 파일럿이 어떤
리미터로 비행하든 같은 잣대로 잰다. 결정 경로 무영향(읽기 전용).

    mon = LimitMonitor(plant)
    ...매 물리 틱 후 mon.sample()...
    mon.summary()   → dict (JSON 직렬화 가능)
"""
from __future__ import annotations

import numpy as np

from aircombat.control.limiter import CombinedLimiter, LimiterConfig

G_STRUCT_MAX = 9.0
G_STRUCT_MIN = -3.0
ROLL_MAX_DPS = 220.0          # LimiterConfig.p_max_dps (명령 상한) — 달성값 감시
ELEV_PULL_STOP = -1.0         # INDI 클립 하한 (JSBSim: 음수 = 기수 올림)
ELEV_PUSH_STOP = 0.44         # f16.xml fcs/elevator-cmd-limiter 상한
ONSET_WIN_S = 0.1             # G onset 창 — 틱 단위 차분은 잡음을 onset 으로 오인
# 실격 기준: 구조한계 초과, 또는 봉투를 ENV_TOL_G 넘게 초과. 리미터는 명령을 자르지만
# 달성 G 는 동역학 오버슈트로 잠깐 넘을 수 있어 공차를 둔다. 기준 제어기 실측 후 확정.
ENV_TOL_G = 0.5


class LimitMonitor:
    def __init__(self, plant, dt: float = 1.0 / 120.0):
        self.p = plant
        self.dt = float(dt)
        self.env = CombinedLimiter(LimiterConfig(envelope="manual"))
        self._nz = []
        self._rows = []   # (nz, g_hi, g_lo, alpha_deg, |p| dps, elev_cmd)

    def sample(self) -> None:
        p = self.p
        nz = p["accelerations/Nz"]
        kcas = p["velocities/vc-kts"]
        self._rows.append((nz, self.env.max_load_factor(kcas), self.env.min_load_factor(kcas),
                           p["aero/alpha-deg"], abs(np.degrees(p["velocities/p-rad_sec"])),
                           p["fcs/elevator-cmd-norm"]))

    def summary(self) -> dict:
        if not self._rows:
            return {}
        a = np.array(self._rows)
        nz, hi, lo, alpha, pdps, elev = a.T
        over = np.maximum(nz - hi, 0.0)          # 양의 봉투 초과 [G]
        under = np.maximum(lo - nz, 0.0)         # 음의 봉투 초과 [G]
        w = max(1, round(ONSET_WIN_S / self.dt))
        onset = np.abs(nz[w:] - nz[:-w]) / (w * self.dt) if len(nz) > w else np.zeros(1)
        struct = bool(nz.max() > G_STRUCT_MAX or nz.min() < G_STRUCT_MIN)
        env_max = float(max(over.max(), under.max()))
        return dict(
            nz_max=float(nz.max()), nz_min=float(nz.min()),
            env_excess_max=env_max,
            env_excess_int=float((over + under).sum() * self.dt),     # [G·s] — E4 비용 항
            struct_violation=struct,
            onset_max=float(onset.max()),                             # [G/s]
            alpha_max=float(alpha.max()),
            roll_rate_max=float(pdps.max()),
            roll_violation=bool(pdps.max() > ROLL_MAX_DPS),
            elev_sat_frac=float(np.mean((elev <= ELEV_PULL_STOP + 1e-3)
                                        | (elev >= ELEV_PUSH_STOP - 1e-3))),
            disqualified=bool(struct or env_max > ENV_TOL_G),
        )


def attach(pilot, dt: float = 1.0 / 120.0) -> LimitMonitor:
    """Pilot 의 물리 스텝 뒤에 기록을 끼운다 (엔진 무수정)."""
    mon = LimitMonitor(pilot.plant, dt)
    step = pilot.step_physics

    def stepped():
        step()
        mon.sample()
    pilot.step_physics = stepped
    return mon
