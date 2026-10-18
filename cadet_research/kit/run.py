"""INDI 설정 주입 + 리그 실행기.

  python run.py --selfcheck                 # E0: 주입·결정론 점검 (약 1분)
  python run.py E1 --procs 20               # 실험 하나 실행. out/<시드접두어>/games.csv 에 이어 쓴다
  python run.py E2 --procs 20 --salts 2     # 시드 수를 줄여 빨리 돌려 보기
  python run.py E3 --dry                    # 판 수만 세고 실행하지 않는다
  python run.py E2 --salts 2 --prefix smoke --quick  # 실행 점검용. 확증 시드(main-*)를 쓰지 않는다

이미 기록된 판은 건너뛴다(중단 후 같은 명령으로 재개). 엔진은 이 폴더의 aircombat/ 스냅샷이다.
"""
from __future__ import annotations

import argparse
import collections
import csv
import itertools
import json
import os
import sys
import time

import numpy as np

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)

from aircombat.bridge import CompetitionMatch, derive_seed  # noqa: E402
from aircombat.control.indi import SecondOrderLPF  # noqa: E402
from aircombat.engine import pilot as pilot_mod  # noqa: E402
from experiments import CONDITIONS, EXPERIMENTS  # noqa: E402

FIELDS = ["cond", "target", "blue", "red", "scenario", "salt", "winner", "condition",
          "hp_blue", "hp_red", "blue_corr_q", "blue_mae_q_dps",
          "red_corr_q", "red_mae_q_dps", "wall_s"]

CFG: dict = {}      # 이 프로세스에서 지금 도는 판의 설정 {knobs, target, seed}
TRACE: dict = {}    # 기체 색 -> 피치 명령·응답 누적합
APPLIED: list = []  # 이 판에서 설정이 걸린 기체 색 (자가점검용)
_orig_setup = pilot_mod.Pilot.setup


def apply_knobs(pilot, knobs: dict, seed) -> None:
    """Pilot.setup() 이 만든 INDI 에 실험 설정을 건다. 빈 knobs 면 기준 그대로(측정만)."""
    indi = pilot.indi
    if "kappa" in knobs:                     # INDI 가 믿는 피치 제어효과 = 실제 × κ
        indi.G0[1, :] *= knobs["kappa"]
    if "kq" in knobs:
        indi.k_rate[1] *= knobs["kq"]
    if "filt_hz" in knobs:                   # 세 필터를 같은 새 차단주파수로 (동기화 유지)
        fs = 1.0 / indi.dt
        for name in ("f_acc", "f_act", "f_rate"):
            setattr(indi, name, SecondOrderLPF(knobs["filt_hz"], fs, 3))
        indi._primed = False
    sigma = np.radians(knobs.get("sigma_dps", 0.0))
    d_async = float(knobs.get("delay_async", 0))   # 소수 허용: 이웃 두 틱을 선형 보간
    n_sync = int(knobs.get("delay_sync", 0))
    n0, frac = int(np.floor(d_async)), d_async - np.floor(d_async)
    n = max(n0, n_sync)
    rng = np.random.default_rng(derive_seed(seed, pilot.color))
    meas = collections.deque(maxlen=n + 2)   # (각속도, 각가속도) 측정 이력
    u_hist = collections.deque(maxlen=n + 1)  # INDI 가 낸 조종 입력 이력 (동기 지연용)

    def lag(buf, k):                          # k 틱 전 값. 이력이 차기 전에는 가장 오래된 값
        return buf[max(len(buf) - 1 - k, 0)]
    st = TRACE[pilot.color] = dict(n=0, sx=0.0, sy=0.0, sxx=0.0, syy=0.0, sxy=0.0, ae=0.0)
    raw_update = indi.update

    def update(omega, omega_sp, qbar, ang_accel=None, **kw):
        omega = np.asarray(omega, float)
        x, y = np.degrees(omega_sp[1]), np.degrees(omega[1])   # 피치 명령, 실제 응답 [°/s]
        st["n"] += 1; st["sx"] += x; st["sy"] += y
        st["sxx"] += x * x; st["syy"] += y * y; st["sxy"] += x * y; st["ae"] += abs(x - y)
        noisy = omega + rng.normal(0.0, sigma, 3) if sigma > 0 else omega
        meas.append((noisy, np.asarray(ang_accel, float)))
        w_d, a_d = lag(meas, max(n0, n_sync))
        if frac:
            w_b, a_b = lag(meas, n0 + 1)
            w_d, a_d = (1 - frac) * w_d + frac * w_b, (1 - frac) * a_d + frac * a_b
        if n_sync:
            u_hist.append(indi.u_prev.copy())
            kw["u_meas"] = lag(u_hist, n_sync)
        return raw_update(w_d, omega_sp, qbar, ang_accel=a_d, **kw)

    indi.update = update


