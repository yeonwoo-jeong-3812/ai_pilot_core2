"""분석 묶음 — 개정 A10-1(ε 히트맵)·A11-1(교전 맥락·사례)·A12·A22(운영 정의).

  --heatmap  RQ1 기준 파라미터 시계열 126개 → (α × Nz) 칸별 ε
  --context  P2 궤적 440경기 → L1 전술 모드별 명령 크기·포화·1 s 창 J
  --case     사례 3건 (blue INDI 설정만 기준/튜닝으로 바꿔 같은 경기 재실행)

사용: python research/l3_indi/bundle.py --heatmap --context --case
출력: results/paper/bundle/<commit10>/ + research/l3_indi/reports/BUNDLE_<commit10>.md
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import glob
import io
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO, DT            # noqa: E402

RQ1_TS = os.path.join(REPO, "results", "paper", "rq1", "c45f90998c", "ts")
TRACES = os.path.join(REPO, "results", "paper", "traces", "296ce41ff0", "npz")
CAP_CSV = os.path.join(HERE, "reports", "capability_05b869f2e4.csv")
WIN_TICKS = 120
MODE_MIN_S = 60.0
TUNED_K = (1.0, 1.5, 0.5)
TUNED_FILT = 15.0


def pct(a, q):
    a = np.asarray([x for x in a if np.isfinite(x)], float)
    return float(np.percentile(a, q)) if len(a) else float("nan")


# --------------------------------------------------------------------------------------
def heatmap(out_dir: str) -> list[str]:
    from l3_indi import metrics as M
    from l3_indi.evaluate import maneuver_by_name
    from l3_indi.design import capability
    from l3_indi.harness import Condition
    acc = {0: None, 1: None}
    n_files = 0
    for fp in sorted(glob.glob(os.path.join(RQ1_TS, "*.npz"))):
        z = np.load(fp)
        ts = {k: z[k] for k in z.files if k not in ("G0_true", "qbar_ref")}
        g = re.search(r"alt_ft=([\d.]+)__fbw=(\d)__filt=[\d.]+__kcas=([\d.]+)__kp=", fp)
        if g is None:                       # 파일명 순서가 다르면 개별 키로 파싱
            kv = dict(re.findall(r"([a-z_0-9]+)=([\w.\-]+)", os.path.basename(fp)))
            alt, fbw, kcas, man = float(kv["alt_ft"]), int(kv["fbw"]), float(kv["kcas"]), kv["man"]
        else:
            alt, fbw, kcas = float(g.group(1)), int(g.group(2)), float(g.group(3))
            man = re.search(r"man=([A-Za-z0-9_.]+?)__", fp).group(1)
        cap = capability(Condition(alt, kcas, fbw_override=fbw))
        w = maneuver_by_name(man, cap).window()
        acc[fbw] = M.tss_accumulate(acc[fbw], ts, w, z["G0_true"], float(z["qbar_ref"]))
        n_files += 1
    rows = []
    for fbw in (0, 1):
        for r in M.tss_heatmap(acc[fbw] or {}):
            rows.append(dict(fbw=fbw, **r))
    with open(os.path.join(out_dir, "eps_heatmap.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    L = ["## 1. 시간척도 분리 잔차 ε 히트맵 (개정 A10-1, A22-1)\n",
         f"- 대상 {n_files} 런(RQ1 기준 파라미터), 칸 = 받음각 2° × Nz 0.5 G, 틱 ≥ 120 인 칸만. 전체 칸 {len(rows)}개.",
         "- ε 는 \"INDI 의 1틱 증분 모델이 설명하지 못한 각가속도 변화의 비율\" — 클수록 가정 위반이 크다.\n"]
    for fbw in (0, 1):
        R = [r for r in rows if r["fbw"] == fbw]
        if not R:
            continue
        L.append(f"**FLCS {'on' if fbw == 0 else 'off'}** — 칸 {len(R)}개\n")
        nzs = sorted({r["nz_lo"] for r in R})
        als = sorted({r["alpha_lo_deg"] for r in R})
        for axis in ("eps_q", "eps_p"):
            L.append(f"{axis} (행 = 받음각 [°], 열 = Nz [G])\n")
            L.append("```")
            L.append("  α\\Nz " + " ".join(f"{n:>5.1f}" for n in nzs))
            for a in als:
                cells = []
                for n in nzs:
                    v = next((r[axis] for r in R if r["alpha_lo_deg"] == a and r["nz_lo"] == n), None)
                    cells.append(f"{v:>5.2f}" if v is not None and np.isfinite(v) else "    ·")
                L.append(f"{a:>6.0f} " + " ".join(cells))
            L.append("```\n")
        tot = sum(r["ticks"] for r in R)
        big = [r for r in R if np.isfinite(r["eps_q"]) and r["eps_q"] > 1.0]
        L.append(f"- 틱 합계 {tot:,}, ε_q > 1.0 인 칸 {len(big)}/{len(R)}\n")
    return L


# --------------------------------------------------------------------------------------
def context(out_dir: str) -> list[str]:
    from l3_indi import taxonomy as T
    cap = T.Capability(CAP_CSV, fbw=0)
    agg = {}
    n_matches = 0
    for fp in sorted(glob.glob(os.path.join(TRACES, "*.npz"))):
        z = np.load(fp)
        meta = json.loads(str(z["meta"]))
        inv = {v: k for k, v in meta["modes"].items()}
        for side in ("blue", "red"):
            lab, _, _ = T.classify_side({k: z[k] for k in z.files if k.startswith(side + "__")}, side, cap)
            g = lambda c: z[f"{side}__{c}"]
            mode = g("mode_code").astype(int)
            man_mask = np.asarray(lab) != "low_g"
            for code in np.unique(mode):
                m = man_mask & (mode == code)
                if not m.any():
                    continue
                d = agg.setdefault(inv.get(int(code), f"code{code}"),
                                   {"ticks": 0, "psp": [], "qsp": [], "sat": 0, "satn": 0, "jp": [], "jq": []})
                d["ticks"] += int(m.sum())
                d["psp"].append(np.abs(np.rad2deg(g("sp_p")[m])))
                d["qsp"].append(np.abs(np.rad2deg(g("sp_q")[m])))
                u = np.stack([g("u_ail")[m], g("u_ele")[m], g("u_rud")[m]], 1)
                d["sat"] += int(np.sum(np.abs(u) > 0.999))
                d["satn"] += int(u.size)
                # 1 s 창 J (연속 구간 안에서만)
                idx = np.nonzero(m)[0]
                if len(idx) >= WIN_TICKS:
                    brk = np.nonzero(np.diff(idx) != 1)[0]
                    for seg in np.split(idx, brk + 1):
                        for s in range(0, len(seg) - WIN_TICKS + 1, WIN_TICKS):
                            w = seg[s:s + WIN_TICKS]
                            for ax, key in (("p", "jp"), ("q", "jq")):
                                sp = np.rad2deg(g(f"sp_{ax}")[w])
                                act = np.rad2deg(g(ax)[w])
                                den = max(float(np.sqrt(np.mean(sp ** 2))), 2.0)
                                d[key].append(float(np.sqrt(np.mean((sp - act) ** 2)) / den))
        n_matches += 1
    total_ticks = sum(d["ticks"] for d in agg.values())
    small = [k for k, d in agg.items() if d["ticks"] * DT < MODE_MIN_S]
    if small:
        etc = agg.setdefault("기타", {"ticks": 0, "psp": [], "qsp": [], "sat": 0, "satn": 0, "jp": [], "jq": []})
        for k in small:
            if k == "기타":
                continue
            d = agg.pop(k)
            for f in ("ticks", "sat", "satn"):
                etc[f] += d[f]
            for f in ("psp", "qsp", "jp", "jq"):
                etc[f] += d[f]
    rows = []
    for name, d in sorted(agg.items(), key=lambda kv: -kv[1]["ticks"]):
        psp = np.concatenate(d["psp"]) if d["psp"] else np.array([np.nan])
        qsp = np.concatenate(d["qsp"]) if d["qsp"] else np.array([np.nan])
        rows.append({"mode": name, "maneuver_s": d["ticks"] * DT, "time_frac": d["ticks"] / total_ticks,
                     "psp_p50": pct(psp, 50), "psp_p90": pct(psp, 90), "qsp_p50": pct(qsp, 50), "qsp_p90": pct(qsp, 90),
                     "sat_pct": 100 * d["sat"] / max(d["satn"], 1), "n_win": len(d["jp"]),
                     "Jp_p50": pct(d["jp"], 50), "Jp_p90": pct(d["jp"], 90),
                     "Jq_p50": pct(d["jq"], 50), "Jq_p90": pct(d["jq"], 90)})
    with open(os.path.join(out_dir, "context_modes.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    L = ["## 2. 교전 맥락별 실현도 (개정 A11-1, A12, A22-2)\n",
         f"- {n_matches}경기 양측, A7 기동 시간(low_g 제외) 틱만. 1 s 창 = 겹치지 않는 120틱. 모드 합계 60 s 미만은 '기타'.",
         f"- 총 기동 시간 {total_ticks * DT / 60:.0f} 기체-분.\n",
         "| L1 전술 모드 | 기동 시간 [분] | 비율 | \\|p_sp\\| p50/p90 [°/s] | \\|q_sp\\| p50/p90 [°/s] | 명령 포화 | 1 s 창 J_p p50/p90 | 1 s 창 J_q p50/p90 | 창 수 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['mode']} | {r['maneuver_s']/60:.0f} | {100*r['time_frac']:.1f}% | "
                 f"{r['psp_p50']:.0f} / {r['psp_p90']:.0f} | {r['qsp_p50']:.1f} / {r['qsp_p90']:.1f} | {r['sat_pct']:.1f}% | "
                 f"{r['Jp_p50']:.2f} / {r['Jp_p90']:.2f} | {r['Jq_p50']:.2f} / {r['Jq_p90']:.2f} | {r['n_win']:,} |")
    L.append("")
    return L


# --------------------------------------------------------------------------------------
def case(out_dir: str) -> list[str]:
    from aircombat.bridge import derive_seed
    from aircombat.control.indi import INDIRateController
    from aircombat.engine.factory import load_policy, make_pilot
    from aircombat.engine.match import Match
    from aircombat.engine.scenarios import initial_conditions
    from l3_indi import taxonomy as T
    rows = []
    cwd = os.getcwd()
    for scen in ("headon", "perch_offense", "perch_defense"):
        for gain, (k, filt) in {"base": (None, None), "tuned": (TUNED_K, TUNED_FILT)}.items():
            os.chdir(REPO)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    pb, db = load_policy("examples/doctrine_regulator.yaml")
                    pr, dr = load_policy("redteams/red_prime.yaml")
                    ic = initial_conditions(scen, seed=derive_seed("battery-v1", scen, "red_prime"))
                    blue = make_pilot("Blue", ic["blue"], pb, db, name="doctrine_regulator")
                    red = make_pilot("Red", ic["red"], pr, dr, name="red_prime")
                    if k is not None:                     # A22-3: setup 직후 INDI 만 재생성 (build() 와 같은 방식)
                        orig = blue.setup

                        def setup(_orig=orig, _blue=blue):
                            _orig()
                            base = (9.0, 9.0, 6.0)
                            ind = INDIRateController(_blue.dt_phys, _blue.indi.G0, _blue.indi.qbar_ref,
                                                     k_rate=tuple(b * s for b, s in zip(base, k)), filt_hz=filt)
                            ind.reset(u0=[_blue.plant["fcs/aileron-cmd-norm"], _blue.plant["fcs/elevator-cmd-norm"],
                                          _blue.plant["fcs/rudder-cmd-norm"]])
                            _blue.indi = ind
                            return _blue
                        blue.setup = setup
                    buf = []
                    orig_sp = blue.step_physics

                    def sp(_o=orig_sp, _b=blue, _buf=buf):
                        _o()
                        P = _b.plant
                        buf.append((P["velocities/p-rad_sec"], P["velocities/q-rad_sec"], P["aero/beta-rad"],
                                    P["accelerations/Nz"], P["fcs/aileron-cmd-norm"], P["fcs/elevator-cmd-norm"],
                                    P["fcs/rudder-cmd-norm"]))
                    blue.step_physics = sp
                    sp_log = []
                    lim = blue.limiter
                    orig_lim = lim.limit_omega_sp

                    def limit(omega_sp, v_fps, kcas, g_lift=0.0, _o=orig_lim, _l=sp_log):
                        out, fl = _o(omega_sp, v_fps, kcas, g_lift=g_lift)
                        _l.append((out[0], out[1]))
                        return out, fl
                    lim.limit_omega_sp = limit
                    res = Match(blue, red, duration_s=300.0, log_hz=0, wall_limit_s=3600, overtime_s=0.0).run()
            finally:
                os.chdir(cwd)
            a = np.asarray(buf)
            s = np.asarray(sp_log)
            n = min(len(a), len(s))
            a, s = a[:n], s[:n]
            jp, jq = [], []
            for st in range(0, n - WIN_TICKS + 1, WIN_TICKS):
                w = slice(st, st + WIN_TICKS)
                for col, spc, out in ((0, 0, jp), (1, 1, jq)):
                    sp_d = np.rad2deg(s[w, spc])
                    ac = np.rad2deg(a[w, col])
                    den = max(float(np.sqrt(np.mean(sp_d ** 2))), 2.0)
                    out.append(float(np.sqrt(np.mean((sp_d - ac) ** 2)) / den))
            rows.append({"scenario": scen, "gain": gain, "winner": res.winner, "condition": res.condition,
                         "time_s": round(res.time_s, 1), "hp_blue": round(res.hp_blue, 1), "hp_red": round(res.hp_red, 1),
                         "Jp_p50": pct(jp, 50), "Jp_p90": pct(jp, 90), "Jq_p50": pct(jq, 50), "Jq_p90": pct(jq, 90),
                         "nz_p50": pct(a[:, 3], 50), "nz_p95": pct(a[:, 3], 95),
                         "sat_pct": 100 * float(np.mean(np.abs(a[:, 4:7]) > 0.999)),
                         "beta_p95_deg": pct(np.abs(np.rad2deg(a[:, 2])), 95), "n_win": len(jp)})
    with open(os.path.join(out_dir, "case_studies.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    L = ["## 3. 사례 분석 3건 (개정 A11-1, A22-3) — 기술 통계, 인과 주장 없음\n",
         "- blue = doctrine_regulator (INDI 설정만 교체), red = red_prime, 솔트 battery-v1, 300 s.\n",
         "| 시나리오 | blue INDI | 승자 | 종료 | 시간 [s] | 체력 B/R | 1 s 창 J_p p50/p90 | 1 s 창 J_q p50/p90 | Nz p50/p95 | 포화 | \\|β\\| p95 |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['scenario']} | {r['gain']} | {r['winner']} | {r['condition']} | {r['time_s']} | "
                 f"{r['hp_blue']}/{r['hp_red']} | {r['Jp_p50']:.2f} / {r['Jp_p90']:.2f} | {r['Jq_p50']:.2f} / {r['Jq_p90']:.2f} | "
                 f"{r['nz_p50']:.2f} / {r['nz_p95']:.2f} | {r['sat_pct']:.1f}% | {r['beta_p95_deg']:.1f}° |")
    L.append("")
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--heatmap", action="store_true")
    ap.add_argument("--context", action="store_true")
    ap.add_argument("--case", action="store_true")
    args = ap.parse_args()
    from l3_indi.runner import git_state
    st = git_state()
    out_dir = os.path.join(REPO, "results", "paper", "bundle", st["commit"][:10])
    os.makedirs(out_dir, exist_ok=True)
    L = [f"# 분석 묶음 — 커밋 {st['commit'][:10]} (clean={st['clean']})\n",
         "규칙: 개정 A10-1, A11-1, A12, A22. 추가 시뮬레이션은 사례 분석 6경기뿐.\n"]
    if args.heatmap:
        L += heatmap(out_dir)
    if args.context:
        L += context(out_dir)
    if args.case:
        L += case(out_dir)
    rep = os.path.join(HERE, "reports", f"BUNDLE_{st['commit'][:10]}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
