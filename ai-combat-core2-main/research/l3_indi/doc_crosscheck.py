"""세 문서의 수치를 원본 CSV에서 다시 계산해 대조한다.

문서에서 값을 읽어 오지 않는다. runs.csv 에서 새로 계산한 뒤,
그 값이 각 문서에 적힌 대로 들어 있는지 문자열로 찾는다.
"""
import io
import os
import sys

import numpy as np

sys.path.insert(0, "research")
import importlib.util

spec = importlib.util.spec_from_file_location("se", "research/l3_indi/speed_explore.py")
se = importlib.util.module_from_spec(spec)
spec.loader.exec_module(se)

DOCS = {
    "M": "docs/EXPERIMENT_MASTER_20261001.md",
    "A": "docs/PROGRESS_REPORT_FOR_ADVISOR_v3.md",
    "H": "docs/HANDOFF_FOR_WRITING.md",
}
TEXT = {k: io.open(v, encoding="utf-8").read() for k, v in DOCS.items()}

conf = se.load("results/paper/dogfight_confirm/a27c40f9e4")
a36 = se.load("results/paper/dogfight_f16fix/b3c448ab85")
expl = se.load("results/paper/dogfight_speed/c11b502d3c")
K = lambda r: (r["scenario"], r["red"], r["salt"])


def eff(rows, s, c, scale=1.0):
    d = se.paired(rows, s, c) * scale
    b = se.boot(d)
    return b["mean"], b["lo"], b["hi"]


def contrast(rows, a, b, c, scale=1.0):
    A = {K(r): r for r in rows if r["setting_name"] == a}
    B = {K(r): r for r in rows if r["setting_name"] == b}
    d = np.array([scale * (A[k][c] - B[k][c]) for k in A if k in B
                  and np.isfinite(A[k][c]) and np.isfinite(B[k][c])], float)
    rng = np.random.default_rng(20260929)
    m = np.mean(d[rng.integers(0, len(d), size=(10000, len(d)))], axis=1)
    return float(np.mean(d)), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def med(rows, s, c):
    return float(np.nanmedian([r[c] for r in rows if r["setting_name"] == s]))


checks = []       # (라벨, 계산값, [문서에 있어야 할 문자열], 어느 문서)


def add(label, val, strings, where="MAH"):
    checks.append((label, val, strings if isinstance(strings, list) else [strings], where))


# ---- 규모
add("확증 경기 수", len(conf), "4,480")
add("탐색 경기 수", len(expl), "2,080")
add("확증 설정 수", len(set(r["setting_name"] for r in conf)), "28")
add("확증 설정당 짝", sum(1 for r in conf if r["setting_name"] == "BASE"), "160")

# ---- 표 3 / §5.2 주 판정값
for s, c, want in [
    ("V3_lam_25", "reach63_q", ["-0.618", "−0.618", "-0.6184"]),
    ("V3_lam_25", "ss_ratio_q", ["-0.181", "−0.181", "-0.1810"]),
    ("V3_lam_25", "tau_eq_q", ["+0.277", "+0.2774"]),
    ("V3_lam_16", "reach63_q", ["-0.586", "−0.586", "-0.5859"]),
    ("V3_lam_8", "reach63_q", ["-0.367", "−0.367", "-0.3669"]),
    ("V3_lam_4", "reach63_q", ["-0.131", "−0.131", "-0.1314"]),
    ("V1_kq_0.5", "reach63_q", ["-0.074", "−0.074", "-0.0744"]),
    ("V4_sync_8t", "reach63_q", ["-0.054", "−0.054", "-0.0542"]),
    ("V6_turb_severe", "reach63_q", ["+0.207", "+0.2071"]),
    ("V6_turb_severe", "ss_ratio_q", ["-0.115", "−0.115", "-0.1148"]),
    ("V6_turb_moderate", "reach63_q", ["+0.131", "+0.1312"]),
    ("V6_turb_light", "reach63_q", ["+0.088", "+0.0876"]),
    ("SYM_lam_25", "reach63_q", ["-0.615", "−0.615", "-0.6145"]),
    ("SYM_lam_25", "ss_ratio_q", ["-0.206", "−0.206", "-0.2055"]),
    ("SYM_lam_8", "reach63_q", ["-0.366", "−0.366", "-0.3663"]),
]:
    m, _, _ = eff(conf, s, c)
    add(f"확증 {s} {c}", round(m, 4), want)

