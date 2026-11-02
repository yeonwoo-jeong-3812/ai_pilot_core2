"""교전 기하 관측기 (읽기 전용). 엔진 상태를 바꾸지 않는다.

origin/YEOP 의 ai-combat-core2-main/research/indi/combat.py (CombatMonitor.sample/summary)에서
기하 지표 4개만 같은 정의·같은 상수로 옮겼다. INDI 입력 가로채기(hook_indi)와 추종 지표는 뺐다.

  off_frac    공세 시간 비율: ATA_me < 60° 이고 ATA_foe > 120°
  def_frac    수세 시간 비율: ATA_me > 120° 이고 ATA_foe < 60°
  e_adv_ft    비에너지 우위 평균 [ft]: (h + V²/2g)_me − (h + V²/2g)_foe
  t_first_wez 최초 WEZ 진입 시각 [s]: ATA_me < 30° 이고 거리 500–3,000 ft. 없으면 None
  node_frac   me 트리가 실행한 action 노드별 시간 비율 (me._cmd.name, dwell 히스테리시스 뒤 실제 명령). bt 추가분
  node_frac_red  foe 트리의 같은 기록 (foe._cmd.name). bt 추가분

표본: me.step_physics() 직후 6틱마다(20 Hz). 원본과 같이 me 의 물리 스텝 뒤, foe 의 물리 스텝 전에 잰다.
"""
from __future__ import annotations

import json
from collections import Counter

import numpy as np

from aircombat.geometry.combat_geometry import CombatGeometry

G = 32.174
GEO_EVERY = 6            # 120 Hz / 6 = 20 Hz


class CombatMonitor:
    def __init__(self, me, foe, dt: float = 1.0 / 120.0):
        self.me, self.foe, self.dt = me, foe, dt
        self.geo = []          # (t, ata_me, ata_foe, range_ft, e_adv)
        self.nodes = Counter()  # action 노드 이름 → 표본 수
        self.foe_nodes = Counter()
        self.k = 0

    def sample(self):
        self.k += 1
        if self.k % GEO_EVERY:
            return
        a, b = self.me.state(), self.foe.state()
        self.nodes[getattr(self.me._cmd, "name", None) or "none"] += 1
        self.foe_nodes[getattr(getattr(self.foe, "_cmd", None), "name", None) or "none"] += 1
        geom_a = CombatGeometry(a.pos_ned, b.pos_ned, a.vel_ned, b.vel_ned, a.phi, a.theta, a.psi, b.theta, b.psi)
        geom_b = CombatGeometry(b.pos_ned, a.pos_ned, b.vel_ned, a.vel_ned, b.phi, b.theta, b.psi, a.theta, a.psi)
        rng = float(np.linalg.norm(b.pos_ned - a.pos_ned))
        e_adv = (a.alt_ft + a.v_fps ** 2 / (2 * G)) - (b.alt_ft + b.v_fps ** 2 / (2 * G))
        self.geo.append((self.k * self.dt, geom_a.ata_deg(), geom_b.ata_deg(), rng, e_adv))

    def summary(self) -> dict:
        if not self.geo:
            return dict(off_frac=None, def_frac=None, e_adv_ft=None, t_first_wez=None, node_frac=None, node_frac_red=None)
        t, ata, ata_f, rng, eadv = np.array(self.geo).T
        wez = (rng >= 500.0) & (rng <= 3000.0) & (ata < 30.0)
        return dict(
            off_frac=float(np.mean((ata < 60.0) & (ata_f > 120.0))),
            def_frac=float(np.mean((ata > 120.0) & (ata_f < 60.0))),
            e_adv_ft=float(eadv.mean()),
            t_first_wez=float(t[np.argmax(wez)]) if wez.any() else None,
            node_frac=_frac(self.nodes, len(self.geo)), node_frac_red=_frac(self.foe_nodes, len(self.geo)))


def _frac(c: Counter, n: int) -> str:
    return json.dumps({k: round(v / n, 4) for k, v in sorted(c.items())})


def attach(me, foe, dt: float = 1.0 / 120.0) -> CombatMonitor:
    """me.step_physics 뒤에 기하 표본을 붙인다. 이 인스턴스의 메서드만 감싸고, 읽기만 한다."""
    mon = CombatMonitor(me, foe, dt)
    step = me.step_physics

    def step_w():
        step()
        mon.sample()
    me.step_physics = step_w
    return mon
