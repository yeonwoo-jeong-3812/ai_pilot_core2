"""RQ3 분석 — 사전등록 A24 §9 의 판정 규칙 + A25 의 지표·δ·제외 규칙을 그대로 구현한다.

  짝    : 같은 (KCAS × 기하 × 적 패턴 × 기동)에서 설정만 다른 런. 기준은 S2.
  제외  : departure = 1 이거나 α > 30° 인 런은 짝에서 빼고 개수를 보고한다 (A25-2(c)).
  통계  : 짝 차이 **중앙값**의 부트스트랩 95% CI (짝 단위 재표집 10,000 회, 시드 20260920).
  판정  : CI ⊂ [-δ,+δ] → 차이 없음 / CI ∩ [-δ,+δ] = ∅ → 차이 있음 / 그 외 → 판정 불가.
  양성 대조: S5 vs S2 가 "차이 있음" 이 아닌 지표는 둔감한 지표로 보고,
            그 지표의 "차이 없음" 판정을 전부 "판정 불가" 로 낮춘다.

사용: python research/l3_indi/rq3.py --analyze results/paper/rq3/<commit10>
"""
from __future__ import annotations

import csv
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

SEED = 20260920
NBOOT = 10000
REF = "S2"
STR_COLS = ("setting", "geom", "enemy", "kind", "flow_intent")
PAIR_KEY = ("kcas", "geom", "enemy", "kind")

# 지표 정의 — (열, 표시명, δ, (민감도 하, 상), 검열값 = 창 끝이면 True)
M_ATA_MIN = ("ata_min", "ATA 최소 [deg]", 2.0, (1.0, 5.0), False)
M_ATA30 = ("T_ata30", "T_ATA30 [s]", 0.25, (0.1, 0.5), True)
M_ATA_MEAN = ("ata_mean", "평균 지향오차 [deg]", 2.0, (1.0, 5.0), False)
M_FLOW_DELAY = ("flow_switch_delay_s", "(b) flow 전환 지연 [s]", 0.25, (0.1, 0.5), True)
M_DEV_HDG = ("dev_heading_rms_deg", "(c1) 헤딩 편차 RMS [deg]", 1.0, (0.5, 2.0), False)
M_DEV_POS = ("dev_pos_end_ft", "(c2) 위치 편차 [ft]", 50.0, (25.0, 100.0), False)
M_PSI90 = ("T_psi90", "T_psi90 [s]", 0.25, (0.1, 0.5), True)
M_PSI180 = ("T_psi180", "T_psi180 [s]", 0.25, (0.1, 0.5), True)

# 팔(arm) = 기동 묶음. (표시명, 기동 목록, 주 지표, 보조 열)
ARMS = [
    ("P", "주 실험 — 배치 유도(lead pursuit) 추격", ("P",),
     [M_ATA_MIN, M_ATA30, M_ATA_MEAN],
     ["T_ata10", "T_wez", "wez_s", "range_min_ft", "q_gain", "nz_mean", "J_q", "dkcas", "dalt_ft"]),
    ("B", "기동유형 실현 충실도 — 개루프 시퀀스", ("B",),
     [M_FLOW_DELAY, M_DEV_HDG, M_DEV_POS],
     ["flow_match_frac", "J_p", "J_q", "dkcas", "dalt_ft"]),
    ("A", "부록 음성 대조 — 유도 없는 개루프 당김", ("A",),
     [M_ATA_MIN, M_ATA30, M_ATA_MEAN],
     ["T_ata10", "wez_s", "J_q", "dkcas"]),
    ("C", "보조 — 선회율 경쟁(적 없음)", ("C_45", "C_70"),
     [M_PSI90, M_PSI180],
     ["J_q", "dkcas", "dalt_ft"]),
    ("D", "부록 롤 지배 대조", ("D",),
     [M_ATA_MIN, M_ATA_MEAN],
     ["J_p", "dev_heading_rms_deg", "dkcas"]),
]


def _load(run_dir: str):
    rows = []
    for r in csv.DictReader(open(os.path.join(run_dir, "runs.csv"), encoding="utf-8")):
        d = dict(r)
        for k, v in r.items():
            if k in STR_COLS:
                continue
            try:
                d[k] = float(v)
            except (TypeError, ValueError):
                d[k] = float("nan")
        rows.append(d)
    return rows


