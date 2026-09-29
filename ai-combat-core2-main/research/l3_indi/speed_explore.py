"""명령 실현 충실도 탐색 분석 (개정 A35 준비).

성격: **탐색이다.** 효과 크기와 CI 만 낸다. 등가성·차이 판정은 하지 않는다.
A31 의 `dogfight_analysis.py` 는 그대로 두고 계보를 분리한다.

내는 것
  1. 설정별 짝 차이(평균·중앙·95% CI)와 |z| 순위 — 반응 속도 지표가 기존 지표 사이에서 어디에 들어가는지
  2. corr_q 와 반응 속도 지표가 같이 움직이는지 (설정 단위 상관)
  3. SHAM 짝 차이 분포 = 잡음 바닥 → δ 후보
  4. WEZ 누적 발생률 (60/120/180 s) — 검열 지표 t_first_wez 의 대체
  5. 사슬 표: (반응 속도, 조준, 교전) 세 값을 나란히

사용: python research/l3_indi/speed_explore.py results/paper/dogfight_speed/<commit10>
"""
from __future__ import annotations

import csv
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

N_BOOT = 10_000
BOOT_SEED = 20260929
PAIR_KEY = ("scenario", "red", "salt")
BASE, SHAM = "BASE", "SHAM"
STR_COLS = ("match_id", "setting_name", "family", "variable", "level", "red", "red_path",
            "blue_policy", "scenario", "salt", "winner", "condition", "indi_side")

# 1 순위 = 명령 실현 충실도, 2 순위 = 조준, 3 순위 = 교전 결과, 그 외 = 보조
SPEED = ("reach63_q", "ss_ratio_q", "t63_q", "t90_q", "tau_eq_q", "tau_eq_p")
AIM = ("frac_ata30_blue",)
OUTCOME = ("net_wez", "blue_pts", "hp_diff_d8")
AUX = ("corr_q", "J_q", "J_p", "q_gain", "sat_ele", "n_event_q", "n_event_p",
       "wez_censored_blue", "xcorr_peak_q")
ALL_METRICS = SPEED + AIM + OUTCOME + AUX
WEZ_MARKS = (60.0, 120.0, 180.0)
TIME_COLS = ("t63_q", "t90_q", "tau_eq_q", "tau_eq_p")   # δ 바닥 = 1 틱
TICK = 1.0 / 120.0
# 개정 A35 §5 에 등록된 δ = max(SHAM p95 × 2, 실용 바닥). 확증 실행에서만 쓴다 (--judge).
DELTA = {"reach63_q": 0.03125, "ss_ratio_q": 0.01, "t63_q": TICK, "t90_q": 0.02, "tau_eq_q": TICK}
POSITIVE = "V3_lam_25"                 # A35 §5: 1 순위의 양성 대조는 이것 하나


def load(run_dir: str):
    rows = []
    with open(os.path.join(run_dir, "runs.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
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


def boot(d: np.ndarray, seed=BOOT_SEED):
    """짝 차이 평균의 부트스트랩 95% CI. 중앙값도 함께."""
    d = np.asarray([x for x in d if np.isfinite(x)], float)
    if len(d) < 3:
        return dict(n=len(d), mean=np.nan, median=np.nan, lo=np.nan, hi=np.nan, z=np.nan)
    rng = np.random.default_rng(seed)
    m = np.mean(d[rng.integers(0, len(d), size=(N_BOOT, len(d)))], axis=1)
    lo, hi = float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))
    se = (hi - lo) / (2 * 1.959964)
    return dict(n=len(d), mean=float(np.mean(d)), median=float(np.median(d)),
                lo=lo, hi=hi, z=(abs(np.mean(d)) / se if se > 0 else np.nan))


def paired(rows, setting: str, col: str):
    key = lambda r: tuple(r[k] for k in PAIR_KEY)
    base = {key(r): r for r in rows if r["setting_name"] == BASE}
    out = []
    for r in rows:
        if r["setting_name"] != setting:
            continue
        b = base.get(key(r))
        if b is None:
            continue
        a, c = r.get(col, np.nan), b.get(col, np.nan)
        if np.isfinite(a) and np.isfinite(c):
            out.append(a - c)
    return np.array(out, float)


def wez_incidence(rows, setting: str, t: float) -> float:
    """t 초 안에 WEZ 에 진입한 경기 비율. 검열에 안전하다 (t_first_wez 대체)."""
    R = [r for r in rows if r["setting_name"] == setting]
    if not R:
        return float("nan")
    hit = sum(1 for r in R if r.get("wez_censored_blue", 1) < 0.5
              and r.get("t_first_wez_blue", 1e9) <= t)
    return hit / len(R)


