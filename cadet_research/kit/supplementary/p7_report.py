"""P7 분석 (사전 등록 ../../PREREG_P7.md). p7_run.py 가 부른다. 단독: python p7_run.py --report

조건 고르기 (탐침 결과를 보기 전에 정함, select()):
  지연형: 비동기 지연 2·4·6·8·10·12틱 (필터 25 Hz) 6조건 전부
  둔한 지연형: 후보 κ 8·25·50·100, k_q 0.25 중 탐침 mae 가 지연형 6조건의 탐침 mae 범위 안에 드는 것을,
             그 범위의 로그 중앙에 가까운 순서로 최대 2개
판정
  T7-1 (주) 지연형 6조건의 D–mae 기울기가 등록 기울기 0.0531과 같은가: 차이의 95 % 구간이 ±0.020(P6과 같은 여유) 안이면 "같다",
       전체가 밖이면 "다르다", 그 밖 "판정 불가". 퍼센타일 부트스트랩과 시드 단위 t 구간(자유도 7)이 같을 때만 결론
  T7-2 (보조) 등록 곡선(원래 구성)이 실제형의 D를 맞히는가: 지연형 6조건 평균 오차, 등록 판정 규칙(95 % 구간 대 ±δ_D)
  T7-3 (보조) 같은 mae에서 둔한 지연형이 결과를 더 바꾸는가: 실제형 지연형 직선(6조건)에 대한 둔한 지연형 잔차 평균,
       95 % 구간 하한 > 0 이면 "확인", 상한 < 0 이면 "반대", 그 밖 "판정 불가". 두 구간 방식이 같을 때만 결론
"""
from __future__ import annotations

import collections
import csv
import json
import os

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
DELAY = ["F25_D2", "F25_D4", "F25_D6", "F25_D8", "F25_D10", "F25_D12"]
SLUG_CAND = ["R_kappa_8", "R_kappa_25", "R_kappa_50", "R_kappa_100", "R_kq_0.25"]
B_REG = 0.05309285306453424
A_REG = 0.14380045578818365
EQ = 0.020
N_BOOT = 2000


def _read(p):
    return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.isfile(p) else []