def boot_median_ci(d: np.ndarray, nboot=NBOOT, seed=SEED):
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(nboot, len(d)))
    meds = np.median(d[idx], axis=1)
    return float(np.median(d)), float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))


def rank_biserial(d: np.ndarray) -> float:
    """짝 순위 이연 상관 = (양의 부호순위합 - 음의 부호순위합) / 전체 순위합. 0 인 차이는 제외."""
    nz = d[d != 0]
    if not len(nz):
        return 0.0
    order = np.argsort(np.abs(nz), kind="mergesort")
    ranks = np.empty(len(nz))
    ranks[order] = np.arange(1, len(nz) + 1)
    return float((ranks[nz > 0].sum() - ranks[nz < 0].sum()) / ranks.sum())


def verdict(lo: float, hi: float, delta: float) -> str:
    if lo >= -delta and hi <= delta:
        return "차이 없음"
    if lo > delta or hi < -delta:
        return "차이 있음"
    return "판정 불가"


def compare(rows, col, delta, sens, is_time, kinds):
    """기준 S2 대비 설정별 짝 차이. 이탈 런(excluded=1)은 짝에서 제외."""
    by, dropped = {}, 0
    for r in rows:
        if r["kind"] not in kinds:
            continue
        if r.get("excluded", 0) >= 1:
            dropped += 1
            continue
        by[(r["setting"],) + tuple(str(r[k]) for k in PAIR_KEY)] = r
    settings = sorted({r["setting"] for r in rows} - {REF})
    out = []
    for s in settings:
        diffs, cens, lost = [], 0, 0
        for key, ref in by.items():
            if key[0] != REF:
                continue
            other = by.get((s,) + key[1:])
            if other is None:
                lost += 1
                continue
            a, b = other.get(col, np.nan), ref.get(col, np.nan)
            if not (np.isfinite(a) and np.isfinite(b)):
                continue
            if is_time and (a >= other["dur"] - 1e-9 or b >= ref["dur"] - 1e-9):
                cens += 1
            diffs.append(a - b)
        d = np.array(diffs, float)
        if len(d) < 3:
            out.append({"setting": s, "n": int(len(d)), "verdict": "표본 부족",
                        "censored": cens, "unpaired": lost})
            continue
        med, lo, hi = boot_median_ci(d)
        out.append({"setting": s, "n": int(len(d)), "censored": cens, "unpaired": lost,
                    "median": med, "lo": lo, "hi": hi, "verdict": verdict(lo, hi, delta),
                    "rb": rank_biserial(d), "verdict_lo": verdict(lo, hi, sens[0]),
                    "verdict_hi": verdict(lo, hi, sens[1]), "max_abs": float(np.max(np.abs(d)))})
    return out, dropped