def judge(lo: float, hi: float, d: float) -> str:
    """A31 dogfight_analysis.judge 와 같은 3 분법."""
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return "판정 불가"
    if lo >= -d and hi <= d:
        return "차이 없음"
    if lo > d or hi < -d:
        return "차이 있음"
    return "판정 불가"


def verdict_table(res, others):
    """A35 §5 판정. **1 순위 지표에만** 적용한다."""
    ok = {c: judge(res[(POSITIVE, c)]["lo"], res[(POSITIVE, c)]["hi"], DELTA[c]) == "차이 있음"
          for c in DELTA}
    cal = {c: judge(res[(SHAM, c)]["lo"], res[(SHAM, c)]["hi"], DELTA[c]) == "차이 없음"
           for c in DELTA}
    print("\n## 6. 판정 (1 순위 지표만, A35 §5 의 δ)\n")
    print(f"- 양성 대조 {POSITIVE}: " + ", ".join(f"{c} {'검출' if ok[c] else '**미검출**'}" for c in DELTA))
    print("- 가짜 짝 SHAM: " + ", ".join(f"{c} {'통과' if cal[c] else '**실패**'}" for c in DELTA))
    print("\n| 설정 | " + " | ".join(f"{c} (δ={DELTA[c]:.5g})" for c in DELTA) + " |")
    print("|---|" + "---|" * len(DELTA))
    for s in others:
        cells = []
        for c in DELTA:
            r = res[(s, c)]
            v = judge(r["lo"], r["hi"], DELTA[c])
            if not cal[c]:
                v = "제외(가짜 짝 보정 실패)"
            elif not ok[c] and v == "차이 없음":
                v = "판정 불가(둔감 지표)"
            cells.append(f"{r['mean']:+.4f} **{v}**")
        print(f"| {s} | " + " | ".join(cells) + " |")


