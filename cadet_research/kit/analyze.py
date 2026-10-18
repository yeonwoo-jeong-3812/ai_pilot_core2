"""실험 분석기. run.py 가 쓴 out/<시드접두어>/games.csv 를 읽어 보고서를 만든다.

  python analyze.py E1      # δ 를 정해 out/cal/delta.json 에 등록한다 (E2·E3·E4 보다 먼저)
  python analyze.py E2      # 대칭 변형 판정
  python analyze.py E3      # 비대칭 변형 판정
  python analyze.py E4      # 일반화
  python analyze.py E5      # 필터 개입 (지연 붕괴를 5 Hz 필터가 막으면 점수도 지켜지나)
  python analyze.py FEAS    # Feasibility 요약 (판정 없음, δ 는 실용 바닥 3점)
  python analyze.py E2 --prefix smoke   # 실행 점검 결과 분석 (δ 도 out/smoke/delta.json 을 쓴다)

보고 순서는 항상 승·무·패와 종료 사유 → 추종 → 참가자별 점수 변화(판정) → 순위 → 경기 일치율이다.
독립 단위는 시드(리그 한 바퀴)다. 모든 신뢰구간은 시드 단위 부트스트랩이다.
"""
from __future__ import annotations

import collections
import csv
import json
import os
import sys

import numpy as np
from scipy.stats import kendalltau

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
from experiments import EXPERIMENTS  # noqa: E402

PRACTICAL_FLOOR = 3.0   # 리그 한 바퀴당 참가자 점수 3점 = 1승. 이보다 작은 차이는 대회에서 의미가 없다
N_BOOT = 10000
OUT = []
DELTA_DIR = "cal"   # --prefix 를 주면 그 폴더
END_CAUSES = ("health_zero", "hard_deck", "timeout", "no_contact", "stall")


def say(s=""):
    print(s)
    OUT.append(s)


def load(exp_name, prefix=None):
    exp = dict(EXPERIMENTS[exp_name])
    if prefix:
        exp["salt"] = prefix
    path = os.path.join(KIT, "out", exp["salt"], "games.csv")
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)
                if r["cond"] in exp["conds"] and r["blue"] in exp["agents"]
                and r["scenario"] in exp["scenarios"]
                # E2(대칭)와 E3(비대칭)는 같은 파일을 쓴다. 대칭 행은 target 이 비어 있다
                and (r["target"] == "") == (exp.get("target") != "each" or r["cond"] == "BASE")]
    salts = sorted({r["salt"] for r in rows}, key=lambda s: int(s.rsplit("-", 1)[1]))
    return exp, rows, salts


def points(games, agents):
    """승 3, 무 1, 무접촉 0(양쪽 패). 반환: {agent: 점수}, {agent: [승, 무, 패]}."""
    p = dict.fromkeys(agents, 0)
    wdl = {a: [0, 0, 0] for a in agents}
    for g in games:
        a, b = g["blue"], g["red"]
        if g["condition"] == "no_contact":
            wdl[a][2] += 1; wdl[b][2] += 1
        elif g["winner"] == "draw":
            p[a] += 1; p[b] += 1; wdl[a][1] += 1; wdl[b][1] += 1
        else:
            lo = b if g["winner"] == a else a
            p[g["winner"]] += 3; wdl[g["winner"]][0] += 1; wdl[lo][2] += 1
    return p, wdl


def judge(lo, hi, delta):
    if -delta <= lo and hi <= delta:
        return "차이 없음"
    if lo > delta or hi < -delta:
        return "차이 있음"
    return "판정 불가"


def boot_mean_ci(d, level, rng):
    """d: (시드, …) 짝 차이. 시드 단위 복원추출 평균의 백분위 CI."""
    idx = rng.integers(0, len(d), (N_BOOT, len(d)))
    m = d[idx].mean(axis=1)
    a = (1 - level) / 2 * 100
    return np.percentile(m, a, axis=0), np.percentile(m, 100 - a, axis=0)


def gkey(g):
    return (g["blue"], g["red"], g["scenario"], g["salt"])


def outcome(g):
    return (g["winner"], g["condition"])


def section_wdl(by, conds, agents):
    say("## 1. 승·무·패와 종료 사유 (전 참가자 합계, 무접촉은 양쪽 패)\n")
    say("종료 사유: health_zero 격추, hard_deck 저고도 이탈 패, timeout 시간 종료 후 HP 비교, no_contact 무접촉, stall 실속.\n")
    say("| 조건 | 경기 | 승 | 무 | 패 | " + " | ".join(END_CAUSES) + " | 피치 추종 상관 | 피치 추종 오차 [°/s] |")
    say("|---|---|---|---|---|" + "---|" * len(END_CAUSES) + "---|---|")
    for c in conds:
        gs = by[c]
        _, wdl = points(gs, agents)
        w, d, l = np.sum([wdl[a] for a in agents], axis=0)
        ends = collections.Counter(g["condition"] for g in gs)
        corr = np.nanmean([float(g[k]) for g in gs for k in ("blue_corr_q", "red_corr_q")])
        mae = np.mean([float(g[k]) for g in gs for k in ("blue_mae_q_dps", "red_mae_q_dps")])
        say(f"| {c} | {len(gs)} | {w} | {d} | {l} | " + " | ".join(str(ends[e]) for e in END_CAUSES)
            + f" | {corr:.3f} | {mae:.2f} |")
    say()


