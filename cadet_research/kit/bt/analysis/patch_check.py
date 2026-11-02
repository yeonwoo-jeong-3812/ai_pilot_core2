"""보정 상대 합격 검증 (bt/analysis/opponent_patch_rules.md). games.csv 는 읽기만 한다.

  python bt/analysis/patch_check.py          # bt/out/bt-diag/games.csv (opponent_set=patched) → bt/out/opponent_patch_check.md
"""
from __future__ import annotations

import collections as C
import csv
import json
import os
import sys

BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BT)
from run_bt import OPPONENTS, win_mode  # noqa: E402

OUT = os.path.join(BT, "out")
MODES = ("shootdown", "opp_hard_deck", "opp_stall", "judge", "other")
LIM_ALL, LIM_OPP, LIM_CLIMB = 0.05, 0.10, 0.20


def rows(p):
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def opp_hd(g):
    return sum(r["end_reason"] == "hard_deck" and r["winner"] == "blue" for r in g) / len(g)


def climb(g):
    return sum(json.loads(r["node_frac_red"]).get("climb", 0.0) for r in g) / len(g) if g and "node_frac_red" in g[0] else None


def block(title, g, by_opp):
    m = C.Counter(win_mode(r["winner"], r["end_reason"]) for r in g)
    L = [f"### {title} ({len(g)}경기)", "",
         "| 상대 | 경기 | 상대 하드덱 | 상대 climb 비율 | 청 하드덱 | 청 승률 |", "|---|---|---|---|---|---|"]
    for o in OPPONENTS:
        h = by_opp(g, o)
        c = climb(h)
        L.append(f"| {o} | {len(h)} | {opp_hd(h):.3f} | {'—' if c is None else f'{c:.3f}'} "
                 f"| {sum(r['end_reason'] == 'hard_deck' and r['winner'] == 'red' for r in h) / len(h):.3f} "
                 f"| {sum(r['winner'] == 'blue' for r in h) / len(h):.3f} |")
    c = climb(g)
    L += [f"| **전체** | {len(g)} | **{opp_hd(g):.3f}** | **{'—' if c is None else f'{c:.3f}'}** "
          f"| {sum(r['end_reason'] == 'hard_deck' and r['winner'] == 'red' for r in g) / len(g):.3f} "
          f"| {sum(r['winner'] == 'blue' for r in g) / len(g):.3f} |", "",
          f"승리 방식 (청 승 {len(g) - m['']}): " + ", ".join(f"{k} {m[k]}" for k in MODES), ""]
    return L


def main(opponent_set="patched", out_name="opponent_patch_check.md"):
    new = [r for r in rows(os.path.join(OUT, "bt-diag", "games.csv")) if r["opponent_set"] == opponent_set]
    old = [r for r in rows(os.path.join(OUT, "bt-diag", "games_diag1.csv")) if not r["opponent"].endswith("_f4000")]
    assert len(new) == 144, len(new)
    per = {o: opp_hd([r for r in new if r["opponent"] == o]) for o in OPPONENTS}
    c = climb(new)
    ok = {"all": opp_hd(new) <= LIM_ALL, "opp": all(v <= LIM_OPP for v in per.values()), "climb": c <= LIM_CLIMB}
    L = ["# 보정 상대 합격 검증", "",
         f"규칙: `bt/analysis/opponent_patch_rules.md` (실행 전 커밋). 상대 묶음 `{opponent_set}`, 청 θ 3개 "
         "(floor_ft 3000/4500/7000) × 48경기, bt-diag 시드. 기준은 상대 행동만 본다.", "",
         "| 기준 | 값 | 한도 | 판정 |", "|---|---|---|---|",
         f"| 상대 하드덱 비율 (전체) | {opp_hd(new):.3f} | ≤ {LIM_ALL} | {'O' if ok['all'] else 'X'} |",
         f"| 상대 하드덱 비율 (상대별 최대) | {max(per.values()):.3f} ({max(per, key=per.get)}) | ≤ {LIM_OPP} | {'O' if ok['opp'] else 'X'} |",
         f"| 상대 climb 실행 비율 (평균) | {c:.3f} | ≤ {LIM_CLIMB} | {'O' if ok['climb'] else 'X'} |", "",
         f"**판정: {'합격' if all(ok.values()) else '불합격'}**", ""]
    L += block(f"보정 상대 ({opponent_set})", new, lambda g, o: [r for r in g if r["opponent"] == o])
    L += block("참고: 원본 상대 (하드덱 진단 때, 같은 θ·시드)", old, lambda g, o: [r for r in g if r["opponent"] == o])
    L += ["원본 상대 행은 하드덱 진단 때 결과다 (`bt-diag/games_diag1.csv`, opponent_set 열이 생기기 전이라 이름만 바꿔 보관).", ""]
    with open(os.path.join(OUT, out_name), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return all(ok.values())


if __name__ == "__main__":
    main(*sys.argv[1:])
