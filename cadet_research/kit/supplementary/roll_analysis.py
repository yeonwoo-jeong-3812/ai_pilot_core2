"""롤 맛보기 분석 (탐색, 판정 아님). 기준은 roll_pilot.py 머리말에 실행 전에 적어 둔 것 그대로.

D 와 피치 오차(전체)는 본실험 원자료(시드 8개 × 시나리오 3개)에서, 롤 오차는 맛보기(main-0, neutral)에서 온다.
맛보기 한 부분만 쓴 효과를 따로 보려고 피치 오차도 맛보기에서 잰 값(P_sub, PR_sub)으로 한 번 더 비교한다."""
import collections
import csv
import os
import sys

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # kit/supplementary → kit
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
import predict as P  # noqa: E402
from experiments import EXPERIMENTS  # noqa: E402

KEY = ("cond", "blue", "red", "scenario", "salt")
pilot = list(csv.DictReader(open(os.path.join(HERE, "roll_pilot_games.csv"), encoding="utf-8")))
main = list(csv.DictReader(open(os.path.join(KIT, "out", "main", "games.csv"), encoding="utf-8")))
rec = {tuple(r[k] for k in KEY): r for r in main if r["target"] == ""}

# 1. 결정론: 다시 돈 판이 기록과 같은가
same = sum(rec[tuple(p[k] for k in KEY)]["winner"] == p["winner"]
           and rec[tuple(p[k] for k in KEY)]["condition"] == p["condition"]
           and all(abs(float(rec[tuple(p[k] for k in KEY)][c]) - float(p[c])) < 1e-4 for c in ("blue_mae_q_dps", "red_mae_q_dps"))
           for p in pilot)
print(f"1. 결정론: 다시 돈 {len(pilot)}판 중 {same}판이 기록과 같음 (승자·종료 사유·피치 오차)")

# 2. 조건별 롤·피치 오차 (맛보기)
e2, e3 = EXPERIMENTS["E2"], EXPERIMENTS["E3"]
fitc = [c for c in e2["conds"] if c != "BASE"]
testc = [c for c in e3["conds"] if c != "BASE"]
by = collections.defaultdict(list)
for p in pilot:
    by[p["cond"]].append(p)


def m(c, k):
    v = [float(g[f"blue_{k}"]) for g in by[c]] + [float(g[f"red_{k}"]) for g in by[c]]
    return float(np.mean(v)), float(np.std(v, ddof=1) / np.sqrt(len(v)))


roll = {c: m(c, "mae_p_dps") for c in ["BASE"] + fitc + testc}
pq_sub = {c: m(c, "mae_q_dps")[0] for c in ["BASE"] + fitc + testc}
rcorr = {c: m(c, "corr_p")[0] for c in ["BASE"] + fitc + testc}
rcmd = {c: m(c, "cmd_p_dps")[0] for c in ["BASE"] + fitc + testc}

# 본실험 전체의 D, 피치 오차
bym = P.load("main")
seeds = P.seeds_of(bym, "main", fitc)
v = P.Table(bym, fitc + testc, "BASE", seeds, list(e2["agents"])).pick(seeds)

print("\n2. 조건별 (롤은 맛보기 56판×2기체, ± 는 표준오차)")
print("| 조건 | 피치 오차 (전체) | 롤 오차 | 롤 오차 − BASE | 롤 추종 상관 | D (전체) |")
print("|---|---|---|---|---|---|")
for c in ["BASE"] + fitc + testc:
    D = v[c][1] if c != "BASE" else 0.0
    mp = v[c][0] if c != "BASE" else float(np.mean([float(g[k]) for s in seeds for g in bym[("BASE", s)]
                                                     for k in ("blue_mae_q_dps", "red_mae_q_dps")]))
    print(f"| {c} | {mp:.2f} | {roll[c][0]:.2f} ± {roll[c][1]:.2f} | {roll[c][0] - roll['BASE'][0]:+.2f} | "
          f"{rcorr[c]:.3f} | {D:.3f} |")

