"""M층 보조 — 유도 추격 팔(P, A25)을 변수 6 종 OFAT 수준으로 돌린다 (개정 A31 §7).

λ 밀집 스윕(A27 §2)과 같은 하네스·기동·조건·지표(rq3.job_fn)를 그대로 쓰고, **청군 설정만** dogfight_grid.json 의
OFAT 수준(baseline·sham·ofat 26 설정)으로 바꾼다. 적 궤적은 설정과 무관하게 기준 INDI 로 한 번 계산해 공유한다(A24-5).

차이점 (A31 §7·§9)
  * 입력 기하: 이 PC 에서 재생성한 results/paper/rq3_geom/3543f00337/geometries.json (원 PC 기하와 G1·G3 가 다르다).
  * 개루프 각가속도 한계(이상 응답 대비 궤적 편차 지표용)는 쓰지 않는다 → dev_* 지표는 NaN. P 팔 주 지표(ATA 최소·T_ATA30·
    평균 지향오차)와 T층 부지표(J_q·상관)는 영향을 받지 않는다.
  * 잡음·지연·난류는 E층(dogfight.py)과 같은 주입 함수(make_proxy·enable_turbulence)를 쓴다. 난류는 청군에만.

구현: rq3.job_fn 을 그대로 부르되, 워커 안에서 rq3.fly 를 감싸 **청군(PursuitScript) 비행만** 전체 설정으로 바꾼다.
  적(FixedSequence) 비행은 원래 fly 를 그대로 탄다. λ·게인·필터만 바꾼 설정은 원래 경로와 비트 동일해야 한다 → --verify.

사용:
  python research/l3_indi/msweep.py --verify                 새 경로 = 기존 rq3 경로(λ), 결정론 점검
  python research/l3_indi/msweep.py --run [--processes N]    26 설정 × 45 짝 = 1,170 런 (체크포인트)
  python research/l3_indi/msweep.py --analyze <결과 폴더>     짝 비교 보고서 (결과 폴더 안 analysis/ 에만 쓴다)
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import math
import multiprocessing as mp
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO, DT, Condition, build, run   # noqa: E402

GEOM_PATH = os.path.join(REPO, "results", "paper", "rq3_geom", "3543f00337", "geometries.json")
N_BOOT, BOOT_SEED = 10_000, 20260926
DELTA = {"ata_min": 2.0, "T_ata30": 0.25, "ata_mean": 2.0}        # A24 §8 / A25-2(d) 과 같은 δ
PAIR_KEY = ("kcas", "geom", "enemy")
_CURRENT = None                                                    # 워커 안에서 한 잡 동안만 설정된다


def _fly_patched(cond, man, k_scale, filt, lam_q, pos0=(0.0, 0.0, 0.0), psi0_deg=0.0):
    """rq3.fly 대체. 청군 추격(PursuitScript)이고 _CURRENT 가 있으면 전체 설정으로, 아니면 원래 fly."""
    from l3_indi import rq3
    from l3_indi.dogfight import make_proxy, enable_turbulence
    if _CURRENT is None or not isinstance(man, rq3.PursuitScript):
        return rq3._orig_fly(cond, man, k_scale, filt, lam_q, pos0=pos0, psi0_deg=psi0_deg)
    st, noise_seed, turb_seed = _CURRENT
    alt = cond.alt_ft - pos0[2]
    unc = st.uncertainty(noise_seed)
    with contextlib.redirect_stdout(io.StringIO()):
        rig = build(Condition(alt, cond.kcas, psi_deg=psi0_deg), st.params(), unc, use_proxy=False)
        rig.pilot.plant = make_proxy(rig.plant, rig.pilot.dt_phys, unc)     # build(use_proxy=True) 와 같은 인자
        enable_turbulence(rig.plant, st.turb, turb_seed)
        rig.pilot._pos[0] += pos0[0]
        rig.pilot._pos[1] += pos0[1]
        man.rig = rig
        ts = run(rig, man)
    # 이하 rq3.fly 와 같은 위치 복원
    v = np.stack([ts["vn"], ts["ve"], ts["vd"]], axis=1)
    p0 = np.array([pos0[0], pos0[1], -alt], float)
    pos = p0 + np.cumsum(v, axis=0) * DT
    out = {c: ts[c] for c in ts if c != "_meta"}
    out["px"], out["py"], out["pz"] = pos[:, 0], pos[:, 1], pos[:, 2]
    return out


def _install():
    from l3_indi import rq3
    if not hasattr(rq3, "_orig_fly"):
        rq3._orig_fly = rq3.fly
        rq3.fly = _fly_patched


def job_fn(job: dict) -> dict:
    """한 런. job["setting"] 은 rq3 가 해석하는 자리표시자 'L1' 이고, 실제 청군 설정은 job["_mset"]."""
    global _CURRENT
    from l3_indi import rq3
    from l3_indi.dogfight import Setting
    _install()
    _CURRENT = (Setting.from_dict(job["_mset"]), job["noise_seed"], job["turb_seed"]) if "_mset" in job else None
    try:
        row = rq3.job_fn(job)
    finally:
        _CURRENT = None
    return row


def build_jobs(names=None) -> list[dict]:
    from l3_indi import rq3
    from l3_indi.dogfight import load_grid, select_settings, sub_seed
    grid = load_grid()
    by = {s["name"]: s for s in grid["settings"]}
    names = names or select_settings(grid, "ofat")
    geoms = json.load(open(GEOM_PATH, encoding="utf-8"))
    jobs = []
    for name in names:
        s = by[name]
        for kcas in rq3.KCAS_SET:
            for g in geoms:
                for e in rq3.ENEMIES:
                    jobs.append({"match_id": f"{name}__{kcas:g}__{g['id']}__{e}",
                                 "m_setting": name, "family": s["family"], "variable": s["variable"],
                                 "level": str(s["level"]), "setting": "L1", "lam_q": 1.0,
                                 "kcas": kcas, "geom": g["id"], "enemy": e, "kind": "P",
                                 "bank0": g["bank_deg"], "switch_t": 1.0, "flow_intent": "na",
                                 "dur": rq3.DUR_GUIDED, "pdot_max": float("nan"), "qdot_max": float("nan"),
                                 "noise_seed": sub_seed("m", kcas, g["id"], e),
                                 "turb_seed": sub_seed("mturb", kcas, g["id"], e),
                                 "_geom": g, "_mset": s["_setting"].to_json()})
    return jobs


# ======================================================================================
def verify(processes: int = 4) -> int:
    """새 경로(λ 를 _mset 으로) = 기존 rq3 경로(setting 'L<λ>')인지, 같은 잡 두 번이 같은지."""
    from l3_indi.dogfight import Setting
    base = [j for j in build_jobs(["BASE"]) if j["geom"] in ("G1", "G4") and j["kcas"] == 350.0]
    tasks = []
    for lam in (1.0, 8.0, 25.0):
        for j in base[:3]:
            new = json.loads(json.dumps(j, default=float))
            new["_geom"] = j["_geom"]
            new["_mset"] = Setting(lam_q=lam).to_json()
            old = {k: v for k, v in new.items() if k != "_mset"}
            old["setting"], old["lam_q"] = f"L{lam:g}", lam
            new["lam_q"] = lam
            tasks += [old, new]
    tasks.append(tasks[1])                                      # 결정론: 첫 새 경로 잡 재실행
    with mp.get_context("spawn").Pool(processes) as pool:
        rows = pool.map(job_fn, tasks, chunksize=1)
    ok_all = True
    skip = {"setting"}
    for i in range(0, len(tasks) - 1, 2):
        a, b = rows[i], rows[i + 1]
        keys = [k for k in a if k not in skip]
        diff = [k for k in keys if not (a[k] == b[k] or (isinstance(a[k], float) and math.isnan(a[k]) and math.isnan(b[k])))]
        ok = not diff
        ok_all &= ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {tasks[i]['setting']} {tasks[i]['geom']} {tasks[i]['enemy']}: "
              f"새 경로 = rq3 경로 (지표 {len(keys)} 개, 다른 열 {diff[:4]}) J_q {a['J_q']:.4f} ATA최소 {a.get('ata_min', float('nan')):.2f}")
    a, b = rows[1], rows[-1]
    diff = [k for k in a if not (a[k] == b[k] or (isinstance(a[k], float) and math.isnan(a[k]) and math.isnan(b[k])))]
    print(f"  [{'PASS' if not diff else 'FAIL'}] 결정론 (같은 잡 두 번): 다른 열 {diff[:4]}")
    ok_all &= not diff
    print(f"[verify] {'PASS' if ok_all else 'FAIL'}")
    return 0 if ok_all else 1


def run_sweep(processes: int) -> str:
    from l3_indi.dogfight import run_checkpointed
    import l3_indi.dogfight as D
    jobs = build_jobs()
    # dogfight.run_checkpointed 는 dogfight.job_fn 을 쓴다 → 이 모듈의 job_fn 으로 바꿔 부른다
    orig = D.job_fn
    D.job_fn = job_fn
    try:
        return run_checkpointed("msweep", jobs, processes)
    finally:
        D.job_fn = orig


# ======================================================================================
def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def _boot(x, stat=np.median):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(BOOT_SEED)
    s = stat(x[rng.integers(0, len(x), size=(N_BOOT, len(x)))], axis=1)
    return float(stat(x)), float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))


def _judge(lo, hi, d):
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return "판정 불가"
    if lo >= -d and hi <= d:
        return "차이 없음"
    if lo > d or hi < -d:
        return "차이 있음"
    return "판정 불가"


def analyze(out_dir: str) -> int:
    """A24-9 와 같은 짝 비교(중앙값, 부트스트랩 CI). 보고서는 결과 폴더 안 analysis/ 에만 쓴다."""
    rows = [{k: _num(v) for k, v in r.items()} for r in csv.DictReader(open(os.path.join(out_dir, "runs.csv"), encoding="utf-8"))]
    by = {}
    for r in rows:
        by.setdefault(r["m_setting"], {})[tuple(r[k] for k in PAIR_KEY)] = r
    B = by["BASE"]
    metrics = ("ata_min", "T_ata30", "ata_mean", "J_q", "corr_early", "corr_late", "q_gain", "dkcas", "oscillating")
    table = []
    for name, S in by.items():
        if name == "BASE":
            continue
        meta = next(iter(S.values()))
        for m in metrics:
            d = [float(S[k][m]) - float(B[k][m]) for k in B]
            med, lo, hi = _boot(d)
            table.append({"setting": name, "variable": meta["variable"], "level": meta["level"], "metric": m,
                          "n": int(np.isfinite(np.asarray(d, float)).sum()), "median": med, "ci_lo": lo, "ci_hi": hi,
                          "judge": _judge(lo, hi, DELTA[m]) if m in DELTA else ""})
    ad = os.path.join(out_dir, "analysis")
    os.makedirs(ad, exist_ok=True)
    with open(os.path.join(ad, "effects.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)
    L = [f"# M층 보조 (유도 추격 팔) — {os.path.basename(os.path.normpath(out_dir))}\n",
         "- 규칙: 개정 A31 §7. 짝 = 같은 (KCAS, 기하, 적) 에서 설정만 다름, 기준 BASE. 짝 차이 **중앙값**과 부트스트랩 95% CI"
         f"({N_BOOT:,} 회, 시드 {BOOT_SEED}) — A24-9 와 같은 통계량.",
         "- δ: ATA 최소·평균 지향오차 2.0°, T_ATA30 0.25 s (A24 §8). 입력 기하는 이 PC 재생성본(A31 §9).\n",
         "| 설정 | 변수 | 수준 | " + " | ".join(metrics) + " |", "|---|---|---|" + "---|" * len(metrics)]
    for name in [s for s in by if s != "BASE"]:
        cells = []
        for m in metrics:
            r = next(x for x in table if x["setting"] == name and x["metric"] == m)
            j = f" **{r['judge']}**" if r["judge"] == "차이 있음" else (f" {r['judge']}" if r["judge"] else "")
            cells.append(f"{r['median']:+.3g} [{r['ci_lo']:+.3g}, {r['ci_hi']:+.3g}]{j}")
        meta = next(x for x in table if x["setting"] == name)
        L.append(f"| {name} | {meta['variable']} | {meta['level']} | " + " | ".join(cells) + " |")
    # oscillating 은 이진 지표라 짝 차이 중앙값만으로는 읽기 어렵다 → 판정 경기 수와 해석 주의를 함께 싣는다
    from l3_indi.metrics import (OSC_WINDOW_S, OSC_RATE_P2P_DPS, OSC_NZ_P2P, OSC_SIGNCHG_HZ,
                                 OSC_SIGNCHG_MIN_RATE_P2P_DPS)
    L += ["\n## oscillating 해석 주의\n",
          f"- 판정 규칙(`metrics.oscillation`, 사전등록 §7.1·개정 A3): 마지막 {OSC_WINDOW_S:g} s 창에서 각속도 봉우리-골 폭 > "
          f"{OSC_RATE_P2P_DPS:g} °/s, 또는 Nz 폭 > {OSC_NZ_P2P:g} G, 또는 조종면 부호반전 > {OSC_SIGNCHG_HZ:g} Hz"
          f"(각속도 폭 ≥ {OSC_SIGNCHG_MIN_RATE_P2P_DPS:g} °/s 일 때)이면 1 이다.",
          "- 이 규칙은 기동 중의 큰 각속도 변화나 돌풍에 의한 요동에도 걸린다. 그래서 기준(BASE)도 일부 경기가 1 이다. "
          "난류 칸의 값은 제어 루프 진동과 구분되지 않으므로 진동 지표로 쓰지 않는다.\n",
          "| 설정 | oscillating = 1 경기 |", "|---|---|"]
    for name, S in by.items():
        k = sum(int(float(r["oscillating"])) for r in S.values())
        L.append(f"| {name} | {k} / {len(S)} |")
    rep = os.path.join(ad, "MSWEEP_report.md")
    with open(rep, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("->", rep)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyze", default=None)
    ap.add_argument("--processes", type=int, default=2)
    args = ap.parse_args()
    if args.verify:
        return verify(args.processes)
    if args.run:
        print("->", run_sweep(args.processes))
        return 0
    if args.analyze:
        return analyze(args.analyze)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
