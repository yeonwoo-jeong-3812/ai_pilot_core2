"""INDI 연구 하네스 — 1경기 실행 (bridge.CompetitionMatch 의 연구판).

서버 계약(bridge·tournament)은 건드리지 않고, 여기서만 측별 INDIConfig 와
G 봉투(paper.md §0: 교범 해석 "manual")를 주입한다. 봉투는 양측 동일.

    python research/indi/runner.py                       # 스모크: 기준 vs 기준
    python research/indi/runner.py --k_q 14 --k_ff 1     # blue 만 변경
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from aircombat.control.indi import INDIConfig
from aircombat.engine.factory import load_policy, make_pilot
from aircombat.engine.match import Match
from aircombat.engine.scenarios import initial_conditions

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENVELOPE = "manual"   # 연구 확정 기준 (paper.md §0)


def play(blue_yaml: str, red_yaml: str, scenario: str = "headon", seed: int | None = None,
         blue_cfg: INDIConfig | None = None, red_cfg: INDIConfig | None = None,
         duration_s: float = 300.0, envelope: str = ENVELOPE) -> dict:
    """1경기 → 결과 dict (JSON 직렬화 가능). 참가자 DQ 개념 없음 — 예외는 그대로 전파."""
    ic = initial_conditions(scenario, seed=seed)
    blue = make_pilot("Blue", ic["blue"], *load_policy(blue_yaml),
                      indi_cfg=blue_cfg, envelope=envelope)
    red = make_pilot("Red", ic["red"], *load_policy(red_yaml),
                     indi_cfg=red_cfg, envelope=envelope)
    r = Match(blue, red, duration_s=duration_s, log_hz=0.0).run()
    wez = r.wez_time or {"blue": 0.0, "red": 0.0}
    ata = r.ata_mean or {"blue": 0.0, "red": 0.0}
    return dict(scenario=scenario, seed=seed, envelope=envelope,
                blue_cfg=dataclasses.asdict(blue_cfg or INDIConfig()),
                red_cfg=dataclasses.asdict(red_cfg or INDIConfig()),
                winner=r.winner, condition=r.condition, time_s=r.time_s,
                hp_blue=r.hp_blue, hp_red=r.hp_red,
                wez_blue=wez["blue"], wez_red=wez["red"],
                ata_blue=ata["blue"], ata_red=ata["red"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blue", default=os.path.join(ROOT, "examples", "energy_fighter.yaml"))
    ap.add_argument("--red", default=os.path.join(ROOT, "redteams", "red_textbook.yaml"))
    ap.add_argument("--scenario", default="headon")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--duration", type=float, default=300.0)
    ap.add_argument("--envelope", default=ENVELOPE, choices=("platform", "manual"))
    for f in dataclasses.fields(INDIConfig):       # blue 측 노브: --k_p 12 ...
        ap.add_argument(f"--{f.name}", type=float, default=f.default)
    a = ap.parse_args()
    cfg = INDIConfig(**{f.name: getattr(a, f.name) for f in dataclasses.fields(INDIConfig)})
    print(play(a.blue, a.red, a.scenario, a.seed, blue_cfg=cfg,
               duration_s=a.duration, envelope=a.envelope))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
