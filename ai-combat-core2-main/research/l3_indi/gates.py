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
  G7 개정 A9 기동         M2a 능력 제한 0, M1 45° 정착, M2b = 기존 M2, A9 수준 R2 재판정
  G8 개정 A10-4 지연      동기화 N=0 비트 동일, 측정 지연·동기화 의미 대조, 지연이 실제로 들어감
  G9 개정 A10-2 F_i       수평 협조선회 F_i ≈ 1, 벡터식 = 스칼라식, 수평 비행 μ ≈ φ
  G10 개정 A10-3 Ĉ        G0 복원 비트 동일, float32 중심차분 Ĉ 오차 5% 이내
  G11 개정 A15 꼬리      꼬리 유무 간 창 W 비트 동일, 착오·리밋사이클 6런 판정 재현
  (G4 에 개정 A10 지표 단위시험 g4_a10 추가)

사용: python research/l3_indi/gates.py            (커밋된 상태에서)
      python research/l3_indi/gates.py --only g7,g9   (부분 점검, 보고서 없음)
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
                             transform_g0, TRUTH_COLS, DT, REPO, GuidanceCommand, G_FT_S2)   # noqa: E402
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
    quiet_body = {"t": np.arange(1200) * DT, "p": np.zeros(1200), "q": np.full(1200, 1e-4),
                  "r": np.zeros(1200), "nz": np.ones(1200),
                  "u_ail": np.zeros(1200), "u_rud": np.zeros(1200),
                  "u_ele": 0.3 + np.random.default_rng(1).normal(0, 0.05, 1200)}
    quiet_body["u_ele"][0] = 0.3
    oq = M.oscillation(quiet_body, DT)
    record("G4", "개정 A3: 기체가 흔들리지 않으면 큰 명령 채터(σ=0.05)도 진동 아님, v1 은 진동",
           oq["oscillating"] == 0 and oq["osc_v1"] == 1 and oq["osc_signchg_only"] == 1,
           f"부호반전 {oq['signchg_hz']:.1f} Hz, 각속도 p2p {oq['p2p_rate_dps']:.3f} dps → "
           f"A3={oq['oscillating']}, v1={oq['osc_v1']}, 부호반전만={oq['osc_signchg_only']}")
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
            o = M.oscillation(d, DT)
            return (o["oscillating"], o["osc_v1"])

        with open(os.path.join(base_dir, "timeseries.csv"), newline="") as f:
            for r in csv.DictReader(f):
                if r["run_id"] != cur:
                    if cur is not None:
                        o = flush(cur, rows); total += 1
                        ok = o[0] == osc_ref[cur] and o[1] == osc_ref[cur]
                        agree += int(ok)
                        if not ok:
                            mism.append((sweep, cur, osc_ref[cur], o))
                    cur, rows = r["run_id"], []
                rows.append(r)
            o = flush(cur, rows); total += 1
            ok = o[0] == osc_ref[cur] and o[1] == osc_ref[cur]
            agree += int(ok)
            if not ok:
                mism.append((sweep, cur, osc_ref[cur], o))
    record("G4", "무잡음에서 새 진동판정(개정 A3 규칙과 원문 v1 규칙 모두) = 탐색 단계 판정 (225런)",
           agree == total, f"{agree}/{total} 일치 (A3·v1 둘 다), 불일치 {mism[:5]}")

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


