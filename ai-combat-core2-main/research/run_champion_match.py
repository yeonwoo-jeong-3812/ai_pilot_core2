"""ChampionPilot(core-live FullUnifiedPolicy) 를 core2 엔진 위에서 측정 — gate-2.

확정 규칙(WEZ 30° 계단·거리균일·50HP/s, 300s, both 5계층 INDI)에서 챔프가 이기는가?
core-live 42/42 는 다른(12°·거리감쇠·25HP/s) 게임 해 → 가정 없이 재검증.

산출물(표준 규칙 준수): 페어링별 ACMI + per-tick CSV. (plot 은 F3 후속.)

usage:
  python -m research.run_champion_match                       # 4시나리오 × 기본 대항(energy_fighter)
  python -m research.run_champion_match --red redteams/red_attacker.yaml --scenario headon
  python -m research.run_champion_match --all                 # 4시나리오 × 4대항 전수 + 미러스왑
"""
from __future__ import annotations

import argparse
import csv
import datetime
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# champion128 은 custom_module(임의 파이썬)을 쓴다 — 기본 봉인이므로 리서치 러너에서 명시 허용.
# 명시 AICOMBAT_ALLOW_CUSTOM=0 은 setdefault 라 여전히 우선(대회 서버 정책 존중).
os.environ.setdefault("AICOMBAT_ALLOW_CUSTOM", "1")

from aircombat.fdm.plant import F16Plant
from aircombat.guidance.bfm_guidance import BFMGuidance
from aircombat.guidance.doctrine import Doctrine
from aircombat.geometry.combat_geometry import CombatGeometry
from aircombat.geometry.wez import WeaponEngagementZone
from aircombat.engine.factory import load_policy, make_pilot
from aircombat.engine.match import Match
from aircombat.engine.state import FT_TO_M
from aircombat.engine.scenarios import initial_conditions

from research import champion_core as C
from research.champion_pilot import ChampionPilot

KST = datetime.timezone(datetime.timedelta(hours=9))
REPLAY_DIR = os.path.join(os.path.dirname(__file__), "campaigns")


class MeasMatch(Match):
    """Match + per-tick CSV(표준 replay 규칙). _log_frame 훅에 CSV 행 추가."""

    def __init__(self, *a, csv_path: str | None = None, **kw):
        super().__init__(*a, **kw)
        self.csv_path = csv_path
        self._rows = []

    def _log_frame(self, writer, t, bs, rs, k, n):
        super()._log_frame(writer, t, bs, rs, k, n)
        if self.csv_path is None:
            return
        # BEM 정합(2026-07-17): 분석 CSV 도 채점과 동일 좌표 — ATA=내 기수,
        # AA=상대 종축 기준이라 양측 자세(theta_t/psi_t)를 모두 전달.
        gb = CombatGeometry(bs.pos_ned, rs.pos_ned, bs.vel_ned, rs.vel_ned,
                            bs.phi, bs.theta, bs.psi, rs.theta, rs.psi)
        gr = CombatGeometry(rs.pos_ned, bs.pos_ned, rs.vel_ned, bs.vel_ned,
                            rs.phi, rs.theta, rs.psi, bs.theta, bs.psi)
        wb = CombatGeometry(bs.pos_ned * FT_TO_M, rs.pos_ned * FT_TO_M,
                            bs.vel_ned * FT_TO_M, rs.vel_ned * FT_TO_M,
                            bs.phi, bs.theta, bs.psi, rs.theta, rs.psi)
        wr = CombatGeometry(rs.pos_ned * FT_TO_M, bs.pos_ned * FT_TO_M,
                            rs.vel_ned * FT_TO_M, bs.vel_ned * FT_TO_M,
                            rs.phi, rs.theta, rs.psi, bs.theta, bs.psi)
        rng = float(np.linalg.norm(rs.pos_ned - bs.pos_ned))
        # 비에너지 Es = alt + |V|^2/2g (참속도 vel_ned, ft·s). esret(에너지 보존율) 산출용.
        _G = 32.174
        b_v = float(np.linalg.norm(bs.vel_ned)); r_v = float(np.linalg.norm(rs.vel_ned))
        self._rows.append(dict(
            t=round(t, 3), rng_ft=round(rng, 1),
            b_alt=round(bs.alt_ft, 1), r_alt=round(rs.alt_ft, 1),
            b_kcas=round(bs.kcas, 1), r_kcas=round(rs.kcas, 1),
            b_ata=round(gb.ata_deg(), 2), r_ata=round(gr.ata_deg(), 2),
            b_aa=round(gb.aa_deg(), 2), r_aa=round(gr.aa_deg(), 2),
            b_wez=int(WeaponEngagementZone.is_in_wez(wb)),
            r_wez=int(WeaponEngagementZone.is_in_wez(wr)),
            b_es=round(bs.alt_ft + b_v * b_v / (2.0 * _G), 1),
            r_es=round(rs.alt_ft + r_v * r_v / (2.0 * _G), 1),
            hp_b=round(self.hp["blue"].current_health, 1),
            hp_r=round(self.hp["red"].current_health, 1),
            b_mode=getattr(self.blue, "last_mode", ""),
            b_tactic=getattr(getattr(self.blue, "last_tactic", None), "name", ""),
            r_mode=getattr(self.red, "last_mode", ""),
            r_tactic=getattr(getattr(self.red, "last_tactic", None), "name", ""),
        ))

    def run(self):
        r = super().run()
        if self.csv_path and self._rows:
            os.makedirs(os.path.dirname(self.csv_path) or ".", exist_ok=True)
            with open(self.csv_path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(self._rows[0].keys()))
                w.writeheader(); w.writerows(self._rows)
        return r