def per_salt_points(games, agents, salts):
    return np.array([[points([g for g in games if g["salt"] == s], agents)[0][a] for a in agents]
                     for s in salts], float)


def section_symmetric(by, pairs, agents, salts, delta, rng):
    base_pts = per_salt_points(by["BASE"], agents, salts)
    order = sorted(range(len(agents)), key=lambda i: -base_pts[:, i].mean())
    names = [agents[i] for i in order]
    level = 1 - 0.05 / len(agents)      # 한 조건 안의 참가자 수로 Bonferroni
    say(f"## 2. 참가자별 점수 변화 (리그 한 바퀴당 평균, 기준 조건 대비, δ = {delta:.2f}점)\n")
    say(f"신뢰구간은 {level * 100:.2f} % (한 조건 안 참가자 {len(agents)}명 Bonferroni), 시드 {len(salts)}개 부트스트랩.\n")
    say("BASE 점수(한 바퀴 평균): " + ", ".join(f"{a} {base_pts[:, agents.index(a)].mean():.1f}" for a in names) + "\n")
    say("| 변형 − 기준 | " + " | ".join(names) + " |")
    say("|---|" + "---|" * len(names))
    verdicts = {}
    for c, ref in pairs:
        d = per_salt_points(by[c], agents, salts) - per_salt_points(by[ref], agents, salts)
        lo, hi = boot_mean_ci(d, level, rng)
        m = d.mean(axis=0)
        cells = []
        for a in names:
            i = agents.index(a)
            v = judge(lo[i], hi[i], delta)
            verdicts[(c, a)] = v
            cells.append(f"{m[i]:+.1f} [{lo[i]:+.1f}, {hi[i]:+.1f}] {v}")
        say(f"| {c} − {ref} | " + " | ".join(cells) + " |")
    say()
    say("조건별 요약 (없음/불가/있음 참가자 수): " + "; ".join(
        f"{c} " + "/".join(str(sum(verdicts[(c, a)] == v for a in agents))
                           for v in ("차이 없음", "판정 불가", "차이 있음"))
        for c, _ in pairs) + "\n")
    return verdicts


def section_rank(by, pairs, agents, salts, rng):
    say("## 3. 순위 (시드 합산 점수)\n")
    top = int(np.argmax(per_salt_points(by["BASE"], agents, salts).sum(0)))
    say("| 변형 vs 기준 | Kendall τ | τ 95 % CI | 1위 유지 비율 (부트스트랩) | 변형의 순위 |")
    say("|---|---|---|---|---|")
    for c, ref in [("BASE", "BASE")] + pairs:
        base_pts = per_salt_points(by[ref], agents, salts)
        bsum = base_pts.sum(0)
        v = per_salt_points(by[c], agents, salts)
        tau = kendalltau(bsum, v.sum(0)).statistic
        idx = rng.integers(0, len(salts), (2000, len(salts)))
        taus = [kendalltau(base_pts[i].sum(0), v[i].sum(0)).statistic for i in idx]
        keep = np.mean([np.argmax(v[i].sum(0)) == np.argmax(base_pts[i].sum(0)) for i in idx])
        rank = " > ".join(f"{agents[i]}({int(v.sum(0)[i])})" for i in np.argsort(-v.sum(0)))
        say(f"| {c} vs {ref} | {tau:+.2f} | [{np.nanpercentile(taus, 2.5):+.2f}, {np.nanpercentile(taus, 97.5):+.2f}]"
            f" | {keep:.2f} | {rank} |")
    say(f"\nBASE 1위: {agents[top]}\n")


def section_agreement(by, pairs, salts, rng):
    say("## 4. 경기 일치율 (같은 대진·시나리오·시드에서 승자와 종료 사유가 기준 조건과 같은 경기의 비율)\n")
    base = {gkey(g): g for g in by["BASE"]}
    dist = collections.defaultdict(collections.Counter)
    for g in by["BASE"]:
        dist[(g["blue"], g["red"], g["scenario"])][outcome(g)] += 1
    ref = np.mean([sum((c / len(salts)) ** 2 for c in dist[(g["blue"], g["red"], g["scenario"])].values())
                   for g in by["BASE"]])
    say(f"무상관 기준 {ref:.3f} (BASE 기준): 변형 경기의 결과가 같은 대진·시나리오 BASE 결과 분포에서 독립으로 뽑혔다면 기대되는 일치율. "
        "이 값에 가까우면 개별 경기는 사실상 새로 뽑은 것과 같다.\n")
    say("| 변형 vs 기준 | 경기 일치율 | 95 % CI (시드 단위) |")
    say("|---|---|---|")
    for c, ref in pairs:
        refg = {gkey(g): g for g in by[ref]}
        per = collections.defaultdict(list)
        for g in by[c]:
            per[g["salt"]].append(outcome(g) == outcome(refg[gkey(g)]))
        arr = [per[s] for s in salts]
        tot = np.mean([x for a in arr for x in a])
        bs = []
        for _ in range(2000):
            pick = rng.integers(0, len(salts), len(salts))
            bs.append(np.mean([x for i in pick for x in arr[i]]))
        say(f"| {c} vs {ref} | {tot:.3f} | [{np.percentile(bs, 2.5):.3f}, {np.percentile(bs, 97.5):.3f}] |")
    say()