def g4_taxonomy():
    """개정 A7 분류기: 알려진 합성 기동을 넣고 범주·크기 확인."""
    from l3_indi import taxonomy as T
    n = int(20 / DT)
    phi, psp, spq = np.zeros(n), np.zeros(n), np.zeros(n)
    vt, theta = np.full(n, 700.0), np.zeros(n)

    def roll(a, b, rate):
        s, e = int(a / DT), int(b / DT)
        psp[s:e] = np.deg2rad(rate)
        phi[s:e] = phi[s - 1] + np.cumsum(np.full(e - s, np.deg2rad(rate) * DT))
        phi[e:] = phi[e - 1]

    roll(2, 3, 60)
    roll(5, 7, -60)
    s, e = int(10 / DT), int(14 / DT)
    spq[s:e] = (4.0 - np.cos(phi[s:e])) * G_FT_S2 / 700
    roll(16, 17.2, 58)
    s, e = int(16.2 / DT), int(19 / DT)
    spq[s:e] = (4.0 - np.cos(phi[s:e])) * G_FT_S2 / 700
    z = {f"blue__{k}": v for k, v in dict(sp_p=psp, phi=phi, theta=theta, sp_q=spq, vt=vt,
                                           alt=np.full(n, 15000.0), kcas=np.full(n, 400.0)).items()}

    class Cap:
        def c_nz(self, a, k):
            return 7.0, True

    lab, ev, _ = T.classify_side(z, "blue", Cap())
    expect = {2.5: "roll_other", 6.0: "roll_reversal", 12.0: "g_capture", 16.5: "rolling_pull",
              18.0: "rolling_pull", 1.0: "low_g"}
    got = {t: lab[int(t / DT)] for t in expect}
    rev = [e for e in ev if e["type"] == "roll_reversal"]
    rp = [e for e in ev if e["type"] == "rolling_pull"]
    gc = [e for e in ev if e["type"] == "g_capture"]
    ok = (got == expect and len(rev) == 1 and abs(rev[0]["dphi_abs_deg"] - 120) < 2 and len(rp) == 1
          and abs(rp[0]["dphi_abs_deg"] - 70) < 2 and len(gc) == 1 and abs(gc[0]["nz_frac"] - 4 / 7) < 0.02)
    record("G4", "기동 분류기(개정 A7): 합성 기동 4종 범주·크기", ok,
           f"라벨 {got}; 반전 Δφ {rev[0]['dphi_abs_deg']:.1f}°, 롤링풀 Δφ {rp[0]['dphi_abs_deg']:.1f}°, "
           f"G포착 C_nz비율 {gc[0]['nz_frac']:.3f}(정답 0.571)")


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
# G4 추가 단위시험 — 개정 A10 지표 (알려진 입력)
# ======================================================================================
def g4_a10():
    print("\n== G4 개정 A10 지표 단위시험 ==")
    from l3_indi import effectiveness as EFF
    rng = np.random.default_rng(3)
    n = 400
    G0 = np.array([[-20.0, 1.0, 3.0], [0.5, -7.0, 0.2], [-1.0, 0.3, -2.0]])
    u = np.cumsum(rng.normal(0, 0.01, (n, 3)), axis=0)
    du = np.vstack([np.zeros(3), np.diff(u, axis=0)])
    wd = np.cumsum(du @ G0.T, axis=0)
    ts = {"t": np.arange(n) * DT, "cmd_ail": u[:, 0], "cmd_ele": u[:, 1], "cmd_rud": u[:, 2],
          "pdot": wd[:, 0], "qdot": wd[:, 1], "rdot": wd[:, 2], "qbar": np.full(n, 400.0),
          "alpha": np.full(n, 0.1), "nz": np.full(n, 3.0)}
    e0 = M.tss_residual(ts, (0, n * DT), G0, 400.0)
    d = rng.normal(0, 0.05, (n, 3))
    wd2 = np.cumsum(du @ G0.T + d, axis=0)
    ts2 = dict(ts, pdot=wd2[:, 0], qdot=wd2[:, 1], rdot=wd2[:, 2])
    e1 = M.tss_residual(ts2, (0, n * DT), G0, 400.0)
    dd = np.diff(wd2, axis=0)
    expect = np.sum(np.abs(d[1:]), axis=0) / np.sum(np.abs(dd), axis=0)
    ok = (max(abs(v) for v in e0.values()) < 1e-9
          and np.allclose([e1["eps_p"], e1["eps_q"], e1["eps_r"]], expect, rtol=1e-9))
    record("G4", "개정 A10-1 ε: 증분 모델이 정확하면 0, 알려진 교란이면 해석값", ok,
           f"정확 {max(abs(v) for v in e0.values()):.1e}; 교란 ε=({e1['eps_p']:.4f},{e1['eps_q']:.4f},{e1['eps_r']:.4f}) "
           f"해석 ({expect[0]:.4f},{expect[1]:.4f},{expect[2]:.4f})")
    wd3 = np.cumsum(2.0 * (du @ G0.T), axis=0)
    e2 = M.tss_residual(dict(ts, qbar=np.full(n, 800.0), pdot=wd3[:, 0], qdot=wd3[:, 1], rdot=wd3[:, 2]),
                        (0, n * DT), G0, 400.0)
    record("G4", "개정 A10-1 ε: 동압 스케줄 G = (q̄/q̄_ref)·G0 반영", max(abs(v) for v in e2.values()) < 1e-9,
           f"q̄ 2배·효과 2배 → ε 최대 {max(abs(v) for v in e2.values()):.1e}")

    x = np.linspace(0, 1, 300)
    yh = 2.0 * np.maximum(0, x - 0.5) + rng.normal(0, 1e-3, 300)
    yl = 0.8 * x + rng.normal(0, 1e-3, 300)
    fh, fl = M.transfer_fit(x, yh), M.transfer_fit(x, yl)
    record("G4", "개정 A10-2 T→M 판정: 힌지 데이터 → 임계형(x₀≈0.5), 선형 데이터 → 선형",
           fh["verdict"] == "threshold" and abs(fh["x0"] - 0.5) < 0.03 and fl["verdict"] == "linear",
           f"힌지: {fh['verdict']} x₀={fh['x0']:.3f} ΔBIC={fh['delta_bic']:.0f}; 선형: {fl['verdict']} ΔBIC={fl['delta_bic']:.1f}")

    wdot = np.cumsum(0.5 * (du @ G0.T), axis=0)
    W = EFF.windows(wdot, u, np.full(n, 400.0), G0, 400.0)
    record("G4", "개정 A10-3 창별 최소제곱: 실효 효과가 식별값의 0.5배면 Ĉ = 0.5",
           len(W["C"]) > 0 and np.allclose(W["C"], 0.5, atol=1e-9),
           f"창 {len(W['C'])}개, Ĉ 범위 {np.nanmin(W['C']):.6f}~{np.nanmax(W['C']):.6f}")