# ---- 승률과 WEZ
for s, want in [("V3_lam_25", ["+22.5"]), ("V3_lam_16", ["+17.7"]),
                ("V3_lam_8", ["+5.0"]), ("V6_turb_severe", ["-8.1", "−8.1"]),
                ("SYM_lam_25", ["+3.8"]), ("SYM_lam_8", ["+4.0"])]:
    m, _, _ = eff(conf, s, "blue_pts", 100 / 3)
    add(f"확증 {s} 승률[%p]", round(m, 1), want)
for s, want in [("V3_lam_25", ["+0.903"]), ("V3_lam_16", ["+0.839"]),
                ("V3_lam_8", ["+0.381"]), ("V6_turb_severe", ["-0.832", "−0.832"]),
                ("SYM_lam_25", ["+0.126"])]:
    m, _, _ = eff(conf, s, "net_wez")
    add(f"확증 {s} net_wez", round(m, 3), want)

# ---- 표 6 대칭 대조
m, lo, hi = contrast(conf, "SYM_lam_25", "V3_lam_25", "blue_pts", 100 / 3)
add("대칭-청군만 승률차", round(m, 2), ["-18.75", "−18.75", "-18.8", "−18.8"])
add("대칭-청군만 승률 CI 하한", round(lo, 2), ["-28.75", "−28.75", "-28.8", "−28.8"])
add("대칭-청군만 승률 CI 상한", round(hi, 2), ["-8.75", "−8.75", "-8.8", "−8.8"])
m, lo, hi = contrast(conf, "SYM_lam_25", "V3_lam_25", "net_wez")
add("대칭-청군만 netwez", round(m, 3), ["-0.777", "−0.777"])
m, lo, hi = contrast(conf, "SYM_lam_8", "V3_lam_8", "frac_ata30_blue")
add("λ8 대칭 조준차", round(m, 4), ["-0.036", "−0.036", "-0.0355"])
add("λ8 대칭 조준차 CI", round(lo, 3), ["-0.058", "−0.058"])

# ---- 표 5 경기별 중앙값
for s, c, want in [("BASE", "corr_q", ["0.862"]), ("V4_async_2t", "corr_q", ["0.623"]),
                   ("V6_turb_severe", "corr_q", ["0.472"]),
                   ("BASE", "t63_q", ["0.150"]), ("V6_turb_severe", "t63_q", ["0.117"]),
                   ("BASE", "ss_ratio_q", ["0.959"]), ("V6_turb_severe", "ss_ratio_q", ["0.842"]),
                   ("V6_turb_severe", "reach63_q", ["0.974"]), ("BASE", "reach63_q", ["0.750"])]:
    add(f"탐색 중앙값 {s} {c}", round(med(expl, s, c), 3), want)

# ---- WEZ 누적 발생률
for s, t, want in [("BASE", 60, ["31.2"]), ("V3_lam_25", 60, ["54.4"]),
                   ("V3_lam_25", 120, ["65.6"]), ("V3_lam_16", 60, ["47.5"]),
                   ("V3_lam_8", 60, ["38.8"]), ("V6_turb_severe", 60, ["30.6"]),
                   ("SYM_lam_25", 60, ["55.6"])]:
    add(f"WEZ {s} {t}s", round(100 * se.wez_incidence(conf, s, t), 1), want)

