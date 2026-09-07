"""M3 — 상설 지표 스캐너 (AUTOMATION_PLAN §S1).

입력: 채점 로그(승/패 라벨) + obs 덤프. 후보 지표 은행을 전수 AUC 채점해
판별자 순위를 보고한다 (루프10 방식의 상설화).

후보 은행 = 덤프 특징 × 집계(평균/최소/최대) × 창(전체/자기-dwell/적-dwell)
          + 파생(tier·race·dwell 시간·첫 dwell 진입시각 등).

usage: MS_LOG=<채점로그> MS_DUMP=<덤프csv> python -m research.metric_scanner
판정(사전등록): |AUC-0.5| ≥ 0.25 인 지표만 S2(기전 층)로 전달.
"""
from __future__ import annotations

import csv
import os
import re
import sys

import numpy as np

PM = os.path.dirname(os.path.abspath(__file__))
RE_RES = re.compile(r"\s+(\S+)/(blue|red)\s+(승|무|패)\s")

WEZ_LO, WEZ_HI, WEZ_ATA = 500.0, 3000.0, 30.0


def tier(a: np.ndarray) -> np.ndarray:
    return np.select([a <= 2, a <= 10, a <= 20, a <= 30],
                     [1.0, 0.75, 0.5, 0.25], 0.0)


def auc(x: np.ndarray, y: np.ndarray) -> float:
    """승(1)/패(0) 라벨 y 에 대한 지표 x 의 ROC-AUC (순위 기반)."""
    order = np.argsort(x)
    rank = np.empty(len(x)); rank[order] = np.arange(1, len(x) + 1)
    n1, n0 = int(y.sum()), int((1 - y).sum())
    if n1 == 0 or n0 == 0:
        return 0.5
    return float((rank[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def case_metrics(rows: list[dict]) -> dict[str, float]:
    F = {k: np.array([float(r[k]) for r in rows])
         for k in rows[0] if k not in ("tag", "t")}
    t = np.array([float(r["t"]) for r in rows])
    my_dwell = (F["rng"] >= WEZ_LO) & (F["rng"] <= WEZ_HI) & (F["ata"] <= WEZ_ATA)
    foe_dwell = (F["rng"] >= WEZ_LO) & (F["rng"] <= WEZ_HI) & (F["eata"] <= WEZ_ATA)
    m: dict[str, float] = {}
    for k, v in F.items():
        m[f"{k}_mean"] = float(v.mean())
        m[f"{k}_min"] = float(v.min())
        m[f"{k}_max"] = float(v.max())
        if my_dwell.any():
            m[f"{k}_mydwell_mean"] = float(v[my_dwell].mean())
        if foe_dwell.any():
            m[f"{k}_foedwell_mean"] = float(v[foe_dwell].mean())
    # 파생 — 조준 품질·경쟁 축
    m["my_tier_dwell"] = float(tier(F["ata"][my_dwell]).mean()) if my_dwell.any() else 0.0
    m["foe_tier_dwell"] = float(tier(F["eata"][foe_dwell]).mean()) if foe_dwell.any() else 0.0
    m["tier_diff_dwell"] = m["my_tier_dwell"] - m["foe_tier_dwell"]
    m["race_mean"] = float((F["eata"] - F["ata"]).mean())
    m["my_dwell_s"] = float(my_dwell.sum()) * 0.1
    m["foe_dwell_s"] = float(foe_dwell.sum()) * 0.1
    m["dwell_diff_s"] = m["my_dwell_s"] - m["foe_dwell_s"]
    m["first_mydwell_t"] = float(t[my_dwell][0]) if my_dwell.any() else 999.0
    return m


def main():
    log = os.environ["MS_LOG"]
    dump = os.environ["MS_DUMP"]
    labels = {}
    for ln in open(log, encoding="utf-8"):
        mm = RE_RES.match(ln)
        if mm and mm.group(3) != "무":
            labels[f"{mm.group(1)}/{mm.group(2)}"] = 1.0 if mm.group(3) == "승" else 0.0
    by_tag: dict[str, list] = {}
    with open(dump) as f:
        for r in csv.DictReader(f):
            if r["tag"] in labels:
                by_tag.setdefault(r["tag"], []).append(r)
    cases = sorted(set(labels) & set(by_tag))
    y = np.array([labels[c] for c in cases])
    print(f"케이스 {len(cases)} (승 {int(y.sum())} / 패 {int(len(y)-y.sum())})")
    table: dict[str, list] = {}
    for c in cases:
        for k, v in case_metrics(by_tag[c]).items():
            table.setdefault(k, []).append(v)
    rows = []
    for k, vals in table.items():
        if len(vals) != len(cases):
            continue                      # 일부 케이스 결측 지표 제외(창 미형성)
        a = auc(np.array(vals), y)
        rows.append((abs(a - 0.5), a, k))
    rows.sort(reverse=True)
    print(f"\n{'지표':<28}{'AUC':>7}  (|AUC-0.5|≥0.25 만 S2 전달; 결과-대리는 제외)")
    for d, a, k in rows[:20]:
        # 결과-대리(outcome proxy): 점수 부기에서 파생된 지표는 승리의 원인이
        # 아니라 결과 — 기전 후보에서 제외하고 표기만 한다.
        proxy = k.startswith(("hp_lead", "fdmg"))
        mark = " [결과-대리]" if proxy else (" ◀ 전달" if d >= 0.25 else "")
        print(f"{k:<28}{a:7.3f}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
