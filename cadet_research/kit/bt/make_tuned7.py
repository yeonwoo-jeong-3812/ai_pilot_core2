"""튜닝 BT 비교 변형 7개 → bt/thetas/tuned7.csv (cadet_research/PREREG_BT_ADDENDUM_TUNING.md). 같은 입력이면 같은 파일.

  python bt/make_tuned7.py

V0 기준 / V1 교범값 (근거 있는 것만, 아래 DOCTRINE) / V2 fight_kcas 만 유리한 방향 / V3 중요 3개만 유리한 방향 /
V4 중요하지 않은 7개만 무작위 (seed 20261106, 범위 안 균등), 중요 3개는 기준값 / V5 V1 에 V3 조정을 얹음 / V6 RQ3 대리모델 1위 θ 그대로.
"유리한 방향" = RQ2 Morris μ 의 부호 (bt/out/analysis/morris.md), 크기 = 범위의 유리한 쪽 끝에서 범위 폭의 10% 안쪽 값.
"""
from __future__ import annotations

import csv
import os
import sys

import numpy as np

BT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BT)
import make_tree as mt  # noqa: E402
import run_bt  # noqa: E402

OUT = os.path.join(BT, "thetas", "tuned7.csv")
IMPORTANT = {"fight_kcas": -1, "threat_aspect_deg": +1, "floor_ft": -1}      # RQ2 중요 3개와 μ 부호 (−2.73, +1.29, −1.25)
# 교범 근거가 있는 파라미터만 (aircombat/guidance/doctrine.py 의 절 번호 표기). 근거 표는 PREREG_BT_ADDENDUM_TUNING.md §2
DOCTRINE = {"fight_kcas": 325.0,          # below_fighting_speed 기본값 = DoctrineParams.fighting_kts_lo 325 (4.4.6.2.2 파이팅 속도 325–375kt)
            "threat_aspect_deg": 120.0,   # DoctrineParams.initial_pull_aspect_deg 120 (4.4.5.2 머지 진입 판정 aspect)
            "merge_range_ft": 6000.0}     # DoctrineParams.slant_ft_hi 6000 (4.4.6.2.1 슬랜트 4,000–6,000ft, 머지 진입 기하 rng < slant_hi)
V4_SEED = 20261106
V6_ID = "c1e4a1d09296"
P = {p["name"]: p for p in mt.PARAMS}


def favorable(name: str) -> float:
    lo, hi = float(P[name]["lo"]), float(P[name]["hi"])
    return lo + 0.1 * (hi - lo) if IMPORTANT[name] < 0 else hi - 0.1 * (hi - lo)


def variants() -> list[dict]:
    base = {**mt.BASE, "dummy": mt.DUMMY["base"]}
    v3 = {k: favorable(k) for k in IMPORTANT}
    rng = np.random.default_rng(V4_SEED)
    v4 = {p["name"]: float(rng.uniform(float(p["lo"]), float(p["hi"]))) for p in mt.PARAMS if p["name"] not in IMPORTANT}
    v6 = next(t for t in run_bt.read_thetas(os.path.join(BT, "thetas", "confirm_candidates.csv")) if mt.theta_id(t) == V6_ID)
    out = [("V0", base), ("V1", {**base, **DOCTRINE}), ("V2", {**base, "fight_kcas": v3["fight_kcas"]}), ("V3", {**base, **v3}),
           ("V4", {**base, **v4}), ("V5", {**base, **DOCTRINE, **v3}), ("V6", dict(v6))]
    for name, th in out:
        mt.normalize(th)                       # 모두 params.yaml 범위 안
    return [dict(variant=n, **th) for n, th in out]


def main():
    rows = variants()
    cols = ["variant"] + mt.NAMES + ["dummy"]
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows({k: (r[k] if k == "variant" else repr(float(r[k]))) for k in cols} for r in rows)
    for r in rows:
        print(r["variant"], mt.theta_id({k: r[k] for k in mt.NAMES + ["dummy"]}))


if __name__ == "__main__":
    main()
