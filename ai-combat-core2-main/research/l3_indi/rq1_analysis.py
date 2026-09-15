"""실험 1 분석 — 사전등록 §7.1·§9 RQ1, 개정 A11-2·A13 을 그대로 구현한다 (결과를 보기 전에 커밋).

  1. 3구간 판정 (임계 1.5, 민감도 1.3 / 2.0), 제외 규칙
  2. 안정 핵 탐색 + 함수형 ANOVA 변동 분해 (블록별), 블록 요약
  3. 튜닝된 INDI (대조군 b) 선택
  4. 부호 반전 가설, ε–J Spearman, M2b 스트레스 표, 대표 조건 안정 지도

사용: python research/l3_indi/rq1_analysis.py <results/paper/rq1/<commit10>>
출력: 같은 폴더의 analysis/ + research/l3_indi/reports/RQ1_<commit10>.md
"""
from __future__ import annotations

import csv
import itertools
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi import metrics as M                                # noqa: E402
from l3_indi.rq1 import KP, KQ, KR, FILT                        # noqa: E402

THRESH = 1.5
SENS = (1.3, 2.0)
BASE = (1.0, 1.0, 1.0, 25.0)
FACTORS = ("kp", "kq", "kr", "filt")
LEVELS = {"kp": KP, "kq": KQ, "kr": KR, "filt": FILT}
MAIN_MANS = ("M1_0.7", "M1_0.8", "M1_0.9", "M2a", "M3_0.7", "M3_0.9")
NUM = ("fbw", "alt_ft", "kcas", "kp", "kq", "kr", "filt")


def mtype(man: str) -> str:
    return man.split("_")[0]


def band_keys(man: str) -> tuple:
    t = mtype(man)
    if t == "M1":
        return ("nz_overshoot", "nz_settle_s", "J_q")
    if t in ("M2a", "M2b"):
        return ("bank_overshoot_deg", "bank_settle_s", "J_p")
    return ("nz_overshoot", "nz_settle_s", "bank_overshoot_deg", "bank_settle_s", "J_p", "J_q")


def primary_metrics(man: str) -> tuple:
    t = mtype(man)
    return {"M1": ("J_q",), "M2a": ("J_p",), "M2b": ("J_p",), "M3": ("J_p", "J_q")}[t]


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def load(run_dir: str) -> list[dict]:
    rows = list(csv.DictReader(open(os.path.join(run_dir, "runs.csv"), encoding="utf-8")))
    for r in rows:
        for k, v in list(r.items()):
            if k == "man":
                continue
            r[k] = fnum(v)
        r["fbw"] = int(r["fbw"])
    return rows


def pkey(r) -> tuple:
    return (r["kp"], r["kq"], r["kr"], r["filt"])


def block_key(r) -> tuple:
    return (r["fbw"], r["alt_ft"], r["kcas"], r["man"])


# --------------------------------------------------------------------------------------
# 1. 3구간
# --------------------------------------------------------------------------------------
def exclusion(r) -> str:
    if r["departure"] >= 1:
        return "departure"
    if mtype(r["man"]) == "M1" and r.get("bank_pre_unsettled", 0) >= 1:
        return "bank_pre_unsettled"
    if r["capability_limited"] >= 1:
        return "capability_limited"
    return ""


def classify_all(rows: list[dict]) -> None:
    ref = {}
    for r in rows:
        if (r["kp"], r["kq"], r["kr"]) == (1.0, 1.0, 1.0):
            ref[block_key(r) + (r["filt"],)] = r
    for r in rows:
        r["excluded"] = exclusion(r)
        base = ref.get(block_key(r) + (r["filt"],))
        rho = {}
        for k in band_keys(r["man"]):
            if base is None:
                rho[k] = float("nan")
            elif k.startswith("J_"):
                a, b = r[k], base[k]
                rho[k] = (a / b) if (np.isfinite(a) and np.isfinite(b) and b > 0) else \
                    (float("inf") if np.isfinite(b) else float("nan"))
            else:
                rho[k] = M.floored_ratio(k, r[k], base[k])
            r[f"rho_{k}"] = rho[k]
        unstable = r["oscillating"] >= 1 or r["g_exceeded"] >= 1
        for th, col in ((THRESH, "band"), (SENS[0], "band_1.3"), (SENS[1], "band_2.0")):
            if unstable:
                r[col] = "unstable"
            elif any(not np.isfinite(v) and not math.isinf(v) for v in rho.values()):
                r[col] = "no_ref"
            elif max(rho.values()) > th:
                r[col] = "degraded"
            else:
                r[col] = "stable"