# ======================================================================================
# G7 개정 A9 합성 기동
# ======================================================================================
def g7():
    print("\n== G7 개정 A9 합성 기동 ==")
    from l3_indi.design import rq1_conditions, capability
    from l3_indi.maneuvers import M1BankedCapture, M2aCappedReversal, paper_maneuvers
    a_ok, b_ok, la, lb = True, True, [], []
    for fbw in (0, 1):
        for cond in rq1_conditions(fbw):
            cap = capability(cond)
            m2a = M2aCappedReversal(cap_p_dps=cap["C_p"])
            with quiet():
                ts = run(build(cond), m2a)
            w = m2a.window()
            lim = M.capability_limited(ts, w, cap["C_p"])
            pmax = float(np.max(np.abs(np.rad2deg(ts["sp_p"][M.window_mask(ts, w)]))))
            ok = lim == 0 and pmax <= 1.01 * 0.8 * cap["C_p"]
            a_ok &= ok
            la.append(f"{'off' if fbw else 'on'} {cond.alt_ft/1000:g}k/{cond.kcas:g}: max|p_sp| {pmax:.1f}"
                      f"/0.8C_p {0.8*cap['C_p']:.1f}, 제한 {lim}")
            m1 = M1BankedCapture(nz_target=0.7 * cap["C_nz"])
            with quiet():
                ts1 = run(build(cond), m1)
            k3 = int(round(m1.pull_start_s / DT)) - 1
            dphi = abs(float(np.rad2deg(ts1["phi"][k3])) - 45.0)
            b_ok &= dphi <= 2.0
            lb.append(f"{'off' if fbw else 'on'} {cond.alt_ft/1000:g}k/{cond.kcas:g}: |φ−45°| {dphi:.2f}°")
    record("G7", "M2a 능력 제한 0, max|p_sp| ≤ 1.01×0.8·C_p (9조건 × FLCS on/off)", a_ok, "; ".join(la))
    record("G7", "M1 t=3 s 에서 |φ−45°| ≤ 2° (기준 파라미터, 18블록)", b_ok, "; ".join(lb))

    cap = capability(Condition(14000.0, 350.0))
    names = [m.name for m in paper_maneuvers(cap["C_nz"], cap["C_p"])]
    m2b = [m for m in paper_maneuvers(cap["C_nz"], cap["C_p"], tail_s=0) if m.name == "M2b"][0]
    with quiet():
        a = run(build(COND), m2b)
        b = run(build(COND), M2RollReversal())
    same, worst, _ = bitwise(a, b, TRUTH_COLS)
    record("G7", "M2b = 기존 M2 시계열 비트 동일, 주 기동 변형 7종", same and len(names) == 7,
           f"최대차 {worst}; 변형 {names}")

    from l3_indi import taxonomy as T
    from l3_indi.design import rq1_conditions as rc
    caps = [capability(c)["C_p"] for c in rc(0)]
    synth = {k: dict(v) for k, v in T.SYNTH_A9.items()}
    synth["M2a"]["peak_psp_dps"] = (round(0.8 * min(caps), 1), round(0.8 * max(caps), 1))
    ev = list(csv.DictReader(open(os.path.join(REPO, "results", "paper", "taxonomy", "296ce41ff0", "events.csv"),
                                  encoding="utf-8")))
    r2 = T.r2_from_events(ev, synth)
    outside = {k: v["outside"] for k, v in r2.items() if v["outside"]}
    record("G7", "개정 A9 수준으로 A7 R2 재판정 — 실전 p10~p90 밖 수준 없음", not outside,
           "; ".join(f"{k} {v['levels']} (p10 {v['real_p10']:.2f}, p90 {v['real_p90']:.2f}, 밖 {v['outside']})"
                     for k, v in r2.items()))


