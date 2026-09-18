"""RQ3 준비 확인 — 개정 A23.

  --stability  RQ3 후보 설정 5종 × RQ1 9조건 × 주 기동 6 × FLCS on (270 런), S2 기준 3구간 판정
  --roll       롤 성능 제한 원인 진단 (M2a·M2b 36 런 + shim 220 변형 18 런)

사용: python research/l3_indi/rq3_prep.py --stability --roll
출력: results/paper/rq3_prep/<commit10>/ + research/l3_indi/reports/RQ3PREP_<commit10>.md
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO, DT            # noqa: E402

SETTINGS = {"S1p": ((1.0, 1.0, 1.0), 25.0, 10.0), "S2": ((1.0, 1.0, 1.0), 25.0, 1.0),
            "S3": ((1.0, 1.5, 0.5), 15.0, 1.0), "S4": ((1.0, 1.0, 1.0), 25.0, 4.0),
            "S5": ((1.0, 1.0, 1.0), 25.0, 25.0)}
MANS = ("M1_0.7", "M1_0.8", "M1_0.9", "M2a", "M3_0.7", "M3_0.9")
RQ1_CSV = os.path.join(REPO, "results", "paper", "rq1", "c45f90998c", "runs.csv")
AIL_RATE = 2.0 / 0.3            # f16.xml fcs/aileron-position: 전 행정 0.3 s


def pct(a, q):
    a = np.asarray([x for x in a if np.isfinite(x)], float)
    return float(np.percentile(a, q)) if len(a) else float("nan")


# --------------------------------------------------------------------------------------
def stab_job(job):
    from l3_indi.evaluate import evaluate
    return evaluate(job)


def stability(out_dir: str) -> list[str]:
    from l3_indi.design import rq1_conditions
    from l3_indi.runner import run_experiment
    from l3_indi import metrics as M
    from l3_indi.rq1_analysis import band_keys, exclusion, fnum
    jobs = []
    for cond in rq1_conditions(0):
        for man in MANS:
            for s, (k, f, lq) in SETTINGS.items():
                jobs.append({"fbw": 0, "alt_ft": cond.alt_ft, "kcas": cond.kcas, "man": man, "setting": s,
                             "kp": k[0], "kq": k[1], "kr": k[2], "filt": f, "lam_q": lq})
    d = run_experiment("rq3_prep_stability", jobs, stab_job, os.path.join(REPO, "results", "paper"))
    rows = list(csv.DictReader(open(os.path.join(d, "runs.csv"), encoding="utf-8")))
    for r in rows:
        for k, v in list(r.items()):
            if k not in ("man", "setting", "osc_freq_axis"):
                r[k] = fnum(v)
    ref = {(r["alt_ft"], r["kcas"], r["man"]): r for r in rows if r["setting"] == "S2"}
    for r in rows:
        r["excluded"] = exclusion(r)
        b = ref[(r["alt_ft"], r["kcas"], r["man"])]
        rho = []
        for k in band_keys(r["man"]):
            if k.startswith("J_"):
                rho.append(r[k] / b[k] if b[k] > 0 else float("inf"))
            else:
                rho.append(M.floored_ratio(k, r[k], b[k]))
        if r["oscillating"] >= 1 or r["g_exceeded"] >= 1 or r["departure"] >= 1:
            r["band"] = "unstable"
        elif any(v != v for v in rho):
            r["band"] = "no_ref"
        elif max(rho) > 1.5:
            r["band"] = "degraded"
        else:
            r["band"] = "stable"
        r["rho_max"] = max(rho) if rho else float("nan")
    # RQ1 일치 확인 (S2, S3)
    rq1 = {}
    for r in csv.DictReader(open(RQ1_CSV, encoding="utf-8")):
        if r["fbw"] == "0":
            rq1[(float(r["alt_ft"]), float(r["kcas"]), r["man"], float(r["kp"]), float(r["kq"]), float(r["kr"]),
                 float(r["filt"]))] = r
    raw = {(float(r["alt_ft"]), float(r["kcas"]), r["man"], r["setting"]): r
           for r in csv.DictReader(open(os.path.join(d, "runs.csv"), encoding="utf-8"))}
    match = total = 0
    for (a, c, m, s), r in raw.items():
        if s in ("S2", "S3"):
            k, f, _ = SETTINGS[s]
            o = rq1.get((a, c, m, k[0], k[1], k[2], f))
            if o:
                total += 1
                match += int(o["J_q"] == r["J_q"] and o["J_p"] == r["J_p"])
    with open(os.path.join(out_dir, "stability.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader()
        w.writerows(rows)
    L = ["## 1. RQ3 후보 설정 안정성 (A23-1)\n",
         f"- 실행 `{os.path.relpath(d, REPO)}`, 270 런, FLCS on. 3구간 기준 = 같은 조건·기동의 S2 런.",
         f"- S2·S3 의 J 가 RQ1 실행(c45f90998c)과 CSV 문자열까지 일치: **{match} / {total}**\n",
         "| 설정 | 구성 | 안정 | 열화 | 불안정 | 제외 (사유) | 열화 블록의 최대 ρ 항 |", "|---|---|---|---|---|---|---|"]
    for s, (k, f, lq) in SETTINGS.items():
        R = [r for r in rows if r["setting"] == s]
        c = lambda b: sum(1 for r in R if r["band"] == b and not r["excluded"])
        exc = {}
        for r in R:
            if r["excluded"]:
                exc[r["excluded"]] = exc.get(r["excluded"], 0) + 1
        deg = [r for r in R if r["band"] == "degraded" and not r["excluded"]]
        worst = ""
        if deg:
            worst = f"ρ 최대 {max(r['rho_max'] for r in deg):.2f} ({', '.join(sorted({r['man'] for r in deg}))})"
        L.append(f"| {s} | k {k}, {f:g} Hz, λ_q {lq:g} | {c('stable')} | {c('degraded')} | {c('unstable')} | "
                 f"{sum(exc.values())} {exc if exc else ''} | {worst} |")
    L.append("\n### 조건별 M1_0.8 J_q (FLCS on)\n")
    L.append("| 조건 | " + " | ".join(SETTINGS) + " | 최대/최소 |")
    L.append("|---|" + "---|" * (len(SETTINGS) + 1))
    allv = {s: [] for s in SETTINGS}
    for a, c in sorted({(r["alt_ft"], r["kcas"]) for r in rows}):
        v = {s: next(r for r in rows if r["setting"] == s and r["alt_ft"] == a and r["kcas"] == c and r["man"] == "M1_0.8")
             for s in SETTINGS}
        for s in SETTINGS:
            allv[s].append(v[s]["J_q"])
        mark = lambda r: "" if (r["band"] == "stable" and not r["excluded"]) else ("*" if not r["excluded"] else "x")
        js = [v[s]["J_q"] for s in SETTINGS]
        L.append(f"| {int(a/1000)}k/{int(c)} | " + " | ".join(f"{v[s]['J_q']:.3f}{mark(v[s])}" for s in SETTINGS) +
                 f" | {max(js)/min(js):.2f} |")
    L.append("\n(\\* = S2 대비 열화 또는 불안정, x = 제외)\n")
    L.append("### 설정별 M1_0.8 J_q 범위 (9조건)\n")
    L.append("| 설정 | 최소 | 중앙 | 최대 | S3 대비 배율 (중앙) |")
    L.append("|---|---|---|---|---|")
    s3 = float(np.median(allv["S3"]))
    for s in SETTINGS:
        L.append(f"| {s} | {min(allv[s]):.3f} | {np.median(allv[s]):.3f} | {max(allv[s]):.3f} | {np.median(allv[s])/s3:.2f} |")
    L.append("")
    return L


# --------------------------------------------------------------------------------------
EXTRA = ("velocities/mach", "fcs/roll-rate-command", "fcs/left-aileron-pos-norm",
         "fcs/aileron-speed-compensated", "fcs/aileron-cmd-norm", "velocities/p-rad_sec")


def roll_job(job):
    from l3_indi.harness import build, run, Condition, Params
    from l3_indi.design import capability
    from l3_indi.evaluate import maneuver_by_name, M2_REVERSAL
    from l3_indi import metrics as M
    cond = Condition(job["alt_ft"], job["kcas"], fbw_override=job["fbw"])
    cap = capability(cond)
    man = maneuver_by_name(job["man"], cap)
    with contextlib.redirect_stdout(io.StringIO()):
        rig = build(cond, Params())
    if job["shim_p_dps"] != 180.0:
        rig.pilot.shim.rate_limit[0] = np.deg2rad(job["shim_p_dps"])
    buf = []
    orig = rig.pilot.step_physics

    def sp(_o=orig, _P=rig.plant, _b=buf):
        _o()
        _b.append(tuple(_P[p] for p in EXTRA))
    rig.pilot.step_physics = sp
    with contextlib.redirect_stdout(io.StringIO()):
        ts = run(rig, man)
    x = np.asarray(buf)
    w = man.window()
    m = M.window_mask(ts, w)
    psp = np.abs(np.rad2deg(ts["sp_p"][m]))
    p = np.rad2deg(x[m, 5])
    pos = x[:, 2]
    rate = np.abs(np.diff(pos, prepend=pos[0])) / DT
    b = M.bank_metrics(ts, M2_REVERSAL[0], M2_REVERSAL[1], M2_REVERSAL[2])
    row = dict(job, C_p=cap["C_p"], J_p=M.tracking_J(ts, "p", w),
               bank_reach_s=b["bank_reach_s"], p_peak_dps=float(np.max(np.abs(p))),
               cmd_over_cap_p50=pct(psp / cap["C_p"], 50), cmd_over_cap_p90=pct(psp / cap["C_p"], 90),
               frac_cmd_over_cap=float(np.mean(psp > cap["C_p"])), frac_cmd_over_095cap=float(np.mean(psp > 0.95 * cap["C_p"])),
               frac_shim_cap=float(np.mean(psp >= job["shim_p_dps"] - 0.1)),
               frac_limiter=float(np.mean(ts["p_lim"][m] > 0.5)),
               mach_med=pct(x[m, 0], 50),
               sat_cmd=float(np.mean(np.abs(x[m, 4]) > 0.999)),
               sat_flcs_out=float(np.mean(np.abs(x[m, 1]) > 0.999)),
               sat_actuator=float(np.mean(np.abs(x[m, 2]) > 0.999)),
               frac_actuator_rate=float(np.mean(rate[m] >= 0.99 * AIL_RATE)),
               speedcomp_gain_med=pct((np.abs(x[m, 3]) / np.abs(x[m, 2]))[np.abs(x[m, 2]) > 0.05], 50),
               eff_deflection_p90=pct(np.abs(x[m, 3]), 90),
               eff_deflection_max=float(np.max(np.abs(x[m, 3]))))
    return row


def roll(out_dir: str) -> list[str]:
    from l3_indi.design import rq1_conditions, capability
    from l3_indi.runner import run_experiment
    jobs = []
    for fbw in (0, 1):
        for cond in rq1_conditions(fbw):
            for man in ("M2a", "M2b"):
                jobs.append({"fbw": fbw, "alt_ft": cond.alt_ft, "kcas": cond.kcas, "man": man, "shim_p_dps": 180.0})
            jobs.append({"fbw": fbw, "alt_ft": cond.alt_ft, "kcas": cond.kcas, "man": "M2b", "shim_p_dps": 220.0})
    d = run_experiment("rq3_prep_roll", jobs, roll_job, os.path.join(REPO, "results", "paper"))
    rows = list(csv.DictReader(open(os.path.join(d, "runs.csv"), encoding="utf-8")))
    for r in rows:
        for k, v in list(r.items()):
            if k != "man":
                r[k] = float(v)
    FL = {0.0: "on", 1.0: "off"}
    L = ["## 2. 롤 성능 제한 원인 (A23-2)\n", f"- 진단 실행 `{os.path.relpath(d, REPO)}`, 54 런, 기준 게인, 창 = 기동 창 [1, 7) s.\n"]
    med = lambda sel, k: pct([r[k] for r in rows if sel(r)], 50)
    rng = lambda sel, k: (pct([r[k] for r in rows if sel(r)], 0), pct([r[k] for r in rows if sel(r)], 100))
    L.append("### (1) 명령 대비 능력 — |p_sp| / C_p (9조건 중앙값, 범위)\n")
    L.append("| 기동 | FLCS | 비 p50 | 비 p90 | C_p 초과 시간 | 0.95·C_p 초과 시간 |")
    L.append("|---|---|---|---|---|---|")
    for man in ("M2a", "M2b"):
        for fbw in (0.0, 1.0):
            s = lambda r, man=man, fbw=fbw: r["man"] == man and r["fbw"] == fbw and r["shim_p_dps"] == 180.0
            lo, hi = rng(s, "frac_cmd_over_cap")
            L.append(f"| {man} | {FL[fbw]} | {med(s,'cmd_over_cap_p50'):.2f} | {med(s,'cmd_over_cap_p90'):.2f} | "
                     f"{100*med(s,'frac_cmd_over_cap'):.0f}% ({100*lo:.0f}~{100*hi:.0f}%) | {100*med(s,'frac_cmd_over_095cap'):.0f}% |")
    L.append("\n### (3) 이중 상한 — shim 180 deg/s vs 리미터 220 deg/s\n")
    L.append("| 기동 | FLCS | shim 상한에 걸린 시간 | 리미터 p_limited 시간 |")
    L.append("|---|---|---|---|")
    for man in ("M2a", "M2b"):
        for fbw in (0.0, 1.0):
            s = lambda r, man=man, fbw=fbw: r["man"] == man and r["fbw"] == fbw and r["shim_p_dps"] == 180.0
            L.append(f"| {man} | {FL[fbw]} | {100*med(s,'frac_shim_cap'):.0f}% | {100*med(s,'frac_limiter'):.1f}% |")
    L.append("\n**shim 롤 상한 180 → 220 deg/s (M2b, 하네스 주입)** — 9조건 중앙값\n")
    L.append("| FLCS | 최대 실제 롤율 180 → 220 | 반전 뱅크 도달시간 [s] 180 → 220 | J_p 180 → 220 | C_p 중앙값 |")
    L.append("|---|---|---|---|---|")
    for fbw in (0.0, 1.0):
        a = lambda r, fbw=fbw: r["man"] == "M2b" and r["fbw"] == fbw and r["shim_p_dps"] == 180.0
        b = lambda r, fbw=fbw: r["man"] == "M2b" and r["fbw"] == fbw and r["shim_p_dps"] == 220.0
        L.append(f"| {FL[fbw]} | {med(a,'p_peak_dps'):.1f} → {med(b,'p_peak_dps'):.1f} | {med(a,'bank_reach_s'):.2f} → {med(b,'bank_reach_s'):.2f} | "
                 f"{med(a,'J_p'):.3f} → {med(b,'J_p'):.3f} | {med(a,'C_p'):.0f} |")
    L.append("\n### (4) 조종면 경로별 포화 (9조건 중앙값)\n")
    L.append("| 기동 | FLCS | 마하 | INDI 명령 포화 | FLCS 출력 포화 | 구동기 위치 포화 | 구동기 속도 포화 | 마하 보상 계수 | 실효 편각 p90 / 최대 (1 = 21.5°) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for man in ("M2a", "M2b"):
        for fbw in (0.0, 1.0):
            s = lambda r, man=man, fbw=fbw: r["man"] == man and r["fbw"] == fbw and r["shim_p_dps"] == 180.0
            L.append(f"| {man} | {FL[fbw]} | {med(s,'mach_med'):.2f} | {100*med(s,'sat_cmd'):.0f}% | {100*med(s,'sat_flcs_out'):.0f}% | "
                     f"{100*med(s,'sat_actuator'):.0f}% | {100*med(s,'frac_actuator_rate'):.0f}% | {med(s,'speedcomp_gain_med'):.2f} | "
                     f"{med(s,'eff_deflection_p90'):.2f} / {med(s,'eff_deflection_max'):.2f} |")
    L.append("\n### 조건별 상세 (M2b, FLCS on, shim 180)\n")
    L.append("| 조건 | 마하 | C_p | 최대 롤율 | 마하 보상 계수 | 실효 편각 최대 | 구동기 위치 포화 | 구동기 속도 포화 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in sorted((r for r in rows if r["man"] == "M2b" and r["fbw"] == 0.0 and r["shim_p_dps"] == 180.0),
                    key=lambda r: (r["alt_ft"], r["kcas"])):
        L.append(f"| {int(r['alt_ft']/1000)}k/{int(r['kcas'])} | {r['mach_med']:.2f} | {r['C_p']:.0f} | {r['p_peak_dps']:.0f} | "
                 f"{r['speedcomp_gain_med']:.2f} | {r['eff_deflection_max']:.2f} | {100*r['sat_actuator']:.0f}% | {100*r['frac_actuator_rate']:.0f}% |")
    L.append("")
    with open(os.path.join(out_dir, "roll_diag.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stability", action="store_true")
    ap.add_argument("--roll", action="store_true")
    args = ap.parse_args()
    from l3_indi.runner import git_state
    st = git_state()
    out_dir = os.path.join(REPO, "results", "paper", "rq3_prep", st["commit"][:10])
    os.makedirs(out_dir, exist_ok=True)
    L = [f"# RQ3 준비 확인 — 커밋 {st['commit'][:10]}\n", "규칙: 개정 A23.\n"]
    if args.stability:
        L += stability(out_dir)
    if args.roll:
        L += roll(out_dir)
    rep = os.path.join(HERE, "reports", f"RQ3PREP_{st['commit'][:10]}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
