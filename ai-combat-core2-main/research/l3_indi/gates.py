"""검증 게이트 G1~G6 — 본실행 전에 전부 통과해야 한다 (docs/EXPERIMENT_PLAN.md §3.7).

  G1 결정론              같은 설정을 새 프로세스 3개 + 같은 프로세스 2회 실행 → 시계열 비트 동일
  G2 배치 동일성          하네스 조립 Pilot 의 설정이 make_pilot 과 같고, 하네스 가공(INDI 재생성·
                          지령 기록·프록시)을 켜도 원시 배치 루프와 시계열이 비트 동일
  G3 L2 대체 정합         실제 Match 1경기에서 기록한 GuidanceCommand 를 하네스로 재생 → 원 경기와
                          L3 시계열 비트 동일
  G4 측정 단위시험        unwrap, Nz, J, 부호반전 데드밴드(탐색 데이터 225런 대조), 3구간, 주파수응답,
                          잡음·지연 프록시 통계, G0 변형, J_r 파라미터 독립성(사전등록 §3.2 주장 검증)
  G5 기존 결과 재현       탐색 단계 코너 당김을 하네스로 → 안정 경계 위치를 stability_filter_map 과 대조
  G6 출처                 커밋 안 된 변경이 있으면 runner 가 실행 거부

사용: python research/l3_indi/gates.py            (커밋된 상태에서)
결과: research/l3_indi/gate_reports/<commit10>.md, 모두 통과하면 종료코드 0
"""
from __future__ import annotations

import csv
import dataclasses
import io
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # research/
from l3_indi.harness import (build, run, state_view, Condition, Params, Uncertainty, PlantProxy,
                             transform_g0, TRUTH_COLS, DT, REPO, GuidanceCommand)   # noqa: E402
from l3_indi.maneuvers import (Hold, M1NzCapture, M2RollReversal, M3RollingPull, Replay,
                               LegacyCornerPull)    # noqa: E402
from l3_indi import metrics as M                   # noqa: E402
from l3_indi.runner import git_state, require_clean, DirtyTreeError   # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

STATE_COLS = ("p", "q", "r", "u_ail", "u_ele", "u_rud", "cmd_ail", "cmd_ele", "cmd_rud",
              "phi", "theta", "psi", "alpha", "beta", "nz", "vt", "kcas", "alt")
COND = Condition(15000.0, 400.0)
RESULTS = []


def record(gate, name, passed, evidence):
    RESULTS.append({"gate": gate, "check": name, "pass": bool(passed), "evidence": evidence})
    print(f"  [{'PASS' if passed else 'FAIL'}] {gate} {name}: {evidence}")


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


def bitwise(a: dict, b: dict, cols=STATE_COLS):
    """(동일 여부, 최대 절대차, 처음 다른 틱)"""
    n = min(len(a["t"]), len(b["t"]))
    worst, first = 0.0, None
    for c in cols:
        x, y = np.asarray(a[c][:n]), np.asarray(b[c][:n])
        d = np.abs(x - y)
        d = np.where(np.isnan(x) & np.isnan(y), 0.0, d)
        if np.any(d > 0):
            k = int(np.argmax(d > 0))
            first = k if first is None else min(first, k)
            worst = max(worst, float(np.nanmax(d)))
    return (worst == 0.0 and len(a["t"]) == len(b["t"])), worst, first


# ======================================================================================
# G1 결정론
# ======================================================================================
def _child_config(cfg: dict):
    unc = Uncertainty(gyro_sigma_dps=cfg["sigma"], input_delay_ms=cfg["delay"], seed=cfg["seed"])
    with quiet():
        rig = build(COND, Params(), unc)
        ts = run(rig, M3RollingPull(nz_target=4.0))
    return ts


