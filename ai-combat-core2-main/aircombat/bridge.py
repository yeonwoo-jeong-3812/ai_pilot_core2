"""V1 서버 파이프라인 계약 어댑터 — ai-combat-server 가 in-process import 하는 표면.

계약 (ai-combat-server pipeline/match.py 실측, 2026-07-03):
  CompetitionMatch(tree1_file, tree2_file, tree1_name=, tree2_name=, seed=, ...)
      .run(replay_path=None, verbose=False)
  → 결과 속성: winner ∈ {"tree1","tree2","draw"}, condition, total_steps,
    duration_seconds(wall), tree1_health, tree2_health.
  derive_seed(*parts): V1 src/match/seeding.py 와 **값 호환** (SHA-256 앞 4바이트).

판정 규약:
  - 참가자 제출물 오류(파일 없음·문법·미지 노드·doctrine 위반)는 서버 error 가
    아니라 해당 측 DISQUALIFIED — 런타임 트리 예외(엔진 judge ④)와 동일 취급.
  - 판정패(hard_deck/stall/disqualified)는 패자 health 를 0 으로 기록 (D8 득실
    계산 규약 — 엔진 MatchResult 는 실측 HP 를 유지하고, 서버 경계인 여기서 변환).
  - total_steps 는 물리 tick(120Hz) 수 — V1(20Hz env step)과 스케일이 다름.

배포 제외 대상 — 참가자 SDK 빌드에서 이 모듈은 제외한다(기밀은 아니나 서버 전용).
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass

from .engine.factory import load_policy, make_pilot
from .engine.match import Match, OVERTIME_S
from .engine.scenarios import initial_conditions


def derive_seed(*parts) -> int:
    """문자열/정수 조합 → 안정적 32비트 시드. V1 과 값 호환 (기존 매치 재현성)."""
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\x00")
    return int.from_bytes(h.digest()[:4], "big")


@dataclass
class CompetitionResult:
    winner: str            # "tree1" | "tree2" | "draw"
    condition: str         # 엔진 판정 사유 (match.MatchResult.condition + "disqualified")
    total_steps: int       # 물리 tick 수 (120Hz)
    duration_seconds: float  # wall-clock
    tree1_health: float
    tree2_health: float
    # 오버타임 판정 근거 (현장 단판 전용). 서버가 matches.scores 에 실어 참가자에게
    # "왜 졌는지"를 설명한다 — 타이브레이크로 갈린 경기는 이것 없이는 설명 불가.
    overtime: bool = False
    tree1_wez_time: float = 0.0   # 누적 조준 시간 [s] (타이브레이크 ①)
    tree2_wez_time: float = 0.0
    tree1_ata_mean: float = 0.0   # 평균 ATA [deg] (타이브레이크 ②)
    tree2_ata_mean: float = 0.0


_WINNER_MAP = {"blue": "tree1", "red": "tree2", "draw": "draw"}
# 판정패 시 패자 HP 0 기록 대상 (D8). health_zero 는 이미 0, timeout/wall_clock 은 실측 유지.
_FORFEIT_CONDITIONS = ("hard_deck", "stall", "disqualified")


def _ranked_healths(winner: str, condition: str, hp1: float, hp2: float) -> tuple[float, float]:
    """D8 득실 규약: 판정패의 패자 HP → 0. (winner 는 tree1/tree2/draw)"""
    if condition in _FORFEIT_CONDITIONS:
        if winner == "tree1":
            return hp1, 0.0
        if winner == "tree2":
            return 0.0, hp2
    return hp1, hp2


class CompetitionMatch:
    def __init__(self, tree1_file: str, tree2_file: str,
                 tree1_name: str = "tree1", tree2_name: str = "tree2",
                 seed: int | None = None, scenario: str = "headon",
                 duration_s: float = 300.0,
                 config_name: str | None = None, max_steps: int | None = None,
                 match_id: str | None = None, overtime: bool = False):
        # config_name 은 V1 계약 잔재 — 수용만 하고 무시 (시나리오는 scenario 인자).
        # max_steps 는 V1(20Hz env step) 별칭 — duration 으로 환산.
        self.tree1_file = str(tree1_file)
        self.tree2_file = str(tree2_file)
        self.tree1_name = tree1_name
        self.tree2_name = tree2_name
        self.seed = seed
        self.scenario = scenario
        self.match_id = match_id
        # 오버타임은 **현장 단판만** 켠다(서버 pipeline 이 phase 로 판단). 리그·배터리에
        # 켜면 no_contact 쌍방 패의 도주 페이오프 0 설계가 무너진다.
        self.overtime = bool(overtime)
        self.duration_s = (float(max_steps) / 20.0) if max_steps is not None \
            else float(duration_s)

    def _acmi_comments(self) -> str:
        """ACMI 헤더에 새길 매치 식별자. 파일명이 겹치거나 바뀌어도 내용은 자기가
        어느 교전인지 증명한다 — 리플레이 혼선 신고를 파일만 열어 판정하기 위한 것."""
        parts = [f"scenario={self.scenario}", f"seed={self.seed}"]
        if self.match_id:
            parts.insert(0, f"match={self.match_id}")
        commit = os.getenv("AI_COMBAT_ENGINE_COMMIT")
        if commit:
            parts.append(f"engine={commit}")
        return ";".join(parts)

    def run(self, replay_path: str | None = None,
            verbose: bool = False) -> CompetitionResult:
        t0 = time.monotonic()

        # 1) 참가자 과실 도메인 — 제출물 파싱 실패 = 즉시 DQ (교전 없음)
        sides = []
        for tree_file, loser in ((self.tree1_file, "tree1"), (self.tree2_file, "tree2")):
            try:
                sides.append(load_policy(tree_file))
            except Exception as exc:
                if verbose:
                    print(f"[bridge] {loser} 제출물 오류 → DISQUALIFIED: {exc}")
                winner = "tree2" if loser == "tree1" else "tree1"
                hp1, hp2 = _ranked_healths(winner, "disqualified", 100.0, 100.0)
                return CompetitionResult(winner, "disqualified", 0,
                                         time.monotonic() - t0, hp1, hp2)

        # 2) 엔진 도메인 — 이후 예외는 인프라 오류로 전파 (서버가 error 처리)
        ic = initial_conditions(self.scenario, seed=self.seed)
        blue = make_pilot("Blue", ic["blue"], *sides[0], name=self.tree1_name)
        red = make_pilot("Red", ic["red"], *sides[1], name=self.tree2_name)
        m = Match(blue, red, duration_s=self.duration_s, acmi_path=replay_path,
                  log_hz=30.0 if replay_path else 0.0,
                  acmi_comments=self._acmi_comments(),
                  overtime_s=OVERTIME_S if self.overtime else 0.0)
        r = m.run()

        winner = _WINNER_MAP[r.winner]
        hp1, hp2 = _ranked_healths(winner, r.condition, r.hp_blue, r.hp_red)
        if verbose:
            print(f"[bridge] {winner} ({r.condition}) {r.time_s:.1f}s "
                  f"HP {hp1:.1f}/{hp2:.1f}")
        wez = r.wez_time or {"blue": 0.0, "red": 0.0}
        ata = r.ata_mean or {"blue": 0.0, "red": 0.0}
        return CompetitionResult(winner, r.condition, int(round(r.time_s / m.dt)),
                                 time.monotonic() - t0, hp1, hp2,
                                 overtime=r.overtime,
                                 tree1_wez_time=wez["blue"], tree2_wez_time=wez["red"],
                                 tree1_ata_mean=ata["blue"], tree2_ata_mean=ata["red"])
