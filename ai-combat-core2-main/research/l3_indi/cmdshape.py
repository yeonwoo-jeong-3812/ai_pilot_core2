"""개정 A17 — 명령 모양이 J 에 주는 영향 (사후 탐색 분석, 사전등록 외).

질문: 롤 J_p(0.38~0.68)가 피치 J_q(0.07~0.13)보다 큰 것이 축의 물리 한계인가, 명령 모양(짧은 펄스 vs 긴 계단)과 J 정규화 때문인가.

  [1] M2a 뱅크 목표를 상승시간 τ 램프로 바꾼 변형, τ ∈ {0, 0.1, 0.25, 0.5, 1.0} s
  [4] M1 Nz 목표를 같은 τ 램프로 바꾼 변형 (수준 0.7 / 0.8 / 0.9)
      둘 다 게인 {기준 (1,1,1), 튜닝 (1,1.5,0.5)}, filt 25 Hz, RQ1 9조건, FLCS on, 꼬리 5 s (A15)
  [3'] M2b (180 deg/s) τ = 0, 같은 게인·조건
  [2] 각 런의 J 를 과도/정상 구간으로 분해, [3] 순수 지연·가속도 한계 이상 응답 기준선 (분석 단계)
  개루프 최대 각가속도: 9조건 × {에일러론 +1, −1, 엘리베이터 −1} 1.0 s

사용: python research/l3_indi/cmdshape.py            실행 + 분석
      python research/l3_indi/cmdshape.py --analyze <results/paper/cmdshape/<commit10>>
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO, DT, TRUTH_COLS            # noqa: E402

TAUS = (0.0, 0.1, 0.25, 0.5, 1.0)
GAINS = {"base": (1.0, 1.0, 1.0), "tuned": (1.0, 1.5, 0.5)}
FILT = 25.0
DELAYS = (0.05, 0.10, 0.20)
K_ATT = 4.0
RATE_LIM_P_DPS = 180.0


# --------------------------------------------------------------------------------------
# 기동 변형
# --------------------------------------------------------------------------------------
def _ramp(t, t0, tau):
    """t0 에서 시작해 τ 동안 0→1 선형. τ = 0 이면 계단."""
    if t < t0:
        return 0.0
    if tau <= 0:
        return 1.0
    return min(1.0, (t - t0) / tau)


def make_maneuver(kind: str, tau: float, cap: dict, level: float = 0.8):
    from l3_indi.harness import gcmd
    from l3_indi.maneuvers import M1BankedCapture, M2aCappedReversal, M2RollReversal, TailHold, HOLD_S

    if kind in ("M2a", "M2b"):
        base = M2aCappedReversal(cap_p_dps=cap["C_p"]) if kind == "M2a" else M2RollReversal()
        b = np.deg2rad(base.bank_deg)

        class Ramped(type(base)):
            def command(self, t, k, st):
                if tau <= 0:
                    return type(base).command(self, t, k, st)
                target = b * _ramp(t, HOLD_S, tau) - 2 * b * _ramp(t, HOLD_S + 3.0, tau)
                nz = 1.0 / max(float(np.cos(st["phi"])), 0.2)
                g = gcmd(target - st["phi"], nz, st)
                if kind == "M2a":
                    g.dphi_cmd = float(np.clip(g.dphi_cmd, -self.dphi_max, self.dphi_max))
                return g

        kw = {"cap_p_dps": cap["C_p"]} if kind == "M2a" else {}
        return TailHold(Ramped(**kw), -base.bank_deg)

    base = M1BankedCapture(nz_target=level * cap["C_nz"])
    n0 = float(np.sqrt(2.0))                                   # 45° 수평 유지 Nz

    class RampedM1(M1BankedCapture):
        def command(self, t, k, st):
            if tau <= 0 or t < self.pull_start_s:
                return M1BankedCapture.command(self, t, k, st)
            nz = n0 + (self.nz_target - n0) * _ramp(t, self.pull_start_s, tau)
            return gcmd(np.deg2rad(self.bank_deg) - st["phi"], nz, st)

    return TailHold(RampedM1(nz_target=base.nz_target), 45.0)


# --------------------------------------------------------------------------------------
# 실행
# --------------------------------------------------------------------------------------
def jobs():
    from l3_indi.design import rq1_conditions
    out = []
    for cond in rq1_conditions(0):
        c = {"alt_ft": cond.alt_ft, "kcas": cond.kcas}
        for g in GAINS:
            for tau in TAUS:
                out.append(dict(c, exp="roll", kind="M2a", level=0.0, tau=tau, gain=g))
                for lv in (0.7, 0.8, 0.9):
                    out.append(dict(c, exp="pitch", kind="M1", level=lv, tau=tau, gain=g))
            out.append(dict(c, exp="roll_stress", kind="M2b", level=0.0, tau=0.0, gain=g))
        for surf, val in (("ail", 1.0), ("ail", -1.0), ("ele", -1.0)):
            out.append(dict(c, exp="openloop", kind=surf, level=val, tau=0.0, gain="-"))
    return out


def job_fn(job):
    from l3_indi.harness import build, run, Condition, Params
    from l3_indi.design import capability
    from l3_indi import metrics as M
    cond = Condition(job["alt_ft"], job["kcas"])
    if job["exp"] == "openloop":
        with contextlib.redirect_stdout(io.StringIO()):
            rig = build(cond)
        P = rig.plant
        u0 = list(P.get_input())
        acc = []
        for _ in range(int(round(1.0 / DT))):
            u = [1.0, u0[1], 0.0, 0.0]
            if job["kind"] == "ail":
                u[2] = job["level"]
            else:
                u[1] = job["level"]
            P.set_input(u)
            P.step(1)
            acc.append((P["accelerations/pdot-rad_sec2"], P["accelerations/qdot-rad_sec2"]))
        a = np.rad2deg(np.asarray(acc))
        return dict(job, pdot_max_dps2=float(np.max(np.abs(a[:, 0]))), qdot_max_dps2=float(np.max(np.abs(a[:, 1]))))
    cap = capability(cond)
    man = make_maneuver(job["kind"], job["tau"], cap, job["level"])
    with contextlib.redirect_stdout(io.StringIO()):
        rig = build(cond, Params(k_scale=GAINS[job["gain"]], filt_hz=FILT))
        ts = run(rig, man)
    w = man.window()
    row = dict(job)
    row["C_p"], row["C_nz"] = cap["C_p"], cap["C_nz"]
    row["J_p"] = M.tracking_J(ts, "p", w)
    row["J_q"] = M.tracking_J(ts, "q", w)
    row["oscillating"] = M.oscillation(ts, DT)["oscillating"]
    row["departure"] = M.departure(ts)
    row["capability_limited"] = M.capability_limited(ts, w, cap["C_p"])
    d = os.path.join(job["_out"], "ts")
    os.makedirs(d, exist_ok=True)
    fn = f"{job['exp']}_{int(job['alt_ft'])}_{int(job['kcas'])}_{job['kind']}_{job['level']:g}_{job['tau']:g}_{job['gain']}.npz"
    np.savez_compressed(os.path.join(d, fn), **{c: ts[c] for c in TRUTH_COLS})
    row["ts_file"] = fn
    return row


# --------------------------------------------------------------------------------------
# 분석 — [2] 구간 분해, [3] 기준선
# --------------------------------------------------------------------------------------
ONSET_MIN_DPS = 2.0


def segments(t, sp, w, onsets, window):
    """개정 A17-2: 각 onset t0 부터 |ω_sp| ≥ 2 dps 이고 sgn(ω_sp)·ω ≥ 0.9·|ω_sp| 인 첫 틱 전까지 = 과도. 다음 onset/창 끝에서 자름."""
    m = (t >= window[0] - 1e-9) & (t < window[1] - 1e-9)
    trans = np.zeros(len(t), bool)
    bounds = sorted(onsets) + [window[1]]
    for i, t0 in enumerate(sorted(onsets)):
        idx = np.nonzero((t >= t0 - 1e-9) & (t < bounds[i + 1] - 1e-9))[0]
        for k in idx:
            if abs(sp[k]) >= ONSET_MIN_DPS and np.sign(sp[k]) * w[k] >= 0.9 * abs(sp[k]):
                break
            trans[k] = True
    return m, trans & m


def delay_J(t, sp, window, d):
    """개정 A17-3a: 같은 명령을 d 초 늦춘 가상 응답의 J (명령 모양만의 효과)."""
    m = (t >= window[0] - 1e-9) & (t < window[1] - 1e-9)
    n = int(round(d / DT))
    shifted = np.concatenate([np.full(n, sp[0]), sp[:-n]]) if n > 0 else sp
    return float(np.sqrt(np.mean((sp[m] - shifted[m]) ** 2)) / max(np.sqrt(np.mean(sp[m] ** 2)), 2.0))


def effective_delay(t, sp, window, J):
    grid = np.arange(0, 0.5001, DT)
    vals = np.array([delay_J(t, sp, window, d) for d in grid])
    return float(grid[int(np.argmin(np.abs(vals - J)))])


def ideal_roll(kind, tau, cap, pdot_max_dps2, dur, window):
    """개정 A17-3b: 롤 운동학 이상 응답 — 같은 뱅크 목표·shim 식(60 Hz 영차 유지)·dphi 제한, |ṗ| ≤ 개루프 최대 롤 가속도."""
    from l3_indi.maneuvers import HOLD_S
    b = np.deg2rad(60.0)
    dmax = 2.0 * np.arcsin(min(np.deg2rad(0.8 * cap["C_p"]) / (2 * K_ATT), 1.0)) if kind == "M2a" else np.inf
    amax = np.deg2rad(pdot_max_dps2)
    n = int(round(dur / DT))
    phi = p = 0.0
    dphi = 0.0
    t = np.arange(n) * DT
    SP, P = np.zeros(n), np.zeros(n)
    for k in range(n):
        tk = t[k]
        if k % 2 == 0:
            if tau <= 0:
                target = 0.0 if tk < HOLD_S else (b if tk < HOLD_S + 3.0 else -b)
            else:
                target = b * _ramp(tk, HOLD_S, tau) - 2 * b * _ramp(tk, HOLD_S + 3.0, tau)
            if tk >= 7.0:
                target = -b
            dphi = float(np.clip(target - phi, -dmax, dmax))
        psp = float(np.clip(2 * K_ATT * np.sin(dphi / 2), -np.deg2rad(RATE_LIM_P_DPS), np.deg2rad(RATE_LIM_P_DPS)))
        p = p + float(np.clip(psp - p, -amax * DT, amax * DT))
        phi = phi + p * DT
        SP[k], P[k] = psp, p
    m = (t >= window[0] - 1e-9) & (t < window[1] - 1e-9)
    sp_d, p_d = np.rad2deg(SP[m]), np.rad2deg(P[m])
    return float(np.sqrt(np.mean((sp_d - p_d) ** 2)) / max(np.sqrt(np.mean(sp_d ** 2)), 2.0))


def ideal_follow(t, sp, window, rate_max_dps2):
    """개정 A17-3b: 피치 이상 응답 — 기록된 q_sp 를 |q̇| ≤ 개루프 최대 피치 가속도로 따라가는 가상 응답."""
    x = np.zeros_like(sp)
    x[0] = sp[0]
    for k in range(1, len(sp)):
        x[k] = x[k - 1] + np.clip(sp[k] - x[k - 1], -rate_max_dps2 * DT, rate_max_dps2 * DT)
    m = (t >= window[0] - 1e-9) & (t < window[1] - 1e-9)
    return float(np.sqrt(np.mean((sp[m] - x[m]) ** 2)) / max(np.sqrt(np.mean(sp[m] ** 2)), 2.0))


def analyze(run_dir: str):
    from l3_indi.design import capability
    from l3_indi.harness import Condition
    commit = os.path.basename(os.path.normpath(run_dir))
    rows = list(csv.DictReader(open(os.path.join(run_dir, "runs.csv"), encoding="utf-8")))
    for r in rows:
        for k in ("alt_ft", "kcas", "level", "tau"):
            r[k] = float(r[k])
    ol = {}
    for r in rows:
        if r["exp"] == "openloop":
            key = (r["alt_ft"], r["kcas"])
            d = ol.setdefault(key, {"pdot": [], "qdot": None})
            if r["kind"] == "ail":
                d["pdot"].append(float(r["pdot_max_dps2"]))
            else:
                d["qdot"] = float(r["qdot_max_dps2"])
    out = []
    for r in rows:
        if r["exp"] == "openloop":
            continue
        z = np.load(os.path.join(run_dir, "ts", r["ts_file"]))
        t = z["t"]
        ax = "p" if r["kind"].startswith("M2") else "q"
        sp, w = np.rad2deg(z["sp_" + ax]), np.rad2deg(z[ax])
        window = (1.0, 7.0) if ax == "p" else (3.0, 8.0)
        onsets = (1.0, 4.0) if ax == "p" else (3.0,)
        m, tr = segments(t, sp, w, onsets, window)
        e2 = (sp - w) ** 2
        den = max(np.sqrt(np.mean(sp[m] ** 2)), 2.0)
        J = float(np.sqrt(np.mean(e2[m])) / den)
        J_tr = float(np.sqrt(np.sum(e2[tr]) / m.sum()) / den)
        J_ss = float(np.sqrt(np.sum(e2[m & ~tr]) / m.sum()) / den)
        cond = Condition(r["alt_ft"], r["kcas"])
        cap = capability(cond)
        row = {k: r[k] for k in ("exp", "kind", "alt_ft", "kcas", "level", "tau", "gain")}
        row.update({"J": J, "J_reported": float(r["J_" + ax]), "J_tr": J_tr, "J_ss": J_ss,
                    "tr_err2_share": float(np.sum(e2[tr]) / np.sum(e2[m])) if np.sum(e2[m]) > 0 else float("nan"),
                    "tr_time_share": float(tr.sum() / m.sum()),
                    "eff_delay_s": effective_delay(t, sp, window, J),
                    "oscillating": int(r["oscillating"]), "departure": int(r["departure"])})
        for d in DELAYS:
            row[f"J_delay_{int(d*1000)}ms"] = delay_J(t, sp, window, d)
        if ax == "p":
            row["J_ideal_accel"] = ideal_roll(r["kind"], r["tau"], cap, min(ol[(r["alt_ft"], r["kcas"])]["pdot"]),
                                              float(t[-1] + DT), window)
        else:
            row["J_ideal_accel"] = ideal_follow(t, sp, window, ol[(r["alt_ft"], r["kcas"])]["qdot"])
        out.append(row)
    with open(os.path.join(run_dir, "analysis.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        wr.writeheader()
        wr.writerows(out)

    # RQ1 실행과의 일치 (τ = 0)
    rq1 = {}
    rq1_path = os.path.join(REPO, "results", "paper", "rq1", "c45f90998c", "runs.csv")
    for r in csv.DictReader(open(rq1_path, encoding="utf-8")):
        if r["fbw"] == "0" and float(r["filt"]) == 25.0 and float(r["kp"]) == 1.0 and float(r["kq"]) in (1.0, 1.5) \
                and float(r["kr"]) in (1.0, 0.5):
            g = "base" if (float(r["kq"]), float(r["kr"])) == (1.0, 1.0) else \
                "tuned" if (float(r["kq"]), float(r["kr"])) == (1.5, 0.5) else None
            if g:
                rq1[(float(r["alt_ft"]), float(r["kcas"]), r["man"], g)] = r
    match, total = 0, 0
    for r in rows:
        if r["exp"] == "openloop" or float(r["tau"]) != 0.0:
            continue
        man = r["kind"] if r["kind"].startswith("M2") else f"M1_{r['level']:g}"
        ref = rq1.get((r["alt_ft"], r["kcas"], man, r["gain"]))
        if ref is None:
            continue
        ax = "J_p" if man.startswith("M2") else "J_q"
        total += 1
        match += int(ref[ax] == r[ax])

    med = lambda sel, k: float(np.median([o[k] for o in out if sel(o)]))
    L = [f"# 명령 모양 분석 (개정 A17, 사후 탐색) — 실험 커밋 {commit}\n",
         "- FLCS on, filt 25 Hz, RQ1 9조건, 꼬리 5 s. 값은 9조건 중앙값. 규칙: `docs/PREREGISTRATION_AMENDMENTS.md` A17.",
         f"- **τ = 0 런의 J 가 RQ1 실행 c45f90998c 와 CSV 문자열까지 일치: {match} / {total}**\n"]
    L.append("## 개루프 최대 각가속도 (FLCS on, 1.0 s, 9조건)\n")
    pd_ = [min(v["pdot"]) for v in ol.values()]
    qd_ = [v["qdot"] for v in ol.values()]
    L.append(f"- 롤 |ṗ|max (±에일러론 중 작은 쪽): {min(pd_):.0f}~{max(pd_):.0f} deg/s², 피치 |q̇|max (풀 애프트): {min(qd_):.0f}~{max(qd_):.0f} deg/s²\n")
    for gain in GAINS:
        L.append(f"## 게인 {gain}\n")
        L.append("### [1] 롤 M2a: τ 에 따른 J_p, [2] 구간 분해, [3] 기준선\n")
        L.append("| τ [s] | J_p | J 과도 | J 정상 | 과도 오차² 비율 | 과도 시간 비율 | 등가 지연 [s] | J 지연 50/100/200 ms | J 가속도 한계 이상 |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for tau in TAUS:
            s = lambda o, tau=tau: o["kind"] == "M2a" and o["gain"] == gain and o["tau"] == tau
            L.append(f"| {tau:g} | {med(s,'J'):.3f} | {med(s,'J_tr'):.3f} | {med(s,'J_ss'):.3f} | {100*med(s,'tr_err2_share'):.0f}% | "
                     f"{100*med(s,'tr_time_share'):.0f}% | {med(s,'eff_delay_s'):.3f} | {med(s,'J_delay_50ms'):.3f} / "
                     f"{med(s,'J_delay_100ms'):.3f} / {med(s,'J_delay_200ms'):.3f} | {med(s,'J_ideal_accel'):.3f} |")
        s = lambda o: o["kind"] == "M2b" and o["gain"] == gain
        L.append(f"| M2b (τ 0) | {med(s,'J'):.3f} | {med(s,'J_tr'):.3f} | {med(s,'J_ss'):.3f} | {100*med(s,'tr_err2_share'):.0f}% | "
                 f"{100*med(s,'tr_time_share'):.0f}% | {med(s,'eff_delay_s'):.3f} | {med(s,'J_delay_50ms'):.3f} / "
                 f"{med(s,'J_delay_100ms'):.3f} / {med(s,'J_delay_200ms'):.3f} | {med(s,'J_ideal_accel'):.3f} |")
        L.append("\n### [4] 피치 M1 (수준 0.7·0.8·0.9 통합): τ 에 따른 J_q, 구간 분해, 기준선\n")
        L.append("| τ [s] | J_q | J 과도 | J 정상 | 과도 오차² 비율 | 과도 시간 비율 | 등가 지연 [s] | J 지연 50/100/200 ms | J 가속도 한계 이상 |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for tau in TAUS:
            s = lambda o, tau=tau: o["kind"] == "M1" and o["gain"] == gain and o["tau"] == tau
            L.append(f"| {tau:g} | {med(s,'J'):.3f} | {med(s,'J_tr'):.3f} | {med(s,'J_ss'):.3f} | {100*med(s,'tr_err2_share'):.0f}% | "
                     f"{100*med(s,'tr_time_share'):.0f}% | {med(s,'eff_delay_s'):.3f} | {med(s,'J_delay_50ms'):.3f} / "
                     f"{med(s,'J_delay_100ms'):.3f} / {med(s,'J_delay_200ms'):.3f} | {med(s,'J_ideal_accel'):.3f} |")
        L.append("")
    L.append("## 단조성 (조건별 τ 0 → 1.0 에서 J 가 매 단계 감소한 조건 수)\n")
    for kind in ("M2a", "M1"):
        for gain in GAINS:
            n_mono, n_tot = 0, 0
            keys = {(o["alt_ft"], o["kcas"], o["level"]) for o in out if o["kind"] == kind and o["gain"] == gain}
            for key in keys:
                seq = [next(o["J"] for o in out if o["kind"] == kind and o["gain"] == gain and o["tau"] == tau
                            and (o["alt_ft"], o["kcas"], o["level"]) == key) for tau in TAUS]
                n_tot += 1
                n_mono += int(all(b < a for a, b in zip(seq, seq[1:])))
            L.append(f"- {kind} · {gain}: {n_mono} / {n_tot}")
    L.append(f"\n- 불안정·이탈 런: 진동 {sum(o['oscillating'] for o in out)}, 이탈 {sum(o['departure'] for o in out)} / {len(out)}")
    rep = os.path.join(HERE, "reports", f"CMDSHAPE_{commit}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", rep)


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--analyze":
        analyze(sys.argv[2])
        return 0
    from l3_indi.runner import run_experiment, git_state
    out_dir = os.path.join(REPO, "results", "paper", "cmdshape", git_state()["commit"][:10])
    js = jobs()
    for j in js:
        j["_out"] = out_dir
    out = run_experiment("cmdshape", js, job_fn, os.path.join(REPO, "results", "paper"))
    print("->", out)
    analyze(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