def register_delta(by, agents, salts):
    d = np.abs(per_salt_points(by["SHAM"], agents, salts) - per_salt_points(by["BASE"], agents, salts))
    p95 = float(np.percentile(d, 95))
    delta = max(2 * p95, PRACTICAL_FLOOR)
    say("## δ 등록\n")
    say(f"SHAM 짝 차이 |Δ점수| (참가자 × 시드 {d.size}개)의 95 백분위수 = {p95:.2f}점, 2배 = {2 * p95:.2f}점, "
        f"실용 바닥 = {PRACTICAL_FLOOR:.1f}점(1승) → δ = {delta:.2f}점\n")
    path = os.path.join(KIT, "out", DELTA_DIR, "delta.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"delta_pts": delta, "sham_p95": p95, "practical_floor": PRACTICAL_FLOOR,
                   "n": int(d.size), "salts": salts}, f, ensure_ascii=False, indent=1)
    say(f"등록: {path}\n")


def read_delta():
    path = os.path.join(KIT, "out", DELTA_DIR, "delta.json")
    if not os.path.isfile(path):
        sys.exit("δ 가 등록되지 않았다. E1 을 먼저 실행하고 `python analyze.py E1` 을 돌린다.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["delta_pts"]


def section_asymmetric(by, exp, agents, salts, delta, rng):
    say(f"## 2. 비대칭: 대상 참가자 하나만 변형했을 때 그 참가자의 점수 변화 (δ = {delta:.2f}점)\n")
    level = 1 - 0.05 / len(agents)
    base_pts = per_salt_points(by["BASE"], agents, salts)
    say("| 조건 | 대상 | BASE 순위 | 변형 순위 | 대상 점수 변화 [CI] | 판정 | 대상 추종 오차 BASE→변형 [°/s] |")
    say("|---|---|---|---|---|---|---|")
    for c in exp["conds"]:
        if c == "BASE":
            continue
        for a in agents:
            gs = [g for g in by[c] if g["target"] == a]
            if not gs:
                continue
            swapped = {gkey(g): g for g in gs}
            league = [swapped.get(gkey(g), g) for g in by["BASE"]]   # 대상 판만 변형 판으로 바꾼 리그
            v = per_salt_points(league, agents, salts)
            i = agents.index(a)
            d = (v - base_pts)[:, i:i + 1]
            lo, hi = boot_mean_ci(d, level, rng)
            rb = list(np.argsort(-base_pts.sum(0))).index(i) + 1
            rv = list(np.argsort(-v.sum(0))).index(i) + 1
            own = lambda games: np.mean([float(g["blue_mae_q_dps"] if g["blue"] == a else g["red_mae_q_dps"])
                                         for g in games if a in (g["blue"], g["red"])])
            say(f"| {c} | {a} | {rb} | {rv} | {d.mean():+.1f} [{lo[0]:+.1f}, {hi[0]:+.1f}] | "
                f"{judge(lo[0], hi[0], delta)} | {own(by['BASE']):.2f}→{own(gs):.2f} |")
    say()


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "FEAS"
    prefix = sys.argv[sys.argv.index("--prefix") + 1] if "--prefix" in sys.argv else None
    exp, rows, salts = load(name, prefix)
    global DELTA_DIR
    DELTA_DIR = prefix or "cal"
    agents = list(exp["agents"])
    by = collections.defaultdict(list)
    for r in rows:
        by[r["cond"]].append(r)
    missing = [c for c in exp["conds"] if not by[c]]
    if missing:
        sys.exit(f"기록된 판이 없는 조건: {missing}. run.py {name} 를 먼저 실행한다.")
    say(f"# {name} 보고서\n")
    say(f"판 {len(rows)}, 시드 {len(salts)}개 ({salts[0]} … {salts[-1]}), 참가자 {len(agents)}명, "
        f"시나리오 {', '.join(exp['scenarios'])}\n")
    rng = np.random.default_rng(0)
    section_wdl(by, exp["conds"], agents)
    if name == "E1":
        register_delta(by, agents, salts)
        delta = read_delta()
    elif name == "FEAS":
        delta = PRACTICAL_FLOOR
    else:
        delta = read_delta()
    if exp.get("target") == "each":
        section_asymmetric(by, exp, agents, salts, delta, rng)
    else:
        pairs = exp.get("compare") or [(c, "BASE") for c in exp["conds"] if c != "BASE"]
        section_symmetric(by, pairs, agents, salts, delta, rng)
        section_rank(by, pairs, agents, salts, rng)
        section_agreement(by, pairs, salts, rng)
    path = os.path.join(KIT, "out", exp["salt"], f"report_{name}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")
    print("보고서:", path)


if __name__ == "__main__":
    main()
