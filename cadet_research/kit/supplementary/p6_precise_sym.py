"""P6: 정밀 조준 기총에서 대칭 열화의 추종 오차–결과 변화 관계 (사전 등록 ../../PREREG_P6.md, 실행 전 고정).

  python p6_precise_sym.py           # 5,376경기 (약 2.7시간) → ../out/p6/games.csv, 그다음 분석 → p6_output.md
  python p6_precise_sym.py --report  # 경기 없이 분석만
  python p6_precise_sym.py --smoke   # 점검: p6smoke-0 에서 3경기 (결과 파일에 쓰지 않음)

기총 조준각 등급만 2° 미만 100 %, 5° 미만 50 %, 그 밖 0 으로 바꾼다(P2-b와 같음). 사거리·전술 판단·제어는 그대로.
엔진 파일은 고치지 않고 작업 프로세스 안에서 aircombat.geometry.wez.WEZ_ATA_TIERS 만 바꾼다.
{BASE, SHAM, E2 6조건} × 8명 리그(168경기) × 시드 main-0–3. 같은 시드·조건의 원래 기총 결과(out/main)와 짝지어 비교한다.
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
from aircombat.geometry import wez as wez_mod  # noqa: E402
from experiments import AGENTS_MAIN, EXPERIMENTS, LEAGUE  # noqa: E402

PRECISE_TIERS = ((2.0, 1.00), (5.0, 0.50))
ORIGINAL_TIERS = wez_mod.WEZ_ATA_TIERS
wez_mod.WEZ_ATA_TIERS = PRECISE_TIERS          # 모든 작업 프로세스가 이 모듈을 다시 불러오므로 여기서 바꾼다

CONDS = ["F12_D0.5", "F25_D0.5", "F12_D1", "F25_D1", "F5_D3", "F25_D2"]
SEEDS = [f"main-{i}" for i in range(4)]
OUTDIR = os.path.join(KIT, "out", "p6")
OUT = os.environ.get("P6_GAMES", os.path.join(OUTDIR, "games.csv"))     # 환경 변수는 분석 점검용
REPORT = os.environ.get("P6_REPORT", os.path.join(HERE, "p6_output.md"))
LOG = os.path.join(HERE, "p6.log")
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


def play(job):
    assert wez_mod.WeaponEngagementZone._spec(False)[1] == PRECISE_TIERS, "반사실 기총이 적용되지 않았다"
    return run.play(job)


def jobs(salt="main", n=4):
    return run.build_jobs(dict(agents=AGENTS_MAIN, scenarios=LEAGUE, salt=salt, conds=["BASE", "SHAM"] + CONDS), n)


def smoke():
    js = [j for j in jobs("p6smoke", 1) if j["scenario"] == "neutral" and j["blue"] == "GunTracker" and j["red"] == "Extender"
          and j["cond"] in ("BASE", "SHAM", "F25_D2")]
    with mp.Pool(3) as pool:
        rs = pool.map(play, js)
    for r in rs:
        print(r["cond"], r["winner"], r["condition"], r["hp_blue"], r["hp_red"], r["blue_mae_q_dps"])
    log(f"점검(p6smoke-0, {len(rs)}경기) 통과. 본 실행 {len(jobs())}판, 기총 등급 {PRECISE_TIERS}")


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
            if i % 200 == 0 or i == len(todo):
                el = time.time() - t0
                log(f"  {i}/{len(todo)}  {el:.0f}s 경과, 남은 예상 {el / i * (len(todo) - i):.0f}s")
    if any(r["condition"] == "wall_clock" for r in read(OUT)):
        run_games()


def report():
    import predict as P
    P.SHAPE = "linear"
    tol = json.load(open(os.path.join(KIT, "out", "cal", "tolerance.json"), encoding="utf-8"))
    AG = list(EXPERIMENTS["E2"]["agents"])
    fitc = [c for c in EXPERIMENTS["E2"]["conds"] if c != "BASE"]
    rows = read(OUT)
    BYP = collections.defaultdict(list)
    for r in rows:
        BYP[(r["cond"], r["salt"])].append(r)
    BYM = P.load("main")
    sm8 = P.seeds_of(BYM, "main", fitc)
    conds = ["SHAM"] + CONDS
    tp = P.Table(BYP, conds, "BASE", SEEDS, AG)
    to = P.Table(BYM, CONDS, "BASE", SEEDS, AG)
    vp, vo = tp.pick(SEEDS), to.pick(SEEDS)
    rng = np.random.default_rng(0)
    BS = [list(rng.choice(SEEDS, len(SEEDS))) for _ in range(N_BOOT)]
    slope = lambda v: float(np.polyfit([v[c][0] for c in CONDS], [v[c][1] for c in CONDS], 1)[0])
    bp, bo = slope(vp), slope(vo)
    arr_p, arr_o = [], []
    for b in BS:
        arr_p.append(slope(tp.pick(b))); arr_o.append(slope(to.pick(b)))
    dB = np.array(arr_p) - np.array(arr_o)
    ci = lambda a, lv=95.0: tuple(float(x) for x in np.percentile(a, [(100 - lv) / 2, 100 - (100 - lv) / 2]))
    span = max(vo[c][0] for c in CONDS) - min(vo[c][0] for c in CONDS)
    eq = tol["D"] / span
    lo, hi = ci(dB)
    t1 = "같다(무기 모델에 기대지 않음)" if -eq <= lo and hi <= eq else ("다르다" if lo > eq or hi < -eq else "판정 불가")
    lab = lambda r: r["condition"] + ("·무승부" if r["winner"] == "draw" and r["condition"] != "no_contact" else "")
    ends = collections.Counter(lab(r) for r in rows if r["cond"] == "BASE")
    ends_o = collections.Counter(lab(r) for s in SEEDS for r in BYM[("BASE", s)])
    L = ["# P6: 정밀 조준 기총에서 대칭 열화 (사전 등록 `PREREG_P6.md`)\n",
         f"기총 등급 {PRECISE_TIERS} (원래 {ORIGINAL_TIERS}). 경기 {len(rows):,} (사전 등록 5,376), `wall_clock` {sum(r['condition'] == 'wall_clock' for r in rows)}. "
         f"시드 {', '.join(SEEDS)}. 비교 대상은 같은 시드·조건의 원래 기총 결과(`out/main`).\n",
         "## 0. BASE 종료 사유 (기총 모델별, 시드 4개 × 168경기)\n",
         "| 종료 | 정밀 조준 | 원래 |", "|---|---|---|"]
    for k in sorted(set(ends) | set(ends_o)):
        L.append(f"| {k} | {ends[k]} | {ends_o[k]} |")
    L += ["", "## 1. 조건별 (같은 시드 4개)\n",
          "| 조건 | mae 정밀 / 원래 | D 정밀 / 원래 | 등록 직선 예측 (정밀 mae) | 정밀 예측 오차 |", "|---|---|---|---|---|"]
    a0, b0 = 0.14380045578818365, 0.05309285306453424
    for c in conds:
        o = vo.get(c)
        L.append(f"| {c} | {vp[c][0]:.2f} / {o[0] if o else float('nan'):.2f} | {vp[c][1]:.3f} / {o[1] if o else float('nan'):.3f} | "
                 f"{a0 + b0 * vp[c][0]:.3f} | {vp[c][1] - (a0 + b0 * vp[c][0]):+.3f} |")
    L += ["", "## 2. 사전 등록 판정\n",
          f"**T6-1 기울기**: 정밀 조준 {bp:.4f} [{ci(arr_p)[0]:.4f}, {ci(arr_p)[1]:.4f}], 원래 {bo:.4f} [{ci(arr_o)[0]:.4f}, {ci(arr_o)[1]:.4f}] (같은 6조건·시드 4개). "
          f"차이 {bp - bo:+.4f} [{lo:+.4f}, {hi:+.4f}], 동등 여유 ±{eq:.4f} (= δ_D {tol['D']:.3f} / mae 범위 {span:.2f}) → **{t1}**\n"]
    from scipy import stats
    dps = np.array([slope(tp.pick([s])) - slope(to.pick([s])) for s in SEEDS])
    tq = stats.t.ppf(0.975, len(dps) - 1) * dps.std(ddof=1) / np.sqrt(len(dps))
    tl, th = dps.mean() - tq, dps.mean() + tq
    t1t = "같다(무기 모델에 기대지 않음)" if -eq <= tl and th <= eq else ("다르다" if tl > eq or th < -eq else "판정 불가")
    L.append(f"민감도 (시드 단위 짝 t 구간, 자유도 {len(dps) - 1}): 시드별 기울기 차이 " + ", ".join(f"{x:+.4f}" for x in dps)
             + f", 평균 {dps.mean():+.4f} [{tl:+.4f}, {th:+.4f}] → {t1t}" + ("" if t1t == t1 else " — **판정이 구간 방식에 민감하다**") + "\n")
    P.OUT.clear()
    P.validate(BYM, fitc, BYP, CONDS, "BASE", sm8, SEEDS, AG, {"D": tol["D"], "M": tol["M"]},
               "T6-2. 등록 곡선(원래 기총, main 8시드)으로 정밀 조준 기총의 D 예측")
    grp = [l for l in P.OUT if l.startswith("| 원인:") or l.startswith("| 전체")]
    t2 = grp[0].split("|")[3].strip() if grp else "–"
    L.extend(P.OUT); P.OUT.clear()
    L.append(f"**T6-2 판정 (등록 규칙, 필터·비동기 지연 묶음)**: **{t2}**\n")
    final1 = t1 if t1 == t1t else "판정 불가 (구간 방식에 따라 다름)"
    L.append(f"**T6-1 사전 등록 판정 (두 구간 방식이 같을 때만 결론): {final1}**\n")
    res = dict(slope_precise=bp, slope_original=bo, diff=bp - bo, ci=(lo, hi), eq=eq, T1=final1, T1_boot=t1, T1_t=t1t, T2=t2,
               sham_D=vp["SHAM"][1], conds={c: dict(mae=vp[c][0], D=vp[c][1]) for c in conds})
    txt = "\n".join(L) + "\n"
    open(REPORT, "w", encoding="utf-8").write(txt)
    json.dump(res, open(os.environ.get("P6_RESULTS", os.path.join(HERE, "p6_results.json")), "w", encoding="utf-8"),
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
        log("P6 완료")
