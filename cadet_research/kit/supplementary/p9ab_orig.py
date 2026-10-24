"""P9-b·P9-a: 원래 구성에서 U자의 원인 (사전 등록 ../../PREREG_P9.md §P9-b, §P9-a).

  python p9ab_orig.py --smoke    # 점검
  python p9ab_orig.py            # P9-b(1,344경기) → P9-a(기록 재생 252경기) → 분석 → p9ab_output.md
  python p9ab_orig.py --report   # 분석만

P9-b 흔들림만 넣기: 고장 없는 대상 기체의 피치 각속도 명령에 사인파 A·sin(2π·2.2 Hz·t)를 더해 INDI 에 넣는다(대상 한 기체만).
     추종 오차 기록(TRACE)은 더하기 전의 원래 명령으로 잰다 → 흔들림이 오차로 잡힌다(6틱 고장과 같은 방식).
     짝: 원래 구성 BASE(../out/main, 같은 main 시드).
P9-a 기록 재생: ASYM GunTracker × {BASE, F25_D2, F25_D6} × main-0·1 (252경기)를 다시 돌리며 틱마다 위치 관계·조준각과
     상대의 전술 행동 이름을 기록한다. 먼저 기록(out/main, out/asym)과 같은지 확인한다.
엔진·키트·참가자 파일은 고치지 않는다(실행 중에만 감싼다).
"""
from __future__ import annotations

