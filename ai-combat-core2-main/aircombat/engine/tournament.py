"""로컬 리그·랭킹 — round-robin / gauntlet + 진영 스왑 미러 + D8 순위.

매치 실행은 bridge.CompetitionMatch 재사용 — 서버와 동일한 판정·판정패 HP 0 규약.
따라서 로컬 리그 순위 = 서버 순위 규칙(D8). 운영자 도구(배포 제외).

순위(예선): 승점(3/1/0) → 평균 HP 득실차 → 격추승 수 → 팀 등록 순서(결정론 폴백).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from ..bridge import CompetitionMatch, derive_seed

# 배터리(웹 평가·건틀릿) 시나리오 — 참가자 진영이 blue 고정이라 perch 의 공/수가
# 진짜 다른 역할이다. server pipeline/match.py BATTERY_SCENARIOS 와 단일 진실.
BATTERY_SCENARIOS = ("headon", "perch_offense", "perch_defense", "neutral")

# 리그 시나리오 — round-robin 은 이미 ((a,b),(b,a)) 스왑 미러라 perch_defense 의
# 역할 커버리지가 perch_offense 와 완전히 겹친다(IC 자체가 진영 스왑). 제거해도
# 최종 순위 rho +0.98, 격추 비율 39%→38% 로 보존되면서 42경기(25%)가 준다
# (2026-08-01 실측, examples 7종 210경기).
LEAGUE_SCENARIOS = ("headon", "perch_offense", "neutral")


@dataclass
class Standing:
    name: str
    order: int                 # 등록 순서 (결정론 타이브레이크)
    wins: int = 0
    draws: int = 0
    losses: int = 0
    kill_wins: int = 0         # health_zero 로 이긴 경기 (격추승)
    hp_diff_total: float = 0.0
    games: int = 0

    @property
    def pts(self) -> int:
        return self.wins * 3 + self.draws

    @property
    def avg_hp_diff(self) -> float:
        return self.hp_diff_total / self.games if self.games else 0.0

    def rank_key(self) -> tuple:
        # 내림차순 정렬용 — 앞일수록 상위 (order 만 오름차순이라 부호 반전)
        return (self.pts, self.avg_hp_diff, self.kill_wins, -self.order)


@dataclass
class GameResult:
    scenario: str
    blue: str
    red: str
    winner: str                # 팀 이름 또는 "draw"
    condition: str
    hp_blue: float
    hp_red: float


def play_game(name_a: str, path_a: str, name_b: str, path_b: str,
              scenario: str, seed: int) -> GameResult:
    """A=blue, B=red 로 1경기. (스왑 미러는 호출자가 A/B 를 바꿔 다시 부른다.)"""
    r = CompetitionMatch(tree1_file=path_a, tree2_file=path_b,
                         tree1_name=name_a, tree2_name=name_b,
                         scenario=scenario, seed=seed).run()
    winner = {"tree1": name_a, "tree2": name_b, "draw": "draw"}[r.winner]
    return GameResult(scenario, name_a, name_b, winner, r.condition,
                      r.tree1_health, r.tree2_health)


def _record(standings: dict[str, Standing], g: GameResult) -> None:
    sb, sr = standings[g.blue], standings[g.red]
    sb.games += 1
    sr.games += 1
    sb.hp_diff_total += g.hp_blue - g.hp_red
    sr.hp_diff_total += g.hp_red - g.hp_blue
    if g.condition == "no_contact":
        # 무접촉 타임아웃 = 쌍방 패(0점). 무승부(1점)보다 낮아야 도주가 이득이 아니다.
        sb.losses += 1
        sr.losses += 1
    elif g.winner == "draw":
        sb.draws += 1
        sr.draws += 1
    else:
        win, lose = (sb, sr) if g.winner == g.blue else (sr, sb)
        win.wins += 1
        lose.losses += 1
        if g.condition == "health_zero":
            win.kill_wins += 1


def run_league(agents: dict[str, str], scenarios=LEAGUE_SCENARIOS,
               seed_salt: str = "",
               on_game=None) -> tuple[list[Standing], list[GameResult]]:
    """round-robin + 진영 스왑 미러. agents: {name: yaml_path} (삽입 순서 = 등록 순서).

    각 (대진, 시나리오)는 스왑으로 2경기. 시드는 (시나리오, salt)에서 유도 —
    전 대진이 시나리오별 동일 IC (공정), match id 무관(재현성).
    """
    standings = {name: Standing(name, i) for i, name in enumerate(agents)}
    games: list[GameResult] = []
    for a, b in itertools.combinations(agents, 2):
        for scen in scenarios:
            seed = derive_seed(scen, seed_salt)
            for x, y in ((a, b), (b, a)):        # 스왑 미러
                g = play_game(x, agents[x], y, agents[y], scen, seed)
                _record(standings, g)
                games.append(g)
                if on_game:
                    on_game(g)
    ranked = sorted(standings.values(), key=lambda s: s.rank_key(), reverse=True)
    return ranked, games


def run_gauntlet(agent_name: str, agent_path: str, red_team: dict[str, str],
                 scenarios=BATTERY_SCENARIOS,
                 salts=("battery-v1", "battery-v1b")) -> list[GameResult]:
    """web 평가 배터리 미러 — 로컬에서 리더보드 재현·디버깅용.

    server pipeline/match.py BATTERY 와 동일 규칙:
      · 시드 = derive_seed(salt, scen, red_slug) — red별로 다른 IC
      · 참가자 진영 고정(항상 blue/tree1), 스왑 없음
      · red × 시나리오 × 소금 = 경기 수 (현행 5×4×2 = 40)
    red_team 의 **키는 web red 팀 slug** 여야 시드가 서버와 일치한다(예: 'red_attacker').
    대항군 기본 목록은 run_tournament.BATTERY_REDS — 웹 DB 4종과 동일하게 유지한다
    (홀드아웃 red_knife 는 DB 미등록이라 애초에 포함되지 않는다).
    salts 기본값은 match.py BATTERY_SALTS 와 맞춘다 — 서버 변경 시 함께 갱신.
    """
    games: list[GameResult] = []
    for red_name, red_path in red_team.items():
        for scen in scenarios:
            for salt in salts:
                seed = derive_seed(salt, scen, red_name)
                games.append(play_game(agent_name, agent_path, red_name, red_path, scen, seed))
    return games
