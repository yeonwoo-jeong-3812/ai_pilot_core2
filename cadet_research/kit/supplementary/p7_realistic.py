"""P7: 실제형 센서·구동기 (엔진·키트 파일은 고치지 않고 실행 중에만 감싼다).

  import p7_realistic; p7_realistic.enable()          # 이 프로세스의 모든 Pilot.setup 이 실제형이 된다
  python p7_realistic.py --bench                       # 벤치(교전 0판): BASE·이득 여유 확인·비동기 지연 → p7_bench_output.md

바꾸는 것 (계획 PLAN_AFTER_PANEL_v1 §4 P7, GNC 패널 안)
  구동기: 승강타·에일러론 명령과 JSBSim 사이에 1차 지연(20.2 rad/s)과 속도 제한(승강타 60 °/s, 에일러론 80 °/s)을 넣는다.
          JSBSim 모델의 기존 구동기(0.3 s 전 행정)는 그 뒤에 그대로 남는다.
  센서:   각가속도를 시뮬레이터 참값 대신 자이로(잡음·지연이 걸린 각속도)의 차분으로 구한다(INDI 의 ang_accel=None 경로).
  INDI:   구동기 측정값으로 실제 구동기 위치를 쓰고, 차분 각가속도와 시간을 맞추려 두 틱 전 위치를 쓴다(동기화).
열화 주입(run.apply_knobs)은 그 바깥에서 그대로 걸린다. 동기 지연(delay_sync) 조건은 이 모드에서 쓰지 않는다.
"""
from __future__ import annotations

import collections
import os
import sys

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # kit/supplementary → kit
HERE = os.path.dirname(os.path.abspath(__file__))
if KIT not in sys.path:
    sys.path.insert(0, KIT)

DT = 1.0 / 120.0
WA = 20.2                                   # 구동기 대역 [rad/s]
RATE_ELEV = 60.0 / 25.0                     # 승강타 속도 제한 [정규/s] (±25° = ±1)
RATE_AIL = 80.0 / 21.5                      # 에일러론 속도 제한 [정규/s] (±21.5° = ±1)
BETA = 1.0 - np.exp(-WA * DT)
CFG = {"K": None, "fc": None}               # 재조정 값 (None 이면 키트 기본 K 9, 25 Hz)


def _actuate(x, cmd, rate):
    return x + float(np.clip(BETA * (cmd - x), -rate * DT, rate * DT))


def _install(pilot):
    import run
    from aircombat.control.indi import SecondOrderLPF
    indi, plant = pilot.indi, pilot.plant
    if CFG["K"] is not None:
        indi.k_rate[0] = indi.k_rate[1] = CFG["K"]
    if CFG["fc"] is not None:
        fs = 1.0 / indi.dt
        for name in ("f_acc", "f_act", "f_rate"):
            setattr(indi, name, SecondOrderLPF(CFG["fc"], fs, 3))
        indi._primed = False
    st = {"a": float(plant["fcs/aileron-cmd-norm"]), "e": float(plant["fcs/elevator-cmd-norm"])}
    hist = collections.deque([(st["a"], st["e"])] * 3, maxlen=3)
    raw_set = plant.set_input

    def set_input(cmds):
        thr, e_cmd, a_cmd, rud = cmds
        st["e"] = _actuate(st["e"], float(e_cmd), RATE_ELEV)
        st["a"] = _actuate(st["a"], float(a_cmd), RATE_AIL)
        hist.append((st["a"], st["e"]))
        return raw_set([thr, st["e"], st["a"], rud])
    plant.set_input = set_input
    raw_update = indi.update

    def update(omega, omega_sp, qbar, ang_accel=None, **kw):
        if "u_meas" in kw:
            raise RuntimeError("P7 실제형 모드는 동기 지연(delay_sync) 조건을 지원하지 않는다")
        a2, e2 = hist[-2]                    # 두 틱 전 구동기 위치 (차분 각가속도와 시간 맞춤)
        kw["u_meas"] = np.array([a2, e2, indi.u_prev[2]])
        return raw_update(omega, omega_sp, qbar, ang_accel=None, **kw)
    indi.update = update
    pilot._p7 = True


def enable(K=None, fc=None):
    """run._orig_setup 을 감싼다. run._patched_setup 이 호출 시점에 이 이름을 찾으므로, 열화 주입보다 안쪽에 걸린다."""
    import run
    CFG.update(K=K, fc=fc)
    if getattr(run, "_p7_enabled", False):
        return
    base = run._orig_setup

    def realistic_setup(pilot):
        base(pilot)
        _install(pilot)
        return pilot
    run._orig_setup = realistic_setup
    run._p7_enabled = True


# ---------------------------------------------------------------- 벤치 (P1 과 같은 입력)
def _bench_job(job):
    import p1_bench
    enable(**job[-1])
    return p1_bench.run_one(job[:-1])


def bench(conds, K=None, fc=None, procs=14):
    import multiprocessing as mp
    import p1_bench
    js = []
    for label, kn in conds.items():
        for alt, kcas in p1_bench.FLIGHT_POINTS:
            for a in p1_bench.AMPS:
                js.append((label, kn, alt, kcas, "doublet", a, ("p7bench", label, alt, kcas, "doublet", a), dict(K=K, fc=fc)))
    with mp.Pool(procs) as pool:
        res = pool.map(_bench_job, js, chunksize=2)
    out = {}
    for label in conds:
        rs = [r for r in res if r["label"] == label]
        small = [r for r in rs if r["p"] == p1_bench.AMPS[0]]
        div = any(r["diverged"] for r in rs)
        lc = sum((not r["diverged"]) and r["res56"] > p1_bench.LC_RMS and r["res56"] / max(r["res45"], 1e-9) > p1_bench.LC_RATIO for r in small)
        out[label] = dict(J=float(np.mean([r["J"] for r in rs])), J_small=float(np.mean([r["J"] for r in small])),
                          res56=None if div else float(np.mean([r["res56"] for r in small])),
                          cls="발산" if div else ("한계 순환" if lc >= 2 else "안정"))
    return out


if __name__ == "__main__":
    if "--bench" in sys.argv:
        os.chdir(KIT)
        sys.path.insert(0, HERE)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        conds = {"BASE": {}, "이득 2배 (κ 0.5, 6 dB)": {"kappa": 0.5}, "이득 2.8배 (κ 0.355, 9 dB)": {"kappa": 0.355}}
        for d in (0.5, 1, 2, 3, 4, 5, 6, 8, 10, 12):
            conds[f"비동기 {d:g}틱"] = {"delay_async": d}
        for k in (8, 25, 50):
            conds[f"κ {k}"] = {"kappa": k}
        o = bench(conds)
        L = ["# P7 벤치: 실제형 센서·구동기, 키트 기본 게인(K 9, 25 Hz)\n",
             "| 조건 | 분류 | J̄ (이중펄스 6회) | J 작은 진폭 | 잔류 RMS [°/s] |", "|---|---|---|---|---|"]
        for k, v in o.items():
            res = "–" if v["res56"] is None else f"{v['res56']:.2f}"
            L.append(f"| {k} | {v['cls']} | {v['J']:.2f} | {v['J_small']:.2f} | {res} |")
        txt = "\n".join(L) + "\n"
        open(os.path.join(HERE, "p7_bench_output.md"), "w", encoding="utf-8").write(txt)
        print(txt)