# --------------------------------------------------------------------------------------
# 2. 안정 핵 + fANOVA
# --------------------------------------------------------------------------------------
def grid(block_rows: list[dict], value) -> np.ndarray:
    idx = {f: {v: i for i, v in enumerate(LEVELS[f])} for f in FACTORS}
    G = np.full(tuple(len(LEVELS[f]) for f in FACTORS), np.nan)
    for r in block_rows:
        G[tuple(idx[f][r[f]] for f in FACTORS)] = value(r)
    return G


def intervals(n: int):
    return [(a, b) for a in range(n) for b in range(a + 1, n)]


def find_core(ok: np.ndarray):
    """ok: 4D bool. 반환 ((lo,hi)×4) 또는 None. 개정 A13-5."""
    bad = (~ok).astype(np.int64)
    S = np.zeros(tuple(s + 1 for s in bad.shape), np.int64)
    S[1:, 1:, 1:, 1:] = bad.cumsum(0).cumsum(1).cumsum(2).cumsum(3)
    base_idx = [LEVELS[f].index(b) for f, b in zip(FACTORS, BASE)]
    best, best_key = None, None
    for box in itertools.product(*(intervals(n) for n in bad.shape)):
        tot = 0
        for corner in itertools.product((0, 1), repeat=4):
            ix = tuple(box[d][1] + 1 if c else box[d][0] for d, c in enumerate(corner))
            tot += (-1) ** (4 - sum(corner)) * S[ix]
        if tot != 0:
            continue
        cells = int(np.prod([b - a + 1 for a, b in box]))
        n_base = sum(a <= bi <= b for (a, b), bi in zip(box, base_idx))
        key = (-cells, -n_base, box)
        if best_key is None or key < best_key:
            best, best_key = box, key
    return best


def fanova(Y: np.ndarray) -> dict:
    """완전요인 격자의 직교 분해 기여율 {부분집합(축 tuple): 비율}."""
    mu = float(Y.mean())
    var = float(((Y - mu) ** 2).mean())
    axes = tuple(range(Y.ndim))
    g = {}
    for k in range(Y.ndim + 1):
        for S in itertools.combinations(axes, k):
            other = tuple(a for a in axes if a not in S)
            g[S] = Y.mean(axis=other, keepdims=True) if other else Y
    frac = {}
    for k in range(1, Y.ndim + 1):
        for S in itertools.combinations(axes, k):
            f = sum((-1) ** (len(S) - len(T)) * g[T]
                    for j in range(len(S) + 1) for T in itertools.combinations(S, j))
            frac[S] = float((np.broadcast_to(f, Y.shape) ** 2).mean() / var) if var > 0 else float("nan")
    return frac


def term_name(S) -> str:
    return "×".join(FACTORS[a] for a in S)


# --------------------------------------------------------------------------------------
def pct(a, q):
    a = [x for x in a if np.isfinite(x)]
    return float(np.percentile(a, q)) if a else float("nan")


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 3:
        return float("nan"), int(len(x))

    def rank(v):
        order = np.argsort(v, kind="mergesort")
        r = np.empty(len(v))
        r[order] = np.arange(len(v), dtype=float)
        for val in np.unique(v):
            m = v == val
            r[m] = r[m].mean()
        return r
    rx, ry = rank(x), rank(y)
    return float(np.corrcoef(rx, ry)[0, 1]), int(len(x))