# ======================================================================================
# G8 개정 A10-4 측정 지연·동기화
# ======================================================================================
def g8():
    print("\n== G8 개정 A10-4 측정 지연 ==")
    from l3_indi.harness import SyncDelayINDI
    man = M3RollingPull(nz_target=4.0)
    with quiet():
        base = run(build(COND), man)
        rig0 = build(COND, unc=Uncertainty(sync_act_delay=True, meas_delay_steps=0))
        s0 = run(rig0, man)
    same, worst, _ = bitwise(base, s0, TRUTH_COLS)
    record("G8", "동기화 제어기 N=0 → 원본과 비트 동일", same and isinstance(rig0.pilot.indi, SyncDelayINDI),
           f"최대차 {worst}, 클래스 {type(rig0.pilot.indi).__name__}")

    from aircombat.fdm.plant import F16Plant
    with quiet():
        pl = F16Plant(dt=DT)
        pl.set_ic(alt_ft=15000, vc_kts=400)
        pl["fcs/throttle-cmd-norm"] = 0.85
        pl.trim()
    N = 4
    px = PlantProxy(pl, DT, meas_delay_steps=N)
    u0 = list(pl.get_input())
    hist = [(pl["velocities/q-rad_sec"], pl["accelerations/qdot-rad_sec2"])]
    ok = True
    for k in range(40):
        rd = (px["velocities/q-rad_sec"], px["accelerations/qdot-rad_sec2"])
        exp = hist[max(len(hist) - 1 - N, 0)]
        ok &= rd == exp
        px.set_input([u0[0], u0[1] - 0.02 * np.sin(k / 3), u0[2], u0[3]])
        px.step(1)
        hist.append((pl["velocities/q-rad_sec"], pl["accelerations/qdot-rad_sec2"]))
    other = px["attitude/phi-rad"] == pl["attitude/phi-rad"]
    record("G8", "프록시 측정 지연: 자이로·각가속도 읽기 = N틱 전 참 값, 다른 속성은 지연 없음",
           ok and other and hist[-1][0] != hist[0][0], f"N={N}, 40스텝 일치={ok}, 자세 비지연={other}")

    with quiet():
        rig = build(COND, unc=Uncertainty(sync_act_delay=True, meas_delay_steps=N))
    indi = rig.pilot.indi
    inputs = []

    class Spy:
        def __init__(self, f):
            self.f = f

        def __call__(self, x):
            inputs.append(np.array(x, float))
            return self.f(x)

        def reset(self, x0):
            return self.f.reset(x0)

    u_reset = np.array(indi.u_prev, float)
    indi.f_act = Spy(indi.f_act)
    with quiet():
        ts = run(rig, M3RollingPull(nz_target=4.0, duration_s=2.0))
    outs = np.stack([ts["u_ail"], ts["u_ele"], ts["u_rud"]], axis=1)
    ok2 = True
    for k, x in enumerate(inputs):
        j = k - 1 - N
        exp = outs[j] if j >= 0 else u_reset
        ok2 &= np.array_equal(x, exp)
    record("G8", "동기화 변형: f_act 입력 = N+1틱 전 INDI 출력 (첫 N+1틱은 리셋값)", ok2 and len(inputs) == len(outs),
           f"N={N}, {len(inputs)}틱 대조")

    with quiet():
        d_async = run(build(COND, unc=Uncertainty(meas_delay_steps=N)), man)
        d_sync = run(build(COND, unc=Uncertainty(meas_delay_steps=N, sync_act_delay=True)), man)
    differ = (not bitwise(base, d_async, TRUTH_COLS)[0]) and (not bitwise(d_async, d_sync, TRUTH_COLS)[0])
    record("G8", "지연이 실제로 들어감 (기준 ≠ 비동기 ≠ 동기)", differ,
           f"J_q 기준 {M.tracking_J(base,'q',man.window()):.4f} / 비동기 {M.tracking_J(d_async,'q',man.window()):.4f}"
           f" / 동기 {M.tracking_J(d_sync,'q',man.window()):.4f}")


