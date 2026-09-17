"""실험 3 — RQ2 제어효과 모델 오차 λ (사전등록 §7.2·§9 RQ2, 개정 A10·A11-5·A12·A13·A15·A19).

사용: python research/l3_indi/rq2.py                  실행 + 분석
      python research/l3_indi/rq2.py --analyze <results/paper/rq2/<commit10>>
"""
from __future__ import annotations

import csv
import math
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO            # noqa: E402

LAMBDAS = (0.25, 0.35, 0.5, 0.7, 1.0, 1.4, 2.0, 4.0, 10.0, 25.0)
LOW = (0.7, 0.5, 0.35, 0.25)
HIGH = (1.4, 2.0, 4.0, 10.0, 25.0)
AXES = ("p", "q", "r", "all")
MANS = ("M1_0.7", "M1_0.8", "M1_0.9", "M2a", "M3_0.7", "M3_0.9")
THR_F, SENS_F = 2.0, (1.5, 3.0)
THR_M, SENS_M = 0.90, (0.80, 0.95)
RQ1_DIR = os.path.join(REPO, "results", "paper", "rq1", "c45f90998c")


def settings() -> dict:
    """개정 A19-1: 고정 12 + 튜닝 1."""
    s = {}
    for k in (0.5, 0.75, 1.0, 1.5):
        for f in (10.0, 25.0, 50.0):
            s[f"k{k:g}_f{f:g}"] = (k, k, 1.0, f)
    s["tuned"] = (1.0, 1.5, 0.5, 15.0)
    return s


def lam_configs():
    out = [("none", 1.0)]
    for ax in AXES:
        for lam in LAMBDAS:
            if lam != 1.0:
                out.append((ax, lam))
    return out


def jobs():
    from l3_indi.design import rq2_conditions
    out = []
    for fbw in (0, 1):
        for cond in rq2_conditions(fbw):
            for man in MANS:
                for sname, (kp, kq, kr, f) in settings().items():
                    for ax, lam in lam_configs():
                        lp = lam if ax in ("p", "all") else 1.0
                        lq = lam if ax in ("q", "all") else 1.0
                        lr = lam if ax in ("r", "all") else 1.0
                        out.append({"fbw": fbw, "alt_ft": cond.alt_ft, "kcas": cond.kcas, "man": man,
                                    "setting": sname, "kp": kp, "kq": kq, "kr": kr, "filt": f,
                                    "lam_axis": ax, "lam": lam, "lam_p": lp, "lam_q": lq, "lam_r": lr})
    return out


def job_fn(job):
    from l3_indi.evaluate import evaluate
    return evaluate(job)


