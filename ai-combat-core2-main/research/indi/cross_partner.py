"""두 계보 교차 실행 — 비동기 측정 지연(센서만 지연, 구동기 되먹임은 현재 값)의 결과가 왜 다르게 보이는지.

  mine     : 이 계보 배터리(energy_fighter, 5 레드 × 5 시나리오 × 시드 2) + 파트너 계단 지표(combat._step_q)
             blue = 기준 INDI / 절충형(γ=0.3), blue 만 지연 0·2·4 틱 (red 지연 없음)
  partner  : 파트너 배터리(research/l3-indi-paper-v2, A36 격자, tactics.yaml, 5 레드 × 4 시나리오 × 확증 솔트 4)
             BASE / V4_async_2t / V4_async_4t(신규) + 이 계보 G 실현률(요구 G ≥ 3 구간 Nz/목표 G 중앙값)

  python research/indi/cross_partner.py mine
  python research/indi/cross_partner.py partner D:/ai_pilot_core2-main/partner_v2/ai-combat-core2-main [설정,설정,...]
  python research/indi/cross_partner.py report
출력: results/indi/cross_mine.json, cross_partner.json (캐시 안 씀 — 새 지표를 다시 계산해야 하므로)
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "results", "indi")
sys.path.insert(0, HERE)
from workers import auto_workers
WORKERS = auto_workers()   # 8 GB 기계 → 2 (3 이면 메모리 부족으로 종료된 적 있음)


# ---------------------------------------------------------------- 이 계보 배터리
def _mine_job(job):
    sys.path.insert(0, HERE)
    import runner
    from aircombat.control.indi import INDIConfig, SensorConfig
    name, cfg, red, sc, sd, dt = job
    r = runner.play(runner.BLUE_TREE, os.path.join(runner.ROOT, "redteams", f"{red}.yaml"), sc, sd,
                    blue_cfg=INDIConfig(**cfg), sensor=SensorConfig("gyro", runner.NOMINAL_SIGMA_DPS, dt, sd),
                    cond={"red_delay_ticks": 0})
    return dict(cell=f"{name}_d{dt}", red=red, scenario=sc, seed=sd, winner=r["winner"],
                condition=r["condition"], **{k: r["combat_blue"].get(k) for k in
                ("reach63_q", "ss_ratio_q", "t63_q", "n_event_q", "corr_q", "lag_q_ms", "g_ratio")})


def run_mine():
    sys.path.insert(0, HERE)
    import runner
    from aircombat.control.indi import INDIConfig
    best = json.load(open(os.path.join(OUT, "e4.json"), encoding="utf-8"))["best"]
    cfgs = {"A": dataclasses.asdict(INDIConfig()),
            "g0.3": next(b["cfg"] for b in best if abs(b["gamma"] - 0.3) < 1e-9)}
    jobs = [(n, c, r, sc, sd, dt) for n, c in cfgs.items() for dt in (0, 2, 4)
            for r, sc, sd in runner.battery(seeds=(1, 2))]
    rows = runner.pmap(_mine_job, jobs, WORKERS)
    json.dump(rows, open(os.path.join(OUT, "cross_mine.json"), "w", encoding="utf-8"), indent=0)


# ---------------------------------------------------------------- 파트너 배터리
def _partner_setup(root):
    sys.path.insert(0, os.path.join(root, "research"))
    from l3_indi import dogfight as dg
    if getattr(dg, "_g_patched", False):
        return dg
    snap = dg.Recorder.snap

    def snap_g(self):                                  # 청군만: 이 계보 G 실현률용 (목표 G, Nz)
        snap(self)
        if self.blue:
            gc = getattr(self.p, "_gc", None)
            self.__dict__.setdefault("g", []).append((gc.g_target if gc else 0.0, self.P["accelerations/Nz"]))
    dg.Recorder.snap = snap_g
    rec = dg.recorded_metrics

    def rec_g(rb, rr, res):
        m = rec(rb, rr, res)
        gt, nz = np.array(rb.__dict__.get("g", [(0.0, 0.0)])).T
        pull = gt >= 3.0
        m["g_ratio"] = float(np.median(nz[pull] / gt[pull])) if pull.any() else None
        return m
    dg.recorded_metrics = rec_g
    dg._g_patched = True
    return dg


def _partner_job(args):
    root, job = args
    dg = _partner_setup(root)
    r = dg.play(job, instrument=True)
    return {k: r.get(k) for k in ("match_id", "setting_name", "red", "scenario", "salt", "winner", "condition", "blue_pts",
                                  "reach63_q", "ss_ratio_q", "t63_q", "n_event_q", "corr_q", "tau_eq_q",
                                  "g_ratio", "nz_max", "nz_min")}


def run_partner(root):
    dg = _partner_setup(root)
    g = json.load(open(os.path.join(root, "research", "l3_indi", "dogfight_grid_a36.json"), encoding="utf-8"))
    g["settings"].append({"name": "V4_async_4t", "family": "ofat", "variable": "V4_delay_async", "level": "4",
                          "set": {"delay_ticks": 4, "delay_sync": False}})   # 이 계보 주 조건 33 ms
    for nm, st in (("F5_BASE", {}), ("F5_async_2t", {"delay_ticks": 2, "delay_sync": False}),
                   ("F5_async_4t", {"delay_ticks": 4, "delay_sync": False})):     # 필터만 5 Hz (이 계보 filt5)
        g["settings"].append({"name": nm, "family": "ofat", "variable": "filt5", "level": nm,
                              "set": dict(st, filt_hz=5.0)})
    tmp = os.path.join(OUT, "_grid_cross.json")
    json.dump(g, open(tmp, "w", encoding="utf-8"))
    grid = dg.load_grid(tmp)
    names = sys.argv[3].split(",") if len(sys.argv) > 3 else ["BASE", "V4_async_2t", "V4_async_4t"]
    jobs = dg.build_jobs(grid, names, n_salts=4, salt_offset=8)
    out = os.path.join(OUT, "cross_partner.json")
    prev = json.load(open(out, encoding="utf-8")) if os.path.isfile(out) else []
    prev = [r for r in prev if r["setting_name"] not in names]
    # 경기마다 .jsonl 에 덧붙여 기록 — 중단돼도 재실행하면 끝난 경기는 건너뛴다
    part = out + "l"
    done = {json.loads(x)["match_id"] for x in open(part, encoding="utf-8")} if os.path.isfile(part) else set()
    from concurrent.futures import ProcessPoolExecutor, as_completed
    with ProcessPoolExecutor(WORKERS) as ex, open(part, "a", encoding="utf-8") as f:
        for fu in as_completed([ex.submit(_partner_job, (root, j)) for j in jobs if j["match_id"] not in done]):
            f.write(json.dumps(fu.result()) + chr(10))
            f.flush()
    rows = [r for r in map(json.loads, open(part, encoding="utf-8")) if r["setting_name"] in names]
    json.dump(prev + rows, open(out, "w", encoding="utf-8"), indent=0)
    os.remove(part)


# ---------------------------------------------------------------- 표
def report():
    def table(rows, key, title):
        print(f"\n## {title}\n\n| 칸 | n | 승률(승1·무0.5) | reach63_q | ss_ratio_q | t63_q [s] | corr_q | G 실현률 |\n"
              "|---|---|---|---|---|---|---|---|")
        for cell in dict.fromkeys(r[key] for r in rows):
            rs = [r for r in rows if r[key] == cell]
            med = lambda k: np.nanmedian([np.nan if r.get(k) is None else r[k] for r in rs])
            win = np.mean([1.0 if r["winner"] == "blue" else 0.5 if r["winner"] == "draw" else 0.0 for r in rs])
            print(f"| {cell} | {len(rs)} | {win:.3f} | {med('reach63_q'):.3f} | {med('ss_ratio_q'):.3f} | "
                  f"{med('t63_q'):.3f} | {med('corr_q'):.3f} | {med('g_ratio'):.3f} |")
    for fn, key, title in (("cross_mine.json", "cell", "이 계보 배터리 (blue 만 지연, 지표는 경기별 값의 중앙값)"),
                           ("cross_partner.json", "setting_name", "파트너 배터리 (A36, blue 만 지연)")):
        p = os.path.join(OUT, fn)
        if os.path.isfile(p):
            table(json.load(open(p, encoding="utf-8")), key, title)


if __name__ == "__main__":
    {"mine": lambda: run_mine(), "partner": lambda: run_partner(sys.argv[2]), "report": report}[sys.argv[1]]()