# ======================================================================================
# G9 개정 A10-2 F_i
# ======================================================================================
def g9():
    print("\n== G9 개정 A10-2 기동 실현도 F_i ==")
    from aircombat.control.limiter import G_FT_S2 as G_LIM
    from l3_indi.maneuvers import M1BankedCapture
    cond = Condition(14000.0, 350.0)
    turn = M1BankedCapture(nz_target=float(np.sqrt(2.0)), duration_s=12.0)
    with quiet():
        rig_turn = build(cond)
        ts = run(rig_turn, turn)
    w = (8.0, 12.0)
    fi = M.path_realization(ts, w, n_target=ts["nz"])
    geo = M.wind_geometry(ts)
    act, ideal = M.path_rates(ts, ts["nz"])
    n_t = ts["nz"]
    scalar = (M.G_FT_S2 / geo["V"]) * np.sqrt(np.maximum(n_t ** 2 - 2 * n_t * np.cos(geo["mu"]) * np.cos(geo["gamma"])
                                                         + np.cos(geo["gamma"]) ** 2, 0))
    rel = float(np.max(np.abs(scalar - ideal) / np.maximum(ideal, 1e-9)))
    m = M.window_mask(ts, w)
    mu_phi_turn = float(np.max(np.abs(np.rad2deg(geo["mu"][m] - ts["phi"][m]))))
    # 진단: 마지막 틱(플랜트 현재 상태)에서 측방 하중 Ny 를 포함한 수직가속 예측 vs 속도 후진차분
    P = rig_turn.plant
    kk = len(ts["t"]) - 1
    v = np.stack([ts["vn"], ts["ve"], ts["vd"]], axis=1)
    vh = v[kk] / np.linalg.norm(v[kk])
    perp = lambda x: np.linalg.norm(x - np.dot(x, vh) * vh)
    xb, zb = M._body_axes_ned(ts["phi"][kk], ts["theta"][kk], ts["psi"][kk])
    yb = np.cross(zb, xb)
    gd = M.G_FT_S2 * np.array([0.0, 0.0, 1.0])
    meas = perp((v[kk] - v[kk - 1]) / DT)
    with_ny = perp(M.G_FT_S2 * (P["accelerations/Ny"] * yb - P["accelerations/Nz"] * zb) + gd)
    nz_only = perp(-M.G_FT_S2 * P["accelerations/Nz"] * zb + gd)
    passed_i = abs(fi - 1) <= 0.05
    record("G9", "(i) 수평 협조선회(뱅크 45°, Nz √2)에서 n_t=실측 Nz 인 F_i = 1 ± 0.05", passed_i,
           f"F_i {fi:.4f}, 창 {w}, 평균 뱅크 {np.rad2deg(np.mean(ts['phi'][m])):.1f}°, 평균 γ "
           f"{np.rad2deg(np.mean(geo['gamma'][m])):.2f}°, 평균 Nz {np.mean(ts['nz'][m]):.3f}, "
           f"평균 β {np.rad2deg(np.mean(ts['beta'][m])):.2f}°. 진단(마지막 틱): 속도 수직가속 실측 {meas:.2f} ft/s², "
           f"Nz+Ny 예측 {with_ny:.2f}, Nz 만 예측 {nz_only:.2f} (Ny {P['accelerations/Ny']:.3f} G) — "
           f"배치 요축 법칙(요 감쇠)은 협조선회를 하지 않아 측력이 생기고 F_i 식은 Nz 만 쓴다")
    record("G9", "개정 A10-2 대체 규칙 적용 결정 (G9 (i) 결과에 따름)", True,
           "M층 지표 = F_i" if passed_i else "G9 (i) 불통과 → M층 지표를 Nz 실현율(§4)로 대체 (개정 A12)")
    record("G9", "Ω_ideal 벡터식 = 스칼라식 √(n²−2n cosμ cosγ+cos²γ)·g/V", rel < 1e-9 and M.G_FT_S2 == G_LIM,
           f"최대 상대차 {rel:.1e}, g {M.G_FT_S2} = limiter {G_LIM}")
    with quiet():
        hs = run(build(cond), Hold(duration_s=3.0))
    gh = M.wind_geometry(hs)
    mh = hs["t"] >= 1.0
    mu_phi = float(np.max(np.abs(np.rad2deg(gh["mu"][mh] - hs["phi"][mh]))))
    record("G9", "(ii) β≈0 수평 비행(트림 유지)에서 |μ−φ| ≤ 0.5°", mu_phi <= 0.5,
           f"최대 {mu_phi:.4f}°, |β| 최대 {np.rad2deg(np.max(np.abs(hs['beta'][mh]))):.3f}°; "
           f"(참고, 판정 아님) 45° 선회 중 |μ−φ| 최대 {mu_phi_turn:.2f}°")