def main():
    run_dir = sys.argv[1]
    commit = os.path.basename(os.path.normpath(run_dir))
    out = os.path.join(run_dir, "analysis")
    os.makedirs(out, exist_ok=True)
    rows = load(run_dir)
    classify_all(rows)
    L = []                                          # 보고서 줄

    def emit(s=""):
        L.append(s)

    blocks = defaultdict(list)
    for r in rows:
        blocks[block_key(r)].append(r)

    emit(f"# RQ1 결과 — 실험 커밋 {commit}\n")
    emit(f"- 런 {len(rows)}개, 블록 {len(blocks)}개 (FLCS × 조건 × 기동 변형). 판정 임계 {THRESH} (민감도 {SENS}).")
    emit("- 규칙: PREREGISTRATION §7.1·§9, 개정 A9·A11·A12·A13. 이 파일은 `rq1_analysis.py` 가 자동 생성한다.\n")

    # ---- 1. 제외·3구간 집계
    emit("## 1. 제외 런과 3구간 분포\n")
    emit("| FLCS | 기동 | 런 | 이탈 | M1 뱅크 사전 미정착 | 능력 제한 | 미정착 플래그 | 안정 | 열화 | 불안정 | 기준 없음 | 안정(1.3) | 안정(2.0) |")
    emit("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for fbw in (0, 1):
        for man in MAIN_MANS + ("M2b",):
            R = [r for r in rows if r["fbw"] == fbw and r["man"] == man]
            c = lambda f: sum(1 for r in R if f(r))
            emit(f"| {'on' if fbw == 0 else 'off'} | {man} | {len(R)} | {c(lambda r: r['excluded']=='departure')} | "
                 f"{c(lambda r: r['excluded']=='bank_pre_unsettled')} | {c(lambda r: r['excluded']=='capability_limited')} | "
                 f"{c(lambda r: r['unsettled']>=1)} | {c(lambda r: r['band']=='stable')} | {c(lambda r: r['band']=='degraded')} | "
                 f"{c(lambda r: r['band']=='unstable')} | {c(lambda r: r['band']=='no_ref')} | "
                 f"{c(lambda r: r['band_1.3']=='stable')} | {c(lambda r: r['band_2.0']=='stable')} |")
    cap_blocks = sorted({(r["fbw"], r["alt_ft"], r["kcas"], r["man"]) for r in rows
                         if r["excluded"] == "capability_limited" and r["man"] != "M2b"})
    emit(f"\n- 능력 제한 런이 있는 주 분석 블록 (M2b 제외): {len(cap_blocks)}개 "
         f"{[(('on' if b[0]==0 else 'off'), int(b[1]/1000), int(b[2]), b[3]) for b in cap_blocks][:20]}")

    # 인자 수준별 안정 비율
    emit("\n### 인자 수준별 안정 비율 (주 분석 기동, 제외 런 빼고)\n")
    emit("| FLCS | 인자 | " + " | ".join("수준" for _ in range(6)) + " |")
    emit("|---|---|" + "---|" * 6)
    for fbw in (0, 1):
        R = [r for r in rows if r["fbw"] == fbw and r["man"] in MAIN_MANS and not r["excluded"]]
        for f in FACTORS:
            cells = []
            for lv in LEVELS[f]:
                S = [r for r in R if r[f] == lv]
                cells.append(f"{lv:g}: {100*np.mean([r['band']=='stable' for r in S]):.0f}%" if S else "")
            cells += [""] * (6 - len(cells))
            emit(f"| {'on' if fbw == 0 else 'off'} | {f} | " + " | ".join(cells) + " |")

    # ---- 2. 안정 핵 + 분해
    emit("\n## 2. 안정 핵과 변동 분해 (개정 A13-5·6)\n")
    term_rows, core_rows = [], []
    for bk, R in sorted(blocks.items()):
        fbw, alt, kcas, man = bk
        if man == "M2b":
            continue
        ok = grid(R, lambda r: float(r["band"] == "stable" and not r["excluded"]
                                     and all(np.isfinite(r[m]) for m in primary_metrics(man)))) == 1.0
        core = find_core(ok)
        crow = {"fbw": fbw, "alt_kft": int(alt / 1000), "kcas": int(kcas), "man": man,
                "stable_cells": int(ok.sum()), "core": "none" if core is None else json.dumps(
                    {f: [LEVELS[f][a], LEVELS[f][b]] for f, (a, b) in zip(FACTORS, core)}),
                "core_cells": 0 if core is None else int(np.prod([b - a + 1 for a, b in core]))}
        core_rows.append(crow)
        if core is None:
            continue
        sl = tuple(slice(a, b + 1) for a, b in core)
        for metric in primary_metrics(man):
            Y = grid(R, lambda r: r[metric])[sl]
            frac = fanova(Y)
            tr = {"fbw": fbw, "alt_kft": int(alt / 1000), "kcas": int(kcas), "man": man, "metric": metric,
                  "core_cells": crow["core_cells"], "J_mean": float(Y.mean()), "J_sd": float(Y.std())}
            for S, v in frac.items():
                tr[term_name(S)] = v
            for i, fa in enumerate(FACTORS):
                tr[f"total_{fa}"] = sum(v for S, v in frac.items() if i in S)
            tr["dominant"] = max(FACTORS, key=lambda fa: tr[f"total_{fa}"]) if np.isfinite(tr["total_kp"]) else ""
            term_rows.append(tr)
    for name, data in (("cores.csv", core_rows), ("fanova_terms.csv", term_rows)):
        if data:
            keys = list(data[0].keys()) if name == "cores.csv" else sorted({k for d in data for k in d},
                                                                            key=lambda k: (k not in term_rows[0], k))
            with open(os.path.join(out, name), "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=keys)
                w.writeheader()
                w.writerows(data)
    n_core = sum(1 for c in core_rows if c["core"] != "none")
    emit(f"- 핵이 있는 블록 {n_core}/{len(core_rows)}. 핵 크기(칸) p10/p50/p90: "
         f"{pct([c['core_cells'] for c in core_rows if c['core']!='none'],10):.0f} / "
         f"{pct([c['core_cells'] for c in core_rows if c['core']!='none'],50):.0f} / "
         f"{pct([c['core_cells'] for c in core_rows if c['core']!='none'],90):.0f} (전체 450)")
    emit(f"- 핵 없음 블록: {[(('on' if c['fbw']==0 else 'off'), c['alt_kft'], c['kcas'], c['man']) for c in core_rows if c['core']=='none']}\n")
    terms = [term_name(S) for k in (1, 2, 3) for S in itertools.combinations(range(4), k)]
    emit("### 기여율 요약 — (FLCS, 기동 유형, 지표) 별 블록 중앙값 [p10–p90]\n")
    groups = defaultdict(list)
    for tr in term_rows:
        groups[(tr["fbw"], mtype(tr["man"]), tr["metric"])].append(tr)
    for gk, T in sorted(groups.items()):
        emit(f"**FLCS {'on' if gk[0]==0 else 'off'} · {gk[1]} · {gk[2]}** — 블록 {len(T)}개, "
             f"총효과 1위 인자 블록 수 {dict(sorted(defaultdict(int, {f: sum(1 for t in T if t['dominant']==f) for f in FACTORS}).items()))}\n")
        emit("| 항 | 중앙값 | p10 | p90 |")
        emit("|---|---|---|---|")
        for tn in ("total_kp", "total_kq", "total_kr", "total_filt") + tuple(terms) + ("kp×kq×kr×filt",):
            vals = [t.get(tn, float("nan")) for t in T]
            label = {"kp×kq×kr×filt": "4원(나머지)"}.get(tn, tn)
            emit(f"| {label} | {100*pct(vals,50):.1f}% | {100*pct(vals,10):.1f}% | {100*pct(vals,90):.1f}% |")
        emit("")

    # ---- 3. 튜닝된 INDI
    emit("## 3. 튜닝된 INDI — 대조군 (b) (개정 A11-2, A13-7)\n")
    on_main = [r for r in rows if r["fbw"] == 0 and r["man"] in MAIN_MANS]
    base_J = {(r["alt_ft"], r["kcas"], r["man"]): r for r in on_main if pkey(r) == BASE}
    by_p = defaultdict(list)
    for r in on_main:
        by_p[pkey(r)].append(r)
    cands = []
    n_blocks = len(base_J)
    for p, R in by_p.items():
        if len(R) != n_blocks:
            continue
        if not all(r["band"] == "stable" and r["departure"] < 1 and r["unsettled"] < 1
                   and r.get("bank_pre_unsettled", 0) < 1 for r in R):
            continue
        logs = []
        for r in R:
            b = base_J[(r["alt_ft"], r["kcas"], r["man"])]
            for m in primary_metrics(r["man"]):
                logs.append(math.log(r[m] / b[m]))
        gm = math.exp(float(np.mean(logs)))
        dist = sum(abs(math.log(v / bv)) for v, bv in zip(p, BASE))
        cands.append((gm, dist, p))
    cands.sort(key=lambda c: (round(c[0], 6), c[1]))
    tuned = cands[0][2] if cands else BASE
    emit(f"- 전 블록 안정 조건을 만족한 설정 {len(cands)}개 / 450.")
    emit(f"- **선택: k 배율 (p, q, r) = ({tuned[0]:g}, {tuned[1]:g}, {tuned[2]:g}), filt {tuned[3]:g} Hz** "
         f"— 주 지표 비율 기하평균 {cands[0][0]:.4f}" if cands else "- 조건을 만족한 설정이 없어 (b) = (a)")
    emit("\n| 순위 | k_p | k_q | k_r | filt | 기하평균 J 비율 | 기준과 거리 |")
    emit("|---|---|---|---|---|---|---|")
    for i, (gm, dist, p) in enumerate(cands[:10]):
        emit(f"| {i+1} | {p[0]:g} | {p[1]:g} | {p[2]:g} | {p[3]:g} | {gm:.4f} | {dist:.3f} |")
    with open(os.path.join(out, "tuned.json"), "w", encoding="utf-8") as fh:
        json.dump({"tuned": tuned, "n_candidates": len(cands),
                   "top": [{"gm": c[0], "dist": c[1], "params": c[2]} for c in cands[:20]]}, fh, indent=1)

    # ---- 4. 부호 반전 가설
    emit("\n## 4. 부호 반전 가설 (§9 RQ1-5, 개정 A13-8)\n")
    emit("| FLCS | 조건 | M1_0.7 | M1_0.8 | M1_0.9 | 부호가 수준 간 다름 |")
    emit("|---|---|---|---|---|---|")
    n_rev, n_tot = 0, 0
    for fbw in (0, 1):
        for (alt, kcas) in sorted({(r["alt_ft"], r["kcas"]) for r in rows}):
            signs, cells = [], []
            for lv in ("M1_0.7", "M1_0.8", "M1_0.9"):
                R = [r for r in rows if r["fbw"] == fbw and r["alt_ft"] == alt and r["kcas"] == kcas and r["man"] == lv
                     and r["kp"] == 1.0 and r["kr"] == 1.0 and r["filt"] == 25.0 and r["band"] == "stable"
                     and not r["excluded"]]
                if len(R) < 2:
                    cells.append("n<2"); continue
                x = np.array([r["kq"] for r in R]); y = np.array([r["nz_overshoot"] for r in R])
                slope = float(np.polyfit(x, y, 1)[0])
                s = 0 if abs(slope) < 0.01 else int(np.sign(slope))
                signs.append(s)
                cells.append(f"{slope:+.3f} ({'+' if s > 0 else '−' if s < 0 else '0'}, n={len(R)})")
            nz = {s for s in signs if s != 0}
            rev = len(nz) > 1
            n_rev += int(rev); n_tot += 1
            emit(f"| {'on' if fbw==0 else 'off'} | {int(alt/1000)}k/{int(kcas)} | " + " | ".join(cells) + f" | {'예' if rev else '아니오'} |")
    emit(f"\n- 부호가 수준 간 달라진 조건: {n_rev}/{n_tot}")

    # ---- 5. ε–J Spearman
    emit("\n## 5. 시간척도 분리 잔차 ε 와 J (개정 A10-1 (a), A13-9)\n")
    emit("| FLCS | 쌍 | Spearman ρ | n (블록) |")
    emit("|---|---|---|---|")
    for fbw in (0, 1):
        B = [r for r in rows if r["fbw"] == fbw and pkey(r) == BASE and not r["excluded"] and r["man"] in MAIN_MANS]
        for label, sel, e, j in (("M1: ε_q–J_q", "M1", "eps_q", "J_q"), ("M2a: ε_p–J_p", "M2a", "eps_p", "J_p"),
                                 ("M3: ε_p–J_p", "M3", "eps_p", "J_p"), ("M3: ε_q–J_q", "M3", "eps_q", "J_q")):
            S = [r for r in B if mtype(r["man"]) == sel]
            rho, n = spearman([r[e] for r in S], [r[j] for r in S])
            emit(f"| {'on' if fbw==0 else 'off'} | {label} | {rho:.3f} | {n} |")

    # ---- 6. M2b 스트레스
    emit("\n## 6. M2b (180 deg/s 반전) 스트레스 결과 — 주 분석 아님\n")
    emit("| FLCS | 런 | 능력 제한 | 안정 | 열화 | 불안정 | 이탈 | 기준 파라미터 J_p 중앙값 | 전체 J_p p10/p50/p90 (이탈 제외) |")
    emit("|---|---|---|---|---|---|---|---|---|")
    for fbw in (0, 1):
        R = [r for r in rows if r["fbw"] == fbw and r["man"] == "M2b"]
        ok = [r for r in R if r["departure"] < 1]
        emit(f"| {'on' if fbw==0 else 'off'} | {len(R)} | {sum(r['capability_limited']>=1 for r in R)} | "
             f"{sum(r['band']=='stable' for r in R)} | {sum(r['band']=='degraded' for r in R)} | "
             f"{sum(r['band']=='unstable' for r in R)} | {sum(r['departure']>=1 for r in R)} | "
             f"{pct([r['J_p'] for r in R if pkey(r)==BASE],50):.3f} | "
             f"{pct([r['J_p'] for r in ok],10):.3f} / {pct([r['J_p'] for r in ok],50):.3f} / {pct([r['J_p'] for r in ok],90):.3f} |")

    # ---- 7. 대표 조건 안정 지도
    emit("\n## 7. 안정 지도 — 대표 조건 14 kft / 350 KCAS (S 안정, D 열화, X 불안정, - 제외)\n")
    mark = lambda r: "-" if r["excluded"] else {"stable": "S", "degraded": "D", "unstable": "X", "no_ref": "?"}[r["band"]]
    for fbw in (0, 1):
        for man, vary in (("M1_0.8", "kq"), ("M2a", "kp"), ("M3_0.9", "kq")):
            fixed = {f: 1.0 for f in ("kp", "kq", "kr") if f != vary}
            emit(f"**FLCS {'on' if fbw==0 else 'off'} · {man} · 행 filt, 열 {vary} (나머지 배율 1)**\n")
            emit("```")
            emit("filt\\" + vary + "  " + "  ".join(f"{v:>4g}" for v in LEVELS[vary]))
            for f in FILT:
                cells = []
                for v in LEVELS[vary]:
                    R = [r for r in rows if r["fbw"] == fbw and r["alt_ft"] == 14000.0 and r["kcas"] == 350.0
                         and r["man"] == man and r["filt"] == f and r[vary] == v
                         and all(r[k] == val for k, val in fixed.items())]
                    cells.append(f"{mark(R[0]) if R else ' ':>4}")
                emit(f"{f:>8g}  " + "  ".join(cells))
            emit("```\n")

    with open(os.path.join(out, "runs_classified.csv"), "w", newline="", encoding="utf-8") as fh:
        keys = sorted({k for r in rows for k in r})
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    rep = os.path.join(HERE, "reports", f"RQ1_{commit}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