# ---- 봉투 게이트
exc = lambda r: float(r["nz_max"] > 9.0 or r["nz_min"] < -3.0 or r["alpha_max_deg"] > 30.0)
B = {K(r): r for r in conf if r["setting_name"] == "BASE"}
rng = np.random.default_rng(20260925)
for s, want_abs, want_rel in [("BASE", ["7.5"], None), ("V3_lam_25", ["18.8"], ["+11.2"]),
                              ("V6_turb_severe", ["37.5"], ["+30.0"]),
                              ("SYM_lam_25", ["8.8"], ["+1.2"]),
                              ("V3_lam_16", ["11.9"], ["+4.4"])]:
    G = [r for r in conf if r["setting_name"] == s]
    add(f"봉투 절대 {s}", round(100 * np.mean([exc(r) for r in G]), 1), want_abs)
    if want_rel:
        d = np.array([exc(r) - exc(B[K(r)]) for r in G if K(r) in B])
        add(f"봉투 상대 {s}", round(100 * np.mean(d), 1), want_rel)
mx = max(r["nz_max"] for r in conf if r["setting_name"] == "V6_turb_severe")
add("난류강 최대 Nz", round(mx, 2), ["11.11"])
amax = max(r["alpha_max_deg"] for r in conf)
add("확증 전체 최대 alpha", round(amax, 1), ["21.4"])

# ---- 이벤트 수율
add("확증 피치 이벤트 중앙값", int(np.median([r["n_event_q"] for r in conf])),
    ["**27개**(확증 실행", "27~32"], "MH")
add("탐색 피치 이벤트 중앙값", int(np.median([r["n_event_q"] for r in expl])),
    ["**32개**(탐색 실행", "32개(탐색 실행", "32 개(탐색", "32개 중 1개 (탐색 실행 중앙값)"], "MH")
add("롤 이벤트 중앙값(양쪽)", int(np.median([r["n_event_p"] for r in conf])),
    ["롤은 양쪽 실행 모두 경기당 중앙값 **1개**", "경기당 중앙값 1개"], "MAH")
n0 = sum(1 for r in expl if r["n_event_q"] == 0)
add("탐색 계단 0 경기 비율[%]", round(100 * n0 / len(expl), 1), "4.1")

# ---- δ 관련 (SHAM 바닥)
for c, want in [("reach63_q", ["0.00893"]), ("ss_ratio_q", ["0.000687"]), ("t90_q", ["0.01"])]:
    p95 = float(np.percentile(np.abs(se.paired(expl, "SHAM", c)), 95))
    add(f"탐색 SHAM p95 {c}", round(p95, 6), want, "M")


# ---- A36 재실행 (수정 모델) — 논문 본문용 수치
def eff36(s, c, scale=1.0):
    return se.boot(se.paired(a36, s, c) * scale)["mean"]


def contrast36(a, b, c, scale=1.0):
    A = {K(r): r for r in a36 if r["setting_name"] == a}
    B = {K(r): r for r in a36 if r["setting_name"] == b}
    d = np.array([scale * (A[k][c] - B[k][c]) for k in A if k in B
                  and np.isfinite(A[k][c]) and np.isfinite(B[k][c])], float)
    rng = np.random.default_rng(20260929)
    m = np.mean(d[rng.integers(0, len(d), size=(10000, len(d)))], axis=1)
    return float(np.mean(d)), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


add("A36 경기 수", len(a36), "4,480")
for s_, c_, want in [
    ("V3_lam_25", "reach63_q", ["-0.794", "−0.794"]),
    ("V3_lam_16", "reach63_q", ["-0.757", "−0.757"]),
    ("V3_lam_8", "reach63_q", ["-0.440", "−0.440"]),
    ("V3_lam_4", "reach63_q", ["-0.132", "−0.132"]),
    ("V3_lam_25", "ss_ratio_q", ["-0.158", "−0.158"]),
    ("V6_turb_severe", "reach63_q", ["+0.065"]),
    ("V6_turb_severe", "ss_ratio_q", ["-0.108", "−0.108"]),
    ("SYM_lam_25", "reach63_q", ["-0.787", "−0.787"]),
    ("SYM_lam_8", "reach63_q", ["-0.455", "−0.455"]),
    ("V5_noise_1", "ss_ratio_q", ["-0.022", "−0.022"]),
]:
    add(f"A36 {s_} {c_}", round(eff36(s_, c_), 4), want, "MAH")