# 3. 모형 비교: E2 로 적합, E3 예측
def fitpred(X_fit, y_fit, X_test):
    A = np.column_stack([np.ones(len(X_fit)), X_fit])
    coef, *_ = np.linalg.lstsq(A, y_fit, rcond=None)
    return coef, np.column_stack([np.ones(len(X_test)), X_test]) @ coef


def loo(X, y):
    e = []
    for i in range(len(y)):
        k = np.arange(len(y)) != i
        _, p = fitpred(X[k], y[k], X[i:i + 1])
        e.append(y[i] - p[0])
    return float(np.sqrt(np.mean(np.square(e))))


yF = np.array([v[c][1] for c in fitc]); yT = np.array([v[c][1] for c in testc])
pF = np.array([v[c][0] for c in fitc]); pT = np.array([v[c][0] for c in testc])
psF = np.array([pq_sub[c] for c in fitc]); psT = np.array([pq_sub[c] for c in testc])
rF = np.array([roll[c][0] for c in fitc]); rT = np.array([roll[c][0] for c in testc])
models = {
    "P   피치만 (등록 곡선과 같은 모양)": (pF[:, None], pT[:, None]),
    "PR  피치 + 롤": (np.column_stack([pF, rF]), np.column_stack([pT, rT])),
    "S   (피치 + 롤) 한 변수": ((pF + rF)[:, None], (pT + rT)[:, None]),
    "P_sub  피치만 (맛보기에서 잰 피치)": (psF[:, None], psT[:, None]),
    "PR_sub 피치 + 롤 (둘 다 맛보기)": (np.column_stack([psF, rF]), np.column_stack([psT, rT])),
}
print(f"\n3. E2 안에서 피치 오차와 롤 오차의 상관: {np.corrcoef(pF, rF)[0, 1]:.3f}  (1 에 가까우면 둘의 몫을 나눌 수 없다)")
print("| 모형 | 계수 | E2 LOO RMS | E3 RMS | E3 평균 오차 | κ 묶음 | k_q 묶음 | 잡음 묶음 | 동기 지연 묶음 | 조합 | k_q 0.25 | κ 50 | κ 2 |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
base_rms = None
res = {}
for name, (XF, XT) in models.items():
    coef, pr = fitpred(XF, yF, XT)
    e = yT - pr
    res[name] = e
    rms = float(np.sqrt(np.mean(e ** 2)))
    if name.startswith("P "):
        base_rms = rms
    grp = {g: np.mean([e[i] for i, c in enumerate(testc) if P.cause(c) == g]) for g in ("kappa", "kq", "sigma_dps", "delay_sync", "조합")}
    pick = {c: e[testc.index(c)] for c in ("R_kq_0.25", "R_kappa_50", "R_kappa_2")}
    print(f"| {name} | {', '.join(f'{x:+.4f}' for x in coef)} | {loo(XF, yF):.3f} | {rms:.3f} | {e.mean():+.3f} | "
          + " | ".join(f"{grp[g]:+.3f}" for g in grp) + " | " + " | ".join(f"{pick[c]:+.3f}" for c in pick) + " |")

print("\n4. 미리 정한 판단 (기준 모형 P 의 E3 RMS 대비)")
for name, e in res.items():
    if name.startswith(("PR ", "S ")):
        red = 1 - float(np.sqrt(np.mean(e ** 2))) / base_rms
        verdict = "의미 있게 나아짐" if red >= 0.20 else ("나아지지 않음" if red < 0.05 else "약간")
        change = f"{red * 100:.1f} % 감소" if red >= 0 else f"{-red * 100:.1f} % 증가 (나빠짐)"
        print(f"  {name}: RMS {change} → {verdict}")
red_sub = 1 - float(np.sqrt(np.mean(res['PR_sub 피치 + 롤 (둘 다 맛보기)'] ** 2))) / float(np.sqrt(np.mean(res['P_sub  피치만 (맛보기에서 잰 피치)'] ** 2)))
print(f"  (참고) 둘 다 맛보기에서 잰 값끼리: PR_sub 는 P_sub 대비 RMS {red_sub * 100:+.1f} % 감소")
