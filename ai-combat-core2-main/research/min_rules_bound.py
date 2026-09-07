"""9부 P2 — 문장 수 하한 증명서 (충돌그래프 + 최대독립집합, z3 정확해).

주장 형태: "축-정렬 상자·증인-정박·구름 0-침범이라는 합성 의미론 하에서,
기저 32패를 피복하는 문장은 최소 L개 필요하다."

건전성 논거: 문장이 케이스 c 를 피복하려면 그 상자는 c 의 증인점 하나를
포함해야 한다(증인-정박). 두 케이스를 한 문장(같은 행동)이 피복하면 상자는
양쪽 증인점을 모두 포함하고, 따라서 그 두 점의 경계상자를 포함한다. 모든
공유 행동·모든 증인점 쌍에 대해 그 경계상자가 구름을 침범하면 → 두 케이스는
공동 피복 불가(비호환). 비호환 그래프의 독립집합(전부 서로 비호환)은 문장을
공유할 수 없으므로 |MIS| ≤ 최소 문장 수.

usage: python -m research.min_rules_bound
env: MB_FEATS(기본 13특징), MB_MAXPTS(케이스·행동당 증인점 상한, 기본 0=전부)
"""
from __future__ import annotations

import csv
import glob
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

PM = os.path.dirname(os.path.abspath(__file__))
REP = os.path.join(PM, "campaigns")
LBL = os.path.join(PM, "data", "blueteam")
DUMP = os.path.join(LBL, os.environ.get("MB_DUMP", "obs_dump_plain_all_es.csv"))
PLAIN_LOG = os.path.join(REP, "logs", os.environ.get("MB_BASELOG", "obsdump_plain_all_es.log"))
FEATS = tuple(os.environ.get(
    "MB_FEATS",
    "rng,ata,eata,kcas,alt,agap,hp_lead,clos,pursue,hotrun,eclimb,dalt,es_rel"
).split(","))
MAXPTS = int(os.environ.get("MB_MAXPTS", "0"))

RE_RES = re.compile(r"\s+(\S+)/(blue|red)\s+패\s")
RE_WIT = re.compile(r"\s*t0=\s*([\d.]+)\s+(\w+)\s+d=\s*[\d.]+ → ★승")


def main():
    losses = []
    for ln in open(PLAIN_LOG, encoding="utf-8"):
        m = RE_RES.match(ln)
        if m:
            losses.append(f"{m.group(1)}/{m.group(2)}")
    print(f"기저 패배 {len(losses)}")

    # 덤프 적재: 케이스별 (t, vec) + 구름(패배 케이스 외 전 행)
    data: dict[str, list] = {}
    cloud_rows = []
    loss_set = set(losses)
    with open(DUMP) as f:
        rd = csv.DictReader(f)
        for r in rd:
            v = np.array([float(r[k]) for k in FEATS])
            tag = r["tag"]
            if tag in loss_set:
                data.setdefault(tag, []).append((float(r["t"]), v))
            else:
                cloud_rows.append(v)
    cloud = np.vstack(cloud_rows)
    print(f"구름 {len(cloud)}행 × {len(FEATS)}차원")

    # 증인점: 케이스·행동별 (덤프에서 t0 최근접 행, 0.6s 이내)
    wit: dict[str, dict[str, list]] = {}
    for p in glob.glob(os.path.join(REP, "witness", "bs_*.log")):
        b = os.path.basename(p)[3:-4]
        if "@" in b:
            continue
        stem, side = b.rsplit("_", 1)
        case = f"{stem}/{side}"
        if case not in loss_set:
            continue
        rows = data.get(case, [])
        if not rows:
            continue
        ts = np.array([t for t, _ in rows])
        for ln in open(p, encoding="utf-8"):
            m = RE_WIT.match(ln)
            if not m:
                continue
            t0, act = float(m.group(1)), m.group(2)
            i = int(np.argmin(np.abs(ts - t0)))
            if abs(ts[i] - t0) <= 0.6:
                wit.setdefault(case, {}).setdefault(act, []).append(rows[i][1])
    for c in wit:
        for a in wit[c]:
            pts = wit[c][a]
            if MAXPTS and len(pts) > MAXPTS:
                wit[c][a] = pts[:MAXPTS]
    cases = [c for c in losses if c in wit]
    print(f"증인 보유 케이스 {len(cases)}, 총 증인점 "
          f"{sum(len(v2) for v in wit.values() for v2 in v.values())}")

    def pair_compatible(c1: str, c2: str) -> bool:
        """어떤 공유 행동·증인점 쌍의 경계상자가 구름 0-침범이면 호환."""
        for a in set(wit[c1]) & set(wit[c2]):
            P1 = np.vstack(wit[c1][a]); P2 = np.vstack(wit[c2][a])
            for p in P1:
                lo = np.minimum(p, P2); hi = np.maximum(p, P2)   # p×P2 일괄
                # 각 j: 상자 [lo[j],hi[j]] 에 구름점 존재?
                for j in range(len(P2)):
                    inside = np.all((cloud >= lo[j]) & (cloud <= hi[j]), axis=1)
                    if not inside.any():
                        return True
        return False

    n = len(cases)
    comp = np.zeros((n, n), bool)
    total = n * (n - 1) // 2
    k = 0
    for i in range(n):
        for j in range(i + 1, n):
            comp[i, j] = comp[j, i] = pair_compatible(cases[i], cases[j])
            k += 1
            if k % 50 == 0:
                print(f"  쌍 {k}/{total}", flush=True)

    # 최대 독립집합 (호환 그래프에서) — z3 Optimize 정확해
    from z3 import Bool, If, Not, And, Optimize, Sum
    xs = [Bool(f"x{i}") for i in range(n)]
    opt = Optimize()
    for i in range(n):
        for j in range(i + 1, n):
            if comp[i, j]:
                opt.add(Not(And(xs[i], xs[j])))
    opt.maximize(Sum([If(x, 1, 0) for x in xs]))
    opt.check()
    mdl = opt.model()
    mis = [cases[i] for i in range(n) if mdl.eval(xs[i])]
    print(f"\n=== 하한 증명서 ===")
    print(f"특징공간 {len(FEATS)}차원, 케이스 {n}, 호환쌍 {int(comp.sum())//2}/{total}")
    print(f"최대 상호-비호환 집합 |MIS| = {len(mis)}")
    print("→ 이 의미론 하에서 최소 문장 수 ≥", len(mis))
    print("MIS 구성원:", mis)


if __name__ == "__main__":
    raise SystemExit(main())
