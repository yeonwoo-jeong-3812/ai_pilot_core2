"""λ 밀집 스윕 — 사전등록 개정 A27 §2.

목적: 제어효율 모델 오차 λ(= G_model / G_true, 피치 행만 주입)를 촘촘하게 훑어
      **추종 오차 ↔ 조준 이득 ↔ 에너지 손실**의 관계를 곡선으로 제시한다.

  --precheck : 본 스윕 전 안정성 확인 (A27-2). λ {22, 25, 30} × RQ1 9 조건 × 기동 6 종 = 162 런.
               판정은 RQ2 D1 과 같은 정의(oscillating / g_exceeded / departure 중 하나라도 1).
               λ = 25 는 A23-1 에서 불안정 0 이었으므로 재현 확인을 겸한다.
               **λ = 30 의 불안정 비율이 20% 를 넘으면 격자 상한을 22 로 내린다.**
  (기본)     : 본 스윕 — A24·A25 의 P 팔과 같은 하네스·기동·조건·지표로 λ 만 바꾼다.

사용: python research/l3_indi/lamsweep.py --precheck
      python research/l3_indi/lamsweep.py --geom <geometries.json>
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO            # noqa: E402

# A27-2 에서 실행 전에 고정한 격자
LAM_MAIN = (1.0, 1.4, 2.0, 2.8, 4.0, 5.6, 8.0, 11.0, 16.0, 22.0, 30.0)   # 비 √2 로그 11 점
LAM_LOW = (0.5, 0.7)                                                      # λ < 1 별도 계열
PRECHECK_LAMS = (22.0, 25.0, 30.0)
PRECHECK_MANS = ("M1_0.7", "M1_0.8", "M1_0.9", "M2a", "M3_0.7", "M3_0.9")
PRECHECK_ABORT_FRAC = 0.20                                                # λ 30 중단 규칙


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


# ======================================================================================
# 사전 안정성 확인 (A27-2)
# ======================================================================================
def precheck_job(job):
    from l3_indi.evaluate import evaluate
    return evaluate(job)


def precheck():
    from l3_indi.design import rq1_conditions
    from l3_indi.runner import run_experiment
    jobs = []
    for cond in rq1_conditions(0):
        for man in PRECHECK_MANS:
            for lam in PRECHECK_LAMS:
                jobs.append({"fbw": 0, "alt_ft": cond.alt_ft, "kcas": cond.kcas, "man": man,
                             "setting": f"lam{lam:g}", "kp": 1.0, "kq": 1.0, "kr": 1.0,
                             "filt": 25.0, "lam_q": lam})
    out = run_experiment("lam_precheck", jobs, precheck_job, os.path.join(REPO, "results", "paper"))
    rows = list(csv.DictReader(open(os.path.join(out, "runs.csv"), encoding="utf-8")))
    for r in rows:
        for k, v in list(r.items()):
            if k not in ("man", "setting", "osc_freq_axis"):
                r[k] = fnum(v)

    def unstable(r):     # RQ2 D1 과 같은 정의
        return (r.get("oscillating", 0) >= 1 or r.get("g_exceeded", 0) >= 1
                or r.get("departure", 0) >= 1)

    commit = os.path.basename(out)
    L = [f"# λ 밀집 스윕 사전 안정성 확인 — 실험 커밋 {commit}\n",
         "- 규칙: 개정 A27 §2. FLCS on, 기준 게인, 피치 행만 주입(`g0_row_scale=(1, λ, 1)`).",
         "- 불안정 정의는 RQ2 D1 과 동일: `oscillating ≥ 1 or g_exceeded ≥ 1 or departure ≥ 1`.",
         f"- 런 {len(rows)} 개 (λ {len(PRECHECK_LAMS)} × 조건 9 × 기동 {len(PRECHECK_MANS)}).\n",
         "## 1. λ 별 불안정 비율\n",
         "| λ | 런 | 불안정 | 비율 | 진동 | 이탈 | G 초과 | J_q 중앙 | J_q 최대 |",
         "|---|---|---|---|---|---|---|---|---|"]
    frac = {}
    for lam in PRECHECK_LAMS:
        R = [r for r in rows if abs(r["lam_q"] - lam) < 1e-9]
        n_un = sum(1 for r in R if unstable(r))
        frac[lam] = n_un / len(R) if R else float("nan")
        jq = np.array([r["J_q"] for r in R if np.isfinite(r.get("J_q", np.nan))], float)
        L.append(f"| {lam:g} | {len(R)} | {n_un} | {100*frac[lam]:.0f}% | "
                 f"{sum(1 for r in R if r.get('oscillating', 0) >= 1)} | "
                 f"{sum(1 for r in R if r.get('departure', 0) >= 1)} | "
                 f"{sum(1 for r in R if r.get('g_exceeded', 0) >= 1)} | "
                 f"{np.median(jq):.3f} | {jq.max():.3f} |")

    L.append("\n## 2. 기동별 불안정 (λ 별)\n")
    L.append("| 기동 | " + " | ".join(f"λ {l:g}" for l in PRECHECK_LAMS) + " |")
    L.append("|---|" + "---|" * len(PRECHECK_LAMS))
    for man in PRECHECK_MANS:
        cells = []
        for lam in PRECHECK_LAMS:
            R = [r for r in rows if r["man"] == man and abs(r["lam_q"] - lam) < 1e-9]
            cells.append(f"{sum(1 for r in R if unstable(r))}/{len(R)}")
        L.append(f"| {man} | " + " | ".join(cells) + " |")

    L.append("\n## 3. 판정 (A27-2 중단 규칙)\n")
    ok25 = frac.get(25.0, 1.0) == 0.0
    L.append(f"- **λ = 25 재현 확인**: 불안정 {100*frac.get(25.0, float('nan')):.0f}% "
             f"— A23-1(피치 전용 λ_q 25 에서 불안정 0/54)과 {'일치' if ok25 else '**불일치**'}.")
    over = frac.get(30.0, 1.0) > PRECHECK_ABORT_FRAC
    L.append(f"- **λ = 30**: 불안정 {100*frac.get(30.0, float('nan')):.0f}% "
             f"({'20% 초과 → 격자 상한을 22 로 내린다' if over else '20% 이하 → 격자 상한 30 유지'}).")
    L.append(f"\n**결정: 본 스윕 격자 상한 = {22 if over else 30}**")

    rep = os.path.join(HERE, "reports", f"LAMPRECHECK_{commit}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", rep)
    for lam in PRECHECK_LAMS:
        print(f"  λ {lam:g}: 불안정 {100*frac[lam]:.0f}%")
    print("  격자 상한 결정:", 22 if over else 30)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--precheck", action="store_true", help="A27-2 사전 안정성 확인")
    args = ap.parse_args()
    if args.precheck:
        return precheck()
    print("본 스윕은 9/22 작업이다. 먼저 --precheck 를 돌려 격자 상한을 확정한다.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
