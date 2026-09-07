"""검증된 팽창 — 엄격분리의 보수성을 롤아웃 예산으로 교환한다(PIPELINE_SPEC §4.4).

엄격분리는 상자를 승리 자취에 닿기 직전까지만 키운다. 그래서 "겹치는 지점에서도
그 기동이 이겼을" 가능성을 통째로 버린다. 이 도구는 반대로 간다:

  상자를 축별로 **자취 안쪽까지** 넓히되, 그 팽창으로 **새로 덮이는 승리판**마다
  "그 판의 진입틱에서 이 문장이 발화해도 여전히 이기는가"를 재롤아웃으로 검증하고,
  전부 통과할 때만 팽창을 채택한다.

결정론이라 판정은 확정적이다. 실패하면 그 축의 팽창을 원복한다(안전한 최소해로 복귀).

판정(사전등록): 팽창본은 ①훈련 전판 무손 ②홀드아웃 비열화 를 통과해야 채택.
비용: 팽창 후보 축마다 새로 덮이는 승리판 수만큼 롤아웃.

usage:
  python -m research.expand_rules --rules <slim.json> --dump <배포덤프.csv> \
         --out <expanded.json> [--steps 6] [--roster roster/all_128.txt]
env: LG_BASEFN 등 정책 구성은 상위(framework)와 동일하게 전달할 것.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("LG_RULESEL", "0")

from research import champion_core as C            # noqa: E402
from research.branch_search import ACTIONS, run_forced   # noqa: E402

PM = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PM)
LBL = os.path.join(PM, "data", "blueteam")
# 축별 1스텝 팽창 폭(귀납기 PAD0 와 동일 눈금 — 좌표마다 스케일이 다르므로)
PAD = dict(rng=200, ata=5, eata=5, kcas=10, alt=500, agap=500, hp_lead=1,
           clos=20, pursue=0.05, hotrun=0.5, eclimb=30, dalt=30, es_rel=500,
           t=5, fdmg=2, race=7, vdiff=15, armed=1)


def load_dump(path: str):
    """tag -> [(t, {축: 값})] · armed 이전 행 제외(가드 정합, §6.2)."""
    by: dict[str, list] = {}
    for r in csv.DictReader(open(path)):
        if float(r.get("armed", 1.0)) < 0.5:
            continue
        by.setdefault(r["tag"], []).append(
            (float(r["t"]), {k: float(v) for k, v in r.items() if k != "tag"}))
    return by


def entry_tick(rows, box) -> float | None:
    for t, f in rows:
        if all(lo <= f[k] <= hi for k, (lo, hi) in box.items()):
            return t
    return None


def covered_cases(dump, box, exclude: set) -> list[str]:
    """이 상자가 발화하게 되는 판 목록(피복 대상 제외) — 팽창의 부작용 범위."""
    return sorted(tag for tag, rows in dump.items()
                  if tag not in exclude and entry_tick(rows, box) is not None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", required=True)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--steps", type=int, default=6, help="축당 최대 팽창 스텝")
    a = ap.parse_args()

    clf = C.load_clf()
    rules = json.load(open(a.rules))
    dump = load_dump(a.dump)
    total_steps = total_reject = 0

    for i, r in enumerate(rules):
        box = {k: (float(v[0]), float(v[1])) for k, v in r["box"].items()}
        own = set(r.get("covers", [])) | set(r.get("cofire", []))
        act, dur = r["act"], float(r["dur"])
        print(f"[문장 {i}] {act} 축 {len(box)} — 팽창 시도", flush=True)
        for k in sorted(box):
            pad = PAD.get(k, 1.0)
            for sgn in (-1, +1):                    # 하한 아래로 / 상한 위로
                for _ in range(a.steps):
                    lo, hi = box[k]
                    trial = dict(box)
                    trial[k] = (lo - pad * 0.5, hi) if sgn < 0 else (lo, hi + pad * 0.5)
                    newly = [c for c in covered_cases(dump, trial, own)
                             if c not in covered_cases(dump, box, own)]
                    ok = True
                    for c in newly:                 # 새로 덮이는 판마다 보존 검증
                        te = entry_tick(dump[c], trial)
                        stem, side = c.rsplit("/", 1)
                        win, dhp, *_ = run_forced(stem, side, clf,
                                                  (te, dur, ACTIONS[act]))
                        if not (win or dhp >= 0.0):
                            print(f"    {k}{'-' if sgn < 0 else '+'} 거부 — "
                                  f"{c} 보존 실패 Δ{dhp:+.1f}", flush=True)
                            ok = False
                            total_reject += 1
                            break
                    if not ok:
                        break
                    box = trial                     # 채택 — 다음 스텝
                    total_steps += 1
                    if newly:
                        print(f"    {k}{'-' if sgn < 0 else '+'} 채택 "
                              f"(+{len(newly)}판 검증 통과)", flush=True)
        r["box"] = {k: [lo, hi] for k, (lo, hi) in box.items()}

    json.dump(rules, open(a.out, "w"), indent=1)
    print(f"\n팽창 {total_steps}스텝 채택 · {total_reject}회 거부 → {a.out}")
    print("※ 최종 판정은 전판 실측 + 홀드아웃 비열화로(framework gate/run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
