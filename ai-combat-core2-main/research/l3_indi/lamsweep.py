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
import json
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


# ======================================================================================
# 본 스윕 (A27-2) — A24·A25 의 P 팔과 같은 하네스·기동·조건·지표로 λ 만 바꾼다
# ======================================================================================
def sweep_jobs(geoms):
    from l3_indi.ideal_share import open_loop_limits
    from l3_indi import rq3
    lim = open_loop_limits()
    jobs = []
    for kcas in rq3.KCAS_SET:
        L = lim[(rq3.ALT_FT, kcas)]
        for lam in LAM_MAIN + LAM_LOW:
            for g in geoms:
                for e in rq3.ENEMIES:
                    jobs.append({"setting": f"L{lam:g}", "lam_q": lam, "kcas": kcas,
                                 "geom": g["id"], "enemy": e, "kind": "P",
                                 "bank0": g["bank_deg"], "switch_t": 1.0, "flow_intent": "na",
                                 "dur": rq3.DUR_GUIDED, "pdot_max": L["p"], "qdot_max": L["q"],
                                 "_geom": g})
    return jobs


def sweep_job(job):
    from l3_indi import rq3
    return rq3.job_fn(job)


def sweep(geom_path: str):
    from l3_indi.runner import run_experiment
    from l3_indi import rq3
    geoms = json.load(open(geom_path, encoding="utf-8"))
    jobs = sweep_jobs(geoms)
    out = run_experiment("lamsweep", jobs, sweep_job, os.path.join(REPO, "results", "paper"))
    print("->", out, len(jobs), "runs")
    report(out)
    return 0


def report(out_dir: str):
    """λ 별 요약 + 추종 상실 경계 (A29-2)."""
    rows = []
    for r in csv.DictReader(open(os.path.join(out_dir, "runs.csv"), encoding="utf-8")):
        d = dict(r)
        for k, v in r.items():
            if k in ("setting", "geom", "enemy", "kind", "flow_intent"):
                continue
            d[k] = fnum(v)
        rows.append(d)
    rows = [r for r in rows if r.get("excluded", 0) < 1]
    lams = sorted({r["lam_q"] for r in rows})
    med = lambda col, R: float(np.median([r[col] for r in R if np.isfinite(r.get(col, np.nan))]))

    def boundary(thresh):
        """상관 중앙값이 처음으로 기준 아래로 내려가는 λ (전반·후반 중 하나라도)."""
        for lam in [l for l in lams if l >= 1.0]:
            R = [r for r in rows if r["lam_q"] == lam]
            if min(med("corr_early", R), med("corr_late", R)) < thresh:
                return lam
        return float("nan")

    b70, b50, b90 = boundary(0.7), boundary(0.5), boundary(0.9)
    commit = os.path.basename(out_dir)
    L = [f"# λ 밀집 스윕 — 실험 커밋 {commit}", "",
         f"- 규칙: 개정 A27 §2(격자·지표) + A29(상관·추종 상실 경계). 런 {len(rows)} 개, 유도 팔(P) 전용.",
         "- 기동·조건·지표·δ 는 A24·A25 의 P 팔과 **완전히 같고 λ 만 바뀐다**.", "",
         "## 1. λ 별 요약 (조건 45 짝의 중앙값)", "",
         "| λ | 추종 J_q | ATA 최소 [°] | ΔKCAS [kt] | 상관 전반 | 상관 후반 | 명령 대비 응답 | 진동 비율 |",
         "|---|---|---|---|---|---|---|---|"]
    for lam in lams:
        R = [r for r in rows if r["lam_q"] == lam]
        osc = sum(1 for r in R if r.get("oscillating", 0) >= 1) / max(len(R), 1)
        mark = " ◀ 추종 상실 시작" if np.isfinite(b70) and lam == b70 else ""
        L.append(f"| {lam:g}{mark} | {med('J_q', R):.3f} | {med('ata_min', R):.1f} | "
                 f"{med('dkcas', R):+.1f} | {med('corr_early', R):.2f} | {med('corr_late', R):.2f} | "
                 f"{med('q_gain', R):.2f} | {100*osc:.0f}% |")

    L += ["", "## 2. 추종 상실 경계 (A29-2)", "",
          "| 기준 | r | r² (명령이 설명하는 응답 분산) | 경계 λ |", "|---|---|---|---|",
          f"| 민감도(느슨) | 0.5 | 0.25 | {b50:g} |" if np.isfinite(b50) else "| 민감도(느슨) | 0.5 | 0.25 | 없음 |",
          f"| **주 기준** | **0.7** | **0.49** | **{b70:g}** |" if np.isfinite(b70) else "| **주 기준** | **0.7** | **0.49** | 없음 |",
          f"| 민감도(엄격) | 0.9 | 0.81 | {b90:g} |" if np.isfinite(b90) else "| 민감도(엄격) | 0.9 | 0.81 | 없음 |",
          "", "⚠ 이 기준은 양 끝점(λ 1·25)의 상관을 본 상태에서 정했다. 경계가 놓일 중간 λ 값은 보지 않았다(A29-2)."]

    ref = [r for r in rows if r["lam_q"] == 1.0]
    L += ["", "## 3. 조준 이득이 나타나는 구간과 추종이 무너지는 구간", "",
          f"- 기준(λ = 1)의 ATA 최소 중앙값 {med('ata_min', ref):.1f}°, 상관 전반 {med('corr_early', ref):.2f}·후반 {med('corr_late', ref):.2f}, 진동 {100*sum(1 for r in ref if r.get('oscillating', 0) >= 1)/max(len(ref),1):.0f}%."]
    if np.isfinite(b70):
        pre = [l for l in lams if 1.0 < l < b70]
        if pre:
            g = [(l, med("ata_min", [r for r in rows if r["lam_q"] == l])) for l in pre]
            best = min(g, key=lambda x: x[1])
            L.append(f"- 추종 상실 이전 구간(λ 1 ~ {b70:g} 미만)에서 ATA 최소가 가장 작은 λ 는 "
                     f"**{best[0]:g} ({best[1]:.1f}°)** 다. 기준 대비 {best[1] - med('ata_min', ref):+.1f}°.")
            L.append("- 이 값이 등가 한계 2.0° 를 넘는지가 **\"추종을 잃지 않고도 조준이 좋아지는 구간이 있는가\"** 에 대한 답이다.")
    rep = os.path.join(HERE, "reports", f"LAMSWEEP_{commit}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", rep)
    print(f"   추종 상실 경계 λ: 주 기준 {b70}, 민감도 {b50} / {b90}")
    return {"b70": b70, "b50": b50, "b90": b90}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--precheck", action="store_true", help="A27-2 사전 안정성 확인")
    ap.add_argument("--geom", default=None, help="geometries.json 경로 (본 스윕)")
    ap.add_argument("--report", default=None, help="이미 돈 결과 폴더로 보고서만 다시 만든다")
    args = ap.parse_args()
    if args.precheck:
        return precheck()
    if args.report:
        report(args.report)
        return 0
    if args.geom:
        return sweep(args.geom)
    print("--precheck 또는 --geom <geometries.json> 중 하나가 필요하다.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
