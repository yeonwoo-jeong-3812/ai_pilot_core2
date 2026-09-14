"""실전 기동 분류와 합성 기동 대표성 판정 — 개정 A7 을 그대로 구현한다.

사용: python research/l3_indi/taxonomy.py <traces_dir> <capability_csv>
출력: results/paper/taxonomy/<commit10>/events.csv, ticks_summary.json
      research/l3_indi/reports/P2_maneuvers_<commit10>.md
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from l3_indi.harness import REPO, DT, G_FT_S2   # noqa: E402

ROLL_THR_DPS = 30.0
PULL_THR_G = 2.5
MERGE_S = 0.25
ROLL_MIN_S = 0.25
PULL_MIN_S = 0.5
REV_MIN_BANK_DEG = 20.0
RP_WIN = (-0.5, 1.0)
RP_MIN_DPHI_DEG = 30.0
UNLOAD_G = 0.5
LABELS = ("roll_reversal", "rolling_pull", "g_capture", "roll_other", "unload", "low_g")

# 합성 기동 매개변수 (PREREGISTRATION §5, A7 R2)
SYNTH = {
    "M1": {"nz_frac": (0.4, 0.6, 0.8), "duration_s": (5.0,), "bank_abs_deg": (0.0,)},
    "M2": {"dphi_abs_deg": (120.0,), "peak_psp_dps": (180.0,), "dwell_s": (3.0,), "ncmd": (2.0,)},
    "M3": {"dphi_abs_deg": (70.0,), "nz_frac": (0.6, 0.8), "duration_s": (6.0,)},
}


# --------------------------------------------------------------------------------------
def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """True 연속 구간 [s, e) 목록."""
    m = np.concatenate(([False], mask.astype(bool), [False]))
    d = np.diff(m.astype(int))
    return list(zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]))


def events(mask: np.ndarray, merge_s: float, min_s: float) -> list[tuple[int, int]]:
    r = runs(mask)
    merged = []
    for s, e in r:
        if merged and s - merged[-1][1] <= int(round(merge_s / DT)):
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return [(s, e) for s, e in merged if (e - s) * DT >= min_s - 1e-9]


def wrap_deg(x):
    return (np.asarray(x) + 180.0) % 360.0 - 180.0


class Capability:
    """능력표 쌍선형 보간 (FLCS on). 격자 밖은 가장자리로 고정하고 표시."""

    def __init__(self, path: str, fbw: int = 0):
        rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if int(r["fbw_override"]) == fbw]
        self.alts = np.array(sorted({float(r["alt_kft"]) for r in rows}))
        self.kcas = np.array(sorted({float(r["kcas"]) for r in rows}))
        self.cnz = np.full((len(self.alts), len(self.kcas)), np.nan)
        self.valid = np.zeros_like(self.cnz, bool)
        for r in rows:
            i = int(np.searchsorted(self.alts, float(r["alt_kft"])))
            j = int(np.searchsorted(self.kcas, float(r["kcas"])))
            self.cnz[i, j] = float(r["C_nz"])
            self.valid[i, j] = r["trim_valid"] in ("1", "1.0", "True")

    def c_nz(self, alt_ft: float, kcas: float) -> tuple[float, bool]:
        a, k = alt_ft / 1000.0, kcas
        inside = self.alts[0] <= a <= self.alts[-1] and self.kcas[0] <= k <= self.kcas[-1]
        a = float(np.clip(a, self.alts[0], self.alts[-1]))
        k = float(np.clip(k, self.kcas[0], self.kcas[-1]))
        i = int(np.clip(np.searchsorted(self.alts, a) - 1, 0, len(self.alts) - 2))
        j = int(np.clip(np.searchsorted(self.kcas, k) - 1, 0, len(self.kcas) - 2))
        ta = (a - self.alts[i]) / (self.alts[i + 1] - self.alts[i])
        tk = (k - self.kcas[j]) / (self.kcas[j + 1] - self.kcas[j])
        c = self.cnz
        v = ((1 - ta) * (1 - tk) * c[i, j] + ta * (1 - tk) * c[i + 1, j]
             + (1 - ta) * tk * c[i, j + 1] + ta * tk * c[i + 1, j + 1])
        return float(v), bool(inside)


def band95(x: np.ndarray) -> float:
    x = np.asarray(x, float) - np.mean(x)
    if len(x) < 16 or np.allclose(x, 0):
        return float("nan")
    F = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), DT)
    c = np.cumsum(F) / F.sum()
    return float(f[int(np.searchsorted(c, 0.95))])


# --------------------------------------------------------------------------------------
def classify_side(z, side: str, cap: Capability, roll_thr=ROLL_THR_DPS, pull_thr=PULL_THR_G):
    g = lambda c: np.asarray(z[f"{side}__{c}"], float)
    psp = np.rad2deg(g("sp_p"))
    phi = np.rad2deg(g("phi"))
    theta = g("theta")
    ncmd = g("sp_q") * g("vt") / G_FT_S2 + np.cos(np.deg2rad(phi)) * np.cos(theta)
    n = len(psp)
    rolls = events(np.abs(psp) >= roll_thr, MERGE_S, ROLL_MIN_S)
    pulls = events(ncmd >= pull_thr, MERGE_S, PULL_MIN_S)
    roll_info = []
    for idx, (s, e) in enumerate(rolls):
        seg = np.unwrap(np.deg2rad(phi[s:e]))
        dphi = float(np.rad2deg(seg[-1] - seg[0]))
        p0, p1 = wrap_deg(phi[s]), wrap_deg(phi[e - 1])
        rev = bool(abs(p0) >= REV_MIN_BANK_DEG and abs(p1) >= REV_MIN_BANK_DEG and np.sign(p0) != np.sign(p1))
        nxt = rolls[idx + 1][0] if idx + 1 < len(rolls) else n
        roll_info.append({"s": s, "e": e, "dphi": dphi, "rev": rev, "dwell_s": (nxt - e) * DT})

    ev = []
    masks = {L: np.zeros(n, bool) for L in LABELS}
    masks["unload"] = ncmd < UNLOAD_G
    attached_all = set()
    for s, e in pulls:
        w0, w1 = s + int(round(RP_WIN[0] / DT)), s + int(round(RP_WIN[1] / DT))
        attached = [i for i, r in enumerate(roll_info)
                    if r["s"] < w1 and r["e"] > w0 and abs(r["dphi"]) >= RP_MIN_DPHI_DEG]
        kind = "rolling_pull" if attached else "g_capture"
        masks[kind][s:e] = True
        for i in attached:
            if not roll_info[i]["rev"]:
                masks["rolling_pull"][roll_info[i]["s"]:roll_info[i]["e"]] = True   # 롤링 풀의 롤 구간
        attached_all.update(attached)
        plateau = float(np.median(ncmd[s:e]))
        base = float(ncmd[max(s - int(round(0.5 / DT)), 0)])
        seg = ncmd[s:e]
        i10 = np.nonzero(seg >= base + 0.1 * (plateau - base))[0]
        i90 = np.nonzero(seg >= base + 0.9 * (plateau - base))[0]
        rise = float((i90[0] - i10[0]) * DT) if len(i10) and len(i90) else float("nan")
        c, inside = cap.c_nz(float(g("alt")[s]), float(g("kcas")[s]))
        ev.append({"side": side, "type": kind, "t0": s * DT, "duration_s": (e - s) * DT,
                   "ncmd_median": plateau, "nz_frac": plateau / c if c > 0 else float("nan"),
                   "cap_inside_grid": int(inside), "C_nz": c,
                   "bank_abs_median_deg": float(np.median(np.abs(wrap_deg(phi[s:e])))),
                   "dphi_abs_deg": float(max((abs(roll_info[i]["dphi"]) for i in attached), default=np.nan)),
                   "rise_10_90_s": rise, "alt_ft": float(g("alt")[s]), "kcas": float(g("kcas")[s]),
                   "peak_psp_dps": float("nan"), "dwell_s": float("nan")})
    for i, r in enumerate(roll_info):
        s, e = r["s"], r["e"]
        if r["rev"]:
            kind = "roll_reversal"
            masks["roll_reversal"][s:e] = True
        elif i in attached_all:
            kind = "rolling_pull_roll"
        else:
            kind = "roll_other"
            masks["roll_other"][s:e] = True
        ev.append({"side": side, "type": kind, "t0": s * DT, "duration_s": (e - s) * DT,
                   "ncmd_median": float(np.median(ncmd[s:e])), "nz_frac": float("nan"),
                   "cap_inside_grid": 1, "C_nz": float("nan"),
                   "bank_abs_median_deg": float(np.median(np.abs(wrap_deg(phi[s:e])))),
                   "dphi_abs_deg": abs(r["dphi"]), "rise_10_90_s": float("nan"),
                   "alt_ft": float(g("alt")[s]), "kcas": float(g("kcas")[s]),
                   "peak_psp_dps": float(np.max(np.abs(psp[s:e]))), "dwell_s": r["dwell_s"]})
    # 우선순위(A7): roll_reversal > rolling_pull > g_capture > roll_other > unload > low_g
    lab = np.full(n, "low_g", dtype=object)
    for L in ("unload", "roll_other", "g_capture", "rolling_pull", "roll_reversal"):
        lab[masks[L]] = L
    extra = {"alt": g("alt"), "kcas": g("kcas"), "psp_band": band95(psp),
             "qsp_band": band95(np.rad2deg(g("sp_q")))}
    return lab, ev, extra


def pct(a, q):
    a = np.asarray([x for x in a if np.isfinite(x)], float)
    return float(np.percentile(a, q)) if len(a) else float("nan")


def main():
    traces_dir, cap_csv = sys.argv[1], sys.argv[2]
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from l3_indi.runner import git_state
    commit = git_state()["commit"][:10]
    cap = Capability(cap_csv)
    files = sorted(glob.glob(os.path.join(traces_dir, "npz", "*.npz")))
    all_ev, time_by = [], {}
    sens = {}
    alts, kcass, bands = [], [], {"psp": [], "qsp": []}
    for fp in files:
        z = np.load(fp)
        meta = json.loads(str(z["meta"]))
        for side, role in (("blue", "participant"), ("red", "red")):
            lab, ev, extra = classify_side(z, side, cap)
            for e in ev:
                e.update({"match_id": meta["match_id"], "role": role, "scenario": meta["scenario"]})
            all_ev.extend(ev)
            for key in (role, "all", f"scen:{meta['scenario']}"):
                d = time_by.setdefault(key, {L: 0 for L in LABELS})
                for L in LABELS:
                    d[L] += int(np.sum(lab == L))
            man = lab != "low_g"
            alts.extend(extra["alt"][man][::12]); kcass.extend(extra["kcas"][man][::12])
            bands["psp"].append(extra["psp_band"]); bands["qsp"].append(extra["qsp_band"])
            for rt in (20.0, 45.0):
                l2, _, _ = classify_side(z, side, cap, roll_thr=rt)
                d = sens.setdefault(f"roll_thr={rt:g}", {L: 0 for L in LABELS})
                for L in LABELS:
                    d[L] += int(np.sum(l2 == L))
            for pt in (2.0, 3.0):
                l2, _, _ = classify_side(z, side, cap, pull_thr=pt)
                d = sens.setdefault(f"pull_thr={pt:g}", {L: 0 for L in LABELS})
                for L in LABELS:
                    d[L] += int(np.sum(l2 == L))

    out = os.path.join(REPO, "results", "paper", "taxonomy", commit)
    os.makedirs(out, exist_ok=True)
    keys = list(all_ev[0].keys())
    with open(os.path.join(out, "events.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(all_ev)

    def frac_table(d):
        tot = sum(d.values()); man = tot - d["low_g"]
        return {L: (d[L] / tot, (d[L] / man if L != "low_g" and man else float("nan"))) for L in LABELS}, tot * DT, man * DT

    minutes = sum(v for v in time_by["all"].values()) * DT / 60.0
    by = lambda t: [e for e in all_ev if e["type"] == t]
    rep = {"n_matches": len(files), "minutes_all_sides": minutes, "time": {}, "sensitivity": {},
           "events": {}, "envelope": {}, "bandwidth": {}, "R1": {}, "R2": {}}
    for k, d in time_by.items():
        rep["time"][k] = frac_table(d)
    for k, d in sens.items():
        rep["sensitivity"][k] = frac_table(d)
    stats_spec = {"roll_reversal": ("duration_s", "dphi_abs_deg", "peak_psp_dps", "ncmd_median", "dwell_s"),
                  "g_capture": ("duration_s", "ncmd_median", "nz_frac", "bank_abs_median_deg", "rise_10_90_s"),
                  "rolling_pull": ("duration_s", "dphi_abs_deg", "ncmd_median", "nz_frac", "rise_10_90_s"),
                  "roll_other": ("duration_s", "dphi_abs_deg", "peak_psp_dps")}
    for t, fields in stats_spec.items():
        E = by(t)
        rep["events"][t] = {"count": len(E), "per_min": len(E) / minutes,
                            **{f: (pct([e[f] for e in E], 10), pct([e[f] for e in E], 50), pct([e[f] for e in E], 90))
                               for f in fields}}
    rep["envelope"] = {"alt_ft": [pct(alts, q) for q in (5, 10, 50, 90, 95)],
                       "kcas": [pct(kcass, q) for q in (5, 10, 50, 90, 95)]}
    rep["bandwidth"] = {k: (pct(v, 10), pct(v, 50), pct(v, 90)) for k, v in bands.items()}
    all_t = rep["time"]["all"][0]
    covered = sum(all_t[L][1] for L in ("roll_reversal", "rolling_pull", "g_capture"))
    uncovered = sum(all_t[L][1] for L in ("roll_other", "unload"))
    rep["R1"] = {"covered_frac": covered, "uncovered_frac": uncovered, "flag": uncovered > 0.20}
    real_map = {"M1": ("g_capture", {"nz_frac": "nz_frac", "duration_s": "duration_s", "bank_abs_deg": "bank_abs_median_deg"}),
                "M2": ("roll_reversal", {"dphi_abs_deg": "dphi_abs_deg", "peak_psp_dps": "peak_psp_dps",
                                         "dwell_s": "dwell_s", "ncmd": "ncmd_median"}),
                "M3": ("rolling_pull", {"dphi_abs_deg": "dphi_abs_deg", "nz_frac": "nz_frac", "duration_s": "duration_s"})}
    for m, (etype, fmap) in real_map.items():
        E = by(etype)
        for par, levels in SYNTH[m].items():
            vals = [e[fmap[par]] for e in E]
            p10, p90 = pct(vals, 10), pct(vals, 90)
            fin = np.asarray([v for v in vals if np.isfinite(v)])
            between = float(np.mean((fin >= min(levels)) & (fin <= max(levels)))) if len(fin) else float("nan")
            rep["R2"][f"{m}.{par}"] = {"levels": levels, "real_p10": p10, "real_p50": pct(vals, 50), "real_p90": p90,
                                        "outside": [lv for lv in levels if not (p10 <= lv <= p90)],
                                        "frac_real_between_levels": between, "n": int(len(fin))}
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1, default=float)
    print(json.dumps({"R1": rep["R1"], "n_events": {t: rep["events"][t]["count"] for t in rep["events"]}},
                     ensure_ascii=False))
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
