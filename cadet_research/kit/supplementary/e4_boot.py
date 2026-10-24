"""E4 보조 계산: 계획서 §5.3 규칙(시드 부트스트랩 2,000회, 표본마다 곡선 재적합, 평균 예측 오차 CI 를 δ 와 비교)을
E4 에 적용한다. 분석기(predict.py E4)는 점추정만 낸다. 곡선 모양은 E2 에서 등록한 것(linear)만 쓴다."""
import json
import os
import sys

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # kit/supplementary → kit
sys.path.insert(0, KIT)
import predict as P  # noqa: E402
from experiments import EXPERIMENTS  # noqa: E402

P.SHAPE = json.load(open(os.path.join(KIT, "out", "main", "curve.json"), encoding="utf-8"))["shape"]
tol = json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))
e2, e4 = EXPERIMENTS["E2"], EXPERIMENTS["E4"]
fitc = [c for c in e2["conds"] if c != "BASE"]
testc = [c for c in e4["conds"] if c != "BASE"]
by2, by4 = P.load("main"), P.load("gen")
s2, s4 = P.seeds_of(by2, "main", fitc), P.seeds_of(by4, "gen", testc)
tf = P.Table(by2, fitc, "BASE", s2, list(e2["agents"]))
tt = P.Table(by4, testc, "BASE", s4, list(e4["agents"]))
curve, vt = P.fit(tf.pick(s2), fitc), tt.pick(s4)
groups = {"열화 5조건 (SHAM 제외)": [c for c in testc if c != "SHAM"], "6조건 전체 (SHAM 포함)": testc}
rng = np.random.default_rng(0)
boots = {(y, g): [] for y in ("D", "M") for g in list(groups) + testc}
for _ in range(P.N_BOOT):
    cb = P.fit(tf.pick(list(rng.choice(s2, len(s2)))), fitc)
    vb = tt.pick(list(rng.choice(s4, len(s4))))
    for y, i in (("D", 1), ("M", 2)):
        r = {c: vb[c][i] - P.pred(cb, y, vb[c][0]) for c in testc}
        for c in testc:
            boots[(y, c)].append(r[c])
        for g, cs in groups.items():
            boots[(y, g)].append(np.mean([r[c] for c in cs]))
print(f"E2 시드 {len(s2)}개, E4 시드 {len(s4)}개 ({', '.join(s4)}), δ_D {tol['D']:.3f}, δ_M {tol['M']:.2f}")
print("| 조건 | 추종 오차 | D 실제 | D 예측 | D 오차 [95 % CI] | M 실제 | M 예측 | M 오차 [95 % CI] |")
print("|---|---|---|---|---|---|---|---|")
for c in testc:
    mae, D, M = vt[c]
    lo, hi = np.percentile(boots[("D", c)], [2.5, 97.5])
    lm, hm = np.percentile(boots[("M", c)], [2.5, 97.5])
    print(f"| {c} | {mae:.2f} | {D:.3f} | {P.pred(curve, 'D', mae):.3f} | {D - P.pred(curve, 'D', mae):+.3f} "
          f"[{lo:+.3f}, {hi:+.3f}] | {M:.2f} | {P.pred(curve, 'M', mae):.2f} | {M - P.pred(curve, 'M', mae):+.2f} "
          f"[{lm:+.2f}, {hm:+.2f}] |")
print("\n| 묶음 | D 평균 오차 [95 % CI] | D 판정 | M 평균 오차 [95 % CI] | M 판정 |")
print("|---|---|---|---|---|")
for g in groups:
    row = []
    for y in ("D", "M"):
        a = np.array(boots[(y, g)])
        lo, hi = np.percentile(a, [2.5, 97.5])
        row.append(f"{a.mean():+.3f} [{lo:+.3f}, {hi:+.3f}] | {P.judge(lo, hi, tol[y])}")
    print(f"| {g} | " + " | ".join(row) + " |")
