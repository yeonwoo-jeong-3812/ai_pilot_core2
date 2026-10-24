"""E4 시드 단위 t 구간 (사후 민감도, 2026-10-21). 등록 판정을 바꾸지 않는다.

  python e4_tinterval.py     # → e4_tinterval_output.md

E4는 시드가 4개뿐이다. P5·P6 실행 전 점검에서 시드 4개의 퍼센타일 부트스트랩이 좁게 나올 수 있음을 봤다
(../../FEEDBACK_FOR_CADET_v8.md §3). 그래서 E4의 주요 수치에 시드 단위 t 구간(자유도 3)을 함께 계산한다.
  가. 절대 D 예측 오차(등록 곡선): 조건별, 열화 5조건 평균, SHAM
  나. 열화끼리의 차이 ΔD 오차(v2 D-3과 같은 쌍 10개)
t 구간 두 가지: (1) 곡선 고정, 시드 간 변동만 (2) 곡선의 불확실성(main 시드 부트스트랩 표준편차)을 더함.
"""
import itertools
import json
import os
import sys

import numpy as np
from scipy import stats

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # kit/supplementary → kit
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import predict as P  # noqa: E402
from experiments import EXPERIMENTS  # noqa: E402

P.SHAPE = "linear"
DELTA = json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))["D"]
e2, e4 = EXPERIMENTS["E2"], EXPERIMENTS["E4"]
fitc = [c for c in e2["conds"] if c != "BASE"]
testc = [c for c in e4["conds"] if c != "BASE"]
deg = [c for c in testc if c != "SHAM"]
by2, by4 = P.load("main"), P.load("gen")
s2, s4 = P.seeds_of(by2, "main", fitc), P.seeds_of(by4, "gen", testc)
tf = P.Table(by2, fitc, "BASE", s2, list(e2["agents"]))
tt = P.Table(by4, testc, "BASE", s4, list(e4["agents"]))


def line(v):
    b, a = np.polyfit([v[c][0] for c in fitc], [v[c][1] for c in fitc], 1)
    return float(a), float(b)


a0, b0 = line(tf.pick(s2))
rng = np.random.default_rng(0)
curves = [line(tf.pick(list(rng.choice(s2, len(s2))))) for _ in range(2000)]
v_all = tt.pick(s4)
per = {s: tt.pick([s]) for s in s4}
pairs = [(i, j) if v_all[i][0] <= v_all[j][0] else (j, i) for i, j in itertools.combinations(deg, 2)]
tq = stats.t.ppf(0.975, len(s4) - 1)


def judge(lo, hi):
    return P.judge(lo, hi, DELTA)


def stat_abs(cs):
    """절대 D 예측 오차의 평균: 점추정, 시드별 값, 곡선 표준편차."""
    f = lambda v, a, b: float(np.mean([v[c][1] - (a + b * v[c][0]) for c in cs]))
    return f(v_all, a0, b0), [f(per[s], a0, b0) for s in s4], float(np.std([f(v_all, a, b) for a, b in curves]))


def stat_dd():
    f = lambda v, b: float(np.mean([(v[j][1] - v[i][1]) - b * (v[j][0] - v[i][0]) for i, j in pairs]))
    return f(v_all, b0), [f(per[s], b0) for s in s4], float(np.std([f(v_all, b) for _, b in curves]))


L = ["# E4 시드 단위 t 구간 (사후 민감도, 등록 판정을 바꾸지 않음)\n",
     f"E4 시드 {', '.join(s4)}, 등록 곡선 D = {a0:.3f} + {b0:.4f}·mae (E2, main 8시드), δ_D {DELTA:.3f}. t 임계값(자유도 3) {tq:.2f}.\n",
     "| 항목 | 점추정 | 시드별 | 퍼센타일 95 % (기존) | t: 곡선 고정 | t: 곡선 불확실성 포함 | 판정: 퍼센타일 / t 고정 / t 포함 |",
     "|---|---|---|---|---|---|---|"]
old = {"열화 5조건 평균": (0.020, 0.074), "SHAM": (-0.167, -0.121), "ΔD 열화끼리 (10쌍)": (-0.027, 0.026)}
rows = [("열화 5조건 평균", stat_abs(deg)), ("SHAM", stat_abs(["SHAM"])), ("ΔD 열화끼리 (10쌍)", stat_dd())]
rows += [(c, stat_abs([c])) for c in deg]
res = {}
for name, (m, ps, sdc) in rows:
    se = np.std(ps, ddof=1) / np.sqrt(len(ps))
    lo1, hi1 = m - tq * se, m + tq * se
    se2 = np.sqrt(se ** 2 + sdc ** 2)
    lo2, hi2 = m - tq * se2, m + tq * se2
    o = old.get(name)
    j0 = judge(*o) if o else "–"
    res[name] = dict(mean=m, per_seed=ps, t_fixed=(lo1, hi1), t_curve=(lo2, hi2), judge_t=judge(lo2, hi2))
    L.append(f"| {name} | {m:+.3f} | {', '.join(f'{x:+.3f}' for x in ps)} | "
             + (f"[{o[0]:+.3f}, {o[1]:+.3f}]" if o else "–")
             + f" | [{lo1:+.3f}, {hi1:+.3f}] | [{lo2:+.3f}, {hi2:+.3f}] | {j0} / {judge(lo1, hi1)} / {judge(lo2, hi2)} |")
L.append("\n퍼센타일 구간은 `e4_boot_output.md`(절대 D)와 `../out/reanalysis_v2`(D-3, ΔD)의 값이다. 판정 규칙은 등록 규칙(95 % 구간 대 ±δ_D)을 그대로 썼다.\n")
txt = "\n".join(L) + "\n"
open(os.path.join(HERE, "e4_tinterval_output.md"), "w", encoding="utf-8").write(txt)
json.dump(res, open(os.path.join(HERE, "e4_tinterval.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(txt)