def g1():
    print("\n== G1 결정론 ==")
    cfgs = {"noise0": {"sigma": 0.0, "delay": 0.0, "seed": 0},
            "noise_s7": {"sigma": 0.1, "delay": 25.0, "seed": 7},
            "noise_s8": {"sigma": 0.1, "delay": 25.0, "seed": 8}}
    tmp = tempfile.mkdtemp(prefix="g1_")
    arrays = {}
    for name, cfg in cfgs.items():
        runs = []
        reps = 3 if name != "noise_s8" else 1
        for i in range(reps):
            path = os.path.join(tmp, f"{name}_{i}.npz")
            subprocess.run([sys.executable, __file__, "--child", json.dumps(cfg), path],
                           check=True, capture_output=True)
            z = np.load(path)
            runs.append({c: z[c] for c in TRUTH_COLS})
        arrays[name] = runs
    for name in ("noise0", "noise_s7"):
        r = arrays[name]
        same = all(bitwise(r[0], r[i], TRUTH_COLS)[0] for i in (1, 2))
        record("G1", f"새 프로세스 3회 비트 동일 [{name}]", same,
               f"{len(r[0]['t'])}틱 x {len(TRUTH_COLS)}열")
    # 같은 프로세스 안에서 2회 (풀 워커 재사용 상황)
    a, b = _child_config(cfgs["noise0"]), _child_config(cfgs["noise0"])
    same, worst, _ = bitwise(a, b, TRUTH_COLS)
    ref_same = bitwise(a, arrays["noise0"][0], TRUTH_COLS)[0]
    record("G1", "같은 프로세스 2회 비트 동일 + 새 프로세스 결과와 동일", same and ref_same,
           f"최대차 {worst}")
    diff = not bitwise(arrays["noise_s7"][0], arrays["noise_s8"][0], TRUTH_COLS)[0]
    record("G1", "시드가 다르면 결과가 달라짐 (잡음이 실제로 들어감)", diff, "seed 7 vs 8")


# ======================================================================================
# G2 배치 동일성
# ======================================================================================
def _raw_deployed(cond, maneuver):
    """하네스 가공 없이 배치 코드만으로 돈다 (match.py 틱 순서)."""
    from aircombat.engine.factory import make_pilot
    from aircombat.guidance.doctrine import Doctrine
    with quiet():
        pilot = make_pilot("Blue", cond.ic(), None, Doctrine())
        pilot.setup()
    plant = pilot.plant
    n = int(round(maneuver.duration_s / DT))
    out = {c: np.zeros(n) for c in ("t",) + STATE_COLS}
    for k in range(n):
        if k % 2 == 0:
            pilot._gc = maneuver.command(k * DT, k, state_view(plant))
        pilot.control_step(None)
        pilot.step_physics()
        u = pilot.indi.u_prev
        vals = dict(t=k * DT, p=plant["velocities/p-rad_sec"], q=plant["velocities/q-rad_sec"],
                    r=plant["velocities/r-rad_sec"], u_ail=u[0], u_ele=u[1], u_rud=u[2],
                    cmd_ail=plant["fcs/aileron-cmd-norm"], cmd_ele=plant["fcs/elevator-cmd-norm"],
                    cmd_rud=plant["fcs/rudder-cmd-norm"], phi=plant["attitude/phi-rad"],
                    theta=plant["attitude/theta-rad"], psi=plant["attitude/psi-rad"],
                    alpha=plant["aero/alpha-rad"], beta=plant["aero/beta-rad"],
                    nz=plant["accelerations/Nz"], vt=plant["velocities/vt-fps"],
                    kcas=plant["velocities/vc-kts"], alt=plant["position/h-sl-ft"])
        for c, v in vals.items():
            out[c][k] = v
    return pilot, out