import collections
import csv
import ctypes
import json
import math
import multiprocessing as mp
import os
import sys
import time

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
os.chdir(KIT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import run  # noqa: E402
from aircombat.engine import match as match_mod  # noqa: E402
from experiments import AGENTS_MAIN, CONDITIONS, EXPERIMENTS, LEAGUE  # noqa: E402

DT = 1.0 / 120.0
OSC_HZ = 2.2
CONDITIONS.setdefault("OSC10", {"osc_dps": 10.0})
CONDITIONS.setdefault("OSC20", {"osc_dps": 20.0})
TARGETS = ["GunTracker", "Extender"]
B_CONDS = ["OSC10", "OSC20"]
OUT_B = os.path.join(KIT, "out", "p9b", "games.csv")
OUT_A = os.path.join(HERE, "p9a_games.csv")
REPORT = os.path.join(HERE, "p9ab_output.md")
LOG = os.path.join(HERE, "p9.log")
KEY = ("cond", "target", "blue", "red", "scenario", "salt")
DELTA_PTS = 11.10
DEF_RULE = {"EnergyFighter", "Extender", "TwoCircle", "Reactive"}       # is_defensive 규칙이 있는 상대

REC = {"geo": [], "mode": collections.defaultdict(list)}
_orig_apply = run.apply_knobs
_orig_wez = match_mod._wez_damage


def apply_p9(pilot, knobs, seed):
    a = float(knobs.get("osc_dps", 0.0))
    if a:
        inner = pilot.indi.update
        k = [0]

        def update(omega, omega_sp, qbar, **kw):
            sp = np.array(omega_sp, float)
            sp[1] += math.radians(a) * math.sin(2 * math.pi * OSC_HZ * k[0] * DT)
            k[0] += 1
            return inner(omega, sp, qbar, **kw)
        pilot.indi.update = update
    _orig_apply(pilot, knobs, seed)
    if REC.get("on"):
        tick = pilot.policy.tick
        rec = REC["mode"][pilot.color]

        def logged(ctx):
            cmd = tick(ctx)
            rec.append(cmd.name)
            return cmd
        pilot.policy.tick = logged


run.apply_knobs = apply_p9


def _nose(th, ps):
    return np.array([math.cos(th) * math.cos(ps), math.cos(th) * math.sin(ps), -math.sin(th)])


def wez_logged(shooter, target, dt, overtime=False):
    dmg, ata = _orig_wez(shooter, target, dt, overtime)
    if REC.get("on"):
        los = np.asarray(target.pos_ned) - np.asarray(shooter.pos_ned)
        REC["geo"].append((float(ata), float(np.linalg.norm(los)), float(dmg)))
    return dmg, ata


match_mod._wez_damage = wez_logged


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


def play_b(job):
    REC["on"] = False
    return run.play(job)


def play_a(job):
    """재생 + 기록. 대상(GunTracker)의 색을 찾아 틱마다 (대상 조준각, 상대 조준각, 거리, 대상 피해)를 모은다."""
    REC["on"] = True
    REC["geo"].clear(); REC["mode"].clear()
    r = run.play(job)
    t = "GunTracker"
    tc = "Blue" if r["blue"] == t else "Red"
    oc = "Red" if tc == "Blue" else "Blue"
    g = np.array(REC["geo"])            # 짝수: blue 가 쏘는 쪽, 홀수: red 가 쏘는 쪽 (match 의 호출 순서)
    n = len(g) // 2
    blue, red = g[0:2 * n:2], g[1:2 * n:2]
    me, op = (blue, red) if tc == "Blue" else (red, blue)
    ata_t, ata_o, rng = me[:, 0], op[:, 0], me[:, 1]
    inr = (rng >= 500) & (rng <= 3000)
    out = dict(r)
    out.update(n_ticks=n, off=float(np.mean((ata_t <= 30) & (ata_o >= 90))), dfn=float(np.mean((ata_o <= 30) & (ata_t >= 90))),
               a0_2=float(np.mean(inr & (ata_t < 2))), a2_5=float(np.mean(inr & (ata_t >= 2) & (ata_t < 5))),
               a5_10=float(np.mean(inr & (ata_t >= 5) & (ata_t < 10))), a10_30=float(np.mean(inr & (ata_t >= 10) & (ata_t < 30))),
               o0_10=float(np.mean(inr & (ata_o < 10))), o10_30=float(np.mean(inr & (ata_o >= 10) & (ata_o < 30))),
               dmg_dealt=float(me[:, 2].sum()), dmg_recv=float(op[:, 2].sum()), mean_ata_t=float(ata_t.mean()), mean_ata_o=float(ata_o.mean()),
               opp_modes=json.dumps(collections.Counter(REC["mode"][oc]), ensure_ascii=False))
    REC["on"] = False
    return out


A_FIELDS = run.FIELDS + ["n_ticks", "off", "dfn", "a0_2", "a2_5", "a5_10", "a10_30", "o0_10", "o10_30", "dmg_dealt", "dmg_recv",
                         "mean_ata_t", "mean_ata_o", "opp_modes"]


def jobs_b(salt="main", n=8):
    return [j for j in run.build_jobs(dict(agents=AGENTS_MAIN, scenarios=LEAGUE, salt=salt, conds=B_CONDS, target="each"), n)
            if j["target"] in TARGETS]


def jobs_a():
    asym = [j for j in run.build_jobs(EXPERIMENTS["ASYM"], 2) if j["target"] == "GunTracker" and j["cond"] in ("F25_D2", "F25_D6")]
    base = [dict(j, cond="BASE", target="") for j in asym if j["cond"] == "F25_D2"]
    return base + asym


def run_jobs(js, out, fields, fn, name):
    rows = read(out)
    keep = [r for r in rows if r["condition"] != "wall_clock"]
    if len(keep) != len(rows):
        log(f"{name}: wall_clock {len(rows) - len(keep)}판을 지우고 다시 돈다")
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(keep)
    done = {tuple(r[k] for k in KEY) for r in keep}
    todo = [j for j in js if tuple(j[k] for k in KEY) not in done]
    log(f"{name}: 전체 {len(js)}판, 기록됨 {len(js) - len(todo)}, 남음 {len(todo)}")
    if not todo:
        return
    os.makedirs(os.path.dirname(out), exist_ok=True)
    new = not os.path.isfile(out)
    t0 = time.time()
    with mp.Pool(14) as pool, open(out, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        for i, row in enumerate(pool.imap_unordered(fn, todo, chunksize=1), 1):
            w.writerow(row); f.flush()
            if i % 200 == 0 or i == len(todo):
                el = time.time() - t0
                log(f"  {name} {i}/{len(todo)}  {el:.0f}s 경과, 남은 예상 {el / i * (len(todo) - i):.0f}s")
    if any(r["condition"] == "wall_clock" for r in read(out)):
        run_jobs(js, out, fields, fn, name)


def report():
    from analyze import points
    from scipy import stats
    AG = list(EXPERIMENTS["E2"]["agents"])
    lv = 100 * (1 - 0.05 / 3)
    L = ["# P9-b·P9-a: 원래 구성에서 U자의 원인 (사전 등록 `PREREG_P9.md`)\n"]
    res = {}
    # ---- P9-b
    rows = read(OUT_B)
    main = read(os.path.join(KIT, "out", "main", "games.csv"))
    base = {(r["blue"], r["red"], r["scenario"], r["salt"]): r for r in main if r["cond"] == "BASE" and r["target"] == ""}
    kb = lambda r: (r["blue"], r["red"], r["scenario"], r["salt"])
    seeds = sorted({r["salt"] for r in rows}, key=lambda x: int(x.rsplit("-", 1)[1]))
    rng = np.random.default_rng(0)
    BS = [list(rng.choice(seeds, len(seeds))) for _ in range(2000)]
    tq = stats.t.ppf(1 - (1 - lv / 100) / 2, len(seeds) - 1)
    L += ["## P9-b 흔들림만 넣기\n", f"경기 {len(rows):,} (사전 등록 1,344), `wall_clock` {sum(r['condition'] == 'wall_clock' for r in rows)}. "
          f"주입 {OSC_HZ} Hz, 짝: 원래 BASE. δ_점수 {DELTA_PTS}, {lv:.2f} % 구간\n",
          "| 대상 | 조건 | 대상 mae | Δ점수 | 퍼센타일 | 시드 t | 판정 |", "|---|---|---|---|---|---|---|"]

    def judge(lo, hi):
        if -DELTA_PTS <= lo and hi <= DELTA_PTS:
            return "차이 없음"
        if lo > DELTA_PTS:
            return "이득"
        if hi < -DELTA_PTS:
            return "손해"
        return "판정 불가"
    res["b"] = {}
    for t in TARGETS:
        for c in B_CONDS:
            cell = {}
            for s in seeds:
                gs = [r for r in rows if r["cond"] == c and r["target"] == t and r["salt"] == s]
                cell[s] = points(gs, AG)[0][t] - points([base[kb(g)] for g in gs], AG)[0][t]
            m = float(np.mean(list(cell.values())))
            cb = tuple(float(x) for x in np.percentile([np.mean([cell[s] for s in bb]) for bb in BS], [(100 - lv) / 2, 100 - (100 - lv) / 2]))
            sd = np.std(list(cell.values()), ddof=1) / np.sqrt(len(seeds))
            ct = (m - tq * sd, m + tq * sd)
            v = judge(*cb) if judge(*cb) == judge(*ct) else "판정 불가 (구간 방식에 따라 다름)"
            own = float(np.mean([float(g["blue_mae_q_dps"] if g["blue"] == t else g["red_mae_q_dps"]) for g in rows if g["cond"] == c and g["target"] == t]))
            res["b"][(t, c)] = dict(dpts=m, ci_boot=cb, ci_t=ct, verdict=v, mae=own)
            L.append(f"| {t} | {c} | {own:.2f} | {m:+.1f} | [{cb[0]:+.1f}, {cb[1]:+.1f}] | [{ct[0]:+.1f}, {ct[1]:+.1f}] | {v} |")
    L.append("\n사전 등록 주 판정은 OSC20 (두 대상 각각).\n")
    # ---- P9-a
    ra = read(OUT_A)
    rec = {}
    for d in ("main", "asym"):
        for r in read(os.path.join(KIT, "out", d, "games.csv")):
            rec[tuple(r[k] for k in KEY)] = r
    ok = sum(1 for r in ra if (lambda g: g is not None and (g["winner"], g["condition"]) == (r["winner"], r["condition"])
                               and all(abs(float(g[k]) - float(r[k])) < 1e-4 for k in ("hp_blue", "hp_red", "blue_mae_q_dps", "red_mae_q_dps")))(rec.get(tuple(r[k] for k in KEY))))
    L += ["## P9-a 기록 재생 (GunTracker, main-0·1)\n", f"경기 {len(ra)} (사전 등록 252), **재생 일치 {ok}/{len(ra)}**\n"]
    opp = lambda r: r["red"] if r["blue"] == "GunTracker" else r["blue"]
    grp = lambda o: "회피 규칙형" if o in DEF_RULE else "추격형"
    keys = ("off", "dfn", "a0_2", "a2_5", "a5_10", "a10_30", "o0_10", "o10_30", "dmg_dealt", "dmg_recv", "mean_ata_t", "mean_ata_o")
    L += ["| 조건 | 상대 묶음 | 공세 비율 | 수세 비율 | 대상 조준 0–2° / 2–5° / 5–10° / 10–30° | 상대 조준 0–10° / 10–30° | 준/받은 피해 | 평균 조준각 대상/상대 |",
          "|---|---|---|---|---|---|---|---|"]
    res["a"] = {}
    for c in ("BASE", "F25_D2", "F25_D6"):
        for gname in ("추격형", "회피 규칙형", "전체"):
            gs = [r for r in ra if r["cond"] == c and (gname == "전체" or grp(opp(r)) == gname)]
            if not gs:
                continue
            m = {k: float(np.mean([float(r[k]) for r in gs])) for k in keys}
            res["a"][(c, gname)] = m
            L.append(f"| {c} | {gname} | {m['off']:.3f} | {m['dfn']:.3f} | {m['a0_2']:.4f} / {m['a2_5']:.4f} / {m['a5_10']:.4f} / {m['a10_30']:.4f} | "
                     f"{m['o0_10']:.4f} / {m['o10_30']:.4f} | {m['dmg_dealt']:.0f} / {m['dmg_recv']:.0f} | {m['mean_ata_t']:.0f} / {m['mean_ata_o']:.0f} |")
    L += ["", "상대의 전술 행동 비율 (상대 묶음별, BT 틱 기준)\n", "| 조건 | 상대 묶음 | 행동 비율 (상위) |", "|---|---|---|"]
    for c in ("BASE", "F25_D2", "F25_D6"):
        for gname in ("추격형", "회피 규칙형"):
            cnt = collections.Counter()
            for r in ra:
                if r["cond"] == c and grp(opp(r)) == gname:
                    cnt.update(json.loads(r["opp_modes"]))
            tot = sum(cnt.values()) or 1
            L.append(f"| {c} | {gname} | " + ", ".join(f"{k} {v / tot:.2f}" for k, v in cnt.most_common(5)) + " |")
    txt = "\n".join(L) + "\n"
    open(REPORT, "w", encoding="utf-8").write(txt)
    json.dump({"b": {f"{k[0]}|{k[1]}": v for k, v in res["b"].items()}, "a": {f"{k[0]}|{k[1]}": v for k, v in res["a"].items()}, "replay_ok": ok},
              open(os.path.join(HERE, "p9ab_results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(txt)


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        jb = [j for j in jobs_b("p9smoke", 1) if j["scenario"] == "neutral" and j["target"] == "GunTracker" and "RedPrime" in (j["blue"], j["red"])][:2]
        ja = [j for j in jobs_a() if j["salt"] == "main-0" and j["scenario"] == "neutral" and "RedPrime" in (j["blue"], j["red"])][:3]
        with mp.Pool(5) as pool:
            rb = pool.map(play_b, jb)
            rA = pool.map(play_a, ja)
        for r in rb:
            print("B", r["cond"], r["blue"], r["red"], r["winner"], r["condition"], r["blue_mae_q_dps"], r["red_mae_q_dps"])
        rec = {}
        for d in ("main", "asym"):
            for r in read(os.path.join(KIT, "out", d, "games.csv")):
                rec[tuple(r[k] for k in KEY)] = r
        for r in rA:
            g = rec[tuple(r[k] for k in KEY)]
            print("A", r["cond"], r["blue"], r["red"], r["winner"] == g["winner"], r["condition"] == g["condition"], r["blue_mae_q_dps"], g["blue_mae_q_dps"],
                  "off", round(r["off"], 3), "a2_5", round(r["a2_5"], 4), r["opp_modes"][:80])
        print("jobs", len(jobs_b()), len(jobs_a()))
    elif "--report" in sys.argv:
        report()
    else:
        if os.name == "nt":
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        run_jobs(jobs_b(), OUT_B, run.FIELDS, play_b, "P9-b")
        log("P9-b 경기 완료")
        run_jobs(jobs_a(), OUT_A, A_FIELDS, play_a, "P9-a")
        log("P9-a 재생 완료")
        report()
        log("P9 완료")
