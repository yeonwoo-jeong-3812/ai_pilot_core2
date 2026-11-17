"""넓은 상대 일반화 후보 31개의 합격 점검 (cadet_research/PREREG_BT_ADDENDUM_WIDE.md §3). games.csv 는 읽기만 한다.

  python bt/run_bt.py bt/thetas/baseline.csv --prefix bt-smoke --opponents wide-cand    # 기준 θ × 상대당 12경기
  python bt/analysis/wide_check.py      # → bt/out/wide_check.md, bt/opponents_wide/accepted.csv

상대별 기준 (상대 행동만, 결과를 보기 전에 정함):
  (1) 상대 하드덱 (end_reason hard_deck, winner blue) 이 12경기 중 1경기 이하
  (2) 최우선 고도 회복 노드가 있으면 (manifest.csv 의 recovery_node) 그 실행 비율 평균 ≤ 0.30
둘 다 만족하면 합격. 다만 (3) 같은 계열의 두 상대가 12경기 결과 (승자·종료 사유·체력·WEZ 시간·경기 시간·상대 노드 비율) 가
완전히 같으면 같은 행동으로 보고 이름 순 앞 하나만 남긴다 (같은 상대를 두 번 세지 않으려고).
wall_clock 경기가 있으면 판정하지 않고 멈춘다 (재실행 뒤 다시 점검).
기준 θ 승률은 참고로만 적는다 (바닥 상대 표시).
"""
from __future__ import annotations

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BT)
from io_utils import read_games  # noqa: E402

GAMES = os.path.join(BT, "out", "bt-smoke-wide-cand", "games.csv")
MANIFEST = os.path.join(BT, "opponents_wide", "manifest.csv")
ACCEPTED = os.path.join(BT, "opponents_wide", "accepted.csv")
REPORT = os.path.join(BT, "out", "wide_check.md")
MAX_HD, MAX_REC, N_PER_OPP = 1, 0.30, 12
SAME = ["winner", "end_reason", "hp_blue_raw", "hp_red_raw", "wez_blue", "wez_red", "sim_time_s", "node_frac_red"]


def judge(d, manifest) -> list[dict]:
    rows, kept = [], {}
    for m in manifest:
        g = d[d.opponent == m["name"]]
        if len(g) != N_PER_OPP:
            raise ValueError(f"{m['name']}: {len(g)}경기 (계획 {N_PER_OPP})")
        hd = int(((g.end_reason == "hard_deck") & (g.winner == "blue")).sum())
        rec = (sum(json.loads(x).get(m["recovery_node"], 0.0) for x in g.node_frac_red) / len(g)) if m["recovery_node"] else None
        ok = hd <= MAX_HD and (rec is None or rec <= MAX_REC)
        key = (m["family"], tuple(map(tuple, g.sort_values(["scenario", "seed_salt"])[SAME].astype(str).values)))
        same_as = kept.get(key, "") if ok else ""
        if ok and not same_as:
            kept[key] = m["name"]
        ok = ok and not same_as
        rows.append(dict(name=m["name"], kind=m["kind"], family=m["family"], patched=m["patched"], opp_hard_deck=hd,
                         recovery=rec, blue_win=float((g.winner == "blue").mean()), no_contact=float((g.end_reason == "no_contact").mean()),
                         blue_overlap=int(m["blue_overlap"]), same_as=same_as, accepted=int(ok)))
    return rows


def main():
    d = read_games(GAMES)
    if (d.end_reason == "wall_clock").any():
        sys.exit(f"wall_clock {int((d.end_reason == 'wall_clock').sum())}경기: 그 줄을 지우고 재실행한 뒤 다시 점검한다")
    manifest = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
    rows = judge(d, manifest)
    with open(ACCEPTED, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, ["name", "opp_hard_deck", "recovery", "accepted"], lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows([{**r, "recovery": "" if r["recovery"] is None else f"{r['recovery']:.3f}"} for r in rows])
    acc = [r for r in rows if r["accepted"]]
    L = ["# 넓은 상대 일반화 후보 합격 점검", "",
         f"기준 θ × 상대당 {N_PER_OPP}경기 (bt-smoke 시드, `--opponents wide-cand`). 기준: 상대 하드덱 ≤ {MAX_HD}경기, 고도 회복 노드 비율 ≤ {MAX_REC} (상대 행동만), 같은 계열에서 12경기 결과가 완전히 같으면 이름 순 앞 하나만.", "",
         f"**합격 {len(acc)} / {len(rows)}** (변종 {sum(r['kind'] == 'near' for r in acc)}, 새 유형 {sum(r['kind'] == 'far' for r in acc)})", "",
         "| 상대 | 종류 | 계열 | 고도 보정 | 상대 하드덱 | 회복 노드 비율 | 기준 θ 승률 (참고) | 무접촉 (참고) | 청 노드 겹침 | 판정 |", "|---|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {r['name']} | {'변종' if r['kind'] == 'near' else '새 유형'} | {r['family']} | {'예' if r['patched'] == '1' else '아니오'} | {r['opp_hard_deck']} "
          f"| {'—' if r['recovery'] is None else format(r['recovery'], '.3f')} | {r['blue_win']:.2f} | {r['no_contact']:.2f} | {r['blue_overlap']} | {'합격' if r['accepted'] else ('같은 행동: ' + r['same_as'] if r['same_as'] else '**불합격**')} |"
          for r in rows]
    L += ["", f"종료 사유 (전체): {d.end_reason.value_counts().to_dict()}", ""]
    open(REPORT, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