def g2():
    print("\n== G2 배치 동일성 ==")
    from aircombat.engine.factory import make_pilot
    from aircombat.guidance.doctrine import Doctrine
    with quiet():
        ref = make_pilot("Blue", COND.ic(), None, Doctrine())
        ref.setup()
        rig = build(COND)
    hp, ri = rig.pilot, ref.indi
    hi = hp.indi
    checks = {
        "shim k_att/k_yaw_damp/rate_limit": (hp.shim.k_att, hp.shim.k_yaw_damp, tuple(hp.shim.rate_limit))
                                           == (ref.shim.k_att, ref.shim.k_yaw_damp, tuple(ref.shim.rate_limit)),
        "limiter 설정": dataclasses.asdict(hp.limiter.cfg) == dataclasses.asdict(ref.limiter.cfg),
        "INDI k_rate": np.array_equal(hi.k_rate, ri.k_rate),
        "INDI G0 / qbar_ref": np.array_equal(hi.G0, ri.G0) and hi.qbar_ref == ri.qbar_ref,
        "INDI 필터 계수(f_acc/f_act/f_rate)": all(
            getattr(getattr(hi, f), c) == getattr(getattr(ri, f), c)
            for f in ("f_acc", "f_act", "f_rate") for c in ("b0", "b1", "b2", "a1", "a2")),
        "INDI 리셋 상태(u_prev, 필터 상태)": np.array_equal(hi.u_prev, ri.u_prev) and all(
            np.array_equal(getattr(getattr(hi, f), s), getattr(getattr(ri, f), s))
            for f in ("f_acc", "f_act", "f_rate") for s in ("x1", "x2", "y1", "y2")),
        "u_min/u_max/qbar_min": np.array_equal(hi.u_min, ri.u_min) and np.array_equal(hi.u_max, ri.u_max)
                                and hi.qbar_min == ri.qbar_min,
    }
    for name, ok in checks.items():
        record("G2", f"설정 일치: {name}", ok, "하네스 기본값 vs make_pilot+setup")

    for man in (M3RollingPull(nz_target=4.0), M2RollReversal()):
        _, raw = _raw_deployed(COND, man)
        with quiet():
            ts = run(build(COND), man)
        same, worst, first = bitwise(raw, ts)
        record("G2", f"원시 배치 루프 vs 하네스 전 경로 비트 동일 [{man.name}]", same,
               f"{len(raw['t'])}틱 x {len(STATE_COLS)}열, 최대차 {worst}, 첫 차이 틱 {first}")
    # 가공 스위치를 하나씩 켜도 동일
    man = M3RollingPull(nz_target=4.0)
    _, raw = _raw_deployed(COND, man)
    for flags in ({"rebuild_indi": True, "wrap_limiter": False, "use_proxy": False},
                  {"rebuild_indi": False, "wrap_limiter": True, "use_proxy": False},
                  {"rebuild_indi": False, "wrap_limiter": False, "use_proxy": True}):
        with quiet():
            ts = run(build(COND, **flags), man)
        same, worst, first = bitwise(raw, ts)
        on = [k for k, v in flags.items() if v][0]
        record("G2", f"가공 단독 적용 시 비트 동일 [{on}]", same, f"최대차 {worst}")


