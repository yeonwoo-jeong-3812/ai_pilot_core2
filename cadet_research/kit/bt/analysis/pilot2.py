"""재예비 실험 (보정 상대) 보고서 + 원본 상대 예비 실험과 나란히 비교. 규칙은 pilot_rules.md 그대로.

  python bt/analysis/pilot2.py       # bt/out/bt-pilot/games.csv (patched) → bt/out/pilot2_report.md
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pilot  # noqa: E402

NEW = os.path.join(pilot.BT, "out", "bt-pilot", "games.csv")
REPORT = os.path.join(pilot.BT, "out", "pilot2_report.md")
NOTES = [
    "- **없음.** pilot_rules.md 를 고치지 않고 (1)~(5) 를 그대로 계산했다. θ 50개 (`pilot_lhs50.csv`), bt-pilot 시드도 같다.",
    "- 바뀐 것은 상대뿐이다: 보정 상대 (`--opponents patched`, `bt/analysis/opponent_patch_rules.md`). "
    "원본 상대 결과는 `bt-pilot/games_original.csv` (이름만 바꿈) 이고 비교는 아래 \"원본 상대와 비교\" 절.",
]


def main():
    with open(NEW, encoding="utf-8", newline="") as f:
        sets = {r["opponent_set"] for r in csv.DictReader(f)}
    assert sets == {"patched"}, sets
    new = pilot.analyze(NEW, REPORT, "재예비 실험 (관문 2, 보정 상대) 결과", NOTES)
    old = pilot.analyze(pilot.GAMES, os.devnull, "", [])
    f = lambda d, m: (f"{d['res'][m]['v']:.4g} ({d['res'][m]['vlo']:.4g}, {d['res'][m]['vhi']:.4g})", f"{d['res'][m]['r']:.2f}")
    L = ["## 원본 상대와 비교 (같은 θ 50개·같은 시드, 상대만 다름)", "",
         "| 항목 | 원본 상대 | 보정 상대 |", "|---|---|---|",
         f"| 분석 경기 | {old['n']} | {new['n']} |"]
    for m, name in pilot.METRICS.items():
        L += [f"| θ 분산 V — {name} (95% CI) | {f(old, m)[0]} | {f(new, m)[0]} |",
              f"| 비율 R — {name} | {f(old, m)[1]} | {f(new, m)[1]} |"]
    L += [f"| 1차 지표 | {pilot.METRICS[old['primary']]} ({old['why']}) | {pilot.METRICS[new['primary']]} ({new['why']}) |",
          f"| 관문 2 | {'통과' if old['gate'] else '불통과'} | {'통과' if new['gate'] else '불통과'} |",
          f"| 청 승 | {old['wins']} / {old['n']} ({old['wins'] / old['n']:.3f}) | {new['wins']} / {new['n']} ({new['wins'] / new['n']:.3f}) |"]
    for k in pilot.MODES:
        L.append(f"| 승리 방식 {k} | {old['modes'][k]} ({old['modes'][k] / max(old['wins'], 1):.0%}) "
                 f"| {new['modes'][k]} ({new['modes'][k] / max(new['wins'], 1):.0%}) |")
    for o in old["opp_win"]:
        L.append(f"| 청 승률 vs {o} | {old['opp_win'][o]:.3f} | {new['opp_win'][o]:.3f} |")
    for o in old["opp_hd"]:
        L.append(f"| 상대 하드덱 비율 {o} | {old['opp_hd'][o]:.3f} | {new['opp_hd'][o]:.3f} |")
    L += [f"| gun_track 평균 node_frac | {old['gun_mean']:.4f} | {new['gun_mean']:.4f} |",
          f"| gun_track 한 번도 실행 안 된 경기 비율 | {old['gun_never']:.3f} | {new['gun_never']:.3f} |",
          f"| gun_ata_deg 범위 점검 | {old['verdicts']['gun_ata_deg']} | {new['verdicts']['gun_ata_deg']} |",
          f"| gun_range_ft 범위 점검 | {old['verdicts']['gun_range_ft']} | {new['verdicts']['gun_range_ft']} |"]
    changed = [p for p in old["verdicts"] if old["verdicts"][p] != new["verdicts"][p]]
    L += ["", "범위 점검 판정이 바뀐 파라미터: " + (", ".join(f"{p} ({old['verdicts'][p]} → {new['verdicts'][p]})" for p in changed) or "없음"), ""]
    with open(REPORT, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
