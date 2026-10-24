"""3인 패널 검토(`../PLAN_AFTER_PANEL_v1.md`)의 P0 — 분석만, 경기를 새로 돌리지 않는다.

  python reanalysis_p0.py      # → out/reanalysis_p0/ 에 보고서와 results.json

A 상수 예측 대비 기술 점수   B 보정한 무상관 수준   C D 분해(승자/종료 사유)   D 상한 아래 기울기
E 허용폭 민감도   F (시나리오, 시드) 층화 부트스트랩   G ASYM U자 대비와 종료 방식·HP 분해
모두 결과를 본 뒤의 분석이다. 등록된 판정을 바꾸지 않고 사실 보고로만 쓴다.
"""
from __future__ import annotations

import collections
import csv
import json
import os
import sys

import numpy as np

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
import predict as P  # noqa: E402
from experiments import ASYM_CONDS, ASYM_TARGETS, E3X_CONDS, EXPERIMENTS  # noqa: E402

OUTDIR = os.path.join(KIT, "out", "reanalysis_p0")
N_BOOT = 2000
OUT: list[str] = []
RES: dict = {}
KEY = ("blue", "red", "scenario", "salt")


def say(s=""):
    print(s)
    OUT.append(s)


def ci(a, level=95.0):
    lo, hi = np.percentile(np.asarray(a, float), [(100 - level) / 2, 100 - (100 - level) / 2])
    return float(lo), float(hi)


def fmt(a, d=3, level=95.0):
    lo, hi = ci(a, level)
    return f"[{lo:+.{d}f}, {hi:+.{d}f}]"


def judge(lo, hi, d):
    return "성공" if -d <= lo and hi <= d else ("실패" if lo > d or hi < -d else "불가")


def read(d):
    return list(csv.DictReader(open(os.path.join(KIT, "out", d, "games.csv"), encoding="utf-8")))


e2, e3, e4 = EXPERIMENTS["E2"], EXPERIMENTS["E3"], EXPERIMENTS["E4"]
AG = list(e2["agents"])
FIT = [c for c in e2["conds"] if c != "BASE"]
TEST = [c for c in e3["conds"] if c != "BASE"]
DELTA = json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))["D"]

MAIN = [r for r in read("main") if r["target"] == ""] + read("e3x")
BY = collections.defaultdict(list)
for r in MAIN:
    BY[(r["cond"], r["salt"])].append(r)
SEEDS = P.seeds_of(BY, "main", FIT)
ALLC = FIT + TEST + E3X_CONDS
TAB = P.Table(BY, ALLC, "BASE", SEEDS, AG)
V = TAB.pick(SEEDS)
rng = np.random.default_rng(0)
BS = [list(rng.choice(SEEDS, len(SEEDS))) for _ in range(N_BOOT)]
BV = [TAB.pick(b) for b in BS]


def line(vals, conds):
    b, a = np.polyfit([vals[c][0] for c in conds], [vals[c][1] for c in conds], 1)
    return float(a), float(b)


def low_mean(vals):
    return float(np.mean([vals[c][1] for c in FIT if vals[c][0] < 1.0]))


PREDICTORS = {
    "등록 직선 (mae 사용)": lambda vals: (lambda ab: (lambda m: ab[0] + ab[1] * m))(line(vals, FIT)),
    "상수: E2 절편 (mae 무시)": lambda vals: (lambda a: (lambda m: a))(line(vals, FIT)[0]),
    "상수: E2 약한 열화(mae < 1) 평균": lambda vals: (lambda a: (lambda m: a))(low_mean(vals)),
}


