"""실전 궤적 수집 — 개정 A5, A8.

현행 운영 평가 배터리 규칙(tournament.run_gauntlet 미러): 참가자 11종(blue) × 레드팀 5종 × 시나리오 4종
× 솔트 2개 = 440경기, 시드 = derive_seed(솔트, 시나리오, red 이름). 경기 구성은 bridge.CompetitionMatch 와 같다.
양 기체의 L3 매 틱을 기록한다. 기록은 게이트 G2/G3 와 같은 인스턴스 래핑(통과값만 기록)이다.

사용:
  python research/l3_indi/traces.py --selfcheck       기록이 경기 결과를 바꾸지 않는지 4경기 확인
  python research/l3_indi/traces.py --pilot 2          2경기 시간·용량만 측정 (내용 분석 없음)
  python research/l3_indi/traces.py                    440경기 전체
출력: results/paper/traces/<commit10>/{runs.csv, manifest.json, jobs.json, npz/<match_id>.npz}
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from l3_indi.harness import REPO, DT                                   # noqa: E402  (sys.path·env 설정 포함)

PARTICIPANTS = ("examples/starter.yaml", "examples/energy_fighter.yaml", "examples/textbook_headon.yaml",
                "examples/doctrine_regulator.yaml", "agents/maverick_prime.yaml", "agents/maverick_JesterF.yaml",
                "agents/maverick_JesterL.yaml", "agents/Iceman_v1.yaml", "agents/Iceman_v2.yaml",
                "agents/Iceman_v3.yaml", "agents/meta_hybrid_v1.yaml")               # 개정 A8
SCENARIOS = ("headon", "perch_offense", "perch_defense", "neutral")   # tournament.BATTERY_SCENARIOS
SALTS = ("battery-v1", "battery-v1b")                                   # tournament.run_gauntlet 기본값
DURATION_S = 300.0

COLS = ("dphi_cmd", "q_cmd", "thrust_cmd", "g_target",
        "sp_p", "sp_q", "sp_r", "p_lim", "q_lim", "r_lim",
        "p", "q", "r", "phi", "theta", "psi", "alpha", "beta", "nz", "vt", "kcas", "qbar", "alt",
        "u_ail", "u_ele", "u_rud", "pos_ail", "pos_ele", "pos_rud_deg", "mode_code")


def battery_reds():
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    from run_tournament import BATTERY_REDS
    return tuple(BATTERY_REDS)


def all_jobs():
    from aircombat.engine.tournament import BATTERY_SCENARIOS
    from aircombat.bridge import derive_seed
    assert tuple(BATTERY_SCENARIOS) == SCENARIOS, BATTERY_SCENARIOS
    jobs = []
    for part in PARTICIPANTS:
        pname = os.path.splitext(os.path.basename(part))[0]
        for red in battery_reds():
            for sc in SCENARIOS:
                for salt in SALTS:
                    jobs.append({"match_id": f"{pname}__{red}__{sc}__{salt}", "participant": part,
                                 "red": red, "red_path": f"redteams/{red}.yaml", "scenario": sc,
                                 "salt": salt, "seed": derive_seed(salt, sc, red)})
    return jobs


def _instrument(pilot, buf, modes):
    """control_step 직전 L2 명령, 리미터 통과 지령, 스텝 후 참 상태를 buf 에 쌓는다."""
    lim = pilot.limiter
    orig_lim, orig_cs, orig_sp = lim.limit_omega_sp, pilot.control_step, pilot.step_physics
    cur = {}

    def limit(omega_sp, v_fps, kcas, g_lift=0.0):
        out, fl = orig_lim(omega_sp, v_fps, kcas, g_lift=g_lift)
        cur["sp"] = (out[0], out[1], out[2], fl["p_limited"], fl["q_limited"], fl["r_limited"])
        return out, fl

    def control_step(foe):
        g = pilot._gc
        cur["gc"] = (g.dphi_cmd, g.q_cmd, g.thrust_cmd, g.g_target)
        m = pilot._cmd.mode or pilot._cmd.pursuit or "-"
        cur["mode"] = modes.setdefault(f"{pilot._cmd.name}|{m}", len(modes))
        orig_cs(foe)

    def step_physics():
        orig_sp()
        P, u = pilot.plant, pilot.indi.u_prev
        buf.append((*cur["gc"], *cur["sp"],
                    P["velocities/p-rad_sec"], P["velocities/q-rad_sec"], P["velocities/r-rad_sec"],
                    P["attitude/phi-rad"], P["attitude/theta-rad"], P["attitude/psi-rad"],
                    P["aero/alpha-rad"], P["aero/beta-rad"], P["accelerations/Nz"],
                    P["velocities/vt-fps"], P["velocities/vc-kts"], P["aero/qbar-psf"],
                    P["position/h-sl-ft"], u[0], u[1], u[2],
                    P["fcs/left-aileron-pos-norm"], P["fcs/elevator-pos-norm"], P["fcs/rudder-pos-deg"],
                    cur["mode"]))

    lim.limit_omega_sp = limit
    pilot.control_step = control_step
    pilot.step_physics = step_physics


def play(job: dict, record: bool = True, out_dir: str | None = None) -> dict:
    """bridge.CompetitionMatch.run 과 같은 구성(load_policy → initial_conditions → make_pilot → Match)."""
    from aircombat.engine.factory import load_policy, make_pilot
    from aircombat.engine.match import Match
    from aircombat.engine.scenarios import initial_conditions
    cwd = os.getcwd()
    os.chdir(REPO)
    t0 = time.perf_counter()
    try:
        yamls = {"blue": job["participant"], "red": job["red_path"]}
        with contextlib.redirect_stdout(io.StringIO()):
            sides = [load_policy(yamls["blue"]), load_policy(yamls["red"])]
            ic = initial_conditions(job["scenario"], seed=job["seed"])
            pilots = {"blue": make_pilot("Blue", ic["blue"], *sides[0],
                                         name=os.path.splitext(os.path.basename(yamls["blue"]))[0]),
                      "red": make_pilot("Red", ic["red"], *sides[1], name=job["red"])}
        bufs = {"blue": [], "red": []}
        modes = {}
        if record:
            for side in ("blue", "red"):
                _instrument(pilots[side], bufs[side], modes)
        with contextlib.redirect_stdout(io.StringIO()):
            res = Match(pilots["blue"], pilots["red"], duration_s=DURATION_S, log_hz=0,
                        wall_limit_s=3600, overtime_s=0.0).run()
    finally:
        os.chdir(cwd)
    row = {"match_id": job["match_id"], "participant": job["participant"], "red": job["red"],
           "scenario": job["scenario"], "salt": job["salt"], "seed": job["seed"],
           "winner": res.winner, "condition": res.condition, "time_s": round(res.time_s, 4),
           "hp_blue": round(res.hp_blue, 4), "hp_red": round(res.hp_red, 4),
           "wall_s": round(time.perf_counter() - t0, 2)}
    if record and out_dir:
        os.makedirs(os.path.join(out_dir, "npz"), exist_ok=True)
        arrays = {}
        for side in ("blue", "red"):
            a = np.asarray(bufs[side], dtype=np.float64)
            for i, c in enumerate(COLS):
                arrays[f"{side}__{c}"] = a[:, i].astype(np.int16 if c == "mode_code" else np.float32)
        path = os.path.join(out_dir, "npz", job["match_id"] + ".npz")
        np.savez_compressed(path, **arrays,
                            meta=np.array(json.dumps({**row, "modes": modes, "dt": DT, "yamls": yamls})))
        row["n_ticks"] = len(bufs["blue"])
        row["npz_bytes"] = os.path.getsize(path)
    return row


def _job(job):
    return play(job, record=True, out_dir=job["_out_dir"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--pilot", type=int, default=0)
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    jobs = all_jobs()

    if args.selfcheck:
        # 운영 경로 CompetitionMatch.run() 결과 vs 기록 장치를 단 실행 — 시나리오별 1경기
        from aircombat.bridge import CompetitionMatch
        picks = [next(j for j in jobs if j["scenario"] == sc) for sc in SCENARIOS]
        ok = True
        for j in picks:
            cwd = os.getcwd()
            os.chdir(REPO)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    ref = CompetitionMatch(tree1_file=j["participant"], tree2_file=j["red_path"],
                                           tree1_name="p", tree2_name=j["red"],
                                           scenario=j["scenario"], seed=j["seed"]).run()
            finally:
                os.chdir(cwd)
            b = play(j, record=True, out_dir=None)
            ref_w = {"tree1": "blue", "tree2": "red", "draw": "draw"}[ref.winner]
            same = (ref_w == b["winner"] and ref.condition == b["condition"]
                    and abs(ref.tree1_health - b["hp_blue"]) < 1e-3 and abs(ref.tree2_health - b["hp_red"]) < 1e-3)
            ok &= same
            print(f"  {j['match_id']}: 운영경로 {ref_w}/{ref.condition}/HP {ref.tree1_health:.2f}-{ref.tree2_health:.2f}"
                  f"  | 기록실행 {b['winner']}/{b['condition']}/{b['time_s']}s/HP {b['hp_blue']}-{b['hp_red']}  동일={same}")
        print("selfcheck", "PASS" if ok else "FAIL")
        return 0 if ok else 1

    from l3_indi.runner import run_experiment, git_state
    name = "traces_pilot" if args.pilot else "traces"
    sel = jobs[:args.pilot] if args.pilot else jobs
    out_dir = os.path.join(REPO, "results", "paper", name, git_state()["commit"][:10])
    for j in sel:
        j["_out_dir"] = out_dir
    out = run_experiment(name, sel, _job, os.path.join(REPO, "results", "paper"),
                         allow_dirty=args.allow_dirty)
    import csv
    rows = list(csv.DictReader(open(os.path.join(out, "runs.csv"), encoding="utf-8")))
    wall = sum(float(r["wall_s"]) for r in rows)
    size = sum(int(r["npz_bytes"]) for r in rows)
    print(f"-> {out}: {len(rows)}경기, 경기당 벽시계 {wall/len(rows):.1f}s, npz 합계 {size/1e6:.1f} MB "
          f"(경기당 {size/len(rows)/1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