def main(run_dir: str, do_judge: bool = False):
    rows = load(run_dir)
    settings = [s for s in dict.fromkeys(r["setting_name"] for r in rows)]
    others = [s for s in settings if s != BASE]
    commit = os.path.basename(os.path.normpath(run_dir))
    n_base = sum(1 for r in rows if r["setting_name"] == BASE)
    print(f"# 명령 실현 충실도 탐색 — {commit}")
    print(f"- 경기 {len(rows)}, 설정 {len(settings)}, 기준 {BASE} {n_base} 경기. "
          f"짝 = 같은 (시나리오, 레드, 솔트). **판정 없음, 효과 크기만.**\n")

    # ---------------------------------------------------------------- 1. SHAM 잡음 바닥
    print("## 1. SHAM 잡음 바닥 (δ 후보)\n")
    print("| 지표 | 짝 | \|Δ\| p50 | \|Δ\| p95 | 최대 | δ 후보 = p95×2 |")
    print("|---|---|---|---|---|---|")
    floor = {}
    for col in SPEED + AIM + OUTCOME:
        d = np.abs(paired(rows, SHAM, col))
        d = d[np.isfinite(d)]
        if not len(d):
            continue
        p95 = float(np.percentile(d, 95))
        # 시간 차원 지표는 1 틱(1/120 s)보다 작은 δ 를 쓸 수 없다
        dlt = max(2 * p95, 1.0 / 120.0) if col in TIME_COLS else 2 * p95
        floor[col] = dlt
        print(f"| {col} | {len(d)} | {np.percentile(d,50):.5g} | {p95:.5g} | {d.max():.5g} | {dlt:.5g} |")

    # ---------------------------------------------------------------- 2. 전체 순위
    res = {}
    for s in others:
        for col in ALL_METRICS:
            res[(s, col)] = boot(paired(rows, s, col))
    rank = sorted((k for k in res if np.isfinite(res[k]["z"])), key=lambda k: -res[k]["z"])
    n_tests = len(rank)
    zb = 0.0
    lo, hi = 0.0, 10.0
    for _ in range(200):                      # Bonferroni z 임계
        mid = (lo + hi) / 2
        p = 2 * (1 - 0.5 * (1 + math.erf(mid / math.sqrt(2))))
        lo, hi = (mid, hi) if p > 0.05 / max(n_tests, 1) else (lo, mid)
    zb = (lo + hi) / 2
    print(f"\n## 2. 효과 크기 순위 (검정 {n_tests} 개, Bonferroni z 임계 {zb:.2f})\n")
    print("| 순위 | 설정 | 지표 | 층 | 평균 차 | 95% CI | \\|z\\| | Bonf |")
    print("|---|---|---|---|---|---|---|---|")
    layer = lambda c: ("**1 속도**" if c in SPEED else "2 조준" if c in AIM
                       else "3 교전" if c in OUTCOME else "보조")
    for i, (s, col) in enumerate(rank[:25], 1):
        r = res[(s, col)]
        print(f"| {i} | {s} | {col} | {layer(col)} | {r['mean']:+.4g} | "
              f"[{r['lo']:+.4g}, {r['hi']:+.4g}] | {r['z']:.2f} | {'통과' if r['z'] >= zb else '-'} |")
    nspeed = sum(1 for k in rank[:25] if k[1] in SPEED)
    print(f"\n- 상위 25 개 중 1 순위(속도) 지표: **{nspeed} 개**")

    # ---------------------------------------------------------------- 3. corr_q 와의 관계
    print("\n## 3. corr_q 와 반응 속도가 같이 움직이는가 (설정 단위)\n")
    print("| 속도 지표 | corr_q 효과와의 상관 r | 해석 |")
    print("|---|---|---|")
    cq = np.array([res[(s, "corr_q")]["mean"] for s in others], float)
    for col in ("reach63_q", "ss_ratio_q", "t63_q", "tau_eq_q"):
        v = np.array([res[(s, col)]["mean"] for s in others], float)
        ok = np.isfinite(cq) & np.isfinite(v)
        r = float(np.corrcoef(cq[ok], v[ok])[0, 1]) if ok.sum() > 2 else np.nan
        tag = ("표본 부족" if not np.isfinite(r) else
               "같은 것을 잼" if abs(r) > 0.8 else
               "부분적으로 다름" if abs(r) > 0.5 else "**다른 것을 잼**")
        print(f"| {col} | {r:+.3f} | {tag} |")

    # ---------------------------------------------------------------- 4. WEZ 누적 발생률
    print("\n## 4. WEZ 누적 발생률 (검열 지표 t_first_wez 대체)\n")
    print("| 설정 | 60 s | 120 s | 180 s | 전체(미진입 비율) |")
    print("|---|---|---|---|---|")
    for s in settings:
        cens = np.mean([r["wez_censored_blue"] for r in rows if r["setting_name"] == s])
        cells = " | ".join(f"{100*wez_incidence(rows, s, t):.1f}%" for t in WEZ_MARKS)
        print(f"| {s} | {cells} | {100*cens:.1f}% |")

    # ---------------------------------------------------------------- 5. 사슬 표
    print("\n## 5. 사슬 — 1 순위 차이가 2·3 순위로 전달되는가\n")
    print("| 설정 | reach63_q | ss_ratio_q | frac_ata30 | net_wez | 승률 [%p] | 사슬 |")
    print("|---|---|---|---|---|---|---|")
    order = sorted(others, key=lambda s: -(res[(s, "reach63_q")]["z"] if np.isfinite(res[(s, "reach63_q")]["z"]) else -1))
    for s in order:
        g = lambda c: res[(s, c)]
        sig = lambda c: np.isfinite(g(c)["lo"]) and (g(c)["lo"] > 0 or g(c)["hi"] < 0)
        spd = sig("reach63_q") or sig("ss_ratio_q")
        aim = sig("frac_ata30_blue")
        out = sig("net_wez") or sig("blue_pts")
        chain = ("전달" if spd and aim and out else
                 "부분 전달" if spd and (aim or out) else
                 "**끊김**" if spd else "속도 변화 없음")
        wr = g("blue_pts")["mean"] / 3.0 * 100.0     # no_contact 무승부 = 0 점이므로 승률로 환산
        print(f"| {s} | {g('reach63_q')['mean']:+.4f} | {g('ss_ratio_q')['mean']:+.4f} | "
              f"{g('frac_ata30_blue')['mean']:+.4f} | {g('net_wez')['mean']:+.3f} | {wr:+.1f} | {chain} |")
    print("\n- 사슬 판정은 CI 가 0 을 제외하는지로만 표시한 **기술 통계**다. 등가성 판정이 아니다.")
    print("- 승률 [%p] = 승점 평균차 ÷ 3 × 100. `blue_points` 는 no_contact 무승부를 0 점으로 준다.")
    if do_judge:
        verdict_table(res, others)
    return 0


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("-")]
    if not a:
        sys.exit("사용: speed_explore.py <결과 폴더> [--judge]")
    raise SystemExit(main(a[0], "--judge" in sys.argv))
