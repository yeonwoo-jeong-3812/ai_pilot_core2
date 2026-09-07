"""로컬 리그 실행 + D8 순위표 + 종료 사유 분포 (운영자·밸런스 도구).

**용도**: N 에이전트 총당(round-robin) × 시나리오 배터리 × 진영 스왑 → 순위표·JSON(저울).
ACMI 없음. 단일 매치 복기·디버깅은 `run_match.py`(현미경). SDK 배포엔 run_match 만 포함.

사용:
    python scripts/run_tournament.py                       # examples 3종 풀리그
    python scripts/run_tournament.py --agents a.yaml b.yaml c.yaml
    python scripts/run_tournament.py --json out.json       # 결과 저장
    python scripts/run_tournament.py --gauntlet --agents examples/*.yaml
                                                           # 레드팀 건틀릿(웹 배터리 미러)
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.engine.tournament import (run_league, run_gauntlet, Standing,
                                         _record, LEAGUE_SCENARIOS, BATTERY_SCENARIOS)

EXAMPLES = "examples"
DEFAULT_AGENTS = [f"{EXAMPLES}/starter.yaml", f"{EXAMPLES}/energy_fighter.yaml",
                  f"{EXAMPLES}/textbook_headon.yaml"]
# 건틀릿 기본 대항군 — 웹 DB(is_red_team=true)와 동일해야 미러가 성립한다.
# redteams/*.yaml glob 은 폐기된 red(allround·pressure)와 홀드아웃(red_knife)까지
# 잡아 실제 배터리와 어긋나므로 명시 목록으로 고정한다. DB 변경 시 함께 갱신.
# 2026-08-18 교체: attacker·textbook·two_circle 는 examples 복사본이라 SDK 로 배포돼
# 참가자가 파일을 갖고 있었다(과적합). 미공개 roster 아키타입 3종으로 갈았고, 참가자
# 5팀 패널 760경기 측정에서 경기당 변별력(단판 ICC)이 0.321 → 0.454 로 올랐다.
# 2026-08-28 교체: red_energy → red_falco(같은 날 red_prime 으로 개명). 운영 DB 실측(5종 공존 창 824경기)에서
# red_energy 가 레드승률 11.9% 로 최저였다(무접촉 19건도 최다).
BATTERY_REDS = ("red_adaptive", "red_extender", "red_phangman", "red_prime",
                "red_reactive")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", nargs="+", default=DEFAULT_AGENTS,
                    help="에이전트 YAML 경로들 (기본: examples 3종)")
    ap.add_argument("--scenarios", nargs="+", default=None,
                    help="기본: 리그 LEAGUE_SCENARIOS(3종) / 건틀릿 BATTERY_SCENARIOS(4종)")
    ap.add_argument("--salt", default="", help="시드 salt (라운드 구분)")
    ap.add_argument("--json", default=None, help="결과 JSON 저장 경로")
    ap.add_argument("--stream", action="store_true",
                    help="경기별 결과를 한 줄씩 실시간 출력")
    ap.add_argument("--gauntlet", action="store_true",
                    help="레드팀 건틀릿(웹 배터리 미러): 참가자 각각이 --reds 와만 교전")
    ap.add_argument("--reds", nargs="+", default=None,
                    help="건틀릿 대항군 YAML (기본: 웹 배터리 5종 = BATTERY_REDS)")
    args = ap.parse_args()

    if args.scenarios is None:
        args.scenarios = list(BATTERY_SCENARIOS if args.gauntlet else LEAGUE_SCENARIOS)
    agents = {os.path.splitext(os.path.basename(p))[0]: p for p in args.agents}

    on_game = None
    if args.stream:
        n = [0]
        def on_game(g):
            n[0] += 1
            print(f"[{n[0]:>3}] {g.scenario:<13} {g.blue:>16} vs {g.red:<16} "
                  f"→ {g.winner:<16} ({g.condition}) HP {g.hp_blue:.0f}/{g.hp_red:.0f}",
                  flush=True)

    if args.gauntlet:
        red_paths = args.reds or [f"redteams/{n}.yaml" for n in BATTERY_REDS]
        reds = {os.path.splitext(os.path.basename(p))[0]: p for p in red_paths}
        standings = {n: Standing(n, i) for i, n in enumerate(list(agents) + list(reds))}
        games = []
        for cn, cp in agents.items():
            for g in run_gauntlet(cn, cp, reds, tuple(args.scenarios)):
                _record(standings, g)
                games.append(g)
                if on_game:
                    on_game(g)
        ranked = sorted((standings[n] for n in agents),
                        key=lambda s: s.rank_key(), reverse=True)
        print(f"\n건틀릿(배터리 미러): 참가자 {len(agents)} × 대항군 {len(reds)}"
              f"{sorted(reds)} × 시나리오 {list(args.scenarios)} × salt 2 = {len(games)}경기\n")
    else:
        ranked, games = run_league(agents, tuple(args.scenarios), args.salt, on_game)
        print(f"\n리그: {len(agents)}팀 × 시나리오 {args.scenarios} × 스왑 = {len(games)}경기\n")

    label = "참가자" if args.gauntlet else "팀"
    print(f"{'#':>2} {label:<16}{'승점':>4}{'승':>3}{'무':>3}{'패':>3}"
          f"{'격추승':>6}{'평균HP득실':>10}")
    print("-" * 52)
    for i, s in enumerate(ranked, 1):
        print(f"{i:>2} {s.name:<16}{s.pts:>4}{s.wins:>3}{s.draws:>3}{s.losses:>3}"
              f"{s.kill_wins:>6}{s.avg_hp_diff:>+10.1f}")

    conds = collections.Counter(g.condition for g in games)
    print("\n종료 사유 분포:", dict(conds))

    if args.json:
        payload = {
            "standings": [{"name": s.name, "pts": s.pts, "wins": s.wins,
                           "draws": s.draws, "losses": s.losses,
                           "kill_wins": s.kill_wins,
                           "avg_hp_diff": round(s.avg_hp_diff, 2)} for s in ranked],
            "conditions": dict(conds),
            "games": [vars(g) for g in games],
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\n저장: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