# ---------------------------------------------------------------- A
def part_a():
    say("## A. 상수 예측 대비 기술 점수\n")
    say("E2로 만든 세 가지 예측기를 처음 보는 조건에 적용했다. 상수 예측기는 추종 오차를 전혀 쓰지 않는다. "
        "기술 점수 = 1 − RMS(직선) / RMS(상수). R²는 검증 조건 자체의 평균을 기준으로 한 표본 밖 값이다. "
        f"원인 묶음 판정은 등록 규칙(평균 예측 오차의 95 % CI를 ±δ_D {DELTA:.3f}과 비교)을 그대로 쓴다.\n")
    groups = collections.defaultdict(list)
    for c in TEST + E3X_CONDS:
        groups[P.cause(c)].append(c)
    res = {}
    for label, conds in (("E3 22조건", TEST), ("E3X 6조건 (사후 추가)", E3X_CONDS), ("E3 + E3X 28조건", TEST + E3X_CONDS)):
        say(f"### {label}\n")
        say("| 예측기 | RMS [95 % CI] | 표본 밖 R² | 원인 묶음 판정 (평균 오차) |")
        say("|---|---|---|---|")
        rms_b = {}
        for name, mk in PREDICTORS.items():
            f = mk(V)
            e = np.array([V[c][1] - f(V[c][0]) for c in conds])
            y = np.array([V[c][1] for c in conds])
            r2 = 1 - np.sum(e ** 2) / np.sum((y - y.mean()) ** 2)
            rb = []
            gb = collections.defaultdict(list)
            for vb in BV:
                fb = mk(vb)
                eb = {c: vb[c][1] - fb(vb[c][0]) for c in conds}
                rb.append(np.sqrt(np.mean(np.square(list(eb.values())))))
                for g, cs in groups.items():
                    cs2 = [c for c in cs if c in conds]
                    if cs2:
                        gb[g].append(np.mean([eb[c] for c in cs2]))
            rms_b[name] = np.array(rb)
            cells = []
            for g in sorted(gb):
                lo, hi = ci(gb[g])
                m = np.mean([V[c][1] - f(V[c][0]) for c in groups[g] if c in conds])
                cells.append(f"{g} {m:+.3f} {judge(lo, hi, DELTA)}")
            say(f"| {name} | {np.sqrt(np.mean(e ** 2)):.3f} {fmt(rb)} | {r2:+.2f} | {'; '.join(cells)} |")
        line_name = "등록 직선 (mae 사용)"
        say("\n| 비교 | 기술 점수 [95 % CI] |")
        say("|---|---|")
        sk = {}
        for name in PREDICTORS:
            if name == line_name:
                continue
            s = 1 - rms_b[line_name] / rms_b[name]
            s0 = 1 - np.sqrt(np.mean([(V[c][1] - PREDICTORS[line_name](V)(V[c][0])) ** 2 for c in conds])) / \
                np.sqrt(np.mean([(V[c][1] - PREDICTORS[name](V)(V[c][0])) ** 2 for c in conds]))
            sk[name] = (float(s0), ci(s))
            say(f"| 직선 대 {name} | {s0:+.2f} {fmt(s, 2)} |")
        say()
        res[label] = sk
    RES["A"] = res


# ---------------------------------------------------------------- B
def indep(rows, seeds):
    """(대진, 시나리오)마다 BASE 결과 분포. 반환: (plug-in Σp̂², 보정 Σc(c−1)/(n(n−1)))."""
    dist = collections.defaultdict(collections.Counter)
    base = [g for g in rows if g["cond"] == "BASE" and g["target"] == "" and g["salt"] in seeds]
    for g in base:
        dist[(g["blue"], g["red"], g["scenario"])][(g["winner"], g["condition"])] += 1
    n = len(seeds)
    plug = float(np.mean([sum((c / n) ** 2 for c in dist[(g["blue"], g["red"], g["scenario"])].values()) for g in base]))
    unb = float(np.mean([sum(c * (c - 1) for c in cnt.values()) / (n * (n - 1)) for cnt in dist.values()]))
    return plug, unb


def part_b():
    say("## B. 무상관 수준 보정\n")
    say("무상관 기준 = 열화 경기의 결과를 같은 대진·시나리오의 BASE 결과 분포에서 독립으로 뽑았을 때의 기대 일치율. "
        "`analyze.py`와 v2 D-4는 표본 비율 p̂로 Σp̂²를 계산했는데, 이 값은 한 경기가 자기 자신과 일치하는 경우를 포함해 "
        "위로 치우친다. 같은 경기끼리의 비교를 뺀 불편 추정 Σc(c−1)/(n(n−1))로 바로잡았다 (n = 시드 수).\n")
    say("| 실험 | 시드 | 기존 (plug-in) 일치율 → D 상한 | 보정 일치율 → **D 상한** |")
    say("|---|---|---|---|")
    res = {}
    for name, d in (("E1 (cal)", "cal"), ("E2·E3 (main)", "main"), ("E4 (gen)", "gen")):
        rows = read(d)
        seeds = sorted({r["salt"] for r in rows if r["cond"] == "BASE"})
        p, u = indep(rows, seeds)
        res[name] = dict(plugin=p, plugin_ceiling=1 - p, unbiased=u, ceiling=1 - u)
        say(f"| {name} | {len(seeds)} | {p:.3f} → {1 - p:.3f} | {u:.3f} → **{1 - u:.3f}** |")
    ceil = res["E2·E3 (main)"]["ceiling"]
    above_f = [c for c in FIT if V[c][1] > ceil]
    above_x = [c for c in E3X_CONDS if V[c][1] > ceil]
    say(f"\n보정 상한 {ceil:.3f} 위: 적합 {len(above_f)}/20 ({', '.join(above_f)}), 검증 E3 0/22, "
        f"E3X {len(above_x)}/6 ({', '.join(above_x) or '없음'}). 기존 상한 0.403 위는 적합 8/20이었다.\n")
    say("**해석도 바로잡는다.** 상한 위의 D는 \"무정보\"가 아니다. 개별 경기의 짝이 사라진 상태에서도 대진별 결과 분포가 "
        "BASE에서 멀어진 만큼 D가 더 올라간다(분포 이동). 따라서 상한 위의 조건은 \"개별 경기 수준의 짝이 사라지고 "
        "결과 분포가 이동한 구간\"으로 쓴다.\n")
    RES["B"] = dict(levels=res, above_fit=above_f, above_e3x=above_x)
    return ceil


