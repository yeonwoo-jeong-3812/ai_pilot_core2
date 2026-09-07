"""TranscribedPolicy 구동 파일럿 + 32경기 outcome 측정.

목적: off 인코딩 선택(exact 수치argmax vs 설명용 하드-사다리)이 경기 outcome 을 바꾸는지(지표먼저).
  · exact 모드: 결정 틱-동일(0/18446 증명) → outcome = 골든 22-0-10 (구성상 보장, 확인만).
  · ladder 모드: σ-전이 6틱 상이 → outcome delta 측정.
--off {exact,ladder}. 기본 exact.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from research import champion_core as C
from research.champion_pilot import ChampionPilot, tactic_to_command
from research.transcribe import TranscribedPolicy
from research.run_champion_match import MeasMatch, REPLAY_DIR

from aircombat.engine.factory import load_policy, make_pilot
from aircombat.engine.scenarios import initial_conditions


class TranscribedPilot(ChampionPilot):
    def __init__(self, plant, clf, off_mode="exact",
                 deck_guard_ft=0.0, deck_sink_fps=0.0, **kw):
        super().__init__(plant, clf, **kw)
        self.champion = TranscribedPolicy(clf, off_mode=off_mode,
                                          deck_guard_ft=deck_guard_ft,
                                          deck_sink_fps=deck_sink_fps)

    def tactic_step(self, foe) -> None:
        if self._l1_count % self.l1_ratio == 0:
            o = C.reconstruct_obs(self.state(), foe)
            mode, tac = self.champion.decide(o)
            self.last_mode, self.last_tactic = mode, tac
            self._cmd = tactic_to_command(tac, ego_alt_ft=o.ego_alt_ft, enm_alt_ft=o.enm_alt_ft)
        self._l1_count += 1


def make_pilot_t(color, ic, clf, off_mode):
    from aircombat.fdm.plant import F16Plant
    from aircombat.guidance.bfm_guidance import BFMGuidance
    from aircombat.guidance.doctrine import Doctrine
    plant = F16Plant(dt=1.0 / 120.0)
    plant.set_ic(alt_ft=ic["alt"], vc_kts=ic["kcas"], psi_deg=ic["psi"])
    plant["fcs/throttle-cmd-norm"] = 0.85
    plant.trim()
    return TranscribedPilot(plant, clf, off_mode=off_mode, color=color,
                            init_pos_ned=tuple(ic["pos"]),
                            guidance=BFMGuidance(doctrine=Doctrine()), name="Transcribed")


def run_one(scenario, red_yaml, clf, side, off_mode):
    ic = initial_conditions(scenario)
    red_name = os.path.splitext(os.path.basename(red_yaml))[0]
    if side == "blue":
        blue = make_pilot_t("Blue", ic["blue"], clf, off_mode)
        pol, doc = load_policy(red_yaml)
        red = make_pilot("Red", ic["red"], pol, doc, name=red_name)
    else:
        pol, doc = load_policy(red_yaml)
        blue = make_pilot("Blue", ic["blue"], pol, doc, name=red_name)
        red = make_pilot_t("Red", ic["red"], clf, off_mode)
    m = MeasMatch(blue, red, duration_s=300.0, acmi_path=None, csv_path=None,
                  log_hz=30.0, wall_limit_s=3600.0)
    res = m.run()
    win = (res.winner == side)
    loss = (res.winner is not None and res.winner != side)
    return res, win, loss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--off", choices=["exact", "ladder"], default="exact")
    args = ap.parse_args()

    clf = C.load_clf()
    scenarios = ["headon", "perch_offense", "perch_defense", "neutral"]
    reds = ["examples/energy_fighter.yaml", "redteams/red_attacker.yaml",
            "examples/textbook_headon.yaml", "redteams/red_two_circle.yaml"]
    W = L = D = 0
    rows = []
    for red in reds:
        for sc in scenarios:
            for side in ["blue", "red"]:
                res, win, loss = run_one(sc, red, clf, side, args.off)
                W += win; L += loss; D += (not win and not loss)
                rn = os.path.splitext(os.path.basename(red))[0]
                tag = "W" if win else ("L" if loss else "D")
                rows.append((rn, sc, side, tag, res.condition, res.time_s))
                print(f"  [{rn:<16} {sc:<14} {side}] {tag}  cond={res.condition} t={res.time_s:.0f}s", flush=True)
    print(f"\noff={args.off}  전적 {W}승 {D}무 {L}패  (=W-D-L)")


if __name__ == "__main__":
    raise SystemExit(main())