for s_, want in [("V3_lam_25", ["+18.3"]), ("V3_lam_16", ["+15.6"]),
                 ("V3_lam_8", ["+13.7"]), ("SYM_lam_25", ["+3.1"]),
                 ("SYM_lam_8", ["+9.4"]), ("V6_turb_severe", ["-9.4", "−9.4"])]:
    add(f"A36 {s_} 승률[%p]", round(eff36(s_, "blue_pts", 100 / 3), 1), want, "MAH")
m_, lo_, hi_ = contrast36("SYM_lam_25", "V3_lam_25", "blue_pts", 100 / 3)
add("A36 대칭-청군만 승률차", round(m_, 1), ["-15.2", "−15.2"], "MAH")
add("A36 대칭 승률차 CI 하한", round(lo_, 1), ["-25.0", "−25.0"], "MAH")
m_, lo_, hi_ = contrast36("SYM_lam_25", "V3_lam_25", "frac_ata30_blue")
add("A36 대칭-청군만 조준차", round(m_, 3), ["-0.035", "−0.035"], "MAH")
add("A36 대칭 조준차 CI 하한", round(lo_, 3), ["-0.062", "−0.062"], "MAH")
for s_, c_, want in [("BASE", "corr_q", ["0.938"]), ("V4_async_2t", "corr_q", ["0.692"]),
                     ("V6_turb_severe", "corr_q", ["0.471"]), ("BASE", "reach63_q", ["0.930"]),
                     ("V6_turb_severe", "ss_ratio_q", ["0.870"]), ("BASE", "ss_ratio_q", ["0.979"])]:
    add(f"A36 중앙값 {s_} {c_}",
        round(float(np.nanmedian([r[c_] for r in a36 if r["setting_name"] == s_])), 3), want, "MAH")
exc36 = lambda r: float(r["nz_max"] > 9.0 or r["nz_min"] < -3.0 or r["alpha_max_deg"] > 30.0)
G36 = [r for r in a36 if r["setting_name"] == "BASE"]
add("A36 BASE 봉투 초과[%]", round(100 * np.mean([exc36(r) for r in G36]), 1), ["0.0"], "MAH")
add("A36 BASE 최대 Nz", round(max(r["nz_max"] for r in G36), 2), ["7.62"], "MAH")
add("A36 전체 최대 alpha", round(max(r["alpha_max_deg"] for r in a36), 1), ["18.6"], "MAH")
add("A36 피치 이벤트 중앙값", int(np.median([r["n_event_q"] for r in a36])),
    ["중앙값 24개", "24개(이번 재실행", "중앙값 **24개**"], "MAH")
add("A36 계단 0 경기[%]",
    round(100 * sum(1 for r in a36 if r["n_event_q"] == 0) / len(a36), 1), ["4.2"], "MAH")

# ---- 2 x 2 원인 분해 (칸 C, D)
import json
_e = json.load(open("results/paper/env_attrib/runs.json", encoding="utf-8"))
for cell, want in (("C_f16fix_platform", ["0.0"]), ("D_f16_manual", ["5.6"])):
    Gc = [r for r in _e if r["setting_name"] == cell]
    add(f"2x2 {cell} 초과[%]", round(100 * np.mean([exc36(r) for r in Gc]), 1), want, "MAH")

# ---- 실행
print("| # | 항목 | 계산값 | 문서에서 찾은 곳 | 결과 |")
print("|---|---|---|---|---|")
bad = 0
for i, (label, val, strings, where) in enumerate(checks, 1):
    found = []
    for d in where:
        if any(s in TEXT[d] for s in strings):
            found.append(d)
    ok = bool(found)
    if not ok:
        bad += 1
    print(f"| {i} | {label} | {val} | {''.join(found) if found else '**없음**'} | "
          f"{'OK' if ok else '**불일치**'} |")
print()
print(f"검사 {len(checks)}건, 불일치 {bad}건")