# ---------------------------------------------------------------- C
def part_c():
    say("## C. D 분해: 승자가 바뀐 경기와 종료 사유만 바뀐 경기\n")
    base = {tuple(r[k] for k in KEY): r for r in MAIN if r["cond"] == "BASE"}
    per = {}
    for c in ALLC:
        w = o = n = 0
        msum = 0.0
        for r in MAIN:
            if r["cond"] != c:
                continue
            b = base[tuple(r[k] for k in KEY)]
            n += 1
            msum += (float(r["blue_mae_q_dps"]) + float(r["red_mae_q_dps"])) / 2
            if r["winner"] != b["winner"]:
                w += 1
            elif r["condition"] != b["condition"]:
                o += 1
        per[c] = (msum / n, w / n, o / n)
    say("| 묶음 | 조건 수 | 평균 D | 승자 변화율 W | 종료 사유만 변화 O | O / D |")
    say("|---|---|---|---|---|---|")
    for name, cs in (("E2 적합", FIT), ("E3 검증", TEST), ("E3X (사후)", E3X_CONDS)):
        W = np.mean([per[c][1] for c in cs]); O = np.mean([per[c][2] for c in cs])
        say(f"| {name} | {len(cs)} | {W + O:.3f} | {W:.3f} | {O:.3f} | {O / (W + O):.0%} |")
    bw = np.polyfit([per[c][0] for c in FIT], [per[c][1] for c in FIT], 1)[0]
    bo = np.polyfit([per[c][0] for c in FIT], [per[c][2] for c in FIT], 1)[0]
    say(f"\nE2 적합 20조건에서 mae에 대한 기울기: W {bw:.4f}, O {bo:.4f} (합 {bw + bo:.4f} = D 기울기). "
        f"관계의 {bw / (bw + bo):.0%}는 승자 변화가 실어 나른다.\n")
    RES["C"] = dict(slope_winner=float(bw), slope_cause_only=float(bo),
                    per={c: dict(mae=v[0], W=v[1], O=v[2]) for c, v in per.items()})


# ---------------------------------------------------------------- D
def part_d(ceil):
    say("## D. 상한 아래 조건만으로 낸 기울기\n")
    say("| 적합에 쓴 조건 | 조건 수 | 기울기 [95 % CI] | 절편 |")
    say("|---|---|---|---|")
    res = {}
    for name, cs in (("E2 전체", FIT), (f"D < {ceil:.3f} (보정 상한)", [c for c in FIT if V[c][1] < ceil]),
                     ("D < 0.403 (기존 상한)", [c for c in FIT if V[c][1] < 0.403])):
        a, b = line(V, cs)
        bb = [line(vb, cs)[1] for vb in BV]
        res[name] = dict(n=len(cs), slope=b, slope_ci=ci(bb), intercept=a)
        say(f"| {name} | {len(cs)} | {b:.4f} {fmt(bb, 4)} | {a:.3f} |")
    say()
    RES["D"] = res