# ======================================================================================
# G10 개정 A10-3 실효 제어효과 추정
# ======================================================================================
def g10():
    print("\n== G10 개정 A10-3 실효 제어효과 ==")
    from l3_indi import effectiveness as EFF
    from l3_indi.traces import all_jobs, SCENARIOS
    from aircombat.engine.factory import load_policy, make_pilot
    from aircombat.engine.match import Match
    from aircombat.engine.scenarios import initial_conditions
    jobs = all_jobs()
    picks = [next(j for j in jobs if j["scenario"] == sc) for sc in SCENARIOS]
    ok, lines = True, []
    for j in picks:
        cwd = os.getcwd()
        os.chdir(REPO)
        try:
            with quiet():
                sides = [load_policy(j["participant"]), load_policy(j["red_path"])]
                ic = initial_conditions(j["scenario"], seed=j["seed"])
                pb = make_pilot("Blue", ic["blue"], *sides[0])
                pr = make_pilot("Red", ic["red"], *sides[1], name=j["red"])
                Match(pb, pr, duration_s=0.1, log_hz=0, wall_limit_s=600, overtime_s=0.0).run()
        finally:
            os.chdir(cwd)
        rest = EFF.restore_g0(j)
        same = all(np.array_equal(rest[s][0], p.indi.G0) and rest[s][1] == p.indi.qbar_ref
                   for s, p in (("blue", pb), ("red", pr)))
        ok &= same
        lines.append(f"{j['match_id']}: {same}")
    record("G10", "G0 복원 = 경기 중 식별값 비트 동일 (시나리오별 1경기, 양측)", ok, "; ".join(lines))

    from l3_indi.design import capability
    from l3_indi.maneuvers import paper_maneuvers
    cond = Condition(14000.0, 350.0)
    cap = capability(cond)
    mans = [m for m in paper_maneuvers(cap["C_nz"], cap["C_p"]) if m.name in ("M1_0.8", "M2a", "M3_0.9")]
    schemes = {"true": [], "central32": [], "central64": [], "forward64": []}
    for man in mans:
        with quiet():
            rig = build(cond)
            ts = run(rig, man)
        mask = M.window_mask(ts, man.window())
        u = np.stack([ts["cmd_ail"], ts["cmd_ele"], ts["cmd_rud"]], axis=1)
        om = np.stack([ts["p"], ts["q"], ts["r"]], axis=1)
        fwd = np.full_like(om, np.nan)
        fwd[:-1] = (om[1:] - om[:-1]) / DT
        est = {"true": np.stack([ts["pdot"], ts["qdot"], ts["rdot"]], axis=1),
               "central32": EFF.omega_dot_central(om.astype(np.float32)),     # 사전등록 방식 (판정 대상)
               "central64": EFF.omega_dot_central(om), "forward64": fwd}      # 진단용
        for k, wd in est.items():
            W = EFF.windows(wd, u, ts["qbar"], rig.G0_true, rig.qbar_ref, mask)
            schemes[k].append((W["C"], W["rms_phi"]))
    med = {}
    for k, lst in schemes.items():
        C, R = np.vstack([c for c, _ in lst]), np.vstack([r for _, r in lst])
        ex = EFF.excited(R)
        med[k] = [float(np.nanmedian(C[ex[:, i], i])) for i in range(3)]
        if k == "true":
            n_win = len(C)
    rel = lambda k, i: abs(med[k][i] - med["true"][i]) / abs(med["true"][i])
    ok_b = all(rel("central32", i) <= 0.05 for i in range(3))
    diag = "; ".join(f"{k} Ĉ(p,q,r)=({', '.join(f'{v:.3f}' for v in med[k])})"
                     + ("" if k == "true" else f" 차 ({', '.join(f'{100*rel(k, i):.0f}%' for i in range(3))})")
                     for k in med)
    record("G10", "ω̇ 중심차분(float32) Ĉ 가 참 ω̇ Ĉ 와 축별 5% 이내 (14k/350, M1_0.8·M2a·M3_0.9, 가진 상위 50% 창 중앙값)",
           ok_b, f"창 {n_win}개; {diag}. 진단: float32 와 float64 결과가 같으면 정밀도가 아니라 차분 방식이 원인")
    record("G10", "개정 A10-3 격하 규칙 적용 결정 (G10b 결과에 따름)", True,
           "A10-3 주 결과 유지" if ok_b else "G10b 불통과 → A10-3 은 부록 참고치로 격하 (개정 A12)")


