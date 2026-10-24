"""P8: κ가 아닌 둔한 원인도 같은 mae의 진동형보다 결과를 더 바꾸는가 (사전 등록 ../../PREREG_P8.md).

  python p8_run.py --smoke   # 점검: p8smoke-0 3경기
  python p8_run.py           # 탐침(p8probe-0) → 규칙대로 조건 선택 → 본 실행(x8-0–7) → 분석 → p8_output.md
  python p8_run.py --report  # 분석만

실제형 구성(p7_realistic, P7과 같음)에서 돈다. 새 열화 "명령 전달 지연"(cmd_delay, 틱): 유도 계층이 낸 각속도 명령이
n틱 늦게 INDI 에 들어간다(세 축 모두). 추종 오차 기록(run.apply_knobs 의 TRACE)은 늦추기 전의 원래 명령으로 잰다.
루프 안의 측정 지연과 달리 내부 루프를 불안정하게 만들지 않아 느린(지연형) 오차를 만든다.
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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p7_run  # noqa: E402  (실제형 구성 enable, 경로·CONDITIONS F25_D8–12 등록)
import run  # noqa: E402
from experiments import AGENTS_MAIN, CONDITIONS, EXPERIMENTS, LEAGUE  # noqa: E402

KIT = p7_run.KIT
CMD_CAND = [6, 12, 24, 48]                       # 명령 전달 지연 후보 [틱] (50·100·200·400 ms)
KQ_CAND = ["R_kq_0.25", "R_kq_0.5"]
OSC = ["F25_D6", "F25_D8"]                       # 진동형 비교 조건 (고정, P7 main mae 1.26·4.62)
for _n in CMD_CAND:
    CONDITIONS.setdefault(f"CMD{_n}", {"cmd_delay": _n})
OUTDIR = os.path.join(KIT, "out", "p8")
OUT = os.path.join(OUTDIR, "games.csv")
PROBE_OUT = os.path.join(HERE, "p8_probe_games.csv")
SEL = os.path.join(HERE, "p8_conds.json")
REPORT = os.path.join(HERE, "p8_output.md")
LOG = os.path.join(HERE, "p8.log")
KEY = ("cond", "target", "blue", "red", "scenario", "salt")
SALT = "x8"

_orig_apply = run.apply_knobs


def apply_p8(pilot, knobs, seed):
    """명령 전달 지연을 실제형 INDI(안쪽)에 건 뒤 원래 apply_knobs 로 감싼다(TRACE 는 원래 명령을 본다)."""
    n = int(knobs.get("cmd_delay", 0))
    if n:
        inner = pilot.indi.update
        hist = collections.deque(maxlen=n + 1)

        def update(omega, omega_sp, qbar, **kw):
            hist.append(np.array(omega_sp, float))
            return inner(omega, hist[0], qbar, **kw)
        pilot.indi.update = update
    _orig_apply(pilot, knobs, seed)


run.apply_knobs = apply_p8          # run._patched_setup 이 호출 시점에 이 이름을 찾는다


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def play(job):
    assert getattr(run, "_p7_enabled", False) and run.apply_knobs is apply_p8
    return run.play(job)


def run_jobs(js, out, name):
    rows = p7_run.read(out)
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
    if any(r["condition"] == "wall_clock" for r in p7_run.read(out)):
        run_jobs(js, out, name)


def probe_and_select():
    conds = [f"CMD{n}" for n in CMD_CAND] + KQ_CAND
    js = run.build_jobs(dict(agents=AGENTS_MAIN, scenarios=("neutral",), salt="p8probe", conds=conds), 1)
    run_jobs(js, PROBE_OUT, "탐침")
    mae = collections.defaultdict(list)
    for r in p7_run.read(PROBE_OUT):
        mae[r["cond"]] += [float(r["blue_mae_q_dps"]), float(r["red_mae_q_dps"])]
    m = {c: float(np.mean(v)) for c, v in mae.items()}
    p7 = json.load(open(os.path.join(HERE, "p7_results.json"), encoding="utf-8"))["conds"]
    lo, hi = p7[OSC[0]]["mae"], p7[OSC[1]]["mae"]
    mid = float(np.exp((np.log(lo) + np.log(hi)) / 2))

    def pick(cands):
        inside = [c for c in cands if lo <= m[c] <= hi]
        pool = inside if inside else cands
        best = min(pool, key=lambda c: abs(np.log(m[c]) - np.log(mid)))
        return best, bool(inside)
    c1, ok1 = pick([f"CMD{n}" for n in CMD_CAND])
    c2, ok2 = pick(KQ_CAND)
    sel = dict(sluggish=[c1, c2], in_range={c1: ok1, c2: ok2}, osc=OSC, probe_mae=m, osc_range=(lo, hi), log_mid=mid)
    json.dump(sel, open(SEL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log(f"조건 선택: 둔한 {c1}({m[c1]:.2f}, 범위 안 {ok1}), {c2}({m[c2]:.2f}, 범위 안 {ok2}); 진동 {OSC} 범위 {lo:.2f}–{hi:.2f}")
    return sel


def main_run():
    sel = json.load(open(SEL, encoding="utf-8")) if os.path.isfile(SEL) else probe_and_select()
    os.makedirs(OUTDIR, exist_ok=True)
    js = run.build_jobs(dict(agents=AGENTS_MAIN, scenarios=LEAGUE, salt=SALT, conds=["BASE"] + sel["sluggish"] + OSC), 8)
    run_jobs(js, OUT, "본 실행")


def report():
    import predict as P
    from scipy import stats
    sel = json.load(open(SEL, encoding="utf-8"))
    slug, osc = sel["sluggish"], sel["osc"]
    AG = list(EXPERIMENTS["E2"]["agents"])
    BYX, BYP = collections.defaultdict(list), collections.defaultdict(list)
    for r in p7_run.read(OUT):
        BYX[(r["cond"], r["salt"])].append(r)
    for r in p7_run.read(os.path.join(KIT, "out", "p7", "games.csv")):
        BYP[(r["cond"], r["salt"])].append(r)
    sx = sorted({s for (_, s) in BYX}, key=lambda x: int(x.rsplit("-", 1)[1]))
    sp = sorted({s for (_, s) in BYP}, key=lambda x: int(x.rsplit("-", 1)[1]))
    dl = ["F25_D2", "F25_D4", "F25_D6", "F25_D8", "F25_D10", "F25_D12"]
    tp = P.Table(BYP, dl, "BASE", sp, AG)
    tx = P.Table(BYX, slug + osc, "BASE", sx, AG)
    line = lambda v: np.polyfit([v[c][0] for c in dl], [v[c][1] for c in dl], 1)    # (기울기, 절편)
    b0, a0 = line(tp.pick(sp))
    vx = tx.pick(sx)
    res = lambda v, a, b, cs: float(np.mean([v[c][1] - (a + b * v[c][0]) for c in cs]))
    con = lambda v, a, b, cs1, cs2: res(v, a, b, cs1) - res(v, a, b, cs2)
    rng = np.random.default_rng(0)
    BP = [list(rng.choice(sp, len(sp))) for _ in range(2000)]
    BX = [list(rng.choice(sx, len(sx))) for _ in range(2000)]
    curves = [line(tp.pick(b)) for b in BP]
    vxs = [tx.pick(b) for b in BX]
    per = {s: tx.pick([s]) for s in sx}
    tq = stats.t.ppf(0.975, len(sx) - 1)
    ci = lambda a: tuple(float(x) for x in np.percentile(a, [2.5, 97.5]))

    def two(cs1, cs2):
        d0 = con(vx, a0, b0, cs1, cs2)
        cb = ci([con(v, a, b, cs1, cs2) for (b, a), v in zip(curves, vxs)])
        pv = [con(per[s], a0, b0, cs1, cs2) for s in sx]
        ct = (float(np.mean(pv) - tq * np.std(pv, ddof=1) / np.sqrt(len(pv))), float(np.mean(pv) + tq * np.std(pv, ddof=1) / np.sqrt(len(pv))))
        j = lambda lo, hi: "확인" if lo > 0 else ("반대" if hi < 0 else "판정 불가")
        v = j(*cb) if j(*cb) == j(*ct) else "판정 불가 (구간 방식에 따라 다름)"
        return d0, cb, ct, v
    main = two(slug, osc)
    sub = {c: two([c], osc) for c in slug}
    L = ["# P8: κ가 아닌 둔한 원인 (사전 등록 `PREREG_P8.md`)\n",
         f"실제형 구성, 시드 {', '.join(sx)}, 경기 {len(p7_run.read(OUT)):,}. 기준 직선은 P7 지연형 6조건(main 시드): D = {a0:.3f} + {b0:.4f}·mae.\n",
         f"선택(탐침 p8probe-0): 둔한 {slug} (탐침 mae {', '.join(f'{sel['probe_mae'][c]:.2f}' for c in slug)}, 범위 안 {sel['in_range']}), 진동형 {osc}\n",
         "| 조건 | 유형 | mae | D | 기준 직선 잔차 |", "|---|---|---|---|---|"]
    for c in slug + osc:
        L.append(f"| {c} | {'둔한(κ 아님)' if c in slug else '진동형'} | {vx[c][0]:.2f} | {vx[c][1]:.3f} | {vx[c][1] - (a0 + b0 * vx[c][0]):+.3f} |")
    L += ["", f"**T8 (주) 둔한 − 진동 잔차 차이: {main[0]:+.3f}**, 퍼센타일 [{main[1][0]:+.3f}, {main[1][1]:+.3f}], 시드 t [{main[2][0]:+.3f}, {main[2][1]:+.3f}] → **{main[3]}**\n",
          "원인별 (보조):"]
    for c, s in sub.items():
        L.append(f"- {c}: {s[0]:+.3f}, 퍼센타일 [{s[1][0]:+.3f}, {s[1][1]:+.3f}], 시드 t [{s[2][0]:+.3f}, {s[2][1]:+.3f}] → {s[3]}")
    txt = "\n".join(L) + "\n"
    open(REPORT, "w", encoding="utf-8").write(txt)
    json.dump(dict(main=main, sub=sub, conds={c: vx[c] for c in slug + osc}, line=(float(a0), float(b0))),
              open(os.path.join(HERE, "p8_results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    print(txt)


def smoke():
    js = [j for j in run.build_jobs(dict(agents=AGENTS_MAIN, scenarios=("neutral",), salt="p8smoke", conds=["BASE", "CMD24", "R_kq_0.25"]), 1)
          if j["blue"] == "GunTracker" and j["red"] == "Extender"]
    with mp.Pool(3) as pool:
        rs = pool.map(play, js)
    for r in rs:
        print(r["cond"], r["winner"], r["condition"], r["blue_mae_q_dps"], r["red_mae_q_dps"])
    log(f"점검(p8smoke-0, {len(rs)}경기) 통과")


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        smoke()
    elif "--report" in sys.argv:
        report()
    else:
        if os.name == "nt":
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        main_run()
        log("경기 완료")
        report()
        log("P8 완료")