# --------------------------------------------------------------------------------------
STR_COLS = {"man", "setting", "lam_axis", "osc_freq_axis"}


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def load_rows(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for r in rows:
        for k, v in list(r.items()):
            if k not in STR_COLS:
                r[k] = fnum(v)
        r["fbw"] = int(r["fbw"])
    return rows


def mtype(man):
    return man.split("_")[0]


def primary(man):
    return {"M1": ("J_q",), "M2a": ("J_p",), "M3": ("J_p", "J_q")}[mtype(man)]


def unstable(r):
    return r["oscillating"] >= 1 or r["g_exceeded"] >= 1 or r["departure"] >= 1


def excluded(r):
    return (mtype(r["man"]) == "M1" and r.get("bank_pre_unsettled", 0) >= 1) or r["capability_limited"] >= 1


def interp_log(l1, v1, l2, v2, thr):
    return math.exp(math.log(l1) + (thr - v1) / (v2 - v1) * (math.log(l2) - math.log(l1)))


def lam_s(series, side):
    """series: {λ: run}. 반환 (값, 상태, 구간)."""
    base = series.get(1.0)
    if base is None or unstable(base):
        return (float("nan"), "기준 불안정", None)
    prev = 1.0
    for lam in (LOW if side == "low" else HIGH):
        r = series.get(lam)
        if r is None:
            return (float("nan"), "누락", None)
        if unstable(r):
            return (math.sqrt(prev * lam), "ok", (min(prev, lam), max(prev, lam)))
        prev = lam
    return (float("nan"), "< 0.25" if side == "low" else "> 25", None)


def crossing(series, key, thr, up, side):
    """ρ = key(λ)/key(1) 가 thr 를 (up: 위로 / not up: 아래로) 처음 넘는 λ. 개정 A19-6·7."""
    base = series.get(1.0)
    if base is None or unstable(base) or excluded(base) or not np.isfinite(base[key]) or base[key] <= 0:
        return (float("nan"), "기준 없음", None)
    prev_l, prev_v = 1.0, 1.0
    for lam in (HIGH if side == "high" else LOW):
        r = series.get(lam)
        if r is None:
            return (float("nan"), "누락", None)
        if unstable(r):
            return (lam, "불안정 선행", None)
        if excluded(r):
            return (lam, "판정 불가", None)
        v = r[key] / base[key]
        if (v >= thr) if up else (v < thr):
            return (interp_log(prev_l, prev_v, lam, v, thr), "ok", (min(prev_l, lam), max(prev_l, lam)))
        prev_l, prev_v = lam, v
    return (float("nan"), "> 25" if side == "high" else "< 0.25", None)


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 3:
        return float("nan"), int(len(x))

    def rank(v):
        o = np.argsort(v, kind="mergesort")
        rr = np.empty(len(v))
        rr[o] = np.arange(len(v), dtype=float)
        for val in np.unique(v):
            m = v == val
            rr[m] = rr[m].mean()
        return rr
    return float(np.corrcoef(rank(x), rank(y))[0, 1]), int(len(x))


def fmt_lam(v, st):
    return f"{v:.2f}" if st == "ok" else st


def analyze(run_dir: str):
    from l3_indi import metrics as M
    commit = os.path.basename(os.path.normpath(run_dir))
    rows = load_rows(os.path.join(run_dir, "runs.csv"))
    base_runs = {}
    ser = defaultdict(dict)
    for r in rows:
        k0 = (r["fbw"], r["kcas"], r["man"], r["setting"])
        if r["lam_axis"] == "none":
            base_runs[k0] = r
        else:
            ser[k0 + (r["lam_axis"],)][r["lam"]] = r
    for k, s in ser.items():
        if k[:4] in base_runs:
            s[1.0] = base_runs[k[:4]]

    blocks = []
    for k, s in sorted(ser.items()):
        fbw, kcas, man, setting, ax = k
        ls_lo = lam_s(s, "low")
        ls_hi = lam_s(s, "high")
        for metric in primary(man):
            b = {"fbw": fbw, "kcas": kcas, "man": man, "setting": setting, "axis": ax, "metric": metric,
                 "lam_s": ls_lo[0], "lam_s_status": ls_lo[1], "lam_s_hi": ls_hi[0], "lam_s_hi_status": ls_hi[1]}
            for thr, tag in ((THR_F, ""), (SENS_F[0], "_1.5"), (SENS_F[1], "_3.0")):
                v, st, _ = crossing(s, metric, thr, True, "high")
                b[f"lam_f{tag}"], b[f"lam_f{tag}_status"] = v, st
            eps_key = "eps_q" if metric == "J_q" else "eps_p"
            b["eps_base"] = s[1.0][eps_key] if 1.0 in s else float("nan")
            if mtype(man) in ("M1", "M3") and metric == "J_q":
                for thr, tag in ((THR_M, ""), (SENS_M[0], "_0.80"), (SENS_M[1], "_0.95")):
                    for side in ("high", "low"):
                        v, st, _ = crossing(s, "nz_realization", thr, False, side)
                        b[f"lam_M_{side}{tag}"], b[f"lam_M_{side}{tag}_status"] = v, st
                if b["lam_f_status"] == "ok" and b["lam_M_high_status"] == "ok":
                    b["gap_M_f"] = abs(math.log(b["lam_M_high"]) - math.log(b["lam_f"]))
                else:
                    b["gap_M_f"] = float("nan")
            blocks.append(b)
    keys = sorted({k for b in blocks for k in b})
    with open(os.path.join(run_dir, "blocks.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(blocks)

    L = [f"# RQ2 결과 — 실험 커밋 {commit}\n",
         f"- 런 {len(rows)}, 블록 {len(blocks)} (FLCS × 조건 × 기동 × 설정 × 주입 축 × 지표). 규칙: §7.2·§9 RQ2, 개정 A19.",
         "- λ = G_model / G_true. λ < 1 = 제어기가 효과를 **작게** 믿음(조종면을 과하게 움직임), λ > 1 = **크게** 믿음(덜 움직임).\n"]
    FL = {0: "on", 1: "off"}

    def med(vals):
        v = [x for x in vals if np.isfinite(x)]
        return (float(np.median(v)), len(v)) if v else (float("nan"), 0)

    # 1. 불안정·이탈 개수
    L.append("## 1. 불안정 런 (λ 별, 진동 또는 G 포락선 또는 이탈)\n")
    L.append("| FLCS | " + " | ".join(f"λ {l:g}" for l in LAMBDAS) + " | 이탈 수 |")
    L.append("|---|" + "---|" * (len(LAMBDAS) + 1))
    for fbw in (0, 1):
        cells = []
        for lam in LAMBDAS:
            R = [r for r in rows if r["fbw"] == fbw and r["lam"] == lam]
            cells.append(f"{sum(unstable(r) for r in R)}/{len(R)}")
        L.append(f"| {FL[fbw]} | " + " | ".join(cells) + f" | {sum(r['departure'] >= 1 for r in rows if r['fbw'] == fbw)} |")

    # 2. 안정 임계 λ_s
    L.append("\n## 2. 안정 임계 λ_s (λ < 1) — 상태별 블록 수와 λ_s 중앙값\n")
    L.append("| FLCS | 주입 축 | ok 블록 | λ_s 중앙값 | < 0.25 | 기준 불안정 | λ_s 격자 구간 분포 (0.7–1 / 0.5–0.7 / 0.35–0.5 / 0.25–0.35) |")
    L.append("|---|---|---|---|---|---|---|")
    for fbw in (0, 1):
        for ax in AXES:
            B = [b for b in blocks if b["fbw"] == fbw and b["axis"] == ax]
            ok = [b for b in B if b["lam_s_status"] == "ok"]
            dist = [sum(1 for b in ok if lo <= b["lam_s"] <= hi) for lo, hi in ((0.7, 1.0), (0.5, 0.7), (0.35, 0.5), (0.25, 0.35))]
            L.append(f"| {FL[fbw]} | {ax} | {len(ok)}/{len(B)} | {med([b['lam_s'] for b in ok])[0]:.3f} | "
                     f"{sum(b['lam_s_status']=='< 0.25' for b in B)} | {sum(b['lam_s_status']=='기준 불안정' for b in B)} | "
                     f"{' / '.join(map(str, dist))} |")
    L.append("\n### λ > 1 쪽 불안정 λ_s,hi\n")
    L.append("| FLCS | 주입 축 | ok 블록 | 중앙값 | > 25 |")
    L.append("|---|---|---|---|---|")
    for fbw in (0, 1):
        for ax in AXES:
            B = [b for b in blocks if b["fbw"] == fbw and b["axis"] == ax]
            ok = [b for b in B if b["lam_s_hi_status"] == "ok"]
            L.append(f"| {FL[fbw]} | {ax} | {len(ok)}/{len(B)} | {med([b['lam_s_hi'] for b in ok])[0]:.2f} | "
                     f"{sum(b['lam_s_hi_status']=='> 25' for b in B)} |")

    # 3. 충실도 임계 λ_f
    L.append("\n## 3. 충실도 임계 λ_f (λ > 1, J 가 λ = 1 대비 2 배) — 상태별 블록 수\n")
    L.append("| FLCS | 주입 축 | 지표 | ok | λ_f 중앙값 (1.5 / 2.0 / 3.0) | > 25 | 불안정 선행 | 판정 불가 | 기준 없음 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for fbw in (0, 1):
        for ax in AXES:
            for metric in ("J_p", "J_q"):
                B = [b for b in blocks if b["fbw"] == fbw and b["axis"] == ax and b["metric"] == metric]
                if not B:
                    continue
                c = lambda st, tag="": sum(b[f"lam_f{tag}_status"] == st for b in B)
                m15 = med([b["lam_f_1.5"] for b in B if b["lam_f_1.5_status"] == "ok"])[0]
                m20 = med([b["lam_f"] for b in B if b["lam_f_status"] == "ok"])[0]
                m30 = med([b["lam_f_3.0"] for b in B if b["lam_f_3.0_status"] == "ok"])[0]
                L.append(f"| {FL[fbw]} | {ax} | {metric} | {c('ok')}/{len(B)} | {m15:.2f} / {m20:.2f} / {m30:.2f} | "
                         f"{c('> 25')} | {c('불안정 선행')} | {c('판정 불가')} | {c('기준 없음')} |")

    # 4. 설정 의존성
    L.append("\n## 4. 설정(k, filt) 별 λ_s 와 λ_f 중앙값 — 전 축 주입, 블록 수는 괄호\n")
    L.append("| 설정 | FLCS on λ_s | FLCS on λ_f | FLCS off λ_s | FLCS off λ_f |")
    L.append("|---|---|---|---|---|")
    for sname in settings():
        cells = []
        for fbw in (0, 1):
            B = [b for b in blocks if b["fbw"] == fbw and b["setting"] == sname and b["axis"] == "all"]
            ms, ns = med([b["lam_s"] for b in B if b["lam_s_status"] == "ok"])
            mf, nf = med([b["lam_f"] for b in B if b["lam_f_status"] == "ok"])
            cells += [f"{ms:.3f} ({ns})", f"{mf:.2f} ({nf})"]
        L.append(f"| {sname} | " + " | ".join(cells) + " |")

    # 5. FLCS on/off 차이
    L.append("\n## 5. FLCS on vs off — 같은 (조건, 기동, 설정, 축, 지표) 짝\n")
    idx = {(b["kcas"], b["man"], b["setting"], b["axis"], b["metric"], b["fbw"]): b for b in blocks}
    for name, key in (("λ_s", "lam_s"), ("λ_f", "lam_f")):
        d = []
        for (kc, mn, st, ax, mt, fbw), b in idx.items():
            if fbw != 0:
                continue
            o = idx.get((kc, mn, st, ax, mt, 1))
            if o and b[f"{key}_status"] == "ok" and o[f"{key}_status"] == "ok":
                d.append(math.log(o[key]) - math.log(b[key]))
        L.append(f"- {name}: 짝 {len(d)}개, log(off) − log(on) 중앙값 {np.median(d) if d else float('nan'):+.3f} "
                 f"(= off/on 배율 {math.exp(np.median(d)) if d else float('nan'):.2f})")

    # 6. H2
    L.append("\n## 6. H2 — ε (λ = 1 런) 와 경계 (개정 A10-1(b), A19-8)\n")
    L.append("| FLCS | ρ(ε, log λ_f) (n) | ρ(ε, log λ_s) (n) | 판정 | 검열 블록 λ_f / λ_s |")
    L.append("|---|---|---|---|---|")
    for fbw in (0, 1):
        B = [b for b in blocks if b["fbw"] == fbw]
        okf = [b for b in B if b["lam_f_status"] == "ok"]
        oks = [b for b in B if b["lam_s_status"] == "ok"]
        rf, nf = spearman([b["eps_base"] for b in okf], [math.log(b["lam_f"]) for b in okf])
        rs, ns = spearman([b["eps_base"] for b in oks], [math.log(b["lam_s"]) for b in oks])
        dir_ok = (rf < 0) and (rs > 0)
        verdict = "지지" if dir_ok and abs(rf) >= 0.5 and abs(rs) >= 0.5 else ("약한 지지" if dir_ok else "불지지")
        L.append(f"| {FL[fbw]} | {rf:+.3f} ({nf}) | {rs:+.3f} ({ns}) | **{verdict}** | {len(B)-len(okf)} / {len(B)-len(oks)} |")
    L.append("\n### 동압(KCAS) 별 경계 중앙값 (전 축 주입)\n")
    L.append("| FLCS | KCAS | λ_s | λ_f | ε 중앙값 |")
    L.append("|---|---|---|---|---|")
    for fbw in (0, 1):
        for kc in (250.0, 350.0, 400.0):
            B = [b for b in blocks if b["fbw"] == fbw and b["kcas"] == kc and b["axis"] == "all"]
            L.append(f"| {FL[fbw]} | {kc:g} | {med([b['lam_s'] for b in B if b['lam_s_status']=='ok'])[0]:.3f} | "
                     f"{med([b['lam_f'] for b in B if b['lam_f_status']=='ok'])[0]:.2f} | {med([b['eps_base'] for b in B])[0]:.3f} |")

    # 7. 기동 경계 λ_M
    L.append("\n## 7. 기동 경계 λ_M (Nz 실현율 비 < 0.90) 와 T–M 간격 (개정 A12, A19-7)\n")
    L.append("| FLCS | 주입 축 | λ_M 위쪽 ok (중앙값) | λ_M 아래쪽 ok (중앙값) | 간격 |log λ_M − log λ_f| 중앙값 (n) |")
    L.append("|---|---|---|---|---|")
    for fbw in (0, 1):
        for ax in AXES:
            B = [b for b in blocks if b["fbw"] == fbw and b["axis"] == ax and "lam_M_high" in b]
            hi = [b["lam_M_high"] for b in B if b["lam_M_high_status"] == "ok"]
            lo = [b["lam_M_low"] for b in B if b["lam_M_low_status"] == "ok"]
            g, ng = med([b["gap_M_f"] for b in B])
            L.append(f"| {FL[fbw]} | {ax} | {len(hi)}/{len(B)} ({med(hi)[0]:.2f}) | {len(lo)}/{len(B)} ({med(lo)[0]:.3f}) | {g:.3f} ({ng}) |")

    # 8. Smeur 비대칭
    L.append("\n## 8. Smeur 외(2016) 비대칭 확인 (개정 A19-10)\n")
    by = {(r["fbw"], r["kcas"], r["man"], r["setting"], r["lam_axis"], r["lam"]): r for r in rows}
    for side, lams in (("λ < 1", LOW), ("λ > 1", HIGH)):
        n_hi, n_persist = 0, 0
        for (fbw, kc, mn, st, ax, lam), r in by.items():
            if st != "k1_f25" or lam not in lams or not unstable(r):
                continue
            o = by.get((fbw, kc, mn, "k0.5_f25", ax, lam))
            if o is None:
                continue
            n_hi += 1
            n_persist += int(unstable(o))
        L.append(f"- {side}: 설정 (1,1,1, 25 Hz) 불안정 {n_hi} 건 중 이득을 (0.5, 0.5, 1) 로 낮춰도 불안정 **{n_persist}** "
                 f"({100*n_persist/n_hi:.0f}%)" if n_hi else f"- {side}: 해당 불안정 런 없음")
    for side, cond in (("λ < 1", lambda l: l < 1), ("λ > 1", lambda l: l > 1)):
        fr = [r["osc_freq_hz"] for r in rows if cond(r["lam"]) and r["oscillating"] >= 1]
        m, n = med(fr)
        L.append(f"- {side} 진동 런의 진동 주파수 중앙값 {m:.2f} Hz (n {n})")

    # 9. T→M 전이
    L.append("\n## 9. T→M 전이 — D_T = J_q/J_ref − 1, D_M = 1 − Nz실현율/기준 (개정 A10-2, A12, A19-11)\n")
    pts = defaultdict(lambda: {"rq1": ([], []), "rq2": ([], [])})
    for r in rows:
        if mtype(r["man"]) not in ("M1", "M3") or r["lam_axis"] == "none" or unstable(r) or excluded(r):
            continue
        b = base_runs.get((r["fbw"], r["kcas"], r["man"], r["setting"]))
        if b is None or unstable(b) or excluded(b):
            continue
        g = pts[(mtype(r["man"]), r["fbw"])]["rq2"]
        g[0].append(r["J_q"] / b["J_q"] - 1)
        g[1].append(1 - r["nz_realization"] / b["nz_realization"])
    rq1_rows = load_rows(os.path.join(RQ1_DIR, "runs.csv"))
    ref = {}
    for r in rq1_rows:
        if (r["kp"], r["kq"], r["kr"]) == (1.0, 1.0, 1.0):
            ref[(r["fbw"], r["alt_ft"], r["kcas"], r["man"], r["filt"])] = r
    for r in rq1_rows:
        if mtype(r["man"]) not in ("M1", "M3") or unstable(r) or excluded(r) or (r["kp"], r["kq"], r["kr"]) == (1.0, 1.0, 1.0):
            continue
        b = ref.get((r["fbw"], r["alt_ft"], r["kcas"], r["man"], r["filt"]))
        if b is None or unstable(b) or excluded(b):
            continue
        g = pts[(mtype(r["man"]), r["fbw"])]["rq1"]
        g[0].append(r["J_q"] / b["J_q"] - 1)
        g[1].append(1 - r["nz_realization"] / b["nz_realization"])
    L.append("| 기동 | FLCS | 자료 | n | 판정 | ΔBIC | 힌지 x₀ | 선형 기울기 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for (mt, fbw), d in sorted(pts.items()):
        combos = (("RQ1+RQ2", d["rq1"][0] + d["rq2"][0], d["rq1"][1] + d["rq2"][1]),
                  ("RQ1", d["rq1"][0], d["rq1"][1]), ("RQ2", d["rq2"][0], d["rq2"][1]))
        for label, x, y in combos:
            fit = M.transfer_fit(x, y)
            if fit["verdict"] == "insufficient":
                L.append(f"| {mt} | {FL[fbw]} | {label} | {fit['n']} | 자료 부족 | | | |")
                continue
            L.append(f"| {mt} | {FL[fbw]} | {label} | {fit['n']} | {'임계형' if fit['verdict']=='threshold' else '선형'} | "
                     f"{fit['delta_bic']:.1f} | {fit['x0']:.3f} | {fit['a_linear']:.3f} |")

    rep = os.path.join(HERE, "reports", f"RQ2_{commit}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", rep)


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--analyze":
        analyze(sys.argv[2])
        return 0
    from l3_indi.runner import run_experiment
    out = run_experiment("rq2", jobs(), job_fn, os.path.join(REPO, "results", "paper"))
    print("->", out)
    analyze(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