def _patched_setup(self):
    _orig_setup(self)
    target = CFG.get("target")
    on = target is None or self.agent_name == target
    if on:
        APPLIED.append(self.color)
    apply_knobs(self, CFG["knobs"] if on else {}, CFG["seed"])
    return self


pilot_mod.Pilot.setup = _patched_setup


def _corr(s):
    n = s["n"]
    if n < 2:
        return float("nan")
    vx = s["sxx"] / n - (s["sx"] / n) ** 2
    vy = s["syy"] / n - (s["sy"] / n) ** 2
    cov = s["sxy"] / n - (s["sx"] / n) * (s["sy"] / n)
    return cov / np.sqrt(vx * vy) if vx > 0 and vy > 0 else float("nan")


def play(job: dict) -> dict:
    cond, target, a, b = job["cond"], job["target"], job["blue"], job["red"]
    CFG.update(knobs=CONDITIONS[cond], target=target or None,
               seed=(cond, a, b, job["scenario"], job["salt"]))
    TRACE.clear(); APPLIED.clear()
    t0 = time.time()
    r = CompetitionMatch(os.path.join(KIT, job["blue_path"]), os.path.join(KIT, job["red_path"]),
                         a, b, seed=derive_seed(job["scenario"], job["salt"]),
                         scenario=job["scenario"]).run()
    tb, tr = TRACE.get("Blue"), TRACE.get("Red")
    return {"cond": cond, "target": target, "blue": a, "red": b, "scenario": job["scenario"],
            "salt": job["salt"], "winner": {"tree1": a, "tree2": b, "draw": "draw"}[r.winner],
            "condition": r.condition, "hp_blue": round(r.tree1_health, 2),
            "hp_red": round(r.tree2_health, 2),
            "blue_corr_q": round(_corr(tb), 4), "blue_mae_q_dps": round(tb["ae"] / tb["n"], 4),
            "red_corr_q": round(_corr(tr), 4), "red_mae_q_dps": round(tr["ae"] / tr["n"], 4),
            "wall_s": round(time.time() - t0, 1)}


def build_jobs(exp: dict, salts: int) -> list[dict]:
    agents = exp["agents"]
    jobs = []
    for salt in (f"{exp['salt']}-{i}" for i in range(salts)):
        for cond in exp["conds"]:
            targets = [""]
            if exp.get("target") == "each" and cond != "BASE":
                targets = list(agents)
            for target in targets:
                for a, b in itertools.combinations(agents, 2):
                    if target and target not in (a, b):
                        continue                 # 비대칭: 대상이 안 낀 판은 BASE 와 같다
                    for scen in exp["scenarios"]:
                        for x, y in ((a, b), (b, a)):
                            jobs.append(dict(cond=cond, target=target, blue=x, red=y,
                                             blue_path=agents[x], red_path=agents[y],
                                             scenario=scen, salt=salt))
    return jobs


def _key(r):
    return (r["cond"], r["target"], r["blue"], r["red"], r["scenario"], r["salt"])