# ======================================================================================
# G3 L2 대체 정합 — 실제 Match
# ======================================================================================
def g3(duration_s=30.0):
    print("\n== G3 L2 대체 정합 (실제 Match 재생) ==")
    from aircombat.engine.factory import load_policy, make_pilot
    from aircombat.engine.match import Match
    from aircombat.engine.scenarios import initial_conditions
    blue_yaml, red_yaml = "examples/textbook_headon.yaml", "examples/starter.yaml"
    ic = initial_conditions("duel", seed=1)
    cwd = os.getcwd()
    os.chdir(REPO)
    try:
        with quiet():
            pb, db = load_policy(blue_yaml)
            pr, dr = load_policy(red_yaml)
            blue = make_pilot("Blue", ic["blue"], pb, db)
            red = make_pilot("Red", ic["red"], pr, dr)
        gcs, truth = [], {c: [] for c in ("t",) + STATE_COLS}
        orig_cs, orig_sp = blue.control_step, blue.step_physics

        def cs(foe):
            g = blue._gc
            gcs.append(GuidanceCommand(dphi_cmd=g.dphi_cmd, q_cmd=g.q_cmd,
                                       thrust_cmd=g.thrust_cmd, g_target=g.g_target))
            orig_cs(foe)

        def sp():
            orig_sp()
            P, u = blue.plant, blue.indi.u_prev
            vals = dict(t=(len(truth["t"])) * DT, p=P["velocities/p-rad_sec"], q=P["velocities/q-rad_sec"],
                        r=P["velocities/r-rad_sec"], u_ail=u[0], u_ele=u[1], u_rud=u[2],
                        cmd_ail=P["fcs/aileron-cmd-norm"], cmd_ele=P["fcs/elevator-cmd-norm"],
                        cmd_rud=P["fcs/rudder-cmd-norm"], phi=P["attitude/phi-rad"],
                        theta=P["attitude/theta-rad"], psi=P["attitude/psi-rad"],
                        alpha=P["aero/alpha-rad"], beta=P["aero/beta-rad"], nz=P["accelerations/Nz"],
                        vt=P["velocities/vt-fps"], kcas=P["velocities/vc-kts"], alt=P["position/h-sl-ft"])
            for c, v in vals.items():
                truth[c].append(v)

        blue.control_step, blue.step_physics = cs, sp
        t0 = time.perf_counter()
        with quiet():
            res = Match(blue, red, duration_s=duration_s, log_hz=0, wall_limit_s=600).run()
        match_wall = time.perf_counter() - t0
        truth = {c: np.asarray(v) for c, v in truth.items()}
        nz = truth["nz"]
        span = (f"경기 {len(gcs)}틱({len(gcs)*DT:.1f}s), 결과 {getattr(res,'winner','?')}/{getattr(res,'condition','?')}, "
                f"Nz {nz.min():.2f}~{nz.max():.2f}, 뱅크 |φ|max {np.rad2deg(np.abs(truth['phi'])).max():.0f}°, "
                f"KCAS {truth['kcas'].min():.0f}~{truth['kcas'].max():.0f}")

        s = ic["blue"]
        with quiet():
            rig = build(Condition(alt_ft=s["alt"], kcas=s["kcas"], psi_deg=s["psi"]), policy_yaml=blue_yaml)
            ts = run(rig, Replay(commands=gcs))
    finally:
        os.chdir(cwd)
    same, worst, first = bitwise(truth, ts)
    record("G3", "Match 기록 GuidanceCommand 재생 → 하네스 L3 시계열 비트 동일", same,
           f"{span}; {len(STATE_COLS)}열 최대차 {worst}, 첫 차이 틱 {first} (match {match_wall:.1f}s)")
    rs = np.array([g.dphi_cmd for g in gcs])
    record("G3", "재생 입력이 실제 기동을 포함 (자명한 대조가 아님)",
           np.rad2deg(np.abs(rs)).max() > 10 and nz.max() > 3.0,
           f"|dphi_cmd| max {np.rad2deg(np.abs(rs)).max():.0f}°, Nz max {nz.max():.2f}")


