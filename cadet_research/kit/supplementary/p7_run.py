"""P7: 실제형 센서·구동기에서 추종 오차–결과 변화 관계 (사전 등록 ../../PREREG_P7.md).

  python p7_run.py --probe   # 수준 고르기 탐침: 확증이 아닌 시드 p7probe-0, neutral, 후보 조건 × 56경기 → p7_probe_output.md
  python p7_run.py --smoke   # 점검: p7smoke-0 에서 3경기
  python p7_run.py           # 본 실행 (조건은 PREREG_P7.md 에서 고정) → ../out/p7/games.csv, 분석 → p7_output.md
  python p7_run.py --report  # 분석만

실제형 구성은 p7_realistic.enable() (구동기 20.2 rad/s·60/80 °/s, 자이로 차분 각가속도, 구동기 위치 측정 동기화).
게인은 키트 기본(K 9, 25 Hz)이다. 선형 모형(p7_design_output.md)과 벤치(p7_bench_output.md)에서 이득 여유 16 dB·위상 여유 59°로
6 dB/45° 기준을 만족해 다시 조정하지 않았다.
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
sys.path.insert(0, HERE)
os.chdir(KIT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import run  # noqa: E402
import p7_realistic  # noqa: E402
from experiments import AGENTS_MAIN, CONDITIONS, EXPERIMENTS, LEAGUE  # noqa: E402

p7_realistic.enable()
for _d in (8, 10, 12):
    CONDITIONS.setdefault(f"F25_D{_d}", {"filt_hz": 25.0, "delay_async": float(_d)})

PROBE = ["BASE", "F25_D2", "F25_D4", "F25_D6", "F25_D8", "F25_D10", "F25_D12",
         "R_kappa_8", "R_kappa_25", "R_kappa_50", "R_kappa_100", "R_kq_0.25"]
MAIN_CONDS: list = json.load(open(os.path.join(HERE, "p7_conds.json"), encoding="utf-8"))["conds"] \
    if os.path.isfile(os.path.join(HERE, "p7_conds.json")) else []
OUTDIR = os.path.join(KIT, "out", "p7")
OUT = os.environ.get("P7_GAMES", os.path.join(OUTDIR, "games.csv"))
PROBE_OUT = os.path.join(HERE, "p7_probe_games.csv")
REPORT = os.environ.get("P7_REPORT", os.path.join(HERE, "p7_output.md"))
LOG = os.path.join(HERE, "p7.log")
KEY = ("cond", "target", "blue", "red", "scenario", "salt")


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
    assert getattr(run, "_p7_enabled", False), "실제형 구성이 적용되지 않았다"
    return run.play(job)


def run_jobs(js, out, name):
    rows = read(out)
    keep = [r for r in rows if r["condition"] != "wall_clock"]
    if len(keep) != len(rows):
        log(f"{name}: wall_clock {len(rows) - len(keep)}판을 지우고 다시 돈다")
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=run.FIELDS); w.writeheader(); w.writerows(keep)
    done = {tuple(r[k] for k in KEY) for r in keep}
    todo = [j for j in js if tuple(j[k] for k in KEY) not in done]
    log(f"{name}: 전체 {len(js)}판, 기록됨 {len(js) - len(todo)}, 남음 {len(todo)}")
    if not todo:
        return
    new = not os.path.isfile(out)
    t0 = time.time()
    with mp.Pool(14) as pool, open(out, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=run.FIELDS)
        if new:
            w.writeheader()
        for i, row in enumerate(pool.imap_unordered(play, todo, chunksize=1), 1):
            w.writerow(row); f.flush()
            if i % 200 == 0 or i == len(todo):
                el = time.time() - t0
                log(f"  {name} {i}/{len(todo)}  {el:.0f}s 경과, 남은 예상 {el / i * (len(todo) - i):.0f}s")
    if any(r["condition"] == "wall_clock" for r in read(out)):
        run_jobs(js, out, name)


def probe():
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    js = run.build_jobs(dict(agents=AGENTS_MAIN, scenarios=("neutral",), salt="p7probe", conds=PROBE), 1)
    run_jobs(js, PROBE_OUT, "탐침")
    rows = read(PROBE_OUT)
    import predict as P
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["cond"], r["salt"])].append(r)
    v = P.Table(by, [c for c in PROBE if c != "BASE"], "BASE", ["p7probe-0"], list(AGENTS_MAIN)).pick(["p7probe-0"])
    base_mae = float(np.mean([float(r[k]) for r in by[("BASE", "p7probe-0")] for k in ("blue_mae_q_dps", "red_mae_q_dps")]))
    ends = collections.Counter(r["condition"] for r in by[("BASE", "p7probe-0")])
    L = ["# P7 탐침 (수준 고르기, 판정 없음): 실제형 구성, 시드 p7probe-0, neutral 56경기\n",
         f"BASE mae {base_mae:.2f} °/s, 종료 사유 {dict(ends)}\n",
         "| 조건 | mae [°/s] | D (56경기) |", "|---|---|---|"]
    for c in PROBE[1:]:
        L.append(f"| {c} | {v[c][0]:.2f} | {v[c][1]:.3f} |")
    txt = "\n".join(L) + "\n"
    open(os.path.join(HERE, "p7_probe_output.md"), "w", encoding="utf-8").write(txt)
    print(txt)


def smoke():
    js = [j for j in run.build_jobs(dict(agents=AGENTS_MAIN, scenarios=("neutral",), salt="p7smoke", conds=["BASE", "F25_D6", "R_kappa_25"]), 1)
          if j["blue"] == "GunTracker" and j["red"] == "Extender"]
    with mp.Pool(3) as pool:
        rs = pool.map(play, js)
    for r in rs:
        print(r["cond"], r["winner"], r["condition"], r["hp_blue"], r["hp_red"], r["blue_mae_q_dps"], r["red_mae_q_dps"])
    log(f"점검(p7smoke-0, {len(rs)}경기) 통과")


def main_run():
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    assert MAIN_CONDS, "p7_conds.json 이 없다 (사전 등록에서 조건을 먼저 고정한다)"
    os.makedirs(OUTDIR, exist_ok=True)
    js = run.build_jobs(dict(agents=AGENTS_MAIN, scenarios=LEAGUE, salt="main", conds=["BASE"] + MAIN_CONDS), 8)
    run_jobs(js, OUT, "본 실행")


if __name__ == "__main__":
    if "--probe" in sys.argv:
        probe()
    elif "--smoke" in sys.argv:
        smoke()
    elif "--report" in sys.argv:
        import p7_report
        p7_report.report()
    else:
        main_run()
        log("경기 완료")
        import p7_report
        p7_report.report()
        log("P7 완료")