def analyze(run_dir: str, label="RQ3"):
    from l3_indi import metrics as M
    rows = _load(run_dir)
    commit = os.path.basename(os.path.normpath(run_dir))
    settings = sorted({r["setting"] for r in rows})
    have = {r["kind"] for r in rows}
    L = [f"# {label} 결과 — 실험 커밋 {commit}\n",
         f"- 런 {len(rows)} 개, 설정 {settings}, 기준 {REF}. 판정 규칙·δ 는 A24 §9 와 A25 §2 에서 실행 전 고정한 그대로다.",
         f"- 이탈 제외 규칙(A25): departure=1 또는 α > 30° → 짝에서 제외. 전체 이탈 런 "
         f"{sum(1 for r in rows if r.get('excluded', 0) >= 1)}/{len(rows)} 개.\n"]
    js = {"commit": commit, "n_runs": len(rows), "arms": {}}

    for arm, title, kinds, prim, aux in ARMS:
        kinds = tuple(k for k in kinds if k in have)
        if not kinds:
            continue
        sub = [r for r in rows if r["kind"] in kinds]
        L.append(f"## [{arm}] {title}  (기동 {list(kinds)}, 런 {len(sub)} 개)\n")
        js["arms"][arm] = {"metrics": {}, "insensitive": {}}
        for col, name, delta, sens, is_time in prim:
            res, dropped = compare(rows, col, delta, sens, is_time, kinds)
            s5 = next((x for x in res if x["setting"] == "S5"), None)
            insens = not (s5 and s5.get("verdict") == "차이 있음")
            if insens:
                for x in res:
                    if x.get("verdict") == "차이 없음":
                        x["verdict"] = "판정 불가"
                        x["downgraded"] = True
            js["arms"][arm]["metrics"][col] = res
            js["arms"][arm]["insensitive"][col] = insens
            L.append(f"### {name} — δ = {delta:g} (민감도 {sens[0]:g}/{sens[1]:g})")
            if insens:
                L.append("⚠ **둔감 지표**: 양성 대조 S5 가 차이를 내지 못함 → 이 지표의 '차이 없음' 은 모두 '판정 불가' 로 낮춤.")
            L.append("")
            L.append("| 설정 | n | 중앙 차이 | 95% CI | 판정 | 민감도(하/상) | 순위 이연 | 최대 |차이| | 검열 | 짝 실패 |")
            L.append("|---|---|---|---|---|---|---|---|---|---|")
            for x in res:
                if x["verdict"] == "표본 부족":
                    L.append(f"| {x['setting']} | {x['n']} | - | - | 표본 부족 | - | - | - | "
                             f"{x['censored']} | {x['unpaired']} |")
                    continue
                L.append(f"| {x['setting']} | {x['n']} | {x['median']:+.3f} | [{x['lo']:+.3f}, {x['hi']:+.3f}] | "
                         f"**{x['verdict']}** | {x['verdict_lo']} / {x['verdict_hi']} | {x['rb']:+.2f} | "
                         f"{x['max_abs']:.3f} | {x['censored']} | {x['unpaired']} |")
            L.append("")
        # 보조 열: 설정별 중앙값
        L.append("**보조 지표 (설정별 중앙값, 판정 없음)**\n")
        L.append("| 지표 | " + " | ".join(settings) + " |")
        L.append("|---|" + "---|" * len(settings))
        for col in aux:
            cells = []
            for s in settings:
                v = np.array([r[col] for r in sub
                              if r["setting"] == s and np.isfinite(r.get(col, np.nan))], float)
                cells.append(f"{np.median(v):.3f}" if len(v) else "-")
            L.append(f"| {col} | " + " | ".join(cells) + " |")
        L.append("")

    # T층 → M층 (유도 팔)
    if "P" in have:
        L.append("## T층 → M층 전이 (A24-9)\n")
        by = {}
        for r in rows:
            if r["kind"] == "P" and r.get("excluded", 0) < 1:
                by[(r["setting"],) + tuple(str(r[k]) for k in PAIR_KEY)] = r
        for col, name in (("ata_min", "ATA 최소"), ("ata_mean", "평균 지향오차"), ("T_ata30", "T_ATA30")):
            d_t, d_m = [], []
            for key, r in by.items():
                if key[0] == REF:
                    continue
                ref = by.get((REF,) + key[1:])
                if ref is None or not (np.isfinite(r.get(col, np.nan)) and np.isfinite(ref.get(col, np.nan))):
                    continue
                d_t.append(r["J_q"] - ref["J_q"])
                d_m.append(r[col] - ref[col])
            fit = M.transfer_fit(d_t, d_m)
            if fit.get("verdict") == "insufficient":
                L.append(f"- {name}: 짝 {fit['n']} 개 — 적합 불가")
            else:
                extra = f", 임계 x0 = {fit['x0']:.3f}" if fit["verdict"] == "threshold" else ""
                L.append(f"- {name}: n = {fit['n']}, 선형 기울기 {fit['a_linear']:+.3f} (ΔJ_q 1 당), "
                         f"판정 **{fit['verdict']}**{extra}")
        L.append("")
        pl = np.array([r["plane_off_t1_deg"] for r in rows
                       if np.isfinite(r.get("plane_off_t1_deg", np.nan))])
        if len(pl):
            L.append(f"- 평면 이탈각(t = 1 s) 중앙 {np.median(pl):.1f}°, p95 {np.percentile(pl, 95):.1f}° "
                     "— 적을 양력 평면에 놓았다는 설계 근사의 점검값.")

    rep = os.path.join(HERE, "reports", f"{label}_{commit}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    with open(os.path.join(run_dir, "rq3_analysis.json"), "w", encoding="utf-8") as fh:
        json.dump(js, fh, ensure_ascii=False, indent=1)
    print("->", rep)
    return js
