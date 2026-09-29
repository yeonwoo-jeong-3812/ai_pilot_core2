"""교전 과정 지표 기록기 — 승패가 아니라 INDI 튜닝이 교전 '과정'에 주는 영향 (읽기 전용, 엔진 무수정).

명령 추종 (INDI 가 받은 한계 통과 후 각속도 명령 vs JSBSim 참값 각속도, 120 Hz)
  rms_p, rms_q       [deg/s]  추종 RMSE
  lag_p_ms, lag_q_ms [ms]     실효 응답 지연 = 명령·응답 상호상관 최대 시간차 (0–500 ms) — "명령을 따라가는 시간"
  g_ratio                     요구 G ≥ 3 구간의 달성 Nz / L2 목표 G 중앙값 — G 실현률
  act_ail, act_elev           조종면 활동량 (평균 |Δu|)
교전 기하 (20 Hz 표본, 기수축 기준 ATA — 매치 판정과 동일 정의)
  t_first_wez, t_first_gun [s]  최초 WEZ(ATA<30°, 500–3,000 ft) / 조준해(ATA<2°, 같은 거리) 진입 시각, 없으면 None
  wez_s, gun_s             [s]  체류 시간
  off_frac, def_frac            공세(ATA_me<60° ∧ ATA_foe>120°) / 수세(반대) 시간 비율
  e_adv_ft                 [ft] 비에너지 우위 평균 (h + V²/2g, 자기 − 상대)
"""
from __future__ import annotations

import numpy as np

from aircombat.geometry.combat_geometry import CombatGeometry

G = 32.174
GEO_EVERY = 6            # 120 Hz / 6 = 20 Hz
MAX_LAG = 60             # 500 ms @ 120 Hz


class CombatMonitor:
    def __init__(self, me, foe, dt: float = 1.0 / 120.0):
        self.me, self.foe, self.dt = me, foe, dt
        self.sp, self.w, self.u, self.g = [], [], [], []
        self.geo = []          # (t, ata_me, ata_foe, range_ft, e_adv)
        self.k = 0

    # INDI 입력 가로채기 — Pilot.setup 이 indi 를 만든 뒤 호출
    def hook_indi(self):
        indi, p = self.me.indi, self.me.plant
        update = indi.update

        def wrapped(omega, omega_sp, qbar, ang_accel=None, omega_sp_dot=None):
            u = update(omega, omega_sp, qbar, ang_accel=ang_accel, omega_sp_dot=omega_sp_dot)
            self.sp.append(np.asarray(omega_sp, float)[:2].copy())
            self.w.append((p["velocities/p-rad_sec"], p["velocities/q-rad_sec"]))
            self.u.append((u[0], u[1]))
            gc = self.me._gc
            self.g.append((gc.g_target if gc is not None else 0.0, p["accelerations/Nz"]))
            return u
        indi.update = wrapped

    def sample(self):
        self.k += 1
        if self.k % GEO_EVERY:
            return
        a, b = self.me.state(), self.foe.state()
        geom_a = CombatGeometry(a.pos_ned, b.pos_ned, a.vel_ned, b.vel_ned, a.phi, a.theta, a.psi, b.theta, b.psi)
        geom_b = CombatGeometry(b.pos_ned, a.pos_ned, b.vel_ned, a.vel_ned, b.phi, b.theta, b.psi, a.theta, a.psi)
        rng = float(np.linalg.norm(b.pos_ned - a.pos_ned))
        e_adv = (a.alt_ft + a.v_fps ** 2 / (2 * G)) - (b.alt_ft + b.v_fps ** 2 / (2 * G))
        self.geo.append((self.k * self.dt, geom_a.ata_deg(), geom_b.ata_deg(), rng, e_adv))

    @staticmethod
    def _lag_ms(sp: np.ndarray, w: np.ndarray, dt: float) -> float:
        x, y = sp - sp.mean(), w - w.mean()
        if x.std() < 1e-9 or y.std() < 1e-9:
            return float("nan")
        n = len(x)
        c = [np.dot(x[:n - k], y[k:]) for k in range(MAX_LAG + 1)]
        return float(np.argmax(c) * dt * 1000.0)

    def summary(self) -> dict:
        if not self.sp or not self.geo:
            return {}
        sp, w, u = np.array(self.sp), np.array(self.w), np.array(self.u)
        e = np.degrees(sp - w)
        gt, nz = np.array(self.g).T
        pull = gt >= 3.0
        t, ata, ata_f, rng, eadv = np.array(self.geo).T
        in_rng = (rng >= 500.0) & (rng <= 3000.0)
        wez, gun = in_rng & (ata < 30.0), in_rng & (ata < 2.0)
        dtg = GEO_EVERY * self.dt
        first = lambda m: float(t[np.argmax(m)]) if m.any() else None
        return dict(
            rms_p=float(np.sqrt(np.mean(e[:, 0] ** 2))), rms_q=float(np.sqrt(np.mean(e[:, 1] ** 2))),
            lag_p_ms=self._lag_ms(sp[:, 0], w[:, 0], self.dt), lag_q_ms=self._lag_ms(sp[:, 1], w[:, 1], self.dt),
            g_ratio=float(np.median(nz[pull] / gt[pull])) if pull.any() else None,
            act_ail=float(np.abs(np.diff(u[:, 0])).mean()), act_elev=float(np.abs(np.diff(u[:, 1])).mean()),
            t_first_wez=first(wez), t_first_gun=first(gun),
            wez_s=float(wez.sum() * dtg), gun_s=float(gun.sum() * dtg),
            off_frac=float(np.mean((ata < 60.0) & (ata_f > 120.0))),
            def_frac=float(np.mean((ata > 120.0) & (ata_f < 60.0))),
            e_adv_ft=float(eadv.mean()))


def attach(me, foe, dt: float = 1.0 / 120.0) -> CombatMonitor:
    """setup(→ INDI 생성) 뒤 INDI 입력을, 물리 스텝 뒤 기하를 기록."""
    mon = CombatMonitor(me, foe, dt)
    setup, step = me.setup, me.step_physics

    def setup_w():
        r = setup()
        mon.hook_indi()
        return r

    def step_w():
        step()
        mon.sample()
    me.setup, me.step_physics = setup_w, step_w
    return mon
