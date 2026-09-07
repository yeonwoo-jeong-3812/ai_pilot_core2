"""이식된 core-live 검증 상대(13 archetype 중앙 인스턴스) vs core2 챔프 재채점.

핵심 성과: core-live 42/42 는 '다른 게임' 성적 → core2 물리로 재계측 필수라는 확정에 따라,
이식 상대를 core2 엔진에 올려 우리 core2 챔프(TranscribedPilot + 정본 가드)로 재채점한다.

채점: 각 상대 × {headon, neutral} × {blue, red} = 52경기, both-INDI 300s.
챔프 = spec=None (정본 BFMGuidance + 예측 하드덱 가드).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from research import champion_core as C
from research.prototype_floor_recovery import run_pairing

PORTED = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "roster"))
# 검증 42종: canonical-17(anchor 4 + archetype 중앙 13) + held-out 25.
ANCHORS = ["anchor_simple", "anchor_aggressive", "anchor_defensive", "anchor_ace"]
CANON = ["A1_PurePursuer_05", "A2_GunTracker_06", "A3_LagAngler_06",
         "B1_EnergyFighter_06", "B2_Extender_04",
         "C1_TwoCircleRate_03", "C2_OneCircleRad_03", "C3_Lufbery_04",
         "D1_Reactive_06", "D2_LastDitch_03", "D3_Scissors_01",
         "E1_AdaptiveAce_06", "E2_Passive_01"]
HELDOUT = ["A1_PurePursuer_00", "A1_PurePursuer_09", "A2_GunTracker_00",
           "A2_GunTracker_11", "A3_LagAngler_00", "A3_LagAngler_11",
           "B1_EnergyFighter_00", "B1_EnergyFighter_11", "B2_Extender_00",
           "B2_Extender_08", "C1_TwoCircleRate_00", "C1_TwoCircleRate_05",
           "C2_OneCircleRad_00", "C2_OneCircleRad_05", "C3_Lufbery_00",
           "C3_Lufbery_08", "D1_Reactive_00", "D1_Reactive_11",
           "D2_LastDitch_00", "D2_LastDitch_05", "D3_Scissors_00",
           "D3_Scissors_02", "E1_AdaptiveAce_00", "E1_AdaptiveAce_11",
           "E2_Passive_00"]
ROSTER = [("anchor", s) for s in ANCHORS] + \
         [("canon", s) for s in CANON] + [("heldout", s) for s in HELDOUT]
# 합의: 초기상태는 headon 단일. 다른 초기조건 미사용.
DISCRIM = ["headon"]


def main():
    clf = C.load_clf()
    print("=== 이식 core-live 검증 42종 vs core2 챔프 재채점 (headon, both-INDI 300s) ===")
    print(f"{'구분':<9}{'상대':<22}{'승-무-패':>8}{'격추':>5}   상세(HP차, 챔프관점)")
    grp = {}
    tot_w = tot_d = tot_l = tot_k = 0
    worst = []
    for cat, stem in ROSTER:
        rel = f"roster/{stem}.yaml"
        if not os.path.isfile(os.path.join(PORTED, stem + ".yaml")):
            print(f"  [warn] 없음: {stem}"); continue
        w = d = l = k = 0
        cells = []
        for sc in DISCRIM:
            for side in ("blue", "red"):
                res, win, loss, _ = run_pairing(sc, rel, clf, side, None)
                hp_c = res.hp_blue if side == "blue" else res.hp_red
                hp_o = res.hp_red if side == "blue" else res.hp_blue
                if win and hp_o <= 0:
                    k += 1; w += 1
                elif win:
                    w += 1
                elif loss:
                    l += 1
                    worst.append(f"{stem}/{side} (Δ{hp_c-hp_o:+.1f})")
                else:
                    d += 1
                cells.append(f"{side[0]}:{hp_c-hp_o:+.0f}")
        tot_w += w; tot_d += d; tot_l += l; tot_k += k
        g = grp.setdefault(cat, [0, 0, 0, 0]); g[0]+=w; g[1]+=d; g[2]+=l; g[3]+=k
        print(f"  {cat:<9}{stem:<22}{w}-{d}-{l:>1}{'':>3}{k:>4}   " + "  ".join(cells), flush=True)
    print()
    for cat in ("anchor", "canon", "heldout"):
        if cat in grp:
            g = grp[cat]
            print(f"  [{cat}] {g[0]}승 {g[1]}무 {g[2]}패 (격추 {g[3]})")
    print(f"\n  합계: {tot_w}승 {tot_d}무 {tot_l}패  (격추 {tot_k}) / 총 {tot_w+tot_d+tot_l}경기")
    print(f"  패·무 상세: {worst if worst else '없음'}")


if __name__ == "__main__":
    raise SystemExit(main())