# ======================================================================================
# G4 측정 단위시험
# ======================================================================================
def g4():
    print("\n== G4 측정 단위시험 ==")
    # 4.1 heading unwrap
    psi = np.mod(np.deg2rad(np.linspace(-20, 40, 601)), 2 * np.pi)
    h = M.heading_unwrapped_deg(psi)
    record("G4", "heading unwrap (2π 경계 통과)", abs((h[-1] - h[0]) - 60.0) < 1e-9,
           f"감긴 입력 차분 {np.rad2deg(psi[-1]-psi[0]):.1f}° → unwrap {h[-1]-h[0]:.6f}° (정답 60°)")

    # 4.2 Nz 원천: 트림에서 1G, 하네스 nz 열 = accelerations/Nz
    with quiet():
        rig = build(COND)
        ts = run(rig, Hold(duration_s=1.0))
    nz_ok = abs(float(np.mean(ts["nz"])) - 1.0) < 0.05 and ts["nz"][-1] == rig.plant["accelerations/Nz"]
    record("G4", "Nz = accelerations/Nz, 트림 1G", nz_ok, f"트림 1초 평균 Nz {np.mean(ts['nz']):.4f}")

    # 4.3 J
    t = np.arange(0, 5, DT)
    base = {"t": t, "sp_q": np.deg2rad(10 * np.sin(2 * np.pi * t)), "q": np.deg2rad(9 * np.sin(2 * np.pi * t))}
    j1 = M.tracking_J(base, "q", (0, 5))
    small = {"t": t, "sp_q": np.deg2rad(0.5 * np.sin(t)), "q": np.zeros_like(t)}
    j2 = M.tracking_J(small, "q", (0, 5))
    # 창 5 s 는 sin(t) 의 정수 주기가 아니므로 기대값은 해석식이 아니라 같은 표본의 RMS 로 계산한다.
    j2_expect = float(np.sqrt(np.mean((0.5 * np.sin(t)) ** 2))) / M.J_FLOOR_DPS
    record("G4", "J 정규화·분모 하한", abs(j1 - 0.1) < 1e-3 and abs(j2 - j2_expect) < 1e-9,
           f"sp=10sin, ω=9sin → J={j1:.4f}(정답 0.1); |sp| RMS {j2_expect*2:.4f}dps < 하한 2dps → "
           f"J={j2:.4f}(정답 {j2_expect:.4f})")

    # 4.4 부호반전 데드밴드: 합성 + 탐색 데이터 225런 무잡음 동치
    rng = np.random.default_rng(0)
    rates = {}
    for sd in (0.004, 0.008, 0.012, 0.02):
        ch = 0.3 + np.random.default_rng(0).normal(0, sd, 1200)
        rates[sd] = (M.sign_change_hz(ch, 0.3, DT), M.sign_change_hz(ch, 0.3, DT, deadband=0.0))
    # 판정 기준: σ=0.008 채터에서 데드밴드가 거짓 양성을 판정 임계(1 Hz) 아래로 낮춘다.
    # 완전 제거는 보장하지 않는다 — 명령 채터가 커지면 한계가 있음을 수치로 남긴다.
    record("G4", "데드밴드가 트림 주변 채터의 거짓 양성을 1 Hz 아래로 낮춤 (σ=0.008)",
           rates[0.008][0] < M.OSC_SIGNCHG_HZ and rates[0.008][1] > M.OSC_SIGNCHG_HZ,
           "명령 채터 σ별 부호반전율 [데드밴드 0.02 / 없음]: " +
           ", ".join(f"σ={k}: {v[0]:.2f} / {v[1]:.1f} Hz" for k, v in rates.items()))
    agree, total, mism = 0, 0, []
    for sweep in ("corner_pull_sweep", "indi_step_sweep"):
        base_dir = os.path.join(REPO, "results", "exploratory", sweep)
        osc_ref = {r["run_id"]: int(r["oscillating"]) for r in
                   csv.DictReader(open(os.path.join(base_dir, "summary.csv"), encoding="utf-8-sig"))}
        cur, rows = None, []

        def flush(rid, rows):
            if not rows:
                return
            a = {k: np.array([float(r[k]) for r in rows]) for k in
                 ("t", "omega_p_dps", "omega_q_dps", "omega_r_dps", "n_act",
                  "cmd_aileron", "cmd_elevator", "cmd_rudder")}
            d = {"t": a["t"], "p": np.deg2rad(a["omega_p_dps"]), "q": np.deg2rad(a["omega_q_dps"]),
                 "r": np.deg2rad(a["omega_r_dps"]), "nz": a["n_act"],
                 "u_ail": a["cmd_aileron"], "u_ele": a["cmd_elevator"], "u_rud": a["cmd_rudder"]}
            return M.oscillation(d, DT)["oscillating"]

        with open(os.path.join(base_dir, "timeseries.csv"), newline="") as f:
            for r in csv.DictReader(f):
                if r["run_id"] != cur:
                    if cur is not None:
                        o = flush(cur, rows); total += 1
                        agree += int(o == osc_ref[cur]) or 0
                        if o != osc_ref[cur]:
                            mism.append((sweep, cur, osc_ref[cur], o))
                    cur, rows = r["run_id"], []
                rows.append(r)
            o = flush(cur, rows); total += 1
            agree += int(o == osc_ref[cur])
            if o != osc_ref[cur]:
                mism.append((sweep, cur, osc_ref[cur], o))
    record("G4", "무잡음에서 새 진동판정(트림 차감+데드밴드) = 탐색 단계 판정 (225런)",
           agree == total, f"{agree}/{total} 일치, 불일치 {mism[:5]}")

    # 4.5 3구간
    ref = {"a": 1.0, "b": 1.0}
    c1 = M.classify_band({"a": 1.4, "b": 0.9}, ref, ("a", "b"), 0, 0)[0]
    c2 = M.classify_band({"a": 1.6, "b": 0.9}, ref, ("a", "b"), 0, 0)[0]
    c3 = M.classify_band({"a": 1.0, "b": 1.0}, ref, ("a", "b"), 1, 0)[0]
    c4 = M.classify_band({"a": 1.0, "b": 1.0}, ref, ("a", "b"), 0, 1)[0]
    record("G4", "3구간 분류 규칙", (c1, c2, c3, c4) == ("stable", "degraded", "unstable", "unstable"),
           f"ρ1.4→{c1}, ρ1.6→{c2}, osc→{c3}, G초과→{c4}")

    # 4.6 주파수응답 추정기: 알려진 1차 이산 필터
    a_ = 0.9
    freqs = (0.2, 0.5, 1.0, 2.0, 4.0)
    tt = np.arange(0, 40, DT)
    x = sum(np.sin(2 * np.pi * f * tt + i) for i, f in enumerate(freqs))
    y = np.zeros_like(x)
    for k in range(1, len(x)):
        y[k] = a_ * y[k - 1] + (1 - a_) * x[k]
    est = M.freq_response({"t": tt, "sp_q": x, "q": y}, "q", freqs, (10, 40), DT)
    errs = []
    for f in freqs:
        H = (1 - a_) / (1 - a_ * np.exp(-1j * 2 * np.pi * f * DT))
        errs.append((abs(est[f][0] - 20 * np.log10(abs(H))), abs(est[f][1] - np.rad2deg(np.angle(H)))))
    worst_db, worst_deg = max(e[0] for e in errs), max(e[1] for e in errs)
    record("G4", "주파수응답 추정 (알려진 1차 필터)", worst_db < 0.5 and worst_deg < 5.0,
           f"최대 이득오차 {worst_db:.3f} dB, 최대 위상오차 {worst_deg:.2f}°")

    # 4.7 잡음·지연 프록시
    from aircombat.fdm.plant import F16Plant
    with quiet():
        pl = F16Plant(dt=DT)
        pl.set_ic(alt_ft=15000, vc_kts=400)
        pl["fcs/throttle-cmd-norm"] = 0.85
        pl.trim()
    sigma = 0.2
    px = PlantProxy(pl, DT, gyro_sigma_dps=sigma, seed=11)
    gn, an, fd = [], [], []
    prev = None
    for _ in range(6000):
        px.step(1)
        g = px["velocities/q-rad_sec"] - pl["velocities/q-rad_sec"]
        a = px["accelerations/qdot-rad_sec2"] - pl["accelerations/qdot-rad_sec2"]
        gn.append(g); an.append(a)
        if prev is not None:
            fd.append(abs(a - (g - prev) / DT))
        prev = g
    s_meas = np.rad2deg(np.std(gn))
    record("G4", "자이로 잡음 σ", abs(s_meas / sigma - 1) < 0.05, f"설정 {sigma} dps, 실측 {s_meas:.4f} dps (6000샘플)")
    record("G4", "각가속도 잡음 = 잡음 자이로의 1차 차분", max(fd) < 1e-9, f"최대 불일치 {max(fd):.2e} rad/s²")
    with quiet():
        pl2 = F16Plant(dt=DT)
        pl2.set_ic(alt_ft=15000, vc_kts=400)
        pl2["fcs/throttle-cmd-norm"] = 0.85
        pl2.trim()
    px2 = PlantProxy(pl2, DT, input_delay_ms=50.0)
    base_u = list(pl2.get_input())
    sent, ok = [], True
    for k in range(20):
        u = [base_u[0], base_u[1] + 0.001 * (k + 1), base_u[2], base_u[3]]
        sent.append(u[1])
        px2.set_input(u)
        applied = pl2["fcs/elevator-cmd-norm"]
        expect = sent[k - px2.delay_steps] if k >= px2.delay_steps else base_u[1]
        ok &= abs(applied - expect) < 1e-12
        px2.step(1)
    record("G4", "입력 지연 FIFO", ok and px2.delay_steps == 6, f"50 ms → {px2.delay_steps}틱, 20스텝 적용값 일치={ok}")

    # 4.8 G0 변형
    G = np.arange(1, 10, dtype=float).reshape(3, 3)
    T = transform_g0(G, Uncertainty(g0_row_scale=(2.0, 1.0, 0.5), g0_offdiag_scale=0.0))
    record("G4", "G0 변형 (행 배율 · 비대각 배율)", np.array_equal(T, np.diag([2.0, 5.0, 4.5])),
           f"diag → {np.diag(T).tolist()}, 비대각 0")

    # 4.9 J_r 파라미터 독립성 (사전등록 §3.2 의 주장)
    vals = []
    for ks in ((1, 1, 0.5), (1, 1, 1.0), (1, 1, 2.0), (1.5, 1.5, 1.5)):
        with quiet():
            ts = run(build(COND, Params(k_scale=ks)), M3RollingPull(nz_target=4.0))
        w = (1.0, 7.0)
        m = M.window_mask(ts, w)
        vals.append((ks, M.tracking_J(ts, "r", w), float(np.sqrt(np.mean(np.rad2deg(ts["sp_r"][m]) ** 2))),
                     M.tracking_J(ts, "q", w)))
    jr = [v[1] for v in vals]
    spread = (max(jr) - min(jr)) / np.mean(jr)
    record("G4", "J_r 는 파라미터와 무관 (M3, k 배율 4종)", spread < 0.05,
           "; ".join(f"k={v[0]} J_r={v[1]:.3f} RMS(r_sp)={v[2]:.2f}dps J_q={v[3]:.3f}" for v in vals)
           + f"; 상대 범위 {100*spread:.1f}% (이론 2.5/1.5=1.667)")