# ---------------------------------------------------------------- E
def part_e():
    say("## E. 허용폭 민감도 (E3 원인 묶음, 등록 직선, 퍼센타일 CI)\n")
    groups = collections.defaultdict(list)
    for c in TEST:
        groups[P.cause(c)].append(c)
    gb = collections.defaultdict(list)
    for vb in BV:
        a, b = line(vb, FIT)
        for g, cs in groups.items():
            gb[g].append(np.mean([vb[c][1] - (a + b * vb[c][0]) for c in cs]))
    a0, b0 = line(V, FIT)
    say("| 묶음 | 평균 오차 [95 % CI] | δ 0.079 (등록) | δ 0.05 | δ 0.03 |")
    say("|---|---|---|---|---|")
    res = {}
    for g in sorted(groups):
        lo, hi = ci(gb[g])
        m = np.mean([V[c][1] - (a0 + b0 * V[c][0]) for c in groups[g]])
        js = [judge(lo, hi, d) for d in (DELTA, 0.05, 0.03)]
        res[g] = js
        say(f"| {g} | {m:+.3f} [{lo:+.3f}, {hi:+.3f}] | " + " | ".join(js) + " |")
    say()
    RES["E"] = res


# ---------------------------------------------------------------- F
def part_f():
    say("## F. (시나리오, 시드) 층화 부트스트랩\n")
    say("초기 조건 시드는 (시나리오, 시드)마다 따로 정해진다(`run.py`의 `derive_seed(scenario, salt)`). 시나리오 3개를 층으로 두고 "
        "층마다 시드 8개를 복원추출한다(24군집). 등록 방식(시드 8개를 시나리오 묶음째 추출)과 E3 원인 묶음 CI 폭을 비교한다.\n")
    base = {tuple(r[k] for k in KEY): r for r in MAIN if r["cond"] == "BASE"}
    scen = sorted({r["scenario"] for r in MAIN})
    cell = collections.defaultdict(lambda: [0.0, 0, 0])      # (cond, scen, salt) → [mae합, n, 뒤집힘]
    for r in MAIN:
        if r["cond"] in FIT + TEST:
            b = base[tuple(r[k] for k in KEY)]
            x = cell[(r["cond"], r["scenario"], r["salt"])]
            x[0] += (float(r["blue_mae_q_dps"]) + float(r["red_mae_q_dps"])) / 2; x[1] += 1
            x[2] += (r["winner"], r["condition"]) != (b["winner"], b["condition"])

    def pick(clusters):
        out = {}
        for c in FIT + TEST:
            s = np.array([cell[(c, sc, sl)] for sc, sl in clusters])
            out[c] = (s[:, 0].sum() / s[:, 1].sum(), s[:, 2].sum() / s[:, 1].sum())
        return out
    groups = collections.defaultdict(list)
    for c in TEST:
        groups[P.cause(c)].append(c)
    r6 = np.random.default_rng(6)
    sb = collections.defaultdict(list)
    for _ in range(N_BOOT):
        cl = [(sc, sl) for sc in scen for sl in r6.choice(SEEDS, len(SEEDS))]
        vb = pick(cl)
        a, b = line(vb, FIT)
        for g, cs in groups.items():
            sb[g].append(np.mean([vb[c][1] - (a + b * vb[c][0]) for c in cs]))
    seedb = collections.defaultdict(list)
    for vb in BV:
        a, b = line(vb, FIT)
        for g, cs in groups.items():
            seedb[g].append(np.mean([vb[c][1] - (a + b * vb[c][0]) for c in cs]))
    say("| 묶음 | 시드 부트스트랩 (등록) | 층화 부트스트랩 | 폭 비 | 층화 판정 |")
    say("|---|---|---|---|---|")
    res = {}
    for g in sorted(groups):
        l1, h1 = ci(seedb[g]); l2, h2 = ci(sb[g])
        res[g] = dict(seed=(l1, h1), strat=(l2, h2), ratio=(h2 - l2) / (h1 - l1), judge=judge(l2, h2, DELTA))
        say(f"| {g} | [{l1:+.3f}, {h1:+.3f}] | [{l2:+.3f}, {h2:+.3f}] | {res[g]['ratio']:.2f} | {res[g]['judge']} |")
    say()
    RES["F"] = res