# ======================================================================================
# G11 개정 A15 꼬리 유지 구간
# ======================================================================================
def g11():
    print("\n== G11 개정 A15 꼬리 유지 구간 ==")
    from l3_indi.design import capability
    from l3_indi.maneuvers import paper_maneuvers
    W_COLS = tuple(c for c in TRUTH_COLS if c != "t")
    ok_a, la = True, []
    for fbw in (0, 1):
        cond = Condition(14000.0, 350.0, fbw_override=fbw)
        cap = capability(cond)
        plain = paper_maneuvers(cap["C_nz"], cap["C_p"], tail_s=0)
        tailed = paper_maneuvers(cap["C_nz"], cap["C_p"])
        for m0, m1 in zip(plain, tailed):
            with quiet():
                a = run(build(cond), m0)
                b = run(build(cond), m1)
            n = len(a["t"])
            same = all(np.array_equal(a[c], b[c][:n], equal_nan=True) for c in W_COLS)
            longer = len(b["t"]) == n + int(round(5.0 / DT)) and m1.window() == m0.window()
            ok_a &= same and longer
            la.append(f"{'off' if fbw else 'on'} {m0.name}: {same and longer}")
    record("G11", "(a) 꼬리 유무 간 원래 구간 시계열 비트 동일 + 창 W 불변 + 길이 +5 s (14k/350, 7기동 × FLCS on/off)",
           ok_a, "; ".join(la))

    from l3_indi.maneuvers import M1BankedCapture, M2aCappedReversal, M3RollingPull, TailHold
    cases = (("M1_0.8 off 기준", 1, (1, 1, 1), 25.0, lambda c: TailHold(M1BankedCapture(nz_target=0.8 * c["C_nz"]), 45.0), 0),
             ("M2a on 기준", 0, (1, 1, 1), 25.0, lambda c: TailHold(M2aCappedReversal(cap_p_dps=c["C_p"]), -60.0), 0),
             ("M2a on k_p 2 filt 50", 0, (2, 1, 1), 50.0, lambda c: TailHold(M2aCappedReversal(cap_p_dps=c["C_p"]), -60.0), 0),
             ("M1_0.9 on 기준", 0, (1, 1, 1), 25.0, lambda c: TailHold(M1BankedCapture(nz_target=0.9 * c["C_nz"]), 45.0), 0),
             ("M1_0.9 on k_q 2", 0, (1, 2, 1), 25.0, lambda c: TailHold(M1BankedCapture(nz_target=0.9 * c["C_nz"]), 45.0), 1),
             ("M3_0.9 on k_q 2", 0, (1, 2, 1), 25.0, lambda c: TailHold(M3RollingPull(nz_target=0.9 * c["C_nz"]), 70.0), 1))
    ok_b, lb = True, []
    for label, fbw, ks, f, mk, expect in cases:
        cond = Condition(14000.0, 350.0, fbw_override=fbw)
        with quiet():
            ts = run(build(cond, Params(k_scale=ks, filt_hz=f)), mk(capability(cond)))
        o = M.oscillation(ts, DT)
        ok_b &= o["oscillating"] == expect
        lb.append(f"{label}: osc {o['oscillating']}(기대 {expect}), p2p {o['p2p_rate_dps']:.1f} dps, 부호반전 {o['signchg_hz']:.1f} Hz")
    record("G11", "(b) 개정 A15-3 의 6런 판정 재현 (착오 4런 → 진동 아님, 리밋사이클 2런 → 진동)", ok_b, "; ".join(lb))


# ======================================================================================
def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--child":
        cfg = json.loads(sys.argv[2])
        ts = _child_config(cfg)
        np.savez(sys.argv[3], **{c: ts[c] for c in TRUTH_COLS})
        return 0
    only = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--only":
        only = sys.argv[2].split(",")
    st = git_state()
    print(f"[gates] commit {st['commit'][:10]} clean={st['clean']}")
    t0 = time.perf_counter()
    order = (g6, g1, g2, g3, g4, g4_taxonomy, g4_a10, g5, g7, g8, g9, g10, g11)
    if only:
        order = tuple(g for g in order if g.__name__ in only)
    for g in order:
        try:
            g()
        except Exception as e:                                   # 게이트 자체 오류도 실패로 기록
            import traceback
            record(g.__name__.upper(), "게이트 실행 오류", False, repr(e))
            traceback.print_exc()
    wall = time.perf_counter() - t0
    passed = all(r["pass"] for r in RESULTS)
    if only:                                       # 부분 실행은 보고서를 쓰지 않는다
        print(f"\n[gates --only] {sum(r['pass'] for r in RESULTS)}/{len(RESULTS)} pass, {wall:.0f}s")
        return 0 if passed else 1
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