# ======================================================================================
# G5 기존 결과 재현
# ======================================================================================
def g5():
    print("\n== G5 탐색 단계 안정 경계 재현 ==")
    ks = (1.0, 1.4, 1.5, 1.6, 1.7, 1.8)
    fs = (10.0, 25.0, 50.0)
    frozen = {(float(r["filt_hz"]), float(r["k_scale"])): r for r in csv.DictReader(
        open(os.path.join(REPO, "results", "exploratory", "stability_filter_map.csv"), encoding="utf-8-sig"))}
    res = {}
    t0 = time.perf_counter()
    for f in fs:
        for k in ks:
            with quiet():
                rig = build(COND, Params(k_scale=(k, k, k), filt_hz=f))
                man = LegacyCornerPull(g_target=5.0, g_allowed_fn=rig.pilot.limiter.max_load_factor)
                ts = run(rig, man)
            nz, t = ts["nz"], ts["t"]
            band = max(0.3, 0.05 * 5.0)
            out = np.nonzero(np.abs(nz - 5.0) > band)[0]
            met = {"overshoot": max(0.0, float(nz.max()) - 5.0),
                   "settle": float(t[out[-1]] + DT) if len(out) else 0.0,
                   "J_q": M.tracking_J(ts, "q", (0.0, 12.0))}
            res[(f, k)] = (met, M.oscillation(ts, DT), M.envelope(ts))
    wall = time.perf_counter() - t0
    lines, ok_all = [], True
    for f in fs:
        ref = res[(f, 1.0)][0]
        bands = {}
        for k in ks:
            met, osc, env = res[(f, k)]
            bands[k] = M.classify_band(met, ref, ("overshoot", "settle", "J_q"),
                                       osc["oscillating"], env["g_exceeded"])[0]
        last_h = max([k for k in ks if bands[k] == "stable"], default=None)
        last_x = max([k for k in ks if frozen[(f, k)]["band"] == "stable"], default=None)
        ok = last_h is not None and last_x is not None and abs(last_h - last_x) <= 0.1 + 1e-9
        ok_all &= ok
        osc_h = "".join(str(res[(f, k)][1]["oscillating"]) for k in ks)
        osc_x = "".join(frozen[(f, k)]["oscillating"] for k in ks)
        mk = {"stable": "S", "degraded": "D", "unstable": "X"}
        lines.append(f"filt {f:g}: 하네스 {''.join(mk[bands[k]] for k in ks)} (마지막 안정 k={last_h}, osc {osc_h}) | "
                     f"탐색 {''.join(mk[frozen[(f, k)]['band']] for k in ks)} (마지막 안정 k={last_x}, osc {osc_x})")
    for ln in lines:
        print("     ", ln)
    record("G5", "마지막 안정 k_scale 이 탐색 결과와 ±1칸(0.1) 이내 (filt 10/25/50)", ok_all,
           " / ".join(lines) + f" — k 격자 {ks}, {len(res)}런 {wall:.0f}s. "
           "차이 요인: 트림 스로틀 0.85(배치) vs 1.0(탐색), Nz vs 기구학 G, 정착판정 G 원천")


