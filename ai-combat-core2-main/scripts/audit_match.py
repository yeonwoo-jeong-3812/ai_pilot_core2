"""매치 감사 — 기록된 입력(에이전트 쌍 + 시나리오 + 시드)을 재실행해 결과 재현 확인.

의심 매치를 운영자가 동일 조건으로 2회 실행하여 결정론(같은 입력→같은 결과)을 검증.
불일치는 엔진 결함 신호. 사용:
    python scripts/audit_match.py blue.yaml red.yaml --scenario headon --seed 12345
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.bridge import CompetitionMatch
from aircombat.engine.scenarios import SCENARIOS


def _run(blue: str, red: str, scenario: str, seed: int) -> tuple:
    r = CompetitionMatch(tree1_file=blue, tree2_file=red,
                         scenario=scenario, seed=seed).run()
    return (r.winner, r.condition, r.total_steps,
            round(r.tree1_health, 9), round(r.tree2_health, 9))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("blue")
    ap.add_argument("red")
    ap.add_argument("--scenario", default="headon", choices=list(SCENARIOS))
    ap.add_argument("--seed", type=int, required=True)
    args = ap.parse_args()

    a = _run(args.blue, args.red, args.scenario, args.seed)
    b = _run(args.blue, args.red, args.scenario, args.seed)
    print(f"입력: {args.blue} vs {args.red}  scenario={args.scenario} seed={args.seed}")
    print(f"실행1: winner={a[0]} cond={a[1]} steps={a[2]} HP={a[3]:.3f}/{a[4]:.3f}")
    print(f"실행2: winner={b[0]} cond={b[1]} steps={b[2]} HP={b[3]:.3f}/{b[4]:.3f}")
    if a == b:
        print("VERDICT: PASS — 결정론 재현됨")
        return 0
    print("VERDICT: FAIL — 재현 불일치 (엔진 결함)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
