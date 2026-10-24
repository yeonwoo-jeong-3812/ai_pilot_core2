"""P2-b: 정밀 조준 기총 반사실 (사전 등록 ../../PREREG_P2.md §P2-b, 실행 전 고정).

  python p2b_precise_gun.py          # 1,008경기 (약 30분) → p2b_games.csv, p2b_output.md. 끊기면 다시 치면 이어서 돈다
  python p2b_precise_gun.py --report # 경기 없이 분석만

기총 조준각 등급만 2° 미만 100 %, 5° 미만 50 %, 그 밖 0 으로 바꾼다(원래 2/10/20/30°). 사거리는 그대로.
엔진 파일은 고치지 않고 작업 프로세스 안에서 aircombat.geometry.wez.WEZ_ATA_TIERS 만 바꾼다.
전술 판단(in_gun_envelope 30°)과 유도·제어는 그대로라, 조종사 행동은 같고 맞히는 조건만 엄격해진다.
"""
import csv
import ctypes
import multiprocessing as mp
import os
import sys
import time

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # kit/supplementary → kit
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
os.chdir(KIT)
import run  # noqa: E402
from aircombat.geometry import wez as wez_mod  # noqa: E402
from experiments import AGENTS_MAIN, EXPERIMENTS  # noqa: E402

PRECISE_TIERS = ((2.0, 1.00), (5.0, 0.50))
ORIGINAL_TIERS = wez_mod.WEZ_ATA_TIERS
wez_mod.WEZ_ATA_TIERS = PRECISE_TIERS          # 모든 작업 프로세스가 이 모듈을 다시 불러오므로 여기서 바꾼다

TARGET = "GunTracker"
CONDS = ["F25_D2", "F25_D6"]
OUT = os.path.join(HERE, "p2b_games.csv")
REPORT = os.path.join(HERE, "p2b_output.md")
LOG = os.path.join(HERE, "p2b.log")
KEY = ("cond", "target", "blue", "red", "scenario", "salt")
DELTA_PTS = 11.10


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def play(job):
    assert wez_mod.WeaponEngagementZone._spec(False)[1] == PRECISE_TIERS, "반사실 기총이 적용되지 않았다"
    return run.play(job)


def jobs():
    exp = EXPERIMENTS["ASYM"]
    js = [j for j in run.build_jobs(exp, exp["salts"]) if j["cond"] in CONDS and j["target"] == TARGET]
    base = [dict(j, cond="BASE", target="") for j in js if j["cond"] == CONDS[0]]
    return base + js


def read(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_games():
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    js = jobs()
    done = {tuple(r[k] for k in KEY) for r in read(OUT) if r["condition"] != "wall_clock"}
    rows_keep = [r for r in read(OUT) if r["condition"] != "wall_clock"]
    if len(rows_keep) != len(read(OUT)):                       # 실행 인공물 정리 (PREREG_EXTRA 와 같은 규칙)
        log(f"wall_clock {len(read(OUT)) - len(rows_keep)}판을 지우고 다시 돈다")
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=run.FIELDS); w.writeheader(); w.writerows(rows_keep)
    todo = [j for j in js if tuple(j[k] for k in KEY) not in done]
    log(f"전체 {len(js)}판, 기록됨 {len(js) - len(todo)}, 남음 {len(todo)} (기총 등급 {PRECISE_TIERS})")
    if not todo:
        return
    new = not os.path.isfile(OUT)
    t0 = time.time()
    with mp.Pool(14) as pool, open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=run.FIELDS)
        if new:
            w.writeheader()
        for i, row in enumerate(pool.imap_unordered(play, todo, chunksize=1), 1):
            w.writerow(row); f.flush()
            if i % 100 == 0 or i == len(todo):
                el = time.time() - t0
                log(f"  {i}/{len(todo)}  {el:.0f}s 경과, 남은 예상 {el / i * (len(todo) - i):.0f}s")
    left = [r for r in read(OUT) if r["condition"] == "wall_clock"]
    if left:
        log(f"wall_clock {len(left)}판 발견 → 다시 실행")
        return run_games()