# ======================================================================================
# G6 출처
# ======================================================================================
def g6():
    print("\n== G6 출처 강제 ==")
    st = git_state()
    record("G6", "현재 트리 깨끗함 (게이트 실행 커밋 고정)", st["clean"],
           f"commit {st['commit'][:10]}, dirty={st['dirty_files']}")
    probe = os.path.join(HERE, "_g6_probe.py")
    with open(probe, "w") as f:
        f.write("# G6 probe\n")
    try:
        try:
            require_clean()
            refused = False
        except DirtyTreeError:
            refused = True
    finally:
        os.remove(probe)
    record("G6", "추적 안 된 파일 추가 시 실행 거부", refused, "research/l3_indi/_g6_probe.py")
    target = os.path.join(HERE, "__init__.py")
    original = open(target, "rb").read()
    try:
        with open(target, "ab") as f:
            f.write(b"\n")
        try:
            require_clean()
            refused2 = False
        except DirtyTreeError:
            refused2 = True
    finally:
        with open(target, "wb") as f:
            f.write(original)
    record("G6", "추적 파일 수정 시 실행 거부", refused2, "research/l3_indi/__init__.py 한 줄 추가")
    record("G6", "원상복구 후 다시 깨끗함", git_state()["clean"], "")


# ======================================================================================
def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--child":
        cfg = json.loads(sys.argv[2])
        ts = _child_config(cfg)
        np.savez(sys.argv[3], **{c: ts[c] for c in TRUTH_COLS})
        return 0
    st = git_state()
    print(f"[gates] commit {st['commit'][:10]} clean={st['clean']}")
    t0 = time.perf_counter()
    for g in (g6, g1, g2, g3, g4, g5):
        try:
            g()
        except Exception as e:                                   # 게이트 자체 오류도 실패로 기록
            import traceback
            record(g.__name__.upper(), "게이트 실행 오류", False, repr(e))
            traceback.print_exc()
    wall = time.perf_counter() - t0
    passed = all(r["pass"] for r in RESULTS)
    os.makedirs(os.path.join(HERE, "gate_reports"), exist_ok=True)
    path = os.path.join(HERE, "gate_reports", f"{st['commit'][:10]}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 게이트 보고서 — commit {st['commit']}\n\n")
        f.write(f"- 실행: {time.strftime('%Y-%m-%d %H:%M:%S')}, 소요 {wall:.0f}s, 트리 깨끗함={st['clean']}\n")
        f.write(f"- 결과: **{'전체 통과' if passed else '실패 있음'}** "
                f"({sum(r['pass'] for r in RESULTS)}/{len(RESULTS)})\n\n")
        f.write("| 게이트 | 검사 | 결과 | 근거 |\n|---|---|---|---|\n")
        for r in RESULTS:
            ev = str(r["evidence"]).replace("|", "/")
            f.write(f"| {r['gate']} | {r['check']} | {'PASS' if r['pass'] else '**FAIL**'} | {ev} |\n")
    print(f"\n[gates] {sum(r['pass'] for r in RESULTS)}/{len(RESULTS)} pass, {wall:.0f}s -> {path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