# ---------------------------------------------------------------- G
def part_g():
    say("## G. ASYM: U자 대비, 종료 방식과 HP 분해\n")
    asym = read("asym")
    base = {tuple(r[k] for k in KEY): r for r in MAIN if r["cond"] == "BASE"}
    from analyze import points

    def dpts(c, t, s):
        gs = [r for r in asym if r["cond"] == c and r["target"] == t and r["salt"] == s]
        bs = [base[tuple(g[k] for k in KEY)] for g in gs]
        return points(gs, AG)[0][t] - points(bs, AG)[0][t]
    lvl = 100 * (1 - 0.05 / len(ASYM_TARGETS))
    say(f"### U자 대비: Δ점수(6틱) − Δ점수(2틱), 필터 25 Hz (시드 부트스트랩 {lvl:.2f} % CI)\n")
    say("| 대상 | 2틱 Δ점수 | 6틱 Δ점수 | 대비 [CI] | 6틱 > 2틱인 시드 |")
    say("|---|---|---|---|---|")
    res = {}
    for t in ASYM_TARGETS:
        d2 = {s: dpts("F25_D2", t, s) for s in SEEDS}; d6 = {s: dpts("F25_D6", t, s) for s in SEEDS}
        con = {s: d6[s] - d2[s] for s in SEEDS}
        bc = [np.mean([con[s] for s in b]) for b in BS]
        lo, hi = ci(bc, lvl)
        res[t] = dict(d2=float(np.mean(list(d2.values()))), d6=float(np.mean(list(d6.values()))),
                      contrast=float(np.mean(list(con.values()))), ci=(lo, hi), seeds_pos=int(sum(v > 0 for v in con.values())))
        say(f"| {t} | {res[t]['d2']:+.1f} | {res[t]['d6']:+.1f} | {res[t]['contrast']:+.1f} [{lo:+.1f}, {hi:+.1f}] | {res[t]['seeds_pos']}/8 |")
    say("\n### 종료 방식과 HP (대상 기준, 시드 8개 합, 대상당 336경기)\n")
    say("| 대상 | 조건 | 대상 격추승 | 상대 지면충돌(대상승) | 대상 피격패 | 대상 지면충돌패 | 시간종료 승/패 | 무접촉 | 대상 HP 평균 | 상대 HP 평균 |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    tab = {}
    for t in ASYM_TARGETS:
        for c in ["BASE"] + ASYM_CONDS:
            gs = [r for r in asym if r["cond"] == ("F25_D2" if c == "BASE" else c) and r["target"] == t]
            if c == "BASE":
                gs = [base[tuple(g[k] for k in KEY)] for g in gs]
            k = collections.Counter()
            hp_t, hp_o = [], []
            for g in gs:
                tb = g["blue"] == t
                hp_t.append(float(g["hp_blue" if tb else "hp_red"])); hp_o.append(float(g["hp_red" if tb else "hp_blue"]))
                if g["condition"] == "no_contact":
                    k["nc"] += 1
                elif g["winner"] == t:
                    k["w_" + g["condition"]] += 1
                elif g["winner"] == "draw":
                    k["draw"] += 1
                else:
                    k["l_" + g["condition"]] += 1
            tab[(t, c)] = dict(k, hp_t=float(np.mean(hp_t)), hp_o=float(np.mean(hp_o)))
            if c in ("BASE", "F25_D0.5", "F25_D2", "F25_D4", "F25_D6", "R_kappa_50"):
                say(f"| {t} | {c} | {k['w_health_zero']} | {k['w_hard_deck']} | {k['l_health_zero']} | {k['l_hard_deck']} | "
                    f"{k['w_timeout']}/{k['l_timeout']} | {k['nc']} | {np.mean(hp_t):.1f} | {np.mean(hp_o):.1f} |")
    say("\n중간 열화(2틱)에서는 격추승이 줄고 피격패·지면충돌패가 는다. 심한 열화(6틱)에서는 GunTracker·Extender의 격추승이 늘고 "
        "피격패가 줄며, 상대의 지면 충돌도 준다. 맞는 쪽만이 아니라 맞히는 쪽도 좋아졌다. 메커니즘은 P2-a 기록으로 본다.\n")
    RES["G"] = dict(contrast=res, table={f"{t}|{c}": v for (t, c), v in tab.items()})


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    say("# P0 — 패널 검토 대응 분석 (경기 0판)\n")
    say(f"원자료: `out/main`(E2·E3), `out/e3x`, `out/asym`, `out/cal`, `out/gen`. δ_D = {DELTA:.3f}. 모두 사후 분석이며 등록 판정을 바꾸지 않는다.\n")
    part_a(); ceil = part_b(); part_c(); part_d(ceil); part_e(); part_f(); part_g()
    with open(os.path.join(OUTDIR, "report_p0.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")
    with open(os.path.join(OUTDIR, "results.json"), "w", encoding="utf-8") as f:
        json.dump(RES, f, ensure_ascii=False, indent=1, default=float)
    print("보고서: out/reanalysis_p0/report_p0.md")


if __name__ == "__main__":
    main()
