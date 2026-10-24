"""P5: E4의 치우침(+0.045)은 참가자 탓인가 시드 탓인가 (사전 등록 ../../PREREG_P5.md, 실행 전 고정).

  python p5_gen_agents.py           # 4,704경기 (약 2.3시간) → ../out/p5/games.csv, 그다음 분석 → p5_output.md
  python p5_gen_agents.py --report  # 경기 없이 분석만
  python p5_gen_agents.py --smoke   # 점검: p5smoke-0 에서 2경기 (결과 파일에 쓰지 않음)

E2 참가자 8명을 E4 시드(gen-0–3)에서 {BASE, SHAM, E4 열화 5조건}으로 돌린다(168경기 × 7조건 × 시드 4).
세 가지 치우침(등록 곡선의 열화 5조건 평균 예측 오차)을 비교한다.
  E4 참가자 × gen 시드 (기존 out/gen), E2 참가자 × gen 시드 (이번), E2 참가자 × main 시드 (기존 out/main)
엔진·키트 파일은 고치지 않는다.
"""
from __future__ import annotations

import collections
import csv
import ctypes
import json
import multiprocessing as mp
import os
import sys
import time

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # kit/supplementary → kit
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
os.chdir(KIT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import run  # noqa: E402
from experiments import AGENTS_E4, AGENTS_MAIN, EXPERIMENTS, LEAGUE  # noqa: E402

DEG = ["F25_D1", "F25_D3", "R_kappa_25", "R_kq_2", "R_sigma_dps_3"]     # E4 열화 5조건
GEN = [f"gen-{i}" for i in range(4)]
OUTDIR = os.path.join(KIT, "out", "p5")
OUT = os.environ.get("P5_GAMES", os.path.join(OUTDIR, "games.csv"))     # 환경 변수는 분석 점검용
REPORT = os.environ.get("P5_REPORT", os.path.join(HERE, "p5_output.md"))
LOG = os.path.join(HERE, "p5.log")
KEY = ("cond", "target", "blue", "red", "scenario", "salt")
N_BOOT = 2000


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def jobs(salt="gen", n=4):
    return run.build_jobs(dict(agents=AGENTS_MAIN, scenarios=LEAGUE, salt=salt, conds=["BASE", "SHAM"] + DEG), n)


def smoke():
    js = [j for j in jobs("p5smoke", 1) if j["scenario"] == "headon" and j["blue"] == "RedPrime" and j["red"] == "Reactive"
          and j["cond"] in ("BASE", "R_kq_2")]
    with mp.Pool(2) as pool:
        rs = pool.map(run.play, js)
    for r in rs:
        print(r["cond"], r["winner"], r["condition"], r["blue_mae_q_dps"], r["red_mae_q_dps"])
    log(f"점검(p5smoke-0, {len(rs)}경기) 통과. 본 실행 {len(jobs())}판")


def run_games():
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    os.makedirs(OUTDIR, exist_ok=True)
    js = jobs()
    rows = read(OUT)
    keep = [r for r in rows if r["condition"] != "wall_clock"]
    if len(keep) != len(rows):
        log(f"wall_clock {len(rows) - len(keep)}판을 지우고 다시 돈다")
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=run.FIELDS); w.writeheader(); w.writerows(keep)
    done = {tuple(r[k] for k in KEY) for r in keep}
    todo = [j for j in js if tuple(j[k] for k in KEY) not in done]
    log(f"전체 {len(js)}판, 기록됨 {len(js) - len(todo)}, 남음 {len(todo)}")
    if not todo:
        return
    new = not os.path.isfile(OUT)
    t0 = time.time()
    with mp.Pool(14) as pool, open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=run.FIELDS)
        if new:
            w.writeheader()
        for i, row in enumerate(pool.imap_unordered(run.play, todo, chunksize=1), 1):
            w.writerow(row); f.flush()
            if i % 200 == 0 or i == len(todo):
                el = time.time() - t0
                log(f"  {i}/{len(todo)}  {el:.0f}s 경과, 남은 예상 {el / i * (len(todo) - i):.0f}s")
    if any(r["condition"] == "wall_clock" for r in read(OUT)):
        run_games()


