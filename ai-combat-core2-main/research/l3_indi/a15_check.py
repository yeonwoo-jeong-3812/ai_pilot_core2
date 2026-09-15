"""개정 A15 검증 — 꼬리 추가 재실행과 원래 실행(꼬리 없음)을 전 런 대조한다.

  * 창 W 지표(판정용 지표 전부)는 CSV 문자열까지 같아야 한다.
  * 바뀔 수 있는 것: 진동 판정(oscillating, osc_v1, osc_signchg_only, p2p_*, signchg_hz), 런 전체 기준 이탈·G 포락선(nz_max/min).

사용: python research/l3_indi/a15_check.py <원래 실행 폴더> <재실행 폴더>
"""
from __future__ import annotations

import csv
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = ("fbw", "alt_ft", "kcas", "man", "kp", "kq", "kr", "filt")
MAY_CHANGE = {"oscillating", "osc_v1", "osc_signchg_only", "p2p_rate_dps", "p2p_nz", "signchg_hz",
              "departure", "g_exceeded", "nz_max", "nz_min"}


def main():
    old_dir, new_dir = sys.argv[1], sys.argv[2]
    load = lambda d: {tuple(r[k] for k in KEY): r for r in csv.DictReader(open(os.path.join(d, "runs.csv"), encoding="utf-8"))}
    old, new = load(old_dir), load(new_dir)
    cols = sorted(set(next(iter(old.values()))) - MAY_CHANGE - set(KEY))
    diff = Counter()
    changed = Counter()
    for k, o in old.items():
        n = new.get(k)
        if n is None:
            diff["_missing"] += 1
            continue
        for c in cols:
            if o.get(c) != n.get(c):
                diff[c] += 1
        for c in ("oscillating", "departure", "g_exceeded"):
            if o[c] != n[c]:
                changed[(k[3][:2] if k[3] != "M2a" else "M2a", k[0], c, f"{o[c]}→{n[c]}")] += 1
    L = [f"# 개정 A15 검증 — 원래 {os.path.basename(os.path.normpath(old_dir))} vs 꼬리 재실행 {os.path.basename(os.path.normpath(new_dir))}\n",
         f"- 런 {len(old)} / {len(new)}. 비교한 창 W 지표 열 {len(cols)}개: {', '.join(cols)}\n",
         f"- **창 W 지표 불일치: {sum(diff.values())}건** {dict(diff) if diff else ''}\n",
         "## 판정이 바뀐 런\n", "| 기동 | FLCS(fbw) | 항목 | 변화 | 런 수 |", "|---|---|---|---|---|"]
    for (m, fbw, c, ch), v in sorted(changed.items()):
        L.append(f"| {m} | {fbw} | {c} | {ch} | {v} |")
    rep = os.path.join(HERE, "reports", f"A15_CHECK_{os.path.basename(os.path.normpath(new_dir))}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", rep, "| W 불일치", sum(diff.values()))
    return 0 if not diff else 1


if __name__ == "__main__":
    raise SystemExit(main())