def make_champion_pilot(color, ic, clf, name="F-16"):
    plant = F16Plant(dt=1.0 / 120.0)
    plant.set_ic(alt_ft=ic["alt"], vc_kts=ic["kcas"], psi_deg=ic["psi"])
    plant["fcs/throttle-cmd-norm"] = 0.85
    plant.trim()
    return ChampionPilot(plant, clf, color=color, init_pos_ned=tuple(ic["pos"]),
                         guidance=BFMGuidance(doctrine=Doctrine()), name=name)


def run_one(scenario, red_yaml, clf, champion_side="blue", tag=""):
    ic = initial_conditions(scenario)
    os.makedirs(REPLAY_DIR, exist_ok=True)
    red_name = os.path.splitext(os.path.basename(red_yaml))[0]
    stem = f"{tag}champ_vs_{red_name}_{scenario}_{champion_side}"
    acmi = os.path.join(REPLAY_DIR, stem + ".acmi")
    csvp = os.path.join(REPLAY_DIR, stem + ".csv")

    if champion_side == "blue":
        blue = make_champion_pilot("Blue", ic["blue"], clf, name="Champion")
        pol, doc = load_policy(red_yaml)
        red = make_pilot("Red", ic["red"], pol, doc, name=red_name)
    else:
        pol, doc = load_policy(red_yaml)
        blue = make_pilot("Blue", ic["blue"], pol, doc, name=red_name)
        red = make_champion_pilot("Red", ic["red"], clf, name="Champion")

    m = MeasMatch(blue, red, duration_s=300.0, acmi_path=acmi, csv_path=csvp,
                  log_hz=120.0, wall_limit_s=3600.0)  # JSBSim 실시간보다 느려도 거짓 wall_clock 무 방지
    res = m.run()
    # 챔프 관점 결과
    if champion_side == "blue":
        hp_c, hp_o, win_c = res.hp_blue, res.hp_red, res.winner == "blue"
    else:
        hp_c, hp_o, win_c = res.hp_red, res.hp_blue, res.winner == "red"
    outcome = ("격추" if hp_o <= 0 else ("패" if hp_c < hp_o else ("판정승" if hp_c > hp_o else "무"))) \
        if res.winner != "draw" or hp_c != hp_o else "무"
    if res.winner == "draw":
        outcome = "무"
    elif win_c:
        outcome = "격추" if hp_o <= 0 else "판정승"
    else:
        outcome = "패(적격추)" if hp_c <= 0 else "패"
    return dict(scenario=scenario, red=red_name, side=champion_side,
                outcome=outcome, cond=res.condition, t=res.time_s,
                hp_c=hp_c, hp_o=hp_o, acmi=acmi, csv=csvp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--red", default="examples/energy_fighter.yaml")
    ap.add_argument("--scenario", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--mirror", action="store_true", help="진영 스왑 미러도 실행")
    args = ap.parse_args()

    clf = C.load_clf()
    scenarios = (["headon", "perch_offense", "perch_defense", "neutral"]
                 if (args.all or args.scenario is None) else [args.scenario])
    reds = (["examples/energy_fighter.yaml", "redteams/red_attacker.yaml",
             "examples/textbook_headon.yaml", "redteams/red_two_circle.yaml"]
            if args.all else [args.red])
    sides = ["blue", "red"] if (args.mirror or args.all) else ["blue"]

    rows = []
    for red in reds:
        for sc in scenarios:
            for side in sides:
                r = run_one(sc, red, clf, champion_side=side)
                rows.append(r)
                print(f"  [{r['red']:<16} {sc:<14} {side}] {r['outcome']:<10} "
                      f"cond={r['cond']:<12} t={r['t']:5.0f}s  HP {r['hp_c']:5.0f}:{r['hp_o']:<5.0f}",
                      flush=True)

    print("\n" + "=" * 60)
    w = sum(1 for r in rows if r["outcome"] in ("격추", "판정승"))
    d = sum(1 for r in rows if r["outcome"] == "무")
    l = len(rows) - w - d
    print(f"CHAMPION on core2 (확정규칙 300s): {w}승 {d}무 {l}패  / {len(rows)}전")
    print(f"replays: {REPLAY_DIR}")


if __name__ == "__main__":
    raise SystemExit(main())