def report():
    import predict as P
    P.SHAPE = "linear"
    tol = json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))
    fitc = [c for c in EXPERIMENTS["E2"]["conds"] if c != "BASE"]
    AG2, AG4 = list(EXPERIMENTS["E2"]["agents"]), list(AGENTS_E4)
    BYM, BY4 = P.load("main"), P.load("gen")
    BY5 = collections.defaultdict(list)
    rows = read(OUT)
    for r in rows:
        BY5[(r["cond"], r["salt"])].append(r)
    sm = P.seeds_of(BYM, "main", fitc)
    tf = P.Table(BYM, fitc, "BASE", sm, AG2)
    conds = ["SHAM"] + DEG
    t4 = P.Table(BY4, conds, "BASE", GEN, AG4)          # E4 참가자 × gen
    t5 = P.Table(BY5, conds, "BASE", GEN, AG2)          # E2 참가자 × gen (이번)
    tm = P.Table(BYM, DEG, "BASE", sm, AG2)             # E2 참가자 × main
    rng = np.random.default_rng(0)
    BM = [list(rng.choice(sm, len(sm))) for _ in range(N_BOOT)]
    BG = [list(rng.choice(GEN, len(GEN))) for _ in range(N_BOOT)]
    BM2 = [list(rng.choice(sm, len(sm))) for _ in range(N_BOOT)]   # main 시드 치우침용 (곡선과 따로)

    def curve(v):
        b, a = np.polyfit([v[c][0] for c in fitc], [v[c][1] for c in fitc], 1)
        return float(a), float(b)

    def bias(v, a, b):
        return float(np.mean([v[c][1] - (a + b * v[c][0]) for c in DEG]))
    a0, b0 = curve(tf.pick(sm))
    v4, v5, vm = t4.pick(GEN), t5.pick(GEN), tm.pick(sm)
    est = dict(e4=bias(v4, a0, b0), e2gen=bias(v5, a0, b0), e2main=bias(vm, a0, b0))
    arr = collections.defaultdict(list)
    for bm, bg, bm2 in zip(BM, BG, BM2):
        a, b = curve(tf.pick(bm))
        x4, x5, xm = bias(t4.pick(bg), a, b), bias(t5.pick(bg), a, b), bias(tm.pick(bm2), a, b)
        arr["e4"].append(x4); arr["e2gen"].append(x5); arr["e2main"].append(xm)
        arr["P"].append(x4 - x5); arr["S"].append(x5 - xm)
    ci = lambda a: tuple(float(x) for x in np.percentile(a, [2.5, 97.5]))
    excl = lambda a: ci(a)[0] > 0 or ci(a)[1] < 0
    pP, pS = excl(arr["P"]), excl(arr["S"])
    verdict = {(True, False): "참가자 탓", (False, True): "시드 탓", (True, True): "둘 다", (False, False): "판정 불가 (둘 다 0과 구별 안 됨)"}[(pP, pS)]
    L = ["# P5: E4 치우침의 원인 — 참가자 대 시드 (사전 등록 `PREREG_P5.md`)\n",
         f"경기 {len(rows):,} (사전 등록 4,704), `wall_clock` {sum(r['condition'] == 'wall_clock' for r in rows)}. "
         "치우침 = 등록 곡선(E2, main 8시드)으로 예측한 E4 열화 5조건의 평균 예측 오차(D 실제 − 예측). 부트스트랩 2,000회: "
         "곡선은 main 시드, gen 시드는 두 참가자 묶음에 같은 재표본(짝), main 시드 치우침은 따로 재표본.\n",
         "## 1. 조건별\n",
         "| 조건 | E4 참가자 × gen (mae, D) | **E2 참가자 × gen** (mae, D) | E2 참가자 × main (mae, D) |", "|---|---|---|---|"]
    for c in conds:
        m = vm.get(c)
        L.append(f"| {c} | {v4[c][0]:.2f}, {v4[c][1]:.3f} | {v5[c][0]:.2f}, {v5[c][1]:.3f} | "
                 + (f"{m[0]:.2f}, {m[1]:.3f}" if m else "–") + " |")
    L += ["", "## 2. 치우침과 판정\n", "| 묶음 | 치우침 [95 % CI] |", "|---|---|"]
    for k, nm in (("e4", "E4 참가자 × gen (원래 E4)"), ("e2gen", "**E2 참가자 × gen (이번)**"), ("e2main", "E2 참가자 × main")):
        L.append(f"| {nm} | {est[k]:+.3f} [{ci(arr[k])[0]:+.3f}, {ci(arr[k])[1]:+.3f}] |")
    L += ["", f"- **참가자 효과** P = E4 참가자 − E2 참가자 (같은 gen 시드): {est['e4'] - est['e2gen']:+.3f} [{ci(arr['P'])[0]:+.3f}, {ci(arr['P'])[1]:+.3f}]",
          f"- **시드 효과** S = gen 시드 − main 시드 (같은 E2 참가자): {est['e2gen'] - est['e2main']:+.3f} [{ci(arr['S'])[0]:+.3f}, {ci(arr['S'])[1]:+.3f}]",
          f"\n퍼센타일 부트스트랩으로 본 판정: {verdict} (CI가 0을 벗어난 효과만 원인으로 본다)\n",
          f"보조: SHAM의 D — E4 참가자 {v4['SHAM'][1]:.3f}, E2 참가자 × gen {v5['SHAM'][1]:.3f}. "
          f"E2 참가자 × gen의 열화 5조건 기울기(참고) {np.polyfit([v5[c][0] for c in DEG], [v5[c][1] for c in DEG], 1)[0]:.4f}\n"]
    # 민감도: 시드 단위 t 구간 (시드 4개에서 퍼센타일 부트스트랩은 좁게 나올 수 있다)
    from scipy import stats
    per4 = [bias(t4.pick([s]), a0, b0) for s in GEN]
    per5 = [bias(t5.pick([s]), a0, b0) for s in GEN]
    perm = [bias(tm.pick([s]), a0, b0) for s in sm]
    dP = np.array(per4) - np.array(per5)
    tP = stats.t.ppf(0.975, len(dP) - 1) * dP.std(ddof=1) / np.sqrt(len(dP))
    se = np.sqrt(np.var(per5, ddof=1) / len(per5) + np.var(perm, ddof=1) / len(perm))
    dfw = se ** 4 / ((np.var(per5, ddof=1) / len(per5)) ** 2 / (len(per5) - 1) + (np.var(perm, ddof=1) / len(perm)) ** 2 / (len(perm) - 1))
    tS = stats.t.ppf(0.975, dfw) * se
    sP = (dP.mean() - tP > 0) or (dP.mean() + tP < 0)
    sS = (np.mean(per5) - np.mean(perm) - tS > 0) or (np.mean(per5) - np.mean(perm) + tS < 0)
    v2 = {(True, False): "참가자 탓", (False, True): "시드 탓", (True, True): "둘 다", (False, False): "판정 불가 (둘 다 0과 구별 안 됨)"}[(sP, sS)]
    L.append("시드 단위 t 구간으로 본 판정: "
             f"P {dP.mean():+.3f} [{dP.mean() - tP:+.3f}, {dP.mean() + tP:+.3f}] (짝 t, 자유도 {len(dP) - 1}), "
             f"S {np.mean(per5) - np.mean(perm):+.3f} [{np.mean(per5) - np.mean(perm) - tS:+.3f}, {np.mean(per5) - np.mean(perm) + tS:+.3f}] (Welch) → {v2}"
             + ("" if v2 == verdict else " — **판정이 구간 방식에 민감하다**") + "\n")
    L.append("시드별 치우침: E4 참가자 " + ", ".join(f"{x:+.3f}" for x in per4) + " / E2 참가자 gen " + ", ".join(f"{x:+.3f}" for x in per5)
             + " / E2 참가자 main " + ", ".join(f"{x:+.3f}" for x in perm) + "\n")
    final = verdict if verdict == v2 else "판정 불가 (구간 방식에 따라 다름)"
    L.append(f"**사전 등록 판정 (두 구간 방식이 같을 때만 결론): {final}**\n")
    res = dict(est=est, ci={k: ci(v) for k, v in arr.items()}, verdict=final, verdict_boot=verdict, verdict_t=v2, sham=dict(e4=v4["SHAM"][1], e2gen=v5["SHAM"][1]))
    txt = "\n".join(L) + "\n"
    open(REPORT, "w", encoding="utf-8").write(txt)
    json.dump(res, open(os.environ.get("P5_RESULTS", os.path.join(HERE, "p5_results.json")), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(txt)


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        smoke()
    elif "--report" in sys.argv:
        report()
    else:
        run_games()
        log("경기 완료")
        report()
        log("P5 완료")