def select():
    """탐침 결과로 조건을 고정하고 p7_conds.json 에 쓴다 (규칙은 위 docstring, 탐침 전에 정함)."""
    rows = _read(os.path.join(HERE, "p7_probe_games.csv"))
    mae = collections.defaultdict(list)
    for r in rows:
        mae[r["cond"]] += [float(r["blue_mae_q_dps"]), float(r["red_mae_q_dps"])]
    m = {c: float(np.mean(v)) for c, v in mae.items()}
    lo, hi = min(m[c] for c in DELAY), max(m[c] for c in DELAY)
    mid = np.exp((np.log(lo) + np.log(hi)) / 2)
    inside = [c for c in SLUG_CAND if lo <= m[c] <= hi]
    slug = sorted(inside, key=lambda c: abs(np.log(m[c]) - np.log(mid)))[:2]
    sel = dict(conds=DELAY + slug, delay=DELAY, sluggish=slug, probe_mae=m, delay_range=(lo, hi), log_mid=float(mid))
    json.dump(sel, open(os.path.join(HERE, "p7_conds.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return sel


def report():
    import predict as P
    from scipy import stats
    from p7_run import OUT, REPORT
    sel = json.load(open(os.environ.get("P7_CONDS", os.path.join(HERE, "p7_conds.json")), encoding="utf-8"))
    slug = sel["sluggish"]
    tol = json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))
    from experiments import EXPERIMENTS
    AG = list(EXPERIMENTS["E2"]["agents"])
    rows = _read(OUT)
    BY = collections.defaultdict(list)
    for r in rows:
        BY[(r["cond"], r["salt"])].append(r)
    seeds = sorted({s for (_, s) in BY}, key=lambda x: int(x.rsplit("-", 1)[1]))
    conds = DELAY + slug
    tab = P.Table(BY, conds, "BASE", seeds, AG)
    V = tab.pick(seeds)
    rng = np.random.default_rng(0)
    BS = [list(rng.choice(seeds, len(seeds))) for _ in range(N_BOOT)]
    BV = [tab.pick(b) for b in BS]
    PER = {s: tab.pick([s]) for s in seeds}
    tq = stats.t.ppf(0.975, len(seeds) - 1)
    ci = lambda a: tuple(float(x) for x in np.percentile(a, [2.5, 97.5]))
    tci = lambda per, m: (m - tq * np.std(per, ddof=1) / np.sqrt(len(per)), m + tq * np.std(per, ddof=1) / np.sqrt(len(per)))
    line = lambda v: tuple(np.polyfit([v[c][0] for c in DELAY], [v[c][1] for c in DELAY], 1))   # (기울기, 절편)

    def eqv(lo, hi):
        return "같다" if -EQ <= lo and hi <= EQ else ("다르다" if lo > EQ or hi < -EQ else "판정 불가")
    b0 = line(V)[0]
    d0 = b0 - B_REG
    bd = [line(v)[0] - B_REG for v in BV]
    per = [line(PER[s])[0] - B_REG for s in seeds]
    j1b, j1t = eqv(*ci(bd)), eqv(*tci(per, float(np.mean(per))))
    t1 = j1b if j1b == j1t else "판정 불가 (구간 방식에 따라 다름)"
    # T7-2
    e0 = float(np.mean([V[c][1] - (A_REG + B_REG * V[c][0]) for c in DELAY]))
    eb = [np.mean([v[c][1] - (A_REG + B_REG * v[c][0]) for c in DELAY]) for v in BV]
    t2 = P.judge(*ci(eb), tol["D"])
    # T7-3
    t3, d3, c3b, c3t = "실행 안 함 (범위 안 후보 없음)", None, None, None
    if slug:
        res = lambda v: float(np.mean([v[c][1] - (line(v)[1] + line(v)[0] * v[c][0]) for c in slug]))
        d3 = res(V)
        c3b = ci([res(v) for v in BV])
        perr = [res(PER[s]) for s in seeds]
        c3t = tci(perr, float(np.mean(perr)))
        j = lambda lo, hi: "확인" if lo > 0 else ("반대" if hi < 0 else "판정 불가")
        t3 = j(*c3b) if j(*c3b) == j(*c3t) else "판정 불가 (구간 방식에 따라 다름)"
    # 원래 구성과 비교 (같은 이름의 조건)
    BYM = P.load("main")
    sm = P.seeds_of(BYM, "main", [c for c in EXPERIMENTS["E2"]["conds"] if c != "BASE"])
    orig = [c for c in conds if (c, sm[0]) in BYM]
    VO = P.Table(BYM, orig, "BASE", sm, AG).pick(sm) if orig else {}
    lab = lambda r: r["condition"] + ("·무승부" if r["winner"] == "draw" and r["condition"] != "no_contact" else "")
    ends = collections.Counter(lab(r) for s in seeds for r in BY[("BASE", s)])
    ends_o = collections.Counter(lab(r) for s in sm for r in BYM[("BASE", s)])
    base_mae = float(np.mean([float(r[k]) for s in seeds for r in BY[("BASE", s)] for k in ("blue_mae_q_dps", "red_mae_q_dps")]))
    L = ["# P7: 실제형 센서·구동기 (사전 등록 `PREREG_P7.md`)\n",
         f"경기 {len(rows):,}, `wall_clock` {sum(r['condition'] == 'wall_clock' for r in rows)}, 시드 {len(seeds)}개. 조건: 지연형 {', '.join(DELAY)} / 둔한 지연형 {', '.join(slug) or '없음'}.\n",
         "## 0. 기준 리그 (실제형 BASE 대 원래 BASE, 종료 사유)\n", f"실제형 BASE mae {base_mae:.2f} °/s\n",
         "| 종료 | 실제형 | 원래 |", "|---|---|---|"]
    for k in sorted(set(ends) | set(ends_o)):
        L.append(f"| {k} | {ends[k]} | {ends_o[k]} |")
    L += ["", "## 1. 조건별\n", "| 조건 | 유형 | 실제형 mae / D | 원래 mae / D | 등록 직선 예측 (실제형 mae) |", "|---|---|---|---|---|"]
    for c in conds:
        o = VO.get(c)
        L.append(f"| {c} | {'지연형' if c in DELAY else '둔한 지연형'} | {V[c][0]:.2f} / {V[c][1]:.3f} | "
                 + (f"{o[0]:.2f} / {o[1]:.3f}" if o else "–") + f" | {A_REG + B_REG * V[c][0]:.3f} |")
    L += ["", "## 2. 사전 등록 판정\n",
          f"**T7-1 기울기**: 실제형 {b0:.4f}, 등록 {B_REG:.4f}, 차이 {d0:+.4f}. 퍼센타일 [{ci(bd)[0]:+.4f}, {ci(bd)[1]:+.4f}] → {j1b}; "
          f"시드 t [{tci(per, float(np.mean(per)))[0]:+.4f}, {tci(per, float(np.mean(per)))[1]:+.4f}] → {j1t}. 여유 ±{EQ} → **{t1}**\n",
          f"**T7-2 등록 곡선의 수준**: 지연형 6조건 평균 오차 {e0:+.3f} [{ci(eb)[0]:+.3f}, {ci(eb)[1]:+.3f}] (δ_D {tol['D']:.3f}) → **{t2}**\n",
          (f"**T7-3 둔한 지연형 잔차**: {d3:+.3f}, 퍼센타일 [{c3b[0]:+.3f}, {c3b[1]:+.3f}], 시드 t [{c3t[0]:+.3f}, {c3t[1]:+.3f}] → **{t3}**\n"
           if d3 is not None else f"**T7-3**: {t3}\n")]
    res = dict(T1=t1, T1_boot=j1b, T1_t=j1t, slope=b0, T2=t2, mean_err=e0, T3=t3, resid=d3, sluggish=slug,
               conds={c: dict(mae=V[c][0], D=V[c][1]) for c in conds})
    txt = "\n".join(L) + "\n"
    open(REPORT, "w", encoding="utf-8").write(txt)
    json.dump(res, open(os.environ.get("P7_RESULTS", os.path.join(HERE, "p7_results.json")), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(txt)