def report():
    from analyze import points
    ag = list(EXPERIMENTS["E2"]["agents"])
    seeds = [f"main-{i}" for i in range(8)]
    kb = lambda r: (r["blue"], r["red"], r["scenario"], r["salt"])

    def dpts(rows, base_rows):
        base = {kb(r): r for r in base_rows}
        out = {}
        for c in CONDS:
            for s in seeds:
                gs = [r for r in rows if r["cond"] == c and r["target"] == TARGET and r["salt"] == s]
                bs = [base[kb(g)] for g in gs]
                out[(c, s)] = points(gs, ag)[0][TARGET] - points(bs, ag)[0][TARGET]
        return out
    rows = read(OUT)
    cf = dpts(rows, [r for r in rows if r["cond"] == "BASE"])
    orig_rows = read(os.path.join(KIT, "out", "asym", "games.csv"))
    main_base = [r for r in read(os.path.join(KIT, "out", "main", "games.csv")) if r["cond"] == "BASE" and r["target"] == ""]
    og = dpts(orig_rows, main_base)
    rng = np.random.default_rng(0)
    boots = [list(rng.choice(seeds, len(seeds))) for _ in range(2000)]
    lvl = 100 * (1 - 0.05 / 3)

    def summarize(d):
        con = {s: d[("F25_D6", s)] - d[("F25_D2", s)] for s in seeds}
        res = {}
        for name, f in (("2틱", lambda s: d[("F25_D2", s)]), ("6틱", lambda s: d[("F25_D6", s)]), ("대비 6틱 − 2틱", lambda s: con[s])):
            b = [np.mean([f(s) for s in bb]) for bb in boots]
            lo, hi = np.percentile(b, [(100 - lvl) / 2, 100 - (100 - lvl) / 2])
            res[name] = (float(np.mean([f(s) for s in seeds])), float(lo), float(hi), int(sum(f(s) > 0 for s in seeds)))
        return res
    rc, ro = summarize(cf), summarize(og)
    lo, hi = rc["대비 6틱 − 2틱"][1], rc["대비 6틱 − 2틱"][2]
    verdict = "반등 소멸" if hi < DELTA_PTS else ("반등 유지" if lo > DELTA_PTS else "판정 불가")
    import collections
    ends = collections.defaultdict(collections.Counter)
    for r in rows:
        if r["cond"] == "BASE" and TARGET not in (r["blue"], r["red"]):
            continue
        t = TARGET
        k = ("무접촉" if r["condition"] == "no_contact" else "무승부" if r["winner"] == "draw"
             else ("대상 승·" if r["winner"] == t else "대상 패·") + r["condition"])
        ends[r["cond"]][k] += 1
    L = ["# P2-b: 정밀 조준 기총 반사실 (사전 등록 `PREREG_P2.md` §P2-b)\n",
         f"기총 등급 {PRECISE_TIERS} (원래 {ORIGINAL_TIERS}). 대상 {TARGET}, 시드 8개, 경기 {len(rows)} (사전 등록 1,008). "
         f"`wall_clock` {sum(r['condition'] == 'wall_clock' for r in rows)}판.\n",
         f"## 판정 (δ_점수 {DELTA_PTS}, 시드 부트스트랩 {lvl:.2f} % CI)\n",
         "| 기총 모델 | Δ점수 2틱 [CI] | Δ점수 6틱 [CI] | **대비 6틱 − 2틱 [CI]** | 대비 > 0 인 시드 |",
         "|---|---|---|---|---|"]
    for name, r in (("**정밀 조준 (반사실)**", rc), ("원래 (30° 등급, ASYM)", ro)):
        a, b, c = r["2틱"], r["6틱"], r["대비 6틱 − 2틱"]
        L.append(f"| {name} | {a[0]:+.1f} [{a[1]:+.1f}, {a[2]:+.1f}] | {b[0]:+.1f} [{b[1]:+.1f}, {b[2]:+.1f}] | "
                 f"**{c[0]:+.1f} [{c[1]:+.1f}, {c[2]:+.1f}]** | {c[3]}/8 |")
    L.append(f"\n**사전 등록 판정: {verdict}** (반사실 대비의 CI [{lo:+.1f}, {hi:+.1f}]를 +{DELTA_PTS}와 비교)\n")
    L.append("## 종료 방식 (대상 기준, 반사실 기총, 시드 8개 합)\n")
    keys = sorted({k for c in ends for k in ends[c]})
    L.append("| 조건 | " + " | ".join(keys) + " |")
    L.append("|---|" + "---|" * len(keys))
    for c in ("BASE", "F25_D2", "F25_D6"):
        L.append(f"| {c} | " + " | ".join(str(ends[c][k]) for k in keys) + " |")
    txt = "\n".join(L) + "\n"
    open(REPORT, "w", encoding="utf-8").write(txt)
    print(txt)


if __name__ == "__main__":
    if "--report" not in sys.argv:
        run_games()
        log("경기 완료")
    report()
    log("P2-b 완료")
