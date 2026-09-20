"""RQ3 시작 기하 추출 — 개정 A24-4.

시나리오 균등 표본 120 경기를 **위치 기록을 추가해** 재실행하고, 당김 사건 시작 순간의 상대 기하를 모은다.
(P2 궤적에는 위치가 없어 거리·ATA·AA 를 계산할 수 없다.)

사용: python research/l3_indi/rq3_geom.py --selfcheck     4 경기 결과 일치 확인
      python research/l3_indi/rq3_geom.py                  120 경기 재실행 + 기하 추출
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO, DT            # noqa: E402

PER_SCENARIO = 30                                # A24-4: 시나리오당 30 = 120 경기
TRACES_RUNS = os.path.join(REPO, "results", "paper", "traces", "296ce41ff0", "runs.csv")
CAP_CSV = os.path.join(HERE, "reports", "capability_05b869f2e4.csv")
PLANE_TOL_DEG = 10.0                             # 적이 양력 평면 안이라고 보는 한계
COLS = ("p", "q", "phi", "theta", "psi", "alpha", "vt", "kcas", "alt",
        "px", "py", "pz", "vx", "vy", "vz")   # sp_p·sp_q 는 리미터 로그에서 따로 채운다


def selected_jobs() -> list[dict]:
    from l3_indi.traces import all_jobs
    jobs = all_jobs()
    out = []
    for sc in sorted({j["scenario"] for j in jobs}):
        js = sorted((j for j in jobs if j["scenario"] == sc), key=lambda j: j["match_id"])
        step = max(1, len(js) // PER_SCENARIO)
        out += js[::step][:PER_SCENARIO]
    return out


def _instrument(pilot, buf):
    orig_sp = pilot.step_physics

    def sp(_o=orig_sp, _p=pilot, _b=buf):
        _o()
        P = _p.plant
        _b.append((P["velocities/p-rad_sec"], P["velocities/q-rad_sec"], P["attitude/phi-rad"],
                   P["attitude/theta-rad"], P["attitude/psi-rad"], P["aero/alpha-rad"],
                   P["velocities/vt-fps"], P["velocities/vc-kts"], P["position/h-sl-ft"],
                   _p._pos[0], _p._pos[1], _p._pos[2],
                   P["velocities/v-north-fps"], P["velocities/v-east-fps"], P["velocities/v-down-fps"]))
    pilot.step_physics = sp


def _sp_log(pilot, log):
    lim = pilot.limiter
    orig = lim.limit_omega_sp

    def limit(omega_sp, v_fps, kcas, g_lift=0.0, _o=orig, _l=log):
        out, fl = _o(omega_sp, v_fps, kcas, g_lift=g_lift)
        _l.append((out[0], out[1]))
        return out, fl
    lim.limit_omega_sp = limit


def play(job: dict, out_dir: str | None):
    from aircombat.engine.factory import load_policy, make_pilot
    from aircombat.engine.match import Match
    from aircombat.engine.scenarios import initial_conditions
    cwd = os.getcwd()
    os.chdir(REPO)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            sides = [load_policy(job["participant"]), load_policy(job["red_path"])]
            ic = initial_conditions(job["scenario"], seed=job["seed"])
            pilots = {"blue": make_pilot("Blue", ic["blue"], *sides[0],
                                         name=os.path.splitext(os.path.basename(job["participant"]))[0]),
                      "red": make_pilot("Red", ic["red"], *sides[1], name=job["red"])}
        bufs = {s: [] for s in pilots}
        sps = {s: [] for s in pilots}
        for s, p in pilots.items():
            _sp_log(p, sps[s])
            _instrument(p, bufs[s])
        with contextlib.redirect_stdout(io.StringIO()):
            res = Match(pilots["blue"], pilots["red"], duration_s=300.0, log_hz=0,
                        wall_limit_s=3600, overtime_s=0.0).run()
    finally:
        os.chdir(cwd)
    row = {"match_id": job["match_id"], "scenario": job["scenario"], "winner": res.winner,
           "condition": res.condition, "time_s": round(res.time_s, 4),
           "hp_blue": round(res.hp_blue, 4), "hp_red": round(res.hp_red, 4)}
    if out_dir:
        os.makedirs(os.path.join(out_dir, "npz"), exist_ok=True)
        arr = {}
        for s in pilots:
            a = np.asarray(bufs[s], float)
            sp = np.asarray(sps[s], float)[:len(a)]
            for i, c in enumerate(COLS):
                arr[f"{s}__{c}"] = a[:, i].astype(np.float32)
            arr[f"{s}__sp_p"] = sp[:, 0].astype(np.float32)
            arr[f"{s}__sp_q"] = sp[:, 1].astype(np.float32)
        np.savez_compressed(os.path.join(out_dir, "npz", job["match_id"] + ".npz"),
                            meta=np.array(json.dumps(row)), **arr)
    return row


def job_fn(job):
    return play(job, job.get("_out"))


def selfcheck():
    ref = {r["match_id"]: r for r in csv.DictReader(open(TRACES_RUNS, encoding="utf-8"))}
    jobs = selected_jobs()
    picks = [next(j for j in jobs if j["scenario"] == sc) for sc in sorted({j["scenario"] for j in jobs})]
    ok = True
    for j in picks:
        r = play(j, None)
        o = ref[j["match_id"]]
        same = (r["winner"] == o["winner"] and r["condition"] == o["condition"]
                and abs(r["hp_blue"] - float(o["hp_blue"])) < 1e-6 and abs(r["hp_red"] - float(o["hp_red"])) < 1e-6
                and abs(r["time_s"] - float(o["time_s"])) < 1e-6)
        ok &= same
        print(f"  {j['match_id']}: 원래 {o['winner']}/{o['condition']}/{o['time_s']}s HP {o['hp_blue']}-{o['hp_red']} | "
              f"재실행 {r['winner']}/{r['condition']}/{r['time_s']}s HP {r['hp_blue']}-{r['hp_red']} | 동일={same}")
    print("selfcheck", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# --------------------------------------------------------------------------------------
def geometry_rows(npz_dir: str) -> list[dict]:
    """당김 사건 시작 틱의 상대 기하 (양 진영 각각 사수 기준)."""
    from aircombat.geometry.combat_geometry import CombatGeometry
    from aircombat.geometry.units import M_TO_FT
    from l3_indi import taxonomy as T
    FT_TO_M = 1.0 / M_TO_FT
    cap = T.Capability(CAP_CSV, fbw=0)
    rows = []
    for fp in sorted(os.listdir(npz_dir)):
        z = np.load(os.path.join(npz_dir, fp))
        meta = json.loads(str(z["meta"]))
        for me, foe in (("blue", "red"), ("red", "blue")):
            g = lambda s, c: z[f"{s}__{c}"].astype(float)
            lab, ev, _ = T.classify_side({k: z[k] for k in z.files if k.startswith(me + "__")}, me, cap)
            pos_me = np.stack([g(me, "px"), g(me, "py"), g(me, "pz")], 1)
            pos_fo = np.stack([g(foe, "px"), g(foe, "py"), g(foe, "pz")], 1)
            vel_me = np.stack([g(me, "vx"), g(me, "vy"), g(me, "vz")], 1)
            vel_fo = np.stack([g(foe, "vx"), g(foe, "vy"), g(foe, "vz")], 1)
            n = min(len(pos_me), len(pos_fo))
            for e in ev:
                if e["type"] not in ("g_capture", "rolling_pull"):
                    continue
                k = int(round(e["t0"] / DT))
                if k >= n:
                    continue
                geom = CombatGeometry(pos_me[k] * FT_TO_M, pos_fo[k] * FT_TO_M,
                                      vel_me[k] * FT_TO_M, vel_fo[k] * FT_TO_M,
                                      float(g(me, "phi")[k]), float(g(me, "theta")[k]), float(g(me, "psi")[k]),
                                      float(g(foe, "theta")[k]), float(g(foe, "psi")[k]))
                los = pos_fo[k] - pos_me[k]
                rng_ft = float(np.linalg.norm(los))
                if rng_ft < 1.0:
                    continue
                phi, th, ps = float(g(me, "phi")[k]), float(g(me, "theta")[k]), float(g(me, "psi")[k])
                cph, sph, cth, sth, cps, sps_ = np.cos(phi), np.sin(phi), np.cos(th), np.sin(th), np.cos(ps), np.sin(ps)
                y_b = np.array([sph * sth * cps - cph * sps_, sph * sth * sps_ + cph * cps, sph * cth])
                off = np.degrees(np.arcsin(abs(float(np.dot(los / rng_ft, y_b / np.linalg.norm(y_b))))))
                rows.append({"match_id": meta["match_id"], "scenario": meta["scenario"], "side": me,
                             "event": e["type"], "t0": e["t0"], "range_ft": rng_ft,
                             "ata_deg": geom.ata_deg(), "aa_deg": geom.aa_deg(), "hca_deg": geom.hca_deg(),
                             "bank_deg": float(np.degrees(phi)), "alt_ft": float(g(me, "alt")[k]),
                             "kcas": float(g(me, "kcas")[k]), "plane_off_deg": off})
    return rows


def summarize(out_dir: str) -> None:
    rows = geometry_rows(os.path.join(out_dir, "npz"))
    with open(os.path.join(out_dir, "geometry_events.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    inp = [r for r in rows if r["plane_off_deg"] <= PLANE_TOL_DEG]
    q = lambda xs, p: float(np.percentile(xs, p))
    R = [r["range_ft"] for r in inp]; A = [r["ata_deg"] for r in inp]
    L = [f"# RQ3 시작 기하 추출 — {os.path.basename(out_dir)}\n",
         f"- 재실행 {len({r['match_id'] for r in rows})} 경기, 당김 사건 {len(rows)} 건, 그중 양력 평면 안(≤ {PLANE_TOL_DEG:g}°) **{len(inp)} 건**",
         f"- 평면 이탈각 분포 p25/p50/p75: {q([r['plane_off_deg'] for r in rows],25):.1f} / "
         f"{q([r['plane_off_deg'] for r in rows],50):.1f} / {q([r['plane_off_deg'] for r in rows],75):.1f}°\n",
         "| 항목 | p25 | p50 | p75 |", "|---|---|---|---|"]
    for name, xs in (("거리 [ft]", R), ("ATA [deg]", A), ("AA [deg]", [r["aa_deg"] for r in inp]),
                     ("뱅크 [deg]", [abs(r["bank_deg"]) for r in inp]), ("고도 [ft]", [r["alt_ft"] for r in inp]),
                     ("KCAS", [r["kcas"] for r in inp])):
        L.append(f"| {name} | {q(xs,25):.0f} | {q(xs,50):.0f} | {q(xs,75):.0f} |")
    L.append("\n## 대표 기하 5종 (A24-4 규칙: (R, ATA) 분위수 조합, AA·뱅크는 해당 칸 중앙값)\n")
    L.append("| # | R₀ [ft] | ATA₀ [deg] | AA₀ [deg] | 뱅크 φ₀ [deg] | 사건 수 |")
    L.append("|---|---|---|---|---|---|")
    geoms = []
    for i, (pr, pa) in enumerate(((50, 50), (25, 75), (75, 25), (25, 25), (75, 75)), 1):
        r0, a0 = q(R, pr), q(A, pa)
        cell = [r for r in inp if abs(r["range_ft"] - r0) <= 0.25 * r0 and abs(r["ata_deg"] - a0) <= 15.0]
        if not cell:
            cell = inp
        aa0 = float(np.median([r["aa_deg"] for r in cell]))
        b0 = float(np.median([abs(r["bank_deg"]) for r in cell]))
        geoms.append({"id": f"G{i}", "range_ft": round(r0, 1), "ata_deg": round(a0, 2),
                      "aa_deg": round(aa0, 2), "bank_deg": round(b0, 2), "n_events": len(cell)})
        L.append(f"| G{i} (R p{pr}, ATA p{pa}) | {r0:.0f} | {a0:.1f} | {aa0:.1f} | {b0:.1f} | {len(cell)} |")
    with open(os.path.join(out_dir, "geometries.json"), "w", encoding="utf-8") as fh:
        json.dump(geoms, fh, ensure_ascii=False, indent=1)
    rep = os.path.join(HERE, "reports", f"RQ3GEOM_{os.path.basename(out_dir)}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", rep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--summarize", default=None)
    args = ap.parse_args()
    if args.selfcheck:
        return selfcheck()
    if args.summarize:
        summarize(args.summarize)
        return 0
    from l3_indi.runner import run_experiment, git_state
    out_dir = os.path.join(REPO, "results", "paper", "rq3_geom", git_state()["commit"][:10])
    jobs = selected_jobs()
    for j in jobs:
        j["_out"] = out_dir
    out = run_experiment("rq3_geom", jobs, job_fn, os.path.join(REPO, "results", "paper"))
    summarize(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