def selfcheck() -> None:
    """E0. 실패하면 AssertionError 로 멈춘다. 다른 실험을 시작하기 전에 반드시 통과시킨다."""
    ag = EXPERIMENTS["FEAS"]["agents"]
    base = dict(cond="BASE", target="", blue="PurePursuer", red="Extender",
                blue_path=ag["PurePursuer"], red_path=ag["Extender"],
                scenario="neutral", salt="selfcheck")
    show = ("winner", "condition", "hp_blue", "hp_red", "blue_corr_q", "blue_mae_q_dps")
    r0, r1 = play(base), play(base)
    assert all(r0[k] == r1[k] for k in FIELDS if k != "wall_s"), "같은 시드인데 결과가 다르다"
    print("[ok] 결정론: 같은 시드 두 번 =", {k: r0[k] for k in show})
    for cond in ("SHAM", "FILT10", "NOISE1.0", "ASYNC2", "FILT5+ASYNC2", "SYNC8", "KAPPA25", "KQ0.5"):
        r = play({**base, "cond": cond})
        d = abs(r["blue_mae_q_dps"] - r0["blue_mae_q_dps"]) + abs(r["red_mae_q_dps"] - r0["red_mae_q_dps"])
        if cond == "SHAM":
            assert d < 0.05, f"SHAM 이 추종을 바꿨다 ({d:.3f})"
        else:
            assert d > 0, f"{cond} 주입이 아무 효과도 없다"
        print(f"[ok] {cond:8s} 추종오차 blue {r0['blue_mae_q_dps']:.3f}->{r['blue_mae_q_dps']:.3f} °/s,"
              f" corr {r0['blue_corr_q']:.3f}->{r['blue_corr_q']:.3f}, 결과 {r['winner']}/{r['condition']}")
    play({**base, "cond": "KAPPA25"})
    assert APPLIED == ["Blue", "Red"], APPLIED
    play({**base, "cond": "KAPPA25", "target": "PurePursuer"})
    assert APPLIED == ["Blue"], f"청이 대상인데 {APPLIED} 에 걸렸다"
    play({**base, "cond": "KAPPA25", "target": "Extender"})
    assert APPLIED == ["Red"], f"적이 대상인데 {APPLIED} 에 걸렸다"
    print("[ok] 비대칭 대상 지정: 청·적 어느 쪽이 대상이어도 그 기체에만 걸린다")
    print("E0 통과")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exp", nargs="?", choices=list(EXPERIMENTS))
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--procs", type=int, default=8, help="병렬 프로세스 수 (코어 수보다 작게)")
    ap.add_argument("--salts", type=int, help="시드 수 (기본: 실험 정의 값)")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--quick", action="store_true", help="참가자 앞 3명만 (실행 점검용)")
    ap.add_argument("--prefix", help="시드 접두어 바꾸기. 실행 점검은 smoke 로 해서 확증 시드(main)를 건드리지 않는다")
    args = ap.parse_args()
    if args.selfcheck:
        return selfcheck()
    if not args.exp:
        ap.error("실험 이름 또는 --selfcheck 가 필요하다")
    exp = dict(EXPERIMENTS[args.exp])
    if args.prefix:
        exp["salt"] = args.prefix
    if args.quick:
        exp["agents"] = dict(list(exp["agents"].items())[:3])
    jobs = build_jobs(exp, args.salts or exp["salts"])
    out_dir = os.path.join(KIT, "out", exp["salt"])
    path = os.path.join(out_dir, "games.csv")
    done = set()
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            done = {_key(r) for r in csv.DictReader(f)}
    todo = [j for j in jobs if _key(j) not in done]
    print(f"{args.exp}: 전체 {len(jobs)}판, 기록됨 {len(jobs) - len(todo)}, 남음 {len(todo)}")
    if args.dry or not todo:
        return
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(KIT, "ENGINE_VERSION.txt"), encoding="utf-8") as f:
        engine = f.read()
    with open(os.path.join(out_dir, f"manifest_{args.exp}.json"), "w", encoding="utf-8") as f:
        json.dump({"exp": args.exp, "salts": args.salts or exp["salts"], "jobs": len(jobs),
                   "started": time.strftime("%Y-%m-%d %H:%M:%S"), "engine": engine}, f,
                  ensure_ascii=False, indent=1)
    import multiprocessing as mp
    new = not os.path.isfile(path)
    t0 = time.time()
    with mp.Pool(args.procs) as pool, open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for i, row in enumerate(pool.imap_unordered(play, todo, chunksize=1), 1):
            w.writerow(row); f.flush()
            if i % 100 == 0 or i == len(todo):
                el = time.time() - t0
                print(f"  {i}/{len(todo)}  {el:.0f}s 경과, 남은 예상 {el / i * (len(todo) - i):.0f}s",
                      flush=True)
    print("기록:", path)


if __name__ == "__main__":
    main()
