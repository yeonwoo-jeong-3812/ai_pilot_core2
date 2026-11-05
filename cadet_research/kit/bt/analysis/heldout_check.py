"""heldout 상대 묶음 합격 점검 (opponent_patch_check 와 같은 기준). games.csv 는 읽기만 한다.

  python bt/run_bt.py bt/thetas/baseline.csv --prefix bt-smoke --opponents heldout     # 기준 θ × 48경기
  python bt/analysis/heldout_check.py                                                  # → bt/out/heldout_check.md

기준 (상대 행동만): 상대 하드덱 비율 전체 ≤ 5%, 상대별 ≤ 10%, 상대 고도 회복 노드 실행 비율 평균 ≤ 20%.
회복 노드 = climb (A1·A3·B1, 보정 노드) / crash_recovery (red_prime 원본의 최우선 노드).
"""
from __future__ import annotations

import collections as C
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BT)
import run_bt  # noqa: E402
from io_utils import read_games  # noqa: E402

GAMES = os.path.join(BT, "out", "bt-smoke-heldout", "games.csv")
REPORT = os.path.join(BT, "out", "heldout_check.md")
RECOVERY = ("climb", "crash_recovery")
LIM_ALL, LIM_OPP, LIM_REC = 0.05, 0.10, 0.20
MODES = ("shootdown", "opp_hard_deck", "opp_stall", "judge", "other")


def main():
    d = read_games(GAMES)
    assert set(d.opponent_set) == {"heldout"} and len(d) == 48, (set(d.opponent_set), len(d))
    d["opp_hd"] = (d.end_reason == "hard_deck") & (d.winner == "blue")
    d["blue_hd"] = (d.end_reason == "hard_deck") & (d.winner == "red")
    d["rec"] = [sum(json.loads(x).get(k, 0.0) for k in RECOVERY) for x in d.node_frac_red]
    per = d.groupby("opponent").opp_hd.mean()
    ok = {"all": d.opp_hd.mean() <= LIM_ALL, "opp": (per <= LIM_OPP).all(), "rec": d.rec.mean() <= LIM_REC}
    m = C.Counter(d.win_mode[d.win_mode != ""])
    L = ["# heldout 상대 묶음 합격 점검", "",
         "기준 θ × 48경기 (bt-smoke 시드, `--opponents heldout`). 기준은 `bt/analysis/opponent_patch_rules.md` 와 같다 (상대 행동만).", "",
         "| 기준 | 값 | 한도 | 판정 |", "|---|---|---|---|",
         f"| 상대 하드덱 비율 (전체) | {d.opp_hd.mean():.3f} | ≤ {LIM_ALL} | {'O' if ok['all'] else 'X'} |",
         f"| 상대 하드덱 비율 (상대별 최대) | {per.max():.3f} ({per.idxmax()}) | ≤ {LIM_OPP} | {'O' if ok['opp'] else 'X'} |",
         f"| 상대 고도 회복 노드 실행 비율 (평균) | {d.rec.mean():.3f} | ≤ {LIM_REC} | {'O' if ok['rec'] else 'X'} |", "",
         f"**판정: {'합격' if all(ok.values()) else '불합격'}**", "",
         "| 상대 | 경기 | 상대 하드덱 | 회복 노드 비율 | 청 하드덱 | 청 승률 | wall_clock |", "|---|---|---|---|---|---|---|"]
    for o, g in d.groupby("opponent"):
        L.append(f"| {o} | {len(g)} | {g.opp_hd.mean():.3f} | {g.rec.mean():.3f} | {g.blue_hd.mean():.3f} | {(g.winner == 'blue').mean():.3f} "
                 f"| {(g.end_reason == 'wall_clock').sum()} |")
    L += ["", f"승리 방식 (청 승 {sum(m.values())}): " + ", ".join(f"{k} {m[k]}" for k in MODES),
          f"종료 사유: {d.end_reason.value_counts().to_dict()}", ""]
    open(REPORT, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    print("\n".join(L))
    return all(ok.values())


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
